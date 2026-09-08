#!/usr/bin/env python3
"""Tempo through gcx: per-operation latency with exemplars, span trees, exact counts.

    grafana-traces.py ops --service svc --from ... --to ... [--fetch DIR]
    grafana-traces.py get 9ed9a7b6ce4b233f8c6cf373c079811 [ID ...] [--out DIR] [--spans]
    grafana-traces.py search '{ status = error }' --from ... --to ... [--limit 1000]
    grafana-traces.py count '{ resource.service.name = "svc" }' --from ... --to ... [--bin 30s]

Whole surface - ops: --service (repeatable), a window (--from/--to or
--since), --limit (default 1000, the search ceiling), --name (repeatable;
default: every operation the window's traces are rooted at), --settle
(default 90s, the export lag for the span metrics, as grafana-metrics.py),
--fetch DIR (also fetch each operation's p50, worst-rooted and
worst-containing exemplar and summarise them). get: trace ids in either form
gcx prints (padded or not), several at once, --out DIR to keep the raw
documents, --spans to print every span instead of the summary; no window.
search: TRACEQL, a window, --limit. count: TRACEQL, a window, --bin (default
30s) - counts in bins deduplicated on trace id, because a trace overlapping
two bins is listed in both, and says when a bin hit the ceiling. --json
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
from datetime import timedelta

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
            e["span_calls"] = round(raw[1] - (raw[0] or 0.0))
            present = True
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
    for s, r in zip(services, first):
        for t in traces_list(r.data) if r.ok else []:
            if t.get("rootServiceName") == s and t.get("rootTraceName"):
                ops[(s, t["rootTraceName"])] = None
    for s in services:
        for n in ns.name or []:
            ops[(s, n)] = None
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
        table[f"{s} {n}"] = {
            "rooted_traces": st["count"],
            "containing_traces": len(traces),
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
    return (0 if r.ok else 1), {
        "error": r.error,
        "count": len(rows),
        "truncated": len(rows) >= ns.limit,
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
            f"{'operation':44s} {'rooted':>6} {'span p50':>8} {'p95':>7} {'p99':>7} {'calls':>6} | {'trace p50':>9} {'p95':>7} {'max':>7} | worst containing"
        )
        for k, e in o["operations"].items():
            out.append(
                f"{k:44s} {_f(e['rooted_traces']):>6} {_f(e.get('span_p50_ms')):>8} {_f(e.get('span_p95_ms')):>7} {_f(e.get('span_p99_ms')):>7} {_f(e.get('span_calls')):>6} | "
                f"{_f(e['trace_p50_ms']):>9} {_f(e['trace_p95_ms']):>7} {_f(e['trace_max_ms']):>7} | {e['worst_containing_trace']} ({_f(e['worst_containing_ms'])} ms)"
                f"{'  TRUNCATED' if e['truncated'] else ''}"
            )
        out.append(
            "  span p50/p95/p99 and calls: span metrics, settled (exact span latency; calls = raw settled - raw start)"
            + (
                ""
                if o.get("span_metrics_present")
                else " - ABSENT on this store for these operations, only the trace-level reading is available"
            )
            + "; trace p50/p95/max: search over traces rooted at the operation (integer ms); exemplar ids in --json"
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
    elif "traces" in o and o.get("count") is not None:
        out.append(
            f"{o['count']} traces{'  TRUNCATED at --limit' if o['truncated'] else ''}"
        )
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
                attrs = " ".join(f"{k}={v}" for k, v in list(sp["attrs"].items())[:6])
                out.append(
                    f"      {sp['duration_ms']:>9} ms  {sp['service']:16s} {sp['name']}  [{sp['kind']}] parent={sp['parent_id'] or '-'}  {attrs}"
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
    ns = ap.parse_args()
    code, out = {
        "ops": cmd_ops,
        "get": cmd_get,
        "search": cmd_search,
        "count": cmd_count,
    }[ns.cmd](ns)
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
