#!/usr/bin/env python3
"""Tempo through gcx: per-operation latency with exemplars, span trees, exact counts.

    grafana-traces.py ops --service svc --from ... --to ... [--fetch DIR] [--top 15]
    grafana-traces.py get 9ed9a7b6ce4b233f8c6cf373c079811 [ID ...] [--out DIR] [--spans]
    grafana-traces.py search '{ status = error }' --from ... --to ... [--limit 1000]
    grafana-traces.py count '{ resource.service.name = "svc" }' --from ... --to ... [--bin 30s]
    grafana-traces.py breakdown --service svc --from ... --to ... [--sample 200]
    grafana-traces.py watch '{ span.http.user_agent =~ "odd-bench/x/.*" }' --from ... --state FILE [--to ...]

Whole surface - ops: --service (repeatable), a window (--from/--to or
--since), --limit (default 1000, the search ceiling), --name (repeatable,
adds an operation to those the window's traces are rooted at), --settle
(default 90s, the export lag for the span metrics, as grafana-metrics.py),
--top (default 15: for a service never rooted in the window - the output
says why, from the root scan - its operations are the busiest span-metric
names by the counter's settled value, capped there), --fetch DIR (also
fetch each operation's p50, worst-rooted and worst-containing exemplar and
summarise them; a never-rooted operation's p50 exemplar is its median
containing trace, flagged as such). get: trace ids in either form
gcx prints (padded or not), several at once, --out DIR to keep the raw
documents, --spans to print every span instead of the summary; no window.
search: TRACEQL, a window, --limit (the header names the start time of
the first and last trace and the root operations with their counts).
count: TRACEQL, a window, --bin (default 30s) - counts in bins deduplicated
on trace id, because a trace overlapping two bins is listed in both, and
says when a bin hit the ceiling. breakdown: --service (required: the
traces rooted at it are the table), --traceql (narrows the search; the
table still keeps the traces rooted at --service), a window, --limit
(default 1000), --sample (default 200: the newest traces fetched, at least
1) - a get that fails among many is listed under failed and costs nothing
else, the table is built from the rest; each operation names its exemplar
traces (p50, worst, the slowest per status code). watch: TRACEQL (the
run's identity), --from (poll from here: the dispatch, never the announced
start), --to (the deadline; default none - the wall clock), --bin (default
30s), --ended-after (default 4: the run has ended, once started, on that
many consecutive empty closed bins), --settle (default 60s: a bin closes
once its end is that old, so a lagging store never ends a live run),
--every (default 30s between polls), --max (default 8m: the bound one call
holds the watch for), --state FILE (the watch's state; the next call resumes
from the last closed bin), --identity-attr (repeatable; default
user_agent.original then http.user_agent: the span attribute read off the
first and the last row's trace) - exit 0 ended, 3 running at the bound, 4
not started at the bound. --json
everywhere. Every subcommand prints the gcx commands it ran, so the report
can record them. Reads GCX_CONFIG. Exit 0 on success, 1 when gcx errored -
and then nothing but the error is printed.

Two readings of latency, both printed by `ops`, because they are not the
same number: a trace search returns the *trace* duration, so an operation
nested under a slow parent inherits the parent's time - the search-derived
figures are computed only over traces rooted at the operation, and the
worst trace *containing* it is listed separately (that is where a fan-out
shows). The span-level percentiles come from the span metrics the store
derives from traces (traces_spanmetrics_latency_bucket) when it has them;
the output says when it does not. durationMs from a search is a truncated
integer: a sub-millisecond operation reads 0 - the span metrics carry its
real latency.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grafana_gcx import (
    TRACE_LIMIT,
    add_window,
    commands,
    emit,
    errors,
    flatten_trace,
    hex_trace_id,
    iso,
    parse_duration,
    parse_ts,
    percentile_index,
    percentiles,
    prom_result,
    render_commands,
    resolve_window,
    run_gcx,
    run_many,
    trace_summary,
    traces_list,
    window_seconds,
)

QUANTILES = (0.5, 0.95, 0.99)

# The attributes a reader looks for first on a span line: the outcome, the
# route, the peer - then whatever else the span carries, in its own order.
PRIORITY_ATTRS = (
    "http.response.status_code",
    "http.status_code",
    "http.request.method",
    "http.route",
    "url.path",
    "peer.service",
    "server.address",
    "db.system",
    "db.system.name",
    "db.operation.name",
    "rpc.service",
    "rpc.method",
    "messaging.system",
    "messaging.destination.name",
    "error.type",
    "exception.type",
    "gen_ai.request.model",
)


def attrs_line(attrs: dict, n: int = 8) -> str:
    keys = [k for k in PRIORITY_ATTRS if k in attrs]
    keys += [k for k in attrs if k not in PRIORITY_ATTRS]
    return " ".join(f"{k}={attrs[k]}" for k in keys[:n])


def _status(s: str) -> str:
    return s.replace("STATUS_CODE_", "")


def _ns_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _ns_iso(value) -> str | None:
    try:
        return iso(datetime.fromtimestamp(int(value) / 1e9, tz=timezone.utc))
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_traces(ids: list[str], out_dir: str | None) -> tuple[list[dict], list]:
    results = run_many([["traces", "get", i] for i in ids])
    docs = []
    for i, r in zip(ids, results):
        if not r.ok:
            docs.append({"trace_id": hex_trace_id(i), "error": r.error})
            continue
        spans = flatten_trace(r.data)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            with open(
                os.path.join(out_dir, f"trace-{hex_trace_id(i)}.json"),
                "w",
                encoding="utf-8",
            ) as fh:
                json.dump(r.data, fh)
        docs.append({"summary": trace_summary(spans), "spans": spans})
    return docs, results


def _span_quantiles(keys, frm: str, to: str, settle: str) -> tuple[dict, list, bool]:
    """Span-level p50/p95/p99 and calls from the store's span metrics, settled."""
    lag = parse_duration(settle)
    at = iso(parse_ts(to) + timedelta(seconds=lag))
    win = f"[{window_seconds(frm, to) + lag}s]"
    calls = []
    for s, n in keys:
        sel = f'{{service="{s}", span_name="{n}"}}'
        for q in QUANTILES:
            calls.append(
                [
                    "metrics",
                    "query",
                    f"histogram_quantile({q}, sum by (le) (rate(traces_spanmetrics_latency_bucket{sel}{win})))",
                    "--time",
                    at,
                ]
            )
        calls.append(
            [
                "metrics",
                "query",
                f"sum(traces_spanmetrics_calls_total{sel})",
                "--time",
                frm,
            ]
        )
        calls.append(
            [
                "metrics",
                "query",
                f"sum(last_over_time(traces_spanmetrics_calls_total{sel}{win}))",
                "--time",
                at,
            ]
        )
    results = run_many(calls)
    per = len(QUANTILES) + 2
    out = {}
    present = False
    for i, key in enumerate(keys):
        chunk = results[i * per : (i + 1) * per]
        e = {}
        for q, r in zip(QUANTILES, chunk):
            res = prom_result(r.data) if r.ok else []
            try:
                e[f"span_p{int(q * 100)}_ms"] = (
                    round(float(res[0]["value"][1]) * 1000, 2) if res else None
                )
            except (KeyError, IndexError, TypeError, ValueError):
                e[f"span_p{int(q * 100)}_ms"] = None
        raw = []
        for r in chunk[-2:]:
            res = prom_result(r.data) if r.ok else []
            try:
                raw.append(float(res[0]["value"][1]) if res else None)
            except (KeyError, IndexError, TypeError, ValueError):
                raw.append(None)
        if raw[1] is not None:
            present = True
            if raw[0] is not None and raw[1] < raw[0]:
                # the generator restarted inside the window: a
                # subtraction would print a negative call count
                e["span_calls"] = None
                e["span_calls_reset"] = True
            else:
                e["span_calls"] = round(raw[1] - (raw[0] or 0.0))
        else:
            e["span_calls"] = None
        out[key] = e
    return out, results, present


