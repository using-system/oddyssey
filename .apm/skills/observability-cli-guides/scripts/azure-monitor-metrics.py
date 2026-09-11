#!/usr/bin/env python3
"""Metrics: the component's customMetrics with their temporality probed, and the platform metrics of a resource.

    azure-monitor-metrics.py list --app <app_insights_app> --service orders-api --since 30m
    azure-monitor-metrics.py query orders.created --app <app_insights_app> --service orders-api --by product.id --from ... --to ...
    azure-monitor-metrics.py query http.server.request.duration --app <app_insights_app> --by http.route --bin 5m --since 30m
    azure-monitor-metrics.py platform --resource <resource id> --metric Requests --aggregation Total --interval PT1M --since 30m
    azure-monitor-metrics.py definitions --resource <resource id>
    azure-monitor-metrics.py resources --resource-group <resource_group> --subscription <subscription>

Whole surface - list: --app, --service (repeatable), a window, --json.
query <name>: --app, --service, --by (a customDimensions key, repeatable),
--bin (a duration: one row per time bucket), --as auto|delta|cumulative|
gauge|histogram (default auto: histogram when the rows aggregate several
points - valueCount above 1 -, else the temporality probe decides between
delta and cumulative; a gauge is never detected and must be told), a window,
--json. platform: --resource (a resource id, or a name with --resource-group
and --resource-type), --subscription, --metric (repeatable, or several
values), --aggregation (Average, Count, Maximum, Minimum, Total - several
allowed; omitted, the metric's primary one), --interval (ISO 8601, default
PT1M), --dimension (repeatable, splits the series), --filter (an OData
dimension filter, e.g. "statusCodeCategory eq '5xx'"), --show (points
printed per series, default 6, the newest), a window, --json. definitions:
--resource, --resource-group, --resource-type, --subscription, --json.
resources: --resource-group, --resource-type (default Microsoft.App/
containerApps), --subscription, --json. Exit 0, 1 when a query failed.

The temporality probe orders one metric's rows per series (the whole
customDimensions set) and counts the pushes that rose and fell against the
previous row: increases with no decrease is a cumulative pipeline, and the
window is read as the edge delta per series (arg_max minus arg_min of
value, qualified by service.instance.id so a restart never reads as a
drop); any decrease is a delta pipeline (each row one export's increment)
and the window is sum(value); neither (a flat series) is left undetermined
with both readings printed. A platform metric answers points without a
value key when the resource does not publish it or nothing happened, and
an empty timeseries when a dimension filter matched no series: both are
stated as absence, never as zeros.
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
    dims,
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

RESOURCE_KEYS = ("service.", "telemetry.", "deployment.", "instrumentationlibrary.")
AGGS = ("total", "average", "count", "maximum", "minimum")


def cmd_list(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    svc = kql_in("cloud_RoleName", ns.service or [])
    res = run_many(
        [
            ai_call(
                ns.app,
                f"customMetrics {svc}| summarize rows=count(), points=sum(valueCount), max_value_count=max(valueCount), earliest=min(timestamp), latest=max(timestamp) by cloud_RoleName, name | order by cloud_RoleName asc, name asc",
                frm,
                to,
            ),
            ai_call(
                ns.app,
                f"customMetrics {svc}| summarize any(customDimensions) by cloud_RoleName, name",
                frm,
                to,
            ),
        ]
    )
    rows = ai_rows(res[0].data) if res[0].ok else []
    keys = {}
    for r in ai_rows(res[1].data) if res[1].ok else []:
        keys[(r["cloud_RoleName"], r["name"])] = sorted(
            k
            for k in dims(r.get("any_customDimensions"))
            if not k.startswith(RESOURCE_KEYS)
        )
    for r in rows:
        r["aggregated"] = (r.get("max_value_count") or 0) > 1
        r["dimensions"] = keys.get((r["cloud_RoleName"], r["name"]), [])
    out = {
        "window": [frm, to],
        "metrics": rows,
        "failed": failures(res),
        "commands": commands(res),
    }
    return exit_code(out), out


def render_list(o: dict) -> str:
    out = [
        f"customMetrics in {o['window'][0]}..{o['window'][1]} (aggregated = rows carry several points; dimensions = the customDimensions keys beyond the resource's)"
    ]
    rows = [{**r, "dims": ", ".join(r["dimensions"]) or "-"} for r in o["metrics"]]
    out += table(
        rows, ["cloud_RoleName", "name", "rows", "points", "aggregated", "dims"]
    )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def _by(keys: list[str]) -> tuple[str, list[str]]:
    """--by keys -> the KQL `by` aliases and their names."""
    parts = [
        f"by{i}=tostring(customDimensions[{kql_str(k)}])" for i, k in enumerate(keys)
    ]
    return ", ".join(parts), [f"by{i}" for i in range(len(keys))]


def cmd_query(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    svc = kql_in("cloud_RoleName", ns.service or [])
    base = f"customMetrics {svc}| where name == {kql_str(ns.name)} "
    by_expr, by_cols = _by(ns.by or [])
    group = ", ".join(
        x
        for x in [by_expr, f"bin(timestamp, {kql_bin(ns.bin)})" if ns.bin else ""]
        if x
    )
    by_clause = f" by {group}" if group else ""
    probe_q = (
        base
        + "| order by series asc, timestamp asc | serialize | extend prev = prev(value), prev_series = prev(series) | summarize pushes=count(), increases=countif(series == prev_series and value > prev), decreases=countif(series == prev_series and value < prev), vmax=max(value), max_value_count=max(valueCount) by series"
    )
    probe_q = probe_q.replace(
        "| order by series",
        "| extend series=tostring(customDimensions) | order by series",
    )
    res = [run_az(ai_call(ns.app, probe_q, frm, to))]
    probe_rows = ai_rows(res[0].data) if res[0].ok else []
    pushes = sum(r["pushes"] for r in probe_rows)
    inc = sum(r["increases"] for r in probe_rows)
    dec = sum(r["decreases"] for r in probe_rows)
    aggregated = any((r.get("max_value_count") or 0) > 1 for r in probe_rows)
    if ns.kind != "auto":
        kind, why = ns.kind, "told by --as"
    elif not probe_rows:
        kind, why = "none", "no rows for this name in the window"
    elif aggregated:
        kind, why = "histogram", "rows carry several points (valueCount above 1)"
    elif dec > 0:
        kind, why = (
            "delta",
            f"{dec} decreases over {pushes} pushes: each row is one export's increment",
        )
    elif inc > 0:
        kind, why = (
            "cumulative",
            f"{inc} increases, no decrease over {pushes} pushes across {len(probe_rows)} series: running totals",
        )
    else:
        kind, why = (
            "undetermined",
            f"flat: no increase and no decrease over {pushes} pushes - both readings printed, the run decides",
        )
    readings: dict = {}
    calls, tags = [], []
    if kind in ("delta", "undetermined"):
        calls.append(
            ai_call(
                ns.app,
                base + f"| summarize total=sum(value), pushes=count(){by_clause}",
                frm,
                to,
            )
        )
        tags.append("delta")
    if kind in ("cumulative", "undetermined"):
        edge_by = ", ".join(
            x
            for x in [
                "series=tostring(customDimensions)",
                "inst=tostring(customDimensions['service.instance.id'])",
                by_expr,
            ]
            if x
        )
        calls.append(
            ai_call(
                ns.app,
                base
                + f"| summarize latest=arg_max(timestamp, value), earliest=arg_min(timestamp, value) by {edge_by} | extend delta = value - value1",
                frm,
                to,
            )
        )
        tags.append("cumulative")
    if kind == "histogram":
        calls.append(
            ai_call(
                ns.app,
                base
                + f"| summarize points=sum(valueCount), total=sum(valueSum), vmax=max(valueMax), vmin=min(valueMin){by_clause}",
                frm,
                to,
            )
        )
        tags.append("histogram")
    if kind == "gauge":
        calls.append(
            ai_call(
                ns.app,
                base
                + f"| summarize avg=avg(value), vmin=min(value), vmax=max(value), latest=arg_max(timestamp, value){by_clause}",
                frm,
                to,
            )
        )
        tags.append("gauge")
    got = run_many(calls)
    res += got
    for tag, r in zip(tags, got):
        rows = ai_rows(r.data) if r.ok else []
        if tag == "cumulative":
            # the edge delta per series, summed into the --by groups
            groups: dict[tuple, dict] = {}
            for x in rows:
                key = tuple(x.get(c) for c in by_cols)
                g = groups.setdefault(key, {"delta": 0.0, "series": 0})
                g["delta"] += x.get("delta") or 0
                g["series"] += 1
            rows = [{**dict(zip(ns.by or [], k)), **v} for k, v in groups.items()]
        else:
            rows = [
                {**{ns.by[i]: x.pop(c) for i, c in enumerate(by_cols) if c in x}, **x}
                for x in rows
            ]
            if tag == "histogram":
                for x in rows:
                    x["avg"] = (x["total"] / x["points"]) if x.get("points") else None
        readings[tag] = rows
    if ns.bin and kind in ("cumulative", "undetermined"):
        readings["note"] = (
            "--bin is ignored for the cumulative reading: the edge delta is over the whole window"
        )
    out = {
        "window": [frm, to],
        "name": ns.name,
        "temporality": {
            "verdict": kind,
            "why": why,
            "pushes": pushes,
            "increases": inc,
            "decreases": dec,
            "series": len(probe_rows),
            "vmax": max((r.get("vmax") or 0 for r in probe_rows), default=None),
        },
        "readings": readings,
        "failed": failures(res),
        "commands": commands(res),
    }
    return exit_code(out), out


def render_query(o: dict) -> str:
    t = o["temporality"]
    out = [
        f"{o['name']} in {o['window'][0]}..{o['window'][1]}: {t['verdict']} - {t['why']} (pushes={t['pushes']} increases={t['increases']} decreases={t['decreases']} series={t['series']} vmax={t['vmax']})"
    ]
    r = o["readings"]
    if "delta" in r:
        out.append("delta reading, sum(value) - the count over the window:")
        out += table(
            r["delta"],
            [
                c
                for c in (
                    list(r["delta"][0].keys()) if r["delta"] else ["total", "pushes"]
                )
            ],
        )
    if "cumulative" in r:
        out.append(
            "cumulative reading, edge delta per series (arg_max - arg_min of value):"
        )
        out += table(
            r["cumulative"],
            [
                c
                for c in (
                    list(r["cumulative"][0].keys())
                    if r["cumulative"]
                    else ["delta", "series"]
                )
            ],
        )
    if "histogram" in r:
        out.append(
            "histogram reading (points, total and avg in the metric's unit, min/max of the rows' extremes):"
        )
        out += table(
            r["histogram"],
            [
                c
                for c in (
                    list(r["histogram"][0].keys())
                    if r["histogram"]
                    else ["points", "total", "avg"]
                )
            ],
        )
    if "gauge" in r:
        out.append("gauge reading:")
        out += table(
            r["gauge"],
            [
                c
                for c in (
                    list(r["gauge"][0].keys())
                    if r["gauge"]
                    else ["avg", "vmin", "vmax", "latest", "value"]
                )
            ],
        )
    if r.get("note"):
        out.append("  " + r["note"])
    if t["verdict"] == "none":
        out.append(
            "  (no rows: the name is not exported in the window - `list` names what is)"
        )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def _resource_args(ns) -> list[str]:
    args = ["--resource", ns.resource]
    if ns.resource_group:
        args += ["--resource-group", ns.resource_group]
    if ns.resource_type:
        args += ["--resource-type", ns.resource_type]
    if ns.subscription:
        args += ["--subscription", ns.subscription]
    return args


def cmd_platform(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    args = [
        "monitor",
        "metrics",
        "list",
        *_resource_args(ns),
        "--metric",
        *ns.metric,
        "--interval",
        ns.interval,
        "--start-time",
        frm,
        "--end-time",
        to,
    ]
    if ns.aggregation:
        args += ["--aggregation", *ns.aggregation]
    if ns.dimension:
        args += ["--dimension", *ns.dimension]
    if ns.filter:
        args += ["--filter", ns.filter]
    r = run_az(args)
    metrics = []
    for v in (r.data or {}).get("value") or [] if r.ok else []:
        m = {
            "name": (v.get("name") or {}).get("value"),
            "unit": v.get("unit"),
            "series": [],
            "absence": None,
        }
        for ts in v.get("timeseries") or []:
            meta = {
                (x.get("name") or {}).get("value"): x.get("value")
                for x in ts.get("metadatavalues") or []
            }
            pts = [p for p in ts.get("data") or [] if any(k in p for k in AGGS)]
            stats = {}
            for k in AGGS:
                vals = [p[k] for p in pts if p.get(k) is not None]
                if vals:
                    stats[k] = {
                        "sum": sum(vals),
                        "avg": sum(vals) / len(vals),
                        "max": max(vals),
                        "min": min(vals),
                        "last": vals[-1],
                    }
            m["series"].append(
                {
                    "dimensions": meta,
                    "points": len(pts),
                    "of": len(ts.get("data") or []),
                    "stats": stats,
                    "data": pts,
                }
            )
        if not v.get("timeseries"):
            m["absence"] = "empty timeseries: the dimension filter matched no series"
        elif all(s["points"] == 0 for s in m["series"]):
            m["absence"] = (
                "no point carries a value: nothing happened, or a metric this resource does not publish - read it as nothing happened only when another metric over the same window returned values"
            )
        metrics.append(m)
    out = {
        "window": [frm, to],
        "interval": ns.interval,
        "metrics": metrics,
        "failed": failures([r]),
        "commands": commands([r]),
    }
    return exit_code(out), out


def render_platform(o: dict) -> str:
    out = [
        f"platform metrics, {o['window'][0]}..{o['window'][1]}, interval {o['interval']}"
    ]
    for m in o["metrics"]:
        out.append(
            f"== {m['name']} ({m['unit']})"
            + (f"  ABSENT - {m['absence']}" if m["absence"] else "")
        )
        for s in m["series"]:
            d = (
                " ".join(f"{k}={v}" for k, v in s["dimensions"].items())
                or "(no dimension)"
            )
            st = "  ".join(
                f"{k}: sum={v['sum']:g} avg={v['avg']:.4g} max={v['max']:g} last={v['last']:g}"
                for k, v in s["stats"].items()
            )
            out.append(f"  {d}: {s['points']} of {s['of']} points carry a value  {st}")
            for p in s["data"][-o.get("show", 6) :]:
                out.append(
                    "      "
                    + p.get("timeStamp", "")
                    + "  "
                    + " ".join(f"{k}={p[k]:g}" for k in AGGS if p.get(k) is not None)
                )
    if not o["metrics"] and not o["failed"]:
        out.append("  (no metric in the answer)")
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_definitions(ns) -> tuple[int, dict]:
    r = run_az(["monitor", "metrics", "list-definitions", *_resource_args(ns)])
    rows = [
        {
            "name": (d.get("name") or {}).get("value"),
            "unit": d.get("unit"),
            "primary": d.get("primaryAggregationType"),
            "supported": ", ".join(d.get("supportedAggregationTypes") or []),
            "dimensions": ", ".join(
                (x.get("value") or "") for x in d.get("dimensions") or []
            ),
        }
        for d in (r.data or [])
        if r.ok
    ]
    out = {"definitions": rows, "failed": failures([r]), "commands": commands([r])}
    return exit_code(out), out


def render_definitions(o: dict) -> str:
    out = [
        f"{len(o['definitions'])} metric definitions (the --metric, --aggregation and --dimension values `platform` takes):"
    ]
    out += table(
        o["definitions"], ["name", "unit", "primary", "supported", "dimensions"]
    )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_resources(ns) -> tuple[int, dict]:
    args = ["resource", "list", "--resource-group", ns.resource_group]
    if ns.resource_type:
        args += ["--resource-type", ns.resource_type]
    if ns.subscription:
        args += ["--subscription", ns.subscription]
    r = run_az(args)
    rows = [
        {
            "name": x.get("name"),
            "type": x.get("type"),
            "location": x.get("location"),
            "id": x.get("id"),
        }
        for x in (r.data or [])
        if r.ok
    ]
    out = {"resources": rows, "failed": failures([r]), "commands": commands([r])}
    return exit_code(out), out


def render_resources(o: dict) -> str:
    out = [
        f"{len(o['resources'])} resources (the id is what `platform --resource` takes):"
    ]
    for x in o["resources"]:
        out.append(f"  {x['name']}  {x['type']}  {x['location']}\n      {x['id']}")
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list")
    a.add_argument("--app", required=True)
    a.add_argument("--service", action="append")
    add_window(a)
    b = sub.add_parser("query")
    b.add_argument("name")
    b.add_argument("--app", required=True)
    b.add_argument("--service", action="append")
    b.add_argument("--by", action="append")
    b.add_argument("--bin")
    b.add_argument(
        "--as",
        dest="kind",
        choices=["auto", "delta", "cumulative", "gauge", "histogram"],
        default="auto",
    )
    add_window(b)
    c = sub.add_parser("platform")
    c.add_argument("--metric", action="extend", nargs="+", required=True)
    c.add_argument("--aggregation", action="extend", nargs="+")
    c.add_argument("--interval", default="PT1M")
    c.add_argument("--dimension", action="extend", nargs="+")
    c.add_argument("--filter")
    c.add_argument("--show", type=int, default=6)
    add_window(c)
    d = sub.add_parser("definitions")
    d.add_argument("--json", action="store_true")
    for p in (c, d):
        p.add_argument("--resource", required=True)
        p.add_argument("--resource-group")
        p.add_argument("--resource-type")
        p.add_argument("--subscription")
    e = sub.add_parser("resources")
    e.add_argument("--resource-group", required=True)
    e.add_argument("--resource-type", default="Microsoft.App/containerApps")
    e.add_argument("--subscription")
    e.add_argument("--json", action="store_true")
    ns = ap.parse_args()
    fn = {
        "list": (cmd_list, render_list),
        "query": (cmd_query, render_query),
        "platform": (cmd_platform, render_platform),
        "definitions": (cmd_definitions, render_definitions),
        "resources": (cmd_resources, render_resources),
    }[ns.cmd]
    code, o = fn[0](ns)
    if ns.cmd == "platform":
        o["show"] = ns.show
    emit(o, ns.json, fn[1])
    return code


if __name__ == "__main__":
    sys.exit(main())
