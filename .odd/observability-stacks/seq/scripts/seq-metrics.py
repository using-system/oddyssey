#!/usr/bin/env python3
"""Metrics in Seq: the definitions a window carries, and one metric aggregated by dimension or over time.

    seq-metrics.py list --service svc --from ... --to ...
    seq-metrics.py query HttpRequestDuration --group-by Path --group-by StatusCode --from ... --to ...
    seq-metrics.py query BeanTemperature --agg mean --group-by MachineId --step 1m --since 30m --json

Whole surface - both subcommands take --service NAME (repeatable),
--service-key PROP (default Application), a window (--from/--to or
--since) and --json. `list` prints every metric definition the window
carries (name, kind, unit, description) with its dimensions. `query
METRIC` adds --agg mean|max|min|sum|last|count (default by kind: Gauge
mean, Sum sum, Exponential - a histogram - max, which is the merged
histogram the quantiles are derived from), --group-by DIM (repeatable),
--step DURATION (time slices, e.g. 1m; without it one row per group) and
prints one row per group (and per slice with --step) with the value - for
a histogram: count, min, max and the approximate p50/p95/p99 read off its
buckets. Every subcommand prints the seqcli commands it ran. Exit 0 on
success, 1 when seqcli errored.
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
    fmt,
    hist_quantiles,
    is_histogram,
    query,
    render_commands,
    resolve_window,
    run,
    run_many,
    series,
    service_clause,
    slices,
    sql_where,
    table,
    window_flags,
)

DEFAULT_AGG = {"Gauge": "mean", "Sum": "sum", "Exponential": "max", "Histogram": "max"}


def definitions(svc: str, frm: str, to: str):
    args = ["metrics", "search", "-c", "512", *window_flags(frm, to), "--json"]
    if svc:
        args[2:2] = ["-f", svc]
    r = run(args, "object")
    defs = []
    if r.ok and isinstance(r.data, dict):
        cols = r.data.get("Columns") or []
        defs = [dict(zip(cols, row)) for row in r.data.get("Rows") or []]
    return r, defs


def cmd_list(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    svc = service_clause(ns.service, ns.service_key)
    r, defs = definitions(svc, frm, to)
    dims = run_many(
        [
            (
                [
                    "metrics",
                    "dimensions",
                    "-m",
                    d["Name"],
                    *window_flags(frm, to),
                    "--json",
                ],
                "object",
            )
            for d in defs
        ]
    )
    out = []
    for d, dr in zip(defs, dims):
        out.append(
            {
                "name": d.get("Name"),
                "kind": d.get("Kind"),
                "unit": d.get("Unit"),
                "description": d.get("Description"),
                "dimensions": [
                    x.get("Accessor") for x in (dr.data or []) if isinstance(x, dict)
                ]
                if dr.ok
                else [],
            }
        )
    err = errors([r, *dims])
    return (1 if err else 0), {
        "error": err,
        "window": [frm, to],
        "metrics": out,
        "commands": commands([r, *dims]),
    }


def _value(v):
    if is_histogram(v):
        return hist_quantiles(v)
    return v


def cmd_query(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    svc = service_clause(ns.service, ns.service_key)
    results = []
    agg = ns.agg
    kind = None
    if not agg:
        r, defs = definitions(svc, frm, to)
        results.append(r)
        kind = next((d.get("Kind") for d in defs if d.get("Name") == ns.metric), None)
        agg = DEFAULT_AGG.get(kind or "", "mean")
    groups = list(ns.group_by)
    gb = groups + ([f"time({ns.step})"] if ns.step else [])
    sql = f"select {agg}({ns.metric}) as v from series{sql_where(f'has({ns.metric})', svc)}"
    if gb:
        sql += " group by " + ", ".join(gb)
    q = query(sql, frm, to)
    results.append(q)
    rows = []
    if ns.step and groups:
        for s in series(q):
            for sl in s["slices"]:
                rows.append(
                    {
                        "group": s["key"],
                        "time": sl["time"],
                        "value": _value(sl.get("v")),
                    }
                )
    elif ns.step:
        for sl in slices(q):
            rows.append({"group": {}, "time": sl["time"], "value": _value(sl.get("v"))})
    else:
        for row in table(q):
            rows.append(
                {
                    "group": {g: row.get(g) for g in groups},
                    "time": None,
                    "value": _value(row.get("v")),
                }
            )
    err = errors(results)
    return (1 if err else 0), {
        "error": err,
        "window": [frm, to],
        "metric": ns.metric,
        "kind": kind,
        "agg": agg,
        "group_by": groups,
        "step": ns.step or None,
        "rows": rows,
        "commands": commands(results),
    }


def render(o: dict) -> str:
    if o.get("error"):
        return "ERROR " + o["error"]
    out = [f"window {o['window'][0]} .. {o['window'][1]}"]
    if "metrics" in o:
        for m in o["metrics"]:
            out.append(
                f"  {m['name']} ({m['kind']}, {m['unit']}): {m['description']}  dims: {', '.join(m['dimensions']) or '-'}"
            )
        if not o["metrics"]:
            out.append("  no metric definitions in this window")
    else:
        out.append(
            f"{o['agg']}({o['metric']})"
            + (f" kind {o['kind']}" if o.get("kind") else "")
            + (f" by {', '.join(o['group_by'])}" if o["group_by"] else "")
            + (f" every {o['step']}" if o["step"] else "")
        )
        for r in o["rows"]:
            g = " ".join(f"{k}={v}" for k, v in r["group"].items())
            t = (r["time"] or "")[:19]
            v = r["value"]
            if isinstance(v, dict):
                vs = f"n={v['count']} min={fmt(v['min'])} p50={fmt(v['p50'])} p95={fmt(v['p95'])} p99={fmt(v['p99'])} max={fmt(v['max'])}"
            else:
                vs = fmt(v)
            out.append(f"  {t:19s} {g:40s} {vs}")
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    add_service(p)
    add_window(p)
    p = sub.add_parser("query")
    p.add_argument("metric", help="the metric name, as `list` prints it")
    add_service(p)
    p.add_argument(
        "--agg",
        default="",
        choices=["", "mean", "max", "min", "sum", "last", "count"],
        help="aggregate (default by kind)",
    )
    p.add_argument(
        "--group-by", action="append", default=[], help="a dimension; repeatable"
    )
    p.add_argument("--step", default="", help="time slice, e.g. 1m (default: none)")
    add_window(p)
    ns = ap.parse_args()
    code, out = {"list": cmd_list, "query": cmd_query}[ns.cmd](ns)
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
