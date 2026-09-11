#!/usr/bin/env python3
"""What a Seq store holds for a set of services inside a window, in one call.

    seq-discover.py --from 2026-09-11T07:15:00Z --to 2026-09-11T07:20:00Z
    seq-discover.py --service "Roastery Web Frontend" --since 30m --json

Whole surface: --service NAME (repeatable, none = every service the window
carries), --service-key PROP (the property a service is named by, default
Application; @Resource.service.name on an OTel-instrumented service), a
window (--from/--to or --since), --bucket DURATION (the time slice the data
distribution is reported in, default 1m), --json. Per service it reports
the log-event count and its levels, the span count, the distinct trace
count, the exception count, the root-span operations (by @MessageTemplate,
with counts), the metric definitions the service emits and its series
point count; for the window it reports which slices actually hold events
(where the data sits in time) and the signals the store serves at all.
Profiles are never served. Exit 0 when every probe ran, 2 when one failed
(the failure is in the output).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seq_cli import (
    add_service,
    add_window,
    commands,
    emit,
    errors,
    render_commands,
    resolve_window,
    run_many,
    service_clause,
    slices,
    sql_where,
    table,
    window_flags,
)

NO_KEY = "(no value)"


def _key(v) -> str:
    return NO_KEY if v is None else str(v)


def probe(services: list[str], key: str, frm: str, to: str, bucket: str) -> dict:
    svc = service_clause(services, key)
    w = sql_where(svc)
    sql = [
        f"select count(*) as n, count(distinct(@TraceId)) as traces from stream{w} group by {key}, has(@Start)",
        f"select count(*) as n from stream{sql_where('not has(@Start)', svc)} group by {key}, @Level",
        f"select count(*) as n from stream{sql_where('has(@Start) and not has(@ParentId)', svc)} group by {key}, @MessageTemplate",
        f"select count(*) as n from stream{w} group by time({bucket})",
        f"select count(*) as n from stream{sql_where('has(@Exception)', svc)} group by {key}",
        f"select count(*) as n from series{w} group by {key}",
    ]
    calls = [(["query", "-q", q, *window_flags(frm, to), "--json"], "object") for q in sql]
    metrics_args = ["metrics", "search", "-c", "512", *window_flags(frm, to), "--json"]
    if svc:
        metrics_args[2:2] = ["-f", svc]
    calls.append((metrics_args, "object"))
    results = run_many(calls)
    from seq_cli import _normalise_query  # the query envelope, normalised like query() does

    for r in results[:6]:
        if r.ok:
            r.data = _normalise_query(r.data)
    counts, levels, roots, dist, exc, points, mdefs = results
    report: dict = {"window": [frm, to], "services": {}, "signals": {}, "data_slices": [], "failed": []}
    per: dict[str, dict] = {}

    def svc_entry(name):
        return per.setdefault(
            name,
            {"logs": 0, "spans": 0, "traces": 0, "levels": {}, "exceptions": 0, "root_operations": {}, "metric_points": 0},
        )

    for row in table(counts):
        e = svc_entry(_key(row.get(key)))
        if row.get("has(@Start)"):
            e["spans"] = row.get("n") or 0
            e["traces"] = max(e["traces"], row.get("traces") or 0)
        else:
            e["logs"] = row.get("n") or 0
            e["traces"] = max(e["traces"], row.get("traces") or 0)
    for row in table(levels):
        svc_entry(_key(row.get(key)))["levels"][_key(row.get("@Level"))] = row.get("n") or 0
    for row in table(roots):
        svc_entry(_key(row.get(key)))["root_operations"][_key(row.get("@MessageTemplate"))] = row.get("n") or 0
    for row in table(exc):
        svc_entry(_key(row.get(key)))["exceptions"] = row.get("n") or 0
    for row in table(points):
        svc_entry(_key(row.get(key)))["metric_points"] = row.get("n") or 0
    if mdefs.ok and isinstance(mdefs.data, dict):
        cols = mdefs.data.get("Columns") or []
        defs = [dict(zip(cols, r)) for r in mdefs.data.get("Rows") or []]
        report["metric_definitions"] = [
            {"name": d.get("Name"), "kind": d.get("Kind"), "unit": d.get("Unit")} for d in defs
        ]
    for name, e in per.items():
        e["root_operations"] = dict(sorted(e["root_operations"].items(), key=lambda kv: -kv[1])[:15])
        e["levels"] = dict(sorted(e["levels"].items(), key=lambda kv: -kv[1]))
    for s in services:
        svc_entry(s)
    report["services"] = dict(sorted(per.items(), key=lambda kv: -(kv[1]["logs"] + kv[1]["spans"])))
    report["data_slices"] = [{"time": s["time"], "events": s.get("n") or 0} for s in slices(dist) if (s.get("n") or 0) > 0]
    total_logs = sum(e["logs"] for e in per.values())
    total_spans = sum(e["spans"] for e in per.values())
    total_points = sum(e["metric_points"] for e in per.values())
    report["signals"] = {
        "logs": total_logs,
        "traces": total_spans,
        "metrics": total_points,
        "profiles": "not served",
    }
    report["failed"] = [{"command": r.command, "error": r.error} for r in results if not r.ok]
    report["error"] = errors(results)
    report["commands"] = commands(results)
    return report


def render(o: dict) -> str:
    out = [f"window {o['window'][0]} .. {o['window'][1]}"]
    sig = o["signals"]
    out.append(f"signals: logs={sig['logs']} spans={sig['traces']} metric points={sig['metrics']} profiles={sig['profiles']}")
    if o["data_slices"]:
        out.append("data sits in: " + ", ".join(f"{s['time'][11:16]}({s['events']})" for s in o["data_slices"]))
    else:
        out.append("data sits in: nothing in this window")
    for name, e in o["services"].items():
        out.append(f"{name}: logs={e['logs']} spans={e['spans']} traces={e['traces']} exceptions={e['exceptions']} metric points={e['metric_points']}")
        if e["levels"]:
            out.append("  levels: " + "  ".join(f"{k}={v}" for k, v in e["levels"].items()))
        for op, n in e["root_operations"].items():
            out.append(f"  root op {n:6d}  {op}")
    if o.get("metric_definitions"):
        out.append("metrics: " + ", ".join(f"{m['name']} ({m['kind']}, {m['unit']})" for m in o["metric_definitions"]))
    for f in o["failed"]:
        out.append(f"FAILED {f['command']}: {f['error']}")
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_service(ap)
    ap.add_argument("--bucket", default="1m", help="time slice for the data distribution (default 1m)")
    add_window(ap)
    ns = ap.parse_args()
    frm, to = resolve_window(ns)
    out = probe(ns.service, ns.service_key, frm, to, ns.bucket)
    emit(out, ns.json, render)
    return 2 if out["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
