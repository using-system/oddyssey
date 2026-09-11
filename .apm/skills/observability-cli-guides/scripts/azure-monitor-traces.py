#!/usr/bin/env python3
"""Distributed tracing off the component's requests and dependencies tables.

    azure-monitor-traces.py operations --app <app_insights_app> --service orders-api --from ... --to ...
    azure-monitor-traces.py dependencies --app <app_insights_app> --service orders-api --since 30m
    azure-monitor-traces.py exemplars --app <app_insights_app> --service orders-api --slow 3 --failed 3 --since 30m
    azure-monitor-traces.py trace <operation_Id> --app <app_insights_app> [--since 24h]

Whole surface - every subcommand takes --app (the appId GUID), a window
(--from/--to or --since; `trace` defaults to the last 24h), --json.
operations, dependencies and exemplars take --service (repeatable, a
cloud_RoleName; none = every service). operations adds --top (rows, default
20) and --bin (a duration: adds the request count, failures and p95 per
time bucket). exemplars adds --operation (the request name, repeatable),
--slow N (the slowest requests, default 3), --failed N (the newest failed
requests, default 3). trace takes the operation_Id. Exit 0, 1 when a query
failed (the failure is in the output).

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
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from azure_monitor_az import (
    add_window,
    ai_call,
    ai_rows,
    commands,
    emit,
    exit_code,
    failures,
    kql_bin,
    kql_in,
    kql_str,
    render_commands,
    render_failures,
    resolve_window,
    run_az,
    run_many,
    table,
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
    for p in (a, b, c, d):
        p.add_argument("--app", required=True)
        add_window(p)
    ns = ap.parse_args()
    fn = {
        "operations": (cmd_operations, render_operations),
        "dependencies": (cmd_dependencies, render_dependencies),
        "exemplars": (cmd_exemplars, render_exemplars),
        "trace": (cmd_trace, render_trace),
    }[ns.cmd]
    code, o = fn[0](ns)
    emit(o, ns.json, fn[1])
    return code


if __name__ == "__main__":
    sys.exit(main())
