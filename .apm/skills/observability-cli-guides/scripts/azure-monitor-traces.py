#!/usr/bin/env python3
"""Distributed tracing off the component's requests and dependencies tables.

    azure-monitor-traces.py operations --app <app_insights_app> --service orders-api --from ... --to ...
    azure-monitor-traces.py dependencies --app <app_insights_app> --service orders-api --since 30m
    azure-monitor-traces.py exemplars --app <app_insights_app> --service orders-api --slow 3 --failed 3 --since 30m
    azure-monitor-traces.py trace <operation_Id> --app <app_insights_app> [--since 24h]
    azure-monitor-traces.py watch --app <app_insights_app> --identity odd-bench/<name> --from <dispatch instant> --state <scratch>/<slug>-watch.json [--to <deadline>]

Whole surface - every subcommand takes --app (the appId GUID), a window
(--from/--to or --since; `trace` defaults to the last 24h; `watch` takes
--from and an optional --to, the deadline), --json. operations,
dependencies, exemplars and watch take --service (repeatable, a
cloud_RoleName; none = every service). operations adds --top (rows, default
20) and --bin (a duration: adds the request count, failures and p95 per
time bucket). exemplars adds --operation (the request name, repeatable),
--slow N (the slowest requests, default 3), --failed N (the newest failed
requests, default 3). trace takes the operation_Id. watch takes --identity
(the run's User-Agent prefix, matched with startswith), --state (its state
file; the same invocation again resumes it), --bin (default 30s),
--ended-after (empty closed bins that end a started run with no schedule
to read, default 4), --settle (a bin closes once its end is this old;
default auto: the largest ingestion lag observed - one probe of the
component's rows over the 10 minutes before the dispatch, then the run's
own rows bin by bin - plus one bin, recomputed at every poll), --length
(the manifest's scheduled length: once it has elapsed since the first
row, one empty closed bin ends the run), --expect (the manifest's
scheduled request count: reached, the run ended at its last row, no empty
bin needed), --every (the floor between two polls, default 5s - the watch
wakes when the next bin can close, never on a fixed clock), --max (one
call's bound, default 8m; 0s is one whole poll), --dimension (the
customDimensions key the identity is read from, repeatable, the first
non-empty one wins; default user_agent.original then http.user_agent).
Exit 0 (watch: ended),
1 when a query failed (the failure is in the output; a watch leaves that
bin unread for the next call), watch 3 still running at --max or --to, 4
not started there.

Spans live in requests (incoming) and dependencies (outgoing), never in
traces; a trace is every row sharing an operation_Id, a span's parent is
operation_ParentId, and a log line or an exception hangs off the span it
names there. The per-operation percentiles are one summarize `by name` -
there is no percentileif, and none is needed. A dependency's
operation_Name is empty on an OTel export: the operation it belongs to is
read off the request sharing its operation_Id (a join, done here).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from azure_monitor_az import (
    add_window,
    ai_call,
    ai_rows,
    commands,
    emit,
    exit_code,
    failures,
    iso,
    kql_bin,
    kql_in,
    kql_str,
    parse_duration,
    parse_ts,
    render_commands,
    render_failures,
    resolve_window,
    run_az,
    run_many,
    table,
    usage,
)

PCT = "p50=percentile(duration, 50), p95=percentile(duration, 95), p99=percentile(duration, 99), max=max(duration)"
SEVERITY = {0: "verbose", 1: "info", 2: "warn", 3: "error", 4: "critical"}


def cmd_operations(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    svc = kql_in("cloud_RoleName", ns.service or [])
    calls = [
        ai_call(
            ns.app,
            f"requests {svc}| summarize n=count(), failed=countif(success == false), {PCT} by cloud_RoleName, name | order by n desc",
            frm,
            to,
        ),
        ai_call(
            ns.app,
            f"requests {svc}| where success == false | summarize n=count() by cloud_RoleName, name, resultCode | order by n desc",
            frm,
            to,
        ),
    ]
    if ns.bin:
        calls.append(
            ai_call(
                ns.app,
                f"requests {svc}| summarize n=count(), failed=countif(success == false), p95=percentile(duration, 95) by bin(timestamp, {kql_bin(ns.bin)}) | order by timestamp asc",
                frm,
                to,
            )
        )
    res = run_many(calls)
    ops = ai_rows(res[0].data) if res[0].ok else []
    codes = ai_rows(res[1].data) if res[1].ok else []
    for o in ops:
        o["failed_codes"] = {
            c["resultCode"]: c["n"]
            for c in codes
            if c["cloud_RoleName"] == o["cloud_RoleName"] and c["name"] == o["name"]
        }
    out = {
        "window": [frm, to],
        "operations": ops[: ns.top],
        "total_operations": len(ops),
        "bins": ai_rows(res[2].data) if ns.bin and res[2].ok else None,
        "failed": failures(res),
        "commands": commands(res),
    }
    return exit_code(out), out


def render_operations(o: dict) -> str:
    out = [
        f"requests per operation, {o['window'][0]}..{o['window'][1]} (duration in ms)"
    ]
    rows = [
        {
            **r,
            "codes": " ".join(f"{k}={v}" for k, v in r["failed_codes"].items()) or "-",
        }
        for r in o["operations"]
    ]
    out += table(
        rows,
        ["cloud_RoleName", "name", "n", "failed", "codes", "p50", "p95", "p99", "max"],
    )
    if o["total_operations"] > len(o["operations"]):
        out.append(
            f"  +{o['total_operations'] - len(o['operations'])} more operations (--top)"
        )
    if o["bins"] is not None:
        out.append("per bucket:")
        out += table(o["bins"], ["timestamp", "n", "failed", "p95"])
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_dependencies(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    svc = kql_in("cloud_RoleName", ns.service or [])
    calls = [
        ai_call(
            ns.app,
            f"dependencies {svc}| join kind=inner (requests | project operation_Id, operation=name) on operation_Id | summarize n=count(), failed=countif(success == false), {PCT} by cloud_RoleName, operation, type, name | order by cloud_RoleName asc, operation asc, n desc",
            frm,
            to,
        ),
        ai_call(
            ns.app,
            f"dependencies {svc}| summarize n=count(), failed=countif(success == false), {PCT} by cloud_RoleName, type, target, name | order by n desc",
            frm,
            to,
        ),
    ]
    res = run_many(calls)
    out = {
        "window": [frm, to],
        "per_operation": ai_rows(res[0].data) if res[0].ok else [],
        "all": ai_rows(res[1].data) if res[1].ok else [],
        "failed": failures(res),
        "commands": commands(res),
    }
    return exit_code(out), out


def render_dependencies(o: dict) -> str:
    out = [
        f"dependencies per request operation (joined on operation_Id), {o['window'][0]}..{o['window'][1]} (ms)"
    ]
    out += table(
        o["per_operation"],
        [
            "cloud_RoleName",
            "operation",
            "type",
            "name",
            "n",
            "failed",
            "p50",
            "p95",
            "p99",
            "max",
        ],
    )
    out.append("every dependency of the window, by caller, type, target and name:")
    out += table(
        o["all"],
        [
            "cloud_RoleName",
            "type",
            "target",
            "name",
            "n",
            "failed",
            "p50",
            "p95",
            "p99",
            "max",
        ],
    )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


TRACE_COLS = "itemType, timestamp, id, operation_Id, operation_ParentId, cloud_RoleName, name, duration, success, resultCode, type, target, message, severityLevel, outerMessage, problemId"


def _tree(rows: list[dict]) -> list[dict]:
    """Rows -> depth-first nodes with depth, spans by parent id, logs under their span."""
    spans = [r for r in rows if r["itemType"] in ("request", "dependency")]
    others = [r for r in rows if r["itemType"] not in ("request", "dependency")]
    by_id = {s["id"]: s for s in spans if s.get("id")}
    children: dict[str, list] = {}
    roots = []
    for s in spans:
        p = s.get("operation_ParentId") or ""
        if p in by_id and p != s.get("id"):
            children.setdefault(p, []).append(s)
        else:
            roots.append(s)
    for r in others:
        p = r.get("operation_ParentId") or ""
        (children.setdefault(p, []) if p in by_id else roots).append(r)
    out = []

    def walk(node, depth):
        out.append({**node, "depth": depth})
        for c in sorted(
            children.get(node.get("id") or "", []), key=lambda x: x["timestamp"]
        ):
            walk(c, depth + 1)

    for r in sorted(roots, key=lambda x: x["timestamp"]):
        walk(r, 0)
    return out


def cmd_trace(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns, default_since="24h")
    r = run_az(
        ai_call(
            ns.app,
            f"union requests, dependencies, traces, exceptions | where operation_Id == {kql_str(ns.operation_id)} | project {TRACE_COLS} | order by timestamp asc",
            frm,
            to,
        )
    )
    rows = ai_rows(r.data) if r.ok else []
    nodes = _tree(rows)
    spans = [n for n in nodes if n["itemType"] in ("request", "dependency")]
    root = next(
        (n for n in spans if n["itemType"] == "request" and n["depth"] == 0),
        spans[0] if spans else None,
    )
    out = {
        "operation_id": ns.operation_id,
        "window": [frm, to],
        "summary": {
            "root": f"{root['cloud_RoleName']} {root['name']}" if root else None,
            "duration_ms": root["duration"] if root else None,
            "spans": len(spans),
            "logs": sum(1 for n in nodes if n["itemType"] == "trace"),
            "exceptions": sum(1 for n in nodes if n["itemType"] == "exception"),
            "failed_spans": sum(1 for n in spans if str(n.get("success")) == "False"),
            "services": sorted({n["cloud_RoleName"] for n in spans}),
        },
        "nodes": nodes,
        "failed": failures([r]),
        "commands": commands([r]),
    }
    return exit_code(out), out


def render_trace(o: dict) -> str:
    s = o["summary"]
    out = [
        f"trace {o['operation_id']}: root {s['root'] or '(none)'} {s['duration_ms'] if s['duration_ms'] is not None else '-'} ms, {s['spans']} spans ({s['failed_spans']} failed), {s['logs']} logs, {s['exceptions']} exceptions, services {', '.join(s['services']) or '-'}"
    ]
    if not o["nodes"]:
        out.append(
            "  (no rows: an unknown operation_Id, or one outside the window - trace takes the window of the exemplar)"
        )
    for n in o["nodes"]:
        pad = "  " * (n["depth"] + 1)
        t = n["itemType"]
        if t in ("request", "dependency"):
            out.append(
                f"{pad}{t:10s} {n['timestamp'][11:23]} {n['cloud_RoleName']} {n['name']}  {n['duration']} ms  {'ok' if str(n.get('success')) == 'True' else 'FAILED'} {n.get('resultCode') or ''} {('[' + n['type'] + ' ' + (n.get('target') or '') + ']') if t == 'dependency' else ''}"
            )
        elif t == "trace":
            out.append(
                f"{pad}log        {n['timestamp'][11:23]} {SEVERITY.get(n.get('severityLevel'), n.get('severityLevel'))}: {(n.get('message') or '')[:200]}"
            )
        else:
            out.append(
                f"{pad}exception  {n['timestamp'][11:23]} {n.get('type') or ''}: {(n.get('outerMessage') or '')[:200]}"
            )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


EX_COLS = (
    "timestamp, cloud_RoleName, name, duration, success, resultCode, operation_Id, id"
)


def cmd_exemplars(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    svc = kql_in("cloud_RoleName", ns.service or [])
    op = kql_in("name", ns.operation or [])
    calls = [
        ai_call(
            ns.app,
            f"requests {svc}{op}| top {ns.slow} by duration desc | project {EX_COLS}",
            frm,
            to,
        ),
        ai_call(
            ns.app,
            f"requests {svc}{op}| where success == false | top {ns.failed} by timestamp desc | project {EX_COLS}",
            frm,
            to,
        ),
    ]
    res = run_many(calls)
    slow = ai_rows(res[0].data) if res[0].ok else []
    failed = ai_rows(res[1].data) if res[1].ok else []
    ids = list(dict.fromkeys([r["operation_Id"] for r in slow + failed]))
    detail: dict[str, dict] = {
        i: {"dependencies": [], "exceptions": [], "logs": []} for i in ids
    }
    if ids:
        r = run_az(
            ai_call(
                ns.app,
                f"union dependencies, exceptions, traces | where operation_Id in ({', '.join(kql_str(i) for i in ids)}) | where itemType != 'trace' or severityLevel >= 2 | project {TRACE_COLS} | order by timestamp asc",
                frm,
                to,
            )
        )
        res.append(r)
        for row in ai_rows(r.data) if r.ok else []:
            d = detail[row["operation_Id"]]
            if row["itemType"] == "dependency":
                d["dependencies"].append(
                    {
                        "cloud_RoleName": row["cloud_RoleName"],
                        "type": row["type"],
                        "name": row["name"],
                        "duration": row["duration"],
                        "success": row["success"],
                        "resultCode": row["resultCode"],
                    }
                )
            elif row["itemType"] == "exception":
                d["exceptions"].append(
                    {
                        "type": row["type"],
                        "outerMessage": row["outerMessage"],
                        "problemId": row["problemId"],
                    }
                )
            else:
                d["logs"].append(
                    {
                        "severity": SEVERITY.get(
                            row["severityLevel"], row["severityLevel"]
                        ),
                        "message": row["message"],
                    }
                )
    for r in slow + failed:
        r.update(detail.get(r["operation_Id"], {}))
    out = {
        "window": [frm, to],
        "slow": slow,
        "failed_requests": failed,
        "failed": failures(res),
        "commands": commands(res),
    }
    return exit_code(out), out


def _render_ex(r: dict) -> list[str]:
    out = [
        f"  {r['timestamp'][:19]}Z {r['cloud_RoleName']} {r['name']}  {r['duration']} ms  {'ok' if str(r['success']) == 'True' else 'FAILED'} {r['resultCode']}  operation_Id {r['operation_Id']}"
    ]
    for d in r.get("dependencies", []):
        out.append(
            f"      dependency {d['cloud_RoleName']} [{d['type']}] {d['name']}  {d['duration']} ms  {'ok' if str(d['success']) == 'True' else 'FAILED'} {d['resultCode']}"
        )
    for e in r.get("exceptions", []):
        out.append(f"      exception  {e['type']}: {(e['outerMessage'] or '')[:160]}")
    for lg in r.get("logs", []):
        out.append(f"      log {lg['severity']}: {(lg['message'] or '')[:160]}")
    return out


def render_exemplars(o: dict) -> str:
    out = [f"slowest requests, {o['window'][0]}..{o['window'][1]}:"]
    for r in o["slow"]:
        out += _render_ex(r)
    if not o["slow"]:
        out.append("  (none)")
    out.append("newest failed requests:")
    for r in o["failed_requests"]:
        out += _render_ex(r)
    if not o["failed_requests"]:
        out.append("  (none)")
    out.append(
        "(each with its dependencies, exceptions and warn+ log lines sharing the operation_Id; `trace <operation_Id>` prints the whole tree)"
    )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


# --- watch: a driven run's start and end, polled bin by bin ------------------

IDENTITY_DIMENSIONS = ("user_agent.original", "http.user_agent")


def _identity_expr(dimensions: tuple[str, ...]) -> str:
    """The identity and the dimension it was read from, per row: the first
    non-empty of the customDimensions keys given, in order."""
    val = f"tostring(customDimensions[{kql_str(dimensions[-1])}])"
    dim = kql_str(dimensions[-1])
    for d in reversed(dimensions[:-1]):
        this = f"tostring(customDimensions[{kql_str(d)}])"
        val = f"iff(isempty({this}), {val}, {this})"
        dim = f"iff(isempty({this}), {dim}, {kql_str(d)})"
    return f"| extend odd_identity = {val}, odd_dimension = {dim} "


def _watch_kql(ns, dimensions: tuple[str, ...]) -> str:
    return (
        f"requests {kql_in('cloud_RoleName', ns.service or [])}"
        f"{_identity_expr(dimensions)}"
        f"| where odd_identity startswith {kql_str(ns.identity)} "
        "| summarize n=count(), first_row=min(timestamp), last_row=max(timestamp), "
        "identities=make_set(odd_identity), dimensions=make_set(odd_dimension), "
        "lag_max=max((ingestion_time() - timestamp) / 1s)"
    )


def _probe_kql(ns) -> str:
    """The component's ingestion lag right now, on every row of the service."""
    return (
        f"requests {kql_in('cloud_RoleName', ns.service or [])}"
        "| extend odd_lag = (ingestion_time() - timestamp) / 1s "
        "| summarize n=count(), lag_p99=percentile(odd_lag, 99), lag_max=max(odd_lag)"
    )