def cmd_ops(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    win = ["--from", frm, "--to", to]
    services = ns.service
    first = run_many(
        [
            [
                "traces",
                "query",
                f'{{ resource.service.name = "{s}" }}',
                *win,
                "--limit",
                str(ns.limit),
            ]
            for s in services
        ]
    )
    all_results = list(first)
    ops: dict[tuple[str, str], None] = {}
    seen: dict[str, int] = {}  # traces carrying a span of the service
    other_roots: dict[str, dict[str, int]] = {}  # who the roots belong to instead
    for s, r in zip(services, first):
        seen[s] = 0
        other_roots[s] = {}
        for t in traces_list(r.data) if r.ok else []:
            seen[s] += 1
            if t.get("rootServiceName") == s and t.get("rootTraceName"):
                ops[(s, t["rootTraceName"])] = None
            else:
                root = t.get("rootServiceName") or "?"
                if root == s:
                    root = "<no root name>"
                other_roots[s][root] = other_roots[s].get(root, 0) + 1
    # Decided on the root scan alone: a --name adds an operation, it never
    # switches the discovery off.
    unrooted = [s for s in services if not any(k[0] == s for k in ops)]
    for s in services:
        for n in ns.name or []:
            ops[(s, n)] = None
    # A service that is never a trace's root in the window (a server whose
    # every caller is instrumented: the root is the caller's client span)
    # has no root operation to rank. Its operations are then the span names
    # the store's span metrics carry for it, ranked by calls, in one query.
    never_rooted: dict[str, dict] = {}
    if unrooted:
        lag = parse_duration(ns.settle)
        at = iso(parse_ts(to) + timedelta(seconds=lag))
        swin = f"[{window_seconds(frm, to) + lag}s]"
        named = run_many(
            [
                [
                    "metrics",
                    "query",
                    f'sum by (span_name) (last_over_time(traces_spanmetrics_calls_total{{service="{s}"}}{swin}))',
                    "--time",
                    at,
                ]
                for s in unrooted
            ]
        )
        all_results += named
        for s, r in zip(unrooted, named):
            calls_by_name: dict[str, float] = {}
            for x in prom_result(r.data) if r.ok else []:
                n = x.get("metric", {}).get("span_name", "")
                try:
                    v = float(x["value"][1])
                except (KeyError, IndexError, TypeError, ValueError):
                    v = 0.0
                if n:
                    calls_by_name[n] = calls_by_name.get(n, 0.0) + v
            ranked = sorted(calls_by_name, key=lambda n: -calls_by_name[n])
            names = ranked[: ns.top]
            for n in names:
                ops[(s, n)] = None
            if seen[s] == 0:
                why = "no trace carries a span of it in this window - check the service name and the window before reading anything below"
            else:
                roots = ", ".join(
                    f"{k} ({v})"
                    for k, v in sorted(other_roots[s].items(), key=lambda kv: -kv[1])[
                        :3
                    ]
                )
                why = f"its {seen[s]} traces are rooted at {roots}" + (
                    f" - {len(names)} operations taken from its span metrics"
                    + (
                        f" (the top {len(names)} of {len(ranked)} by the counter's settled value; --top raises it)"
                        if len(ranked) > len(names)
                        else ""
                    )
                    if names
                    else " - and no span metrics carry it: pass --name <operation>"
                )
            never_rooted[s] = {
                "traces_seen": seen[s],
                "roots": other_roots[s],
                "operations_from_span_metrics": names,
                "span_metrics_names": len(ranked),
                "why": why,
            }
    keys = list(ops)
    results = run_many(
        [
            [
                "traces",
                "query",
                f'{{ resource.service.name = "{s}" && name = "{n}" }}',
                *win,
                "--limit",
                str(ns.limit),
            ]
            for s, n in keys
        ]
    )
    all_results += results
    spanq, span_results, span_present = _span_quantiles(keys, frm, to, ns.settle)
    all_results += span_results
    table = {}
    for (s, n), r in zip(keys, results):
        if not r.ok:
            continue
        traces = traces_list(r.data)
        rooted = [
            t
            for t in traces
            if t.get("rootServiceName") == s and t.get("rootTraceName") == n
        ]
        by_dur = sorted(rooted, key=lambda t: t.get("durationMs", 0))
        durs = [t.get("durationMs", 0) for t in by_dur]
        st = percentiles(durs)
        containing = (
            max(traces, key=lambda t: t.get("durationMs", 0)) if traces else None
        )
        p50_t = by_dur[percentile_index(len(by_dur), 0.5)] if by_dur else None
        # never rooted: the median containing trace stands in as the p50
        # exemplar, and is marked as such
        cont_by_dur = sorted(traces, key=lambda t: t.get("durationMs", 0))
        p50_is_containing = False
        if p50_t is None and cont_by_dur:
            p50_t = cont_by_dur[percentile_index(len(cont_by_dur), 0.5)]
            p50_is_containing = True
        table[f"{s} {n}"] = {
            "rooted_traces": st["count"],
            "containing_traces": len(traces),
            "p50_exemplar_is_containing": p50_is_containing,
            "truncated": len(traces) >= ns.limit,
            "trace_p50_ms": st["p50"],
            "trace_p95_ms": st["p95"],
            "trace_p99_ms": st["p99"],
            "trace_max_ms": st["max"],
            **spanq.get((s, n), {}),
            "p50_trace": hex_trace_id(p50_t["traceID"]) if p50_t else None,
            "worst_rooted_trace": hex_trace_id(by_dur[-1]["traceID"])
            if by_dur
            else None,
            "worst_containing_trace": hex_trace_id(containing["traceID"])
            if containing
            else None,
            "worst_containing_ms": containing.get("durationMs") if containing else None,
        }
    out = {
        "window": [frm, to],
        "span_metrics_present": span_present,
        "never_rooted": never_rooted,
        "operations": dict(
            sorted(table.items(), key=lambda kv: -(kv[1]["containing_traces"] or 0))
        ),
    }
    if ns.fetch:
        ids = sorted(
            {
                e[k]
                for e in table.values()
                for k in ("p50_trace", "worst_rooted_trace", "worst_containing_trace")
                if e.get(k)
            }
        )
        docs, get_results = fetch_traces(ids, ns.fetch)
        all_results += get_results
        out["exemplars"] = {
            (d.get("summary", {}).get("trace_id") or d.get("trace_id")): (
                d.get("summary") or {"error": d.get("error")}
            )
            for d in docs
        }
    out["error"] = errors(all_results)
    out["commands"] = commands(all_results)
    return (1 if out["error"] else 0), out


def cmd_get(ns) -> tuple[int, dict]:
    docs, results = fetch_traces(ns.ids, ns.out)
    err = errors(results)
    return (1 if err else 0), {
        "error": err,
        "traces": [
            d if ns.spans else {"summary": d.get("summary"), "error": d.get("error")}
            for d in docs
        ],
        "commands": commands(results),
    }


def cmd_search(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    r = run_gcx(
        [
            "traces",
            "query",
            ns.traceql,
            "--from",
            frm,
            "--to",
            to,
            "--limit",
            str(ns.limit),
        ]
    )
    rows = (
        [
            {**t, "traceID": hex_trace_id(t.get("traceID", ""))}
            for t in traces_list(r.data)
        ]
        if r.ok
        else []
    )
    starts = sorted(
        int(t["startTimeUnixNano"])
        for t in rows
        if str(t.get("startTimeUnixNano", "")).isdigit()
    )
    roots: dict[str, int] = {}
    for t in rows:
        k = f"{t.get('rootServiceName', '')} {t.get('rootTraceName', '')}"
        roots[k] = roots.get(k, 0) + 1
    return (0 if r.ok else 1), {
        "error": r.error,
        "count": len(rows),
        "truncated": len(rows) >= ns.limit,
        "first": _ns_iso(starts[0]) if starts else None,
        "last": _ns_iso(starts[-1]) if starts else None,
        "roots": dict(sorted(roots.items(), key=lambda kv: -kv[1])),
        "traces": rows,
        "commands": [r.command],
    }


def cmd_count(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    a, b = parse_ts(frm), parse_ts(to)
    step = timedelta(seconds=parse_duration(ns.bin))
    bins = []
    t = a
    while t < b:
        bins.append((t, min(t + step, b)))
        t += step
    results = run_many(
        [
            [
                "traces",
                "query",
                ns.traceql,
                "--from",
                iso(x),
                "--to",
                iso(y),
                "--limit",
                str(TRACE_LIMIT),
            ]
            for x, y in bins
        ]
    )
    seen: set[str] = set()
    rows = []
    for (x, y), r in zip(bins, results):
        if not r.ok:
            rows.append({"from": iso(x), "to": iso(y), "error": r.error})
            continue
        ids = [hex_trace_id(t.get("traceID", "")) for t in traces_list(r.data)]
        new = [i for i in ids if i not in seen]
        seen.update(new)
        rows.append(
            {
                "from": iso(x),
                "to": iso(y),
                "listed": len(ids),
                "new": len(new),
                "capped": len(ids) >= TRACE_LIMIT,
            }
        )
    err = errors(results)
    return (1 if err else 0), {
        "traceql": ns.traceql,
        "bin": ns.bin,
        "total": len(seen),
        "capped_bins": sum(1 for r in rows if r.get("capped")),
        "bins": rows,
        "error": err,
        "note": "total is deduplicated on trace id; a capped bin under-counts - narrow --bin or split the selector",
        "commands": commands(results),
    }


IDENTITY_ATTRS = ("user_agent.original", "http.user_agent")


def _identity(
    trace_id: str, attrs: tuple[str, ...]
) -> tuple[list[str], str | None, list]:
    """The identity values one trace carries on the first of ``attrs`` any
    of its spans has - the User-Agent a driven run is selected by."""
    r = run_gcx(["traces", "get", trace_id])
    if not r.ok:
        return [], None, [r]
    spans = flatten_trace(r.data)
    for attr in attrs:
        values = sorted({str(sp["attrs"][attr]) for sp in spans if attr in sp["attrs"]})
        if values:
            return values, attr, [r]
    return [], None, [r]


def _load_watch_state(path: str | None, traceql: str, frm: str, bin_: str) -> dict:
    fresh = {
        "traceql": traceql,
        "from": frm,
        "bin": bin_,
        "cursor": frm,
        "bins": [],
        "last_bin_ids": [],
        "started": None,
        "started_id": None,
        "last_row": None,
        "last_id": None,
        "empty_since": 0,
        "identity": [],
        "identity_attr": None,
        "polls": 0,
        "status": "not started",
        "commands": [],
    }
    if not path or not os.path.isfile(path):
        return fresh
    try:
        with open(path, encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        return fresh
    if saved.get("traceql") != traceql or saved.get("from") != frm:
        raise SystemExit(
            f"{path} holds another watch ({saved.get('traceql')!r} from "
            f"{saved.get('from')}): name a state file of this watch's own"
        )
    fresh.update(saved)
    return fresh


def _save_watch_state(path: str | None, state: dict) -> None:
    if not path:
        return
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)
    os.replace(tmp, path)


def cmd_watch(ns) -> tuple[int, dict]:
    """Poll a driven run's identity, bin by bin, until it has started and
    then ended - the end criterion the watch section of the scenario skill
    states, shipped: once started, ``--ended-after`` consecutive empty
    closed bins; before the first row an empty bin means not started."""
    import time

    if not ns.frm:
        raise SystemExit("watch needs --from <the instant polling starts, RFC3339 UTC>")
    frm = parse_ts(ns.frm)
    deadline = parse_ts(ns.to) if ns.to else None
    if deadline and deadline <= frm:
        raise SystemExit("--to must be after --from")
    step = timedelta(seconds=parse_duration(ns.bin))
    settle = timedelta(seconds=parse_duration(ns.settle))
    every = parse_duration(ns.every)
    bound = parse_duration(ns.max)
    attrs = tuple(ns.identity_attr) if ns.identity_attr else IDENTITY_ATTRS
    state = _load_watch_state(ns.state, ns.traceql, iso(frm), ns.bin)
    results: list = []
    recorded = 0  # how many of ``results`` already sit in the state's commands
    began = time.monotonic()
    polls_this_call = 0
    while True:
        state["polls"] += 1
        polls_this_call += 1
        now = datetime.now(timezone.utc).replace(microsecond=0)
        if deadline and deadline < now:
            now = deadline
        closed = now - settle
        cursor = parse_ts(state["cursor"])
        while cursor + step <= closed and state["status"] != "ended":
            x, y = cursor, cursor + step
            r = run_gcx(
                [
                    "traces",
                    "query",
                    ns.traceql,
                    "--from",
                    iso(x),
                    "--to",
                    iso(y),
                    "--limit",
                    str(TRACE_LIMIT),
                ]
            )
            results.append(r)
            if not r.ok:
                state["bins"].append({"from": iso(x), "to": iso(y), "error": r.error})
                state["commands"].extend(commands(results[recorded:]))
                _save_watch_state(ns.state, state)
                return 1, {
                    **_watch_out(state, ns, now, polls_this_call),
                    "error": r.error,
                }
            rows = traces_list(r.data)
            ids = [hex_trace_id(t.get("traceID", "")) for t in rows]
            previous = set(state["last_bin_ids"])
            new = [i for i in ids if i not in previous]
            starts = sorted(
                (int(t["startTimeUnixNano"]), hex_trace_id(t.get("traceID", "")))
                for t in rows
                if str(t.get("startTimeUnixNano", "")).isdigit()
            )
            entry = {
                "from": iso(x),
                "to": iso(y),
                "listed": len(ids),
                "new": len(new),
                "capped": len(ids) >= TRACE_LIMIT,
            }
            state["bins"].append(entry)
            state["last_bin_ids"] = ids[-200:]
            state["cursor"] = iso(y)
            cursor = y
            if new and starts:
                first_ns, first_id = starts[0]
                last_ns, last_id = starts[-1]
                if state["started"] is None:
                    state["started"] = _ns_iso(first_ns)
                    state["started_id"] = first_id
                    values, attr, got = _identity(first_id, attrs)
                    results.extend(got)
                    state["identity"] = values
                    state["identity_attr"] = attr
                    state["status"] = "running"
                if state["last_row"] is None or _ns_iso(last_ns) >= state["last_row"]:
                    state["last_row"] = _ns_iso(last_ns)
                    state["last_id"] = last_id
                state["empty_since"] = 0
            elif state["started"] is not None:
                state["empty_since"] += 1
                if state["empty_since"] >= ns.ended_after:
                    state["status"] = "ended"
                    state["ended"] = state["last_row"]
                    if state["last_id"] and state["last_id"] != state["started_id"]:
                        values, attr, got = _identity(state["last_id"], attrs)
                        results.extend(got)
                        if attr and attr == state["identity_attr"]:
                            state["identity"] = sorted(
                                set(state["identity"]) | set(values)
                            )
                        elif values and not state["identity"]:
                            state["identity"], state["identity_attr"] = values, attr
        state["commands"].extend(commands(results[recorded:]))
        recorded = len(results)
        _save_watch_state(ns.state, state)
        if state["status"] == "ended":
            return 0, _watch_out(state, ns, now, polls_this_call)
        at_deadline = deadline is not None and now >= deadline
        if at_deadline or time.monotonic() - began >= bound:
            return (3 if state["started"] else 4), _watch_out(
                state, ns, now, polls_this_call
            )
        time.sleep(every)


def _watch_out(state: dict, ns, now, polls_this_call: int) -> dict:
    started, ended = state.get("started"), state.get("ended")
    span = None
    if started and ended:
        span = int((parse_ts(ended) - parse_ts(started)).total_seconds())
    return {
        "traceql": ns.traceql,
        "from": state["from"],
        "to": ns.to,
        "bin": ns.bin,
        "every": ns.every,
        "ended_after": ns.ended_after,
        "settle": ns.settle,
        "status": state["status"],
        "started": started,
        "ended": ended,
        "last_row": state.get("last_row"),
        "span_s": span,
        "identity": state.get("identity") or [],
        "identity_attr": state.get("identity_attr"),
        "several_identities": len(state.get("identity") or []) > 1,
        "empty_since_last_row": state.get("empty_since", 0),
        "bins": state["bins"],
        "polls": state["polls"],
        "polls_this_call": polls_this_call,
        "last_poll": iso(now),
        "state": ns.state,
        "commands": list(state["commands"]),
    }


def cmd_breakdown(ns) -> tuple[int, dict]:
    """Per root operation over the window's traces: outcome, root latency,
    each child span's count per trace, latency and attribute keys."""
    frm, to = resolve_window(ns)
    traceql = ns.traceql or f'{{ resource.service.name = "{ns.service}" }}'
    r = run_gcx(
        [
            "traces",
            "query",
            traceql,
            "--from",
            frm,
            "--to",
            to,
            "--limit",
            str(ns.limit),
        ]
    )
    if not r.ok:
        return 1, {"error": r.error, "commands": [r.command]}
    listed = traces_list(r.data)
    rows = [t for t in listed if t.get("rootServiceName") == ns.service]
    rows.sort(key=lambda t: -_ns_int(t.get("startTimeUnixNano")))
    ids = [hex_trace_id(t.get("traceID", "")) for t in rows][: ns.sample]
    docs, results = fetch_traces(ids, None)
    failed = [
        {"trace_id": d.get("trace_id"), "error": d.get("error")}
        for d in docs
        if d.get("error")
    ]
    rooted_by: dict[str, int] = {}
    if not rows:
        for t in listed:
            k = t.get("rootServiceName") or "?"
            rooted_by[k] = rooted_by.get(k, 0) + 1
    ops: dict[str, dict] = {}
    for d in docs:
        spans = d.get("spans") or []
        if not spans:
            continue
        roots = [x for x in spans if not x["parent_id"]]
        root = roots[0] if roots else spans[0]
        e = ops.setdefault(
            f"{root['service']} {root['name']}",
            {
                "traces": 0,
                "root_status": {},
                "http_status": {},
                "root_ms": [],
                "root_attrs": set(),
                "children": {},
                "by_dur": [],
                "by_code": {},
            },
        )
        e["traces"] += 1
        tid = root.get("trace_id") or (d.get("summary") or {}).get("trace_id") or ""
        e["by_dur"].append((root["duration_ms"], tid))
        st = _status(root["status"])
        e["root_status"][st] = e["root_status"].get(st, 0) + 1
        code = root["attrs"].get("http.response.status_code")
        if code is None:
            code = root["attrs"].get("http.status_code")
        code = "absent" if code is None else str(code)
        e["http_status"][code] = e["http_status"].get(code, 0) + 1
        if tid and (
            code not in e["by_code"] or root["duration_ms"] > e["by_code"][code][0]
        ):
            e["by_code"][code] = (root["duration_ms"], tid)
        e["root_ms"].append(root["duration_ms"])
        e["root_attrs"].update(root["attrs"])
        per: dict[str, int] = {}
        for x in spans:
            if x is root:
                continue
            k = f"{x['service']} {x['name']} [{x['kind']}]"
            c = e["children"].setdefault(
                k, {"count": 0, "in_traces": 0, "errors": 0, "ms": [], "attrs": set()}
            )
            c["count"] += 1
            c["errors"] += x["status"] == "STATUS_CODE_ERROR"
            c["ms"].append(x["duration_ms"])
            c["attrs"].update(x["attrs"])
            per[k] = per.get(k, 0) + 1
        for k in per:
            e["children"][k]["in_traces"] += 1
    table = {}
    for key, e in sorted(ops.items(), key=lambda kv: -kv[1]["traces"]):
        q = percentiles(e["root_ms"])
        children = {}
        for k, c in sorted(e["children"].items(), key=lambda kv: -kv[1]["count"]):
            cq = percentiles(c["ms"])
            children[k] = {
                "count": c["count"],
                "in_traces": c["in_traces"],
                "per_trace": round(c["count"] / e["traces"], 2),
                "errors": c["errors"],
                "p50_ms": cq["p50"],
                "p95_ms": cq["p95"],
                "max_ms": cq["max"],
                "attrs": sorted(c["attrs"]),
            }
        by_dur = sorted(x for x in e["by_dur"] if x[1])
        exemplars = {}
        if by_dur:
            exemplars["p50"] = by_dur[percentile_index(len(by_dur), 0.5)][1]
            exemplars["worst"] = by_dur[-1][1]
        for code, (_, tid) in sorted(e["by_code"].items()):
            exemplars[code] = tid
        table[key] = {
            "traces": e["traces"],
            "root_status": e["root_status"],
            "http_status": e["http_status"],
            "root_p50_ms": q["p50"],
            "root_p95_ms": q["p95"],
            "root_max_ms": q["max"],
            "root_attrs": sorted(e["root_attrs"]),
            "exemplars": exemplars,
            "children": children,
        }
    # one failing get among many is listed, never the whole answer lost
    err = "" if docs and len(failed) < len(docs) else errors(results)
    return (1 if err else 0), {
        "window": [frm, to],
        "traceql": traceql,
        "service": ns.service,
        "listed": len(listed),
        "rooted": len(rows),
        "rooted_elsewhere": rooted_by,
        "truncated": len(listed) >= ns.limit,
        "fetched": len(docs) - len(failed),
        "failed": failed,
        "breakdown": table,
        "error": err,
        "note": "http_status is the root span's http.response.status_code, or http.status_code on an old-semconv service (absent = the root carries neither); exemplars name, over the fetched sample, the p50 and the slowest root trace and the slowest trace per status code - fetch one with get, never search for one; a child's per_trace is its count over the operation's traces",
        "commands": commands([r] + results),
    }


def _positive(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def _f(v) -> str:
    return (
        "-"
        if v is None
        else (f"{v:.0f}" if isinstance(v, float) and v >= 10 else str(v))
    )


def render(o: dict) -> str:
    if o.get("error"):
        return "ERROR " + o["error"]
    out = []
    if "operations" in o:
        out.append(
            f"{'operation':44s} {'rooted':>6} {'contain':>7} {'span p50':>8} {'p95':>7} {'p99':>7} {'calls':>6} | {'trace p50':>9} {'p95':>7} {'max':>7} | worst containing"
        )
        for k, e in o["operations"].items():
            out.append(
                f"{k:44s} {_f(e['rooted_traces']):>6} {_f(e['containing_traces']):>7} {_f(e.get('span_p50_ms')):>8} {_f(e.get('span_p95_ms')):>7} {_f(e.get('span_p99_ms')):>7} {_f(e.get('span_calls')):>6} | "
                f"{_f(e['trace_p50_ms']):>9} {_f(e['trace_p95_ms']):>7} {_f(e['trace_max_ms']):>7} | {e['worst_containing_trace']} ({_f(e['worst_containing_ms'])} ms)"
                f"{'  TRUNCATED' if e['truncated'] else ''}"
                f"{'  RESET inside the window (calls withheld)' if e.get('span_calls_reset') else ''}"
            )
        for s, nr in (o.get("never_rooted") or {}).items():
            out.append(
                f"  {s}: never a trace's root in this window - {nr['why']}"
                + (
                    "; its rooted columns are empty - the containing count, the worst containing trace and the median containing trace (the p50 exemplar) are its trace-level reading"
                    if nr.get("operations_from_span_metrics")
                    else ""
                )
            )
        out.append(
            "  span p50/p95/p99 and calls: span metrics, settled (bucket-interpolated latency; calls = raw settled - raw start, withheld on a reset)"
            + (
                ""
                if o.get("span_metrics_present")
                else " - ABSENT on this store for these operations, only the trace-level reading is available"
            )
            + "; rooted/contain: traces rooted at / containing the operation; trace p50/p95/max: over the rooted ones (integer ms); exemplar ids in --json"
        )
        for tid, s in (o.get("exemplars") or {}).items():
            tok = (
                f", gen_ai tokens in/out {s['gen_ai_tokens']['input']}/{s['gen_ai_tokens']['output']}"
                if s.get("gen_ai_tokens")
                else ""
            )
            out.append(
                f"\n-- {tid}: {s.get('root')}  {s.get('duration_ms')} ms, {s.get('spans')} spans, errors={s.get('errors')}{tok}"
            )
            for name, e in list((s.get("by_name") or {}).items())[:12]:
                out.append(f"     {e['count']:4d}  {name}  (max {e['max_ms']} ms)")
    elif "breakdown" in o:
        out.append(
            f"{o['rooted']} traces rooted at {o['service']} of {o['listed']} listed, {o['fetched']} fetched"
            + (
                f", {len(o['failed'])} get{'s' if len(o['failed']) > 1 else ''} FAILED"
                if o["failed"]
                else ""
            )
            + ("  TRUNCATED at --limit" if o["truncated"] else "")
        )
        for f in o["failed"][:10]:
            out.append(f"   failed: {f['trace_id']}  {f['error']}")
        if o["listed"] and not o["rooted"]:
            out.append(
                "   none rooted at the service - their roots: "
                + ", ".join(f"{k} ({n})" for k, n in o["rooted_elsewhere"].items())
                + "; grafana-traces.py ops names a never-rooted service's operations from its span metrics"
            )
        for k, e in o["breakdown"].items():
            out.append(
                f"== {k}  n={e['traces']}  root p50 {_f(e['root_p50_ms'])} p95 {_f(e['root_p95_ms'])} max {_f(e['root_max_ms'])} ms"
                f"  status {' '.join(f'{a}={b}' for a, b in e['root_status'].items())}"
                f"  http {' '.join(f'{a}={b}' for a, b in e['http_status'].items())}"
            )
            out.append(f"   root attrs: {', '.join(e['root_attrs']) or '(none)'}")
            if e.get("exemplars"):
                out.append(
                    "   exemplars: "
                    + "  ".join(f"{k} {v}" for k, v in e["exemplars"].items())
                )
            for ck, c in e["children"].items():
                out.append(
                    f"   {c['per_trace']:>5}/trace  {ck}  p50 {_f(c['p50_ms'])} p95 {_f(c['p95_ms'])} max {_f(c['max_ms'])} ms"
                    + (f"  errors={c['errors']}" if c["errors"] else "")
                    + f"  attrs: {', '.join(c['attrs']) or '(none)'}"
                )
        if not o["rooted"] and not o["listed"]:
            out.append("  (no trace matched in this window)")
        elif not o["breakdown"] and o["rooted"]:
            out.append("  (nothing fetched - see failed, or --sample)")
        if o["breakdown"]:
            out.append("  " + o["note"])
        cmds = o.get("commands") or []
        n = len(cmds)
        out.append(f"queries run (record these; {n} call{'s' if n != 1 else ''}):")
        out.append("  " + cmds[0] if cmds else "  (none)")
        if n > 1:
            out.append(
                f"  gcx traces get <id> -o json  x{n - 1} - the newest --sample of the traces rooted at {o['service']}, one per trace; the ids are verbatim in --json"
            )
        return "\n".join(out)
    elif "traces" in o and o.get("count") is not None:
        out.append(
            f"{o['count']} traces{'  TRUNCATED at --limit' if o['truncated'] else ''}"
            + (f", first {o['first']} last {o['last']}" if o.get("first") else "")
        )
        for k, n in list((o.get("roots") or {}).items())[:20]:
            out.append(f"  {n:6d}  {k}")
        for t in o["traces"][:50]:
            out.append(
                f"  {t['traceID']}  {t.get('rootServiceName')} {t.get('rootTraceName')}  {t.get('durationMs')} ms"
            )
    elif "traces" in o:
        for d in o["traces"]:
            s = d.get("summary")
            if not s:
                out.append(f"ERROR {d.get('error')}")
                continue
            tok = (
                f", gen_ai tokens in/out {s['gen_ai_tokens']['input']}/{s['gen_ai_tokens']['output']}"
                if s.get("gen_ai_tokens")
                else ""
            )
            out.append(
                f"== {s['trace_id']}  {s['root']}  {s['duration_ms']} ms, {s['spans']} spans over {', '.join(s['services'])}, errors={s['errors']}{tok}"
            )
            for name, e in list(s["by_name"].items())[:15]:
                out.append(f"   {e['count']:4d}  {name}  (max {e['max_ms']} ms)")
            for sp in d.get("spans") or []:
                st = _status(sp["status"])
                out.append(
                    f"      {sp['duration_ms']:>9} ms  {sp['service']:16s} {sp['name']}  [{sp['kind']}]"
                    + (f" status={st}" if st != "UNSET" else "")
                    + f" parent={sp['parent_id'] or '-'}  {attrs_line(sp['attrs'])}"
                )
    elif "status" in o and "bins" in o:
        out.append(f"watch: {o['status']} — {o['traceql']} from {o['from']}")
        if o.get("error"):
            out.append(f"ERROR {o['error']}")
        if o["started"]:
            out.append(
                f"Started (UTC): {o['started']}   # the run's first request row on the identity"
            )
        if o["ended"]:
            out.append(
                f"Ended   (UTC): {o['ended']}   # last request row; {o['ended_after']} empty {o['bin']} bins after it"
            )
        elif o["started"]:
            out.append(
                f"last row {o['last_row']}, {o['empty_since_last_row']} empty {o['bin']} bin(s) since (ends at {o['ended_after']})"
            )
        if o["identity"]:
            out.append(
                f"Identity:  {o['identity_attr']} {', '.join(o['identity'])}"
                + (
                    " (SEVERAL identities on the rows - several runs, not one)"
                    if o["several_identities"]
                    else " (one identity on the rows)"
                )
            )
        if o["span_s"] is not None:
            out.append(f"Span:      {o['span_s']} s")
        out.append(
            f"Watch:     polled from {o['from']}, {o['polls']} poll(s) ({o['polls_this_call']} this call), last poll {o['last_poll']}"
            + (f"; deadline {o['to']}" if o.get("to") else "")
            + (
                f"; state {o['state']}"
                if o.get("state")
                else "; no --state: this call holds the whole watch"
            )
        )
        with_rows = [b for b in o["bins"] if b.get("new")]
        out.append(
            f"bins: {len(o['bins'])} closed, {len(with_rows)} with rows"
            + (
                f" ({with_rows[0]['from'][11:19]} .. {with_rows[-1]['to'][11:19]})"
                if with_rows
                else ""
            )
        )
        for r in o["bins"][-12:]:
            out.append(
                f"  {r['from'][11:19]} .. {r['to'][11:19]}  new={r.get('new')}{'  CAPPED' if r.get('capped') else ''}{'  ' + r['error'] if r.get('error') else ''}"
            )
        if o["status"] != "ended":
            out.append(
                "  still "
                + ("running" if o["started"] else "not started")
                + ": run the same invocation again (the state file resumes it)"
            )
    elif "bins" in o:
        out.append(
            f"{o['total']} traces (deduplicated) in {len(o['bins'])} bins of {o['bin']}; capped bins: {o['capped_bins']}"
        )
        for r in o["bins"]:
            out.append(
                f"  {r['from']} .. {r['to']}  listed={r.get('listed')} new={r.get('new')}{'  CAPPED' if r.get('capped') else ''}{'  ' + r['error'] if r.get('error') else ''}"
            )
        out.append("  " + o["note"])
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ops")
    a.add_argument("--service", action="append", required=True)
    a.add_argument("--name", action="append")
    a.add_argument("--limit", type=int, default=TRACE_LIMIT)
    a.add_argument("--settle", default="90s")
    a.add_argument("--fetch")
    a.add_argument(
        "--top",
        type=int,
        default=15,
        help="operations kept from the span metrics for a never-rooted service, by calls (default 15)",
    )
    add_window(a)
    b = sub.add_parser("get")
    b.add_argument("ids", nargs="+")
    b.add_argument("--out")
    b.add_argument("--spans", action="store_true")
    b.add_argument("--json", action="store_true")
    c = sub.add_parser("search")
    c.add_argument("traceql")
    c.add_argument("--limit", type=int, default=TRACE_LIMIT)
    add_window(c)
    d = sub.add_parser("count")
    d.add_argument("traceql")
    d.add_argument("--bin", default="30s")
    add_window(d)
    e = sub.add_parser("breakdown")
    e.add_argument("--service", required=True)
    e.add_argument(
        "--traceql",
        help="the search to break down (default: every trace carrying a span of --service)",
    )
    e.add_argument("--limit", type=int, default=TRACE_LIMIT)
    e.add_argument(
        "--sample",
        type=_positive,
        default=200,
        help="traces fetched, newest first (default 200)",
    )
    add_window(e)
    w = sub.add_parser("watch")
    w.add_argument("traceql")
    w.add_argument("--from", dest="frm", help="poll from this instant, RFC3339 UTC")
    w.add_argument("--to", help="the deadline, RFC3339 UTC (default: none)")
    w.add_argument("--bin", default="30s")
    w.add_argument("--ended-after", type=int, default=4)
    w.add_argument("--settle", default="60s")
    w.add_argument("--every", default="30s")
    w.add_argument("--max", default="8m")
    w.add_argument("--state", help="the watch's state file; a later call resumes it")
    w.add_argument("--identity-attr", action="append")
    w.add_argument("--json", action="store_true")
    ns = ap.parse_args()
    code, out = {
        "ops": cmd_ops,
        "get": cmd_get,
        "search": cmd_search,
        "count": cmd_count,
        "breakdown": cmd_breakdown,
        "watch": cmd_watch,
    }[ns.cmd](ns)
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