def _row_ts(value) -> str | None:
    """A KQL datetime (100 ns precision) -> RFC3339 UTC at the second."""
    if not value:
        return None
    return iso(parse_ts(value[:19] + "Z"))


def _set(value) -> list[str]:
    """A dynamic column under -o json is a JSON string: decoded here."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            got = json.loads(value)
            return [str(v) for v in got] if isinstance(got, list) else []
        except ValueError:
            return []
    return []


def _read_bin(data) -> dict:
    rows = ai_rows(data)
    r = rows[0] if rows else {}
    return {
        "n": int(r.get("n") or 0),
        "first": _row_ts(r.get("first_row")),
        "last": _row_ts(r.get("last_row")),
        "identities": sorted(_set(r.get("identities"))),
        "dimensions": sorted(_set(r.get("dimensions"))),
        "lag": float(r["lag_max"]) if r.get("lag_max") is not None else None,
    }


def _load_watch_state(path: str | None, identity: str, frm: str, bin_: str) -> dict:
    fresh = {
        "identity_prefix": identity,
        "poll_from": frm,  # the invocation's --from: what identifies the watch
        "from": frm,  # where the bins start: moved back by a walk-back
        "bin": bin_,
        "cursor": frm,
        "bins": [],
        "started": None,
        "last_row": None,
        "empty_since": 0,
        "identity": [],
        "identity_attr": None,
        "walked_back": 0,
        "polls": 0,
        "rows": 0,
        "lag_max_s": None,
        "lag_probe": None,
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
    if saved.get("identity_prefix") != identity or saved.get("poll_from") != frm:
        usage(
            f"{path} holds another watch ({saved.get('identity_prefix')!r} from "
            f"{saved.get('poll_from')}): name a state file of this watch's own"
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


def _note_identity(state: dict, got: dict) -> None:
    state["identity"] = sorted(set(state["identity"]) | set(got["identities"]))
    if got["dimensions"] and state["identity_attr"] is None:
        state["identity_attr"] = got["dimensions"][0]
    if got.get("lag") is not None:
        state["lag_max_s"] = max(state.get("lag_max_s") or 0.0, got["lag"])


def _settle_seconds(ns, state: dict, step: timedelta) -> int:
    """The settle in force: the flag's duration, or the largest ingestion
    lag observed so far plus one bin (one bin alone before any row)."""
    if ns.settle != "auto":
        return parse_duration(ns.settle)
    return math.ceil(state.get("lag_max_s") or 0.0) + int(step.total_seconds())


def _walk_back(ns, kql: str, first_bin_start, step, limit: int = 20):
    """The bins before the first polled one, back to an empty bin (or
    ``limit`` bins): earliest first, with the earliest row found; the
    failed result third when az failed midway - the walk then counts for
    nothing, and the next call does it again whole."""
    results: list = []
    bins: list[dict] = []
    earliest = None
    identities: list[dict] = []
    y = first_bin_start
    for _ in range(limit):
        x = y - step
        r = run_az(ai_call(ns.app, kql, iso(x), iso(y)))
        results.append(r)
        if not r.ok:
            return None, results, r
        got = _read_bin(r.data)
        bins.insert(
            0,
            {
                "from": iso(x),
                "to": iso(y),
                "listed": got["n"],
                "new": got["n"],
                "capped": False,
            },
        )
        if got["n"]:
            earliest = got["first"]
            identities.append(got)
        else:
            break
        y = x
    if earliest is None:
        return None, results, None
    return {"bins": bins, "first": earliest, "identities": identities}, results, None


def cmd_watch(ns) -> tuple[int, dict]:
    """Poll a driven run's identity, bin by bin, until it has started and
    then ended - the end criterion the watch section of the scenario skill
    states, shipped: once started, ``--ended-after`` consecutive empty
    closed bins; before the first row an empty bin means not started. One
    summarize per bin: the count, the first and last row, the identity
    values and the dimension they were read from - never a second call."""
    if not ns.frm:
        usage("watch needs --from <the instant polling starts, RFC3339 UTC>")
    frm = parse_ts(ns.frm)
    deadline = parse_ts(ns.to) if ns.to else None
    if deadline and deadline <= frm:
        usage("--to must be after --from")
    step = timedelta(seconds=parse_duration(ns.bin))
    if step.total_seconds() <= 0:
        usage("--bin must be a positive duration")
    if ns.settle != "auto":
        parse_duration(ns.settle)
    every = parse_duration(ns.every)
    bound = parse_duration(ns.max)
    length = timedelta(seconds=parse_duration(ns.length)) if ns.length else None
    if ns.expect is not None and ns.expect <= 0:
        usage("--expect must be a positive count")
    dimensions = tuple(ns.dimension) if ns.dimension else IDENTITY_DIMENSIONS
    kql = _watch_kql(ns, dimensions)
    state = _load_watch_state(ns.state, ns.identity, iso(frm), ns.bin)
    results: list = []
    recorded = 0
    recorded_bins = 0  # bins queried by this call: --max never cuts the first
    began = time.monotonic()
    polls_this_call = 0
    while True:
        state["polls"] += 1
        polls_this_call += 1
        now = datetime.now(timezone.utc).replace(microsecond=0)
        at_deadline = deadline is not None and now >= deadline
        if at_deadline:
            now = deadline
        error = None
        if ns.settle == "auto" and state["lag_probe"] is None:
            # the component's lag right now, once, before the first bin
            r = run_az(
                ai_call(
                    ns.app, _probe_kql(ns), iso(now - timedelta(minutes=10)), iso(now)
                )
            )
            results.append(r)
            if not r.ok:
                error = r
            else:
                rows = ai_rows(r.data)
                p = rows[0] if rows else {}
                state["lag_probe"] = {
                    "window": [iso(now - timedelta(minutes=10)), iso(now)],
                    "n": int(p.get("n") or 0),
                    "p99_s": round(float(p["lag_p99"]), 2)
                    if p.get("lag_p99") is not None
                    else None,
                    "max_s": round(float(p["lag_max"]), 2)
                    if p.get("lag_max") is not None
                    else None,
                }
                if state["lag_probe"]["max_s"] is not None:
                    state["lag_max_s"] = max(
                        state.get("lag_max_s") or 0.0, state["lag_probe"]["max_s"]
                    )
        settle = timedelta(seconds=_settle_seconds(ns, state, step))
        # a bin closes once its end is the settle old; at the deadline the
        # last settle is read all the same, flagged unsettled, so a run
        # that began inside it is never reported "not started"
        horizon = now if at_deadline else now - settle
        cursor = parse_ts(state["cursor"])
        while error is None and cursor < horizon and state["status"] != "ended":
            if bound and recorded_bins and time.monotonic() - began >= bound:
                break  # --max binds the call, inside a poll as between two
            recorded_bins += 1
            x, y = cursor, min(cursor + step, horizon)
            partial = y < cursor + step
            r = run_az(ai_call(ns.app, kql, iso(x), iso(y)))
            results.append(r)
            if not r.ok:
                error = r  # the bin stays unread: the next call queries it again
                break
            got = _read_bin(r.data)
            entry = {
                "from": iso(x),
                "to": iso(y),
                "listed": got["n"],
                "new": got["n"],
                "capped": False,
            }
            if y > now - settle:
                entry["unsettled"] = True
            if partial:
                entry["partial"] = True
            earlier = None
            if (
                got["n"]
                and state["started"] is None
                and iso(x) == state["from"]
                and not state["walked_back"]
            ):
                # rows in the very first bin: the run may have begun before
                # --from - walk back, bin by bin, to its first row, before
                # this bin is recorded: an az error midway leaves both unread
                earlier, walked, walk_error = _walk_back(ns, kql, x, step)
                results.extend(walked)
                if walk_error is not None:
                    error = walk_error
                    break
            if partial:
                # the clipped last bin before the deadline: read for the start
                # and the rows, kept apart and replaced, never a closed bin
                state["partial_bin"] = entry
            else:
                state["bins"].append(entry)
                state.pop("partial_bin", None)
                state["cursor"] = iso(y)
            cursor = y
            if got["n"]:
                first = got["first"]
                if earlier:
                    state["bins"] = earlier["bins"] + state["bins"]
                    state["from"] = earlier["bins"][0]["from"]
                    state["walked_back"] = len(earlier["bins"])
                    first = earlier["first"]
                    for g in earlier["identities"]:
                        _note_identity(state, g)
                        state["rows"] += g["n"]
                if state["started"] is None:
                    state["started"] = first
                    state["status"] = "running"
                _note_identity(state, got)
                if not partial:
                    state["rows"] += got["n"]
                if state["last_row"] is None or got["last"] >= state["last_row"]:
                    state["last_row"] = got["last"]
                state["empty_since"] = 0
                if not partial and ns.expect and state["rows"] >= ns.expect:
                    # the scheduled count has landed: the run ended at its
                    # last row, no empty bin needed
                    state["status"] = "ended"
                    state["ended"] = state["last_row"]
                    state["ended_by"] = "count"
            elif state["started"] is not None and not partial:
                state["empty_since"] += 1
                scheduled_end = parse_ts(state["started"]) + length if length else None
                if scheduled_end and x >= scheduled_end:
                    # past the scheduled length, one empty closed bin ends it
                    state["status"] = "ended"
                    state["ended"] = state["last_row"]
                    state["ended_by"] = "schedule"
                elif state["empty_since"] >= ns.ended_after:
                    state["status"] = "ended"
                    state["ended"] = state["last_row"]
                    state["ended_by"] = "quiet"
            if partial:
                break
        state["commands"].extend(commands(results[recorded:]))
        recorded = len(results)
        state.pop("deadline_note", None)
        settle_s = int(settle.total_seconds())
        if error is not None:
            _save_watch_state(ns.state, state)
            return 1, _watch_out(
                state, ns, now, polls_this_call, settle_s, failures([error])
            )
        if state["status"] == "ended":
            _save_watch_state(ns.state, state)
            return 0, _watch_out(state, ns, now, polls_this_call, settle_s)
        if at_deadline:
            need = ns.ended_after - state["empty_since"]
            if state["started"] and state["empty_since"]:
                state["deadline_note"] = (
                    f"the deadline closes {state['empty_since']} of the {ns.ended_after} "
                    f"empty {ns.bin} bins the end needs: extend --to past the last row by "
                    f"{ns.ended_after} x {ns.bin} + {settle_s}s ({need * int(step.total_seconds())} s more)"
                )
            elif state["started"]:
                state["deadline_note"] = (
                    "the run was still producing rows at the deadline: extend --to past "
                    f"its end by {ns.ended_after} x {ns.bin} + {settle_s}s"
                )
            else:
                state["deadline_note"] = (
                    f"no row on the identity up to the deadline (the last {settle_s}s read "
                    "unsettled): no run observed in the window"
                )
        _save_watch_state(ns.state, state)
        if at_deadline or time.monotonic() - began >= bound:
            return (3 if state["started"] else 4), _watch_out(
                state, ns, now, polls_this_call, settle_s
            )
        # wake when the next bin can close - its end plus the settle - never
        # on a fixed clock; --every is the floor, --max and --to the ceiling
        wake = parse_ts(state["cursor"]) + step + settle
        wait = (wake - datetime.now(timezone.utc)).total_seconds()
        if deadline is not None:
            wait = min(wait, (deadline - datetime.now(timezone.utc)).total_seconds())
        if bound:
            wait = min(wait, bound - (time.monotonic() - began))
        time.sleep(max(every, wait, 0))


def _watch_out(
    state: dict,
    ns,
    now,
    polls_this_call: int,
    settle_s: int,
    failed: list | None = None,
) -> dict:
    started, ended = state.get("started"), state.get("ended")
    span = None
    if started and ended:
        span = int((parse_ts(ended) - parse_ts(started)).total_seconds())
    return {
        "identity_prefix": ns.identity,
        "poll_from": state["poll_from"],
        "from": state["from"],
        "to": ns.to,
        "bin": ns.bin,
        "every": ns.every,
        "ended_after": ns.ended_after,
        "settle": ns.settle,
        "settle_s": settle_s,
        "lag_max_s": state.get("lag_max_s"),
        "lag_probe": state.get("lag_probe"),
        "length": ns.length,
        "expect": ns.expect,
        "rows": state.get("rows", 0),
        "ended_by": state.get("ended_by"),
        "status": state["status"],
        "started": started,
        "ended": ended,
        "last_row": state.get("last_row"),
        "span_s": span,
        "identity": state.get("identity") or [],
        "identity_attr": state.get("identity_attr"),
        "several_identities": len(state.get("identity") or []) > 1,
        "empty_since_last_row": state.get("empty_since", 0),
        "walked_back": state.get("walked_back", 0),
        "deadline_note": state.get("deadline_note"),
        "bins": state["bins"],
        "partial_bin": state.get("partial_bin"),
        "capped_bins": 0,
        "polls": state["polls"],
        "polls_this_call": polls_this_call,
        "last_poll": iso(now),
        "state": ns.state,
        "note": "one summarize per bin - a count, never a listing: no bin is ever capped; new equals listed, a request row falls in one bin",
        "failed": failed or [],
        "commands": list(state["commands"]),
    }


def render_watch(o: dict) -> str:
    out = [f"watch: {o['status']} - {o['identity_prefix']} from {o['from']}"]
    if o["started"]:
        out.append(
            f"Started (UTC): {o['started']}   # the run's first request row on the identity"
            + (
                f" - {o['walked_back']} bin(s) before --from, the run had begun before the watch"
                if o.get("walked_back")
                else ""
            )
        )
    if o["ended"]:
        why = {
            "count": f"the scheduled {o['expect']} rows landed ({o['rows']} counted)",
            "schedule": f"one empty {o['bin']} bin past the scheduled {o['length']}",
        }.get(o.get("ended_by"), f"{o['ended_after']} empty {o['bin']} bin(s) after it")
        out.append(f"Ended   (UTC): {o['ended']}   # last request row; {why}")
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
    probe = o.get("lag_probe")
    out.append(
        f"settle {o['settle_s']} s "
        + (
            f"(auto: ingestion lag max {probe['max_s']} s on {probe['n']} rows in the 10 min before the dispatch"
            + (
                f", {o['lag_max_s']} s at most on the run's rows"
                if o.get("lag_max_s") is not None
                and probe.get("max_s") is not None
                and o["lag_max_s"] > probe["max_s"]
                else ""
            )
            + f", plus one {o['bin']} bin)"
            if o["settle"] == "auto" and probe
            else f"({o['settle']})"
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
        out.append(f"  {r['from'][11:19]} .. {r['to'][11:19]}  new={r.get('new')}")
    if o.get("partial_bin"):
        r = o["partial_bin"]
        out.append(
            f"  {r['from'][11:19]} .. {r['to'][11:19]}  new={r.get('new')}  partial, up to the deadline: read again next call"
        )
    if o.get("deadline_note"):
        out.append(f"  deadline {o['to']}: {o['deadline_note']}")
    elif o["status"] != "ended":
        out.append(
            "  still "
            + ("running" if o["started"] else "not started")
            + ": run the same invocation again (the state file resumes it)"
        )
    out += render_failures(o)
    out += render_watch_commands(o)
    return "\n".join(out)


def render_watch_commands(o: dict) -> list[str]:
    """The bins' queries differ by their window alone: one line, the window
    as placeholders, and the count - never one line per bin."""
    cmds = o.get("commands") or []
    if not cmds:
        return []
    folded = list(
        dict.fromkeys(
            c.replace(f"--start-time {b}", "--start-time <bin start>").replace(
                f"--end-time {e}", "--end-time <bin end>"
            )
            for c, b, e in (
                (c, *[t.split(" ", 1)[0] for t in c.split("-time ")[1:3]]) for c in cmds
            )
        )
    )
    return [
        f"queries run (record these; {len(cmds)} calls, one per bin, the window folded):"
    ] + ["  " + c for c in folded]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("operations")
    a.add_argument("--service", action="append")
    a.add_argument("--top", type=int, default=20)
    a.add_argument("--bin")
    b = sub.add_parser("dependencies")
    b.add_argument("--service", action="append")
    c = sub.add_parser("exemplars")
    c.add_argument("--service", action="append")
    c.add_argument("--operation", action="append")
    c.add_argument("--slow", type=int, default=3)
    c.add_argument("--failed", type=int, default=3)
    d = sub.add_parser("trace")
    d.add_argument("operation_id")
    w = sub.add_parser("watch")
    w.add_argument("--app", required=True)
    w.add_argument("--identity", required=True, help="the run's User-Agent prefix")
    w.add_argument("--service", action="append")
    w.add_argument("--from", dest="frm", help="poll from this instant, RFC3339 UTC")
    w.add_argument("--to", help="the deadline, RFC3339 UTC (default: none)")
    w.add_argument("--bin", default="30s")
    w.add_argument("--ended-after", type=int, default=4)
    w.add_argument("--settle", default="auto")
    w.add_argument("--length", help="the manifest's scheduled length, a duration")
    w.add_argument("--expect", type=int, help="the manifest's scheduled request count")
    w.add_argument("--every", default="5s")
    w.add_argument("--max", default="8m")
    w.add_argument("--state", help="the watch's state file; a later call resumes it")
    w.add_argument("--dimension", action="append")
    w.add_argument("--json", action="store_true", help="machine-readable output")
    for p in (a, b, c, d):
        p.add_argument("--app", required=True)
        add_window(p)
    ns = ap.parse_args()
    fn = {
        "operations": (cmd_operations, render_operations),
        "dependencies": (cmd_dependencies, render_dependencies),
        "exemplars": (cmd_exemplars, render_exemplars),
        "trace": (cmd_trace, render_trace),
        "watch": (cmd_watch, render_watch),
    }[ns.cmd]
    code, o = fn[0](ns)
    emit(o, ns.json, fn[1])
    return code


if __name__ == "__main__":
    sys.exit(main())
