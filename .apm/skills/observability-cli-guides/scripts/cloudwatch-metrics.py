#!/usr/bin/env python3
"""Metrics, EMF-aware: the namespace's series, the temporality probe per series, the window's counts, and the extracted datapoints.

    cloudwatch-metrics.py list --profile <profile> --region <region> --namespace <namespace>
    cloudwatch-metrics.py probe http.server.request.duration --profile <profile> --region <region> --metrics-log-group <metrics_log_group> --namespace <namespace> --since 30m
    cloudwatch-metrics.py window http.server.request.duration --profile <profile> --region <region> --metrics-log-group <metrics_log_group> --namespace <namespace> --since 30m
    cloudwatch-metrics.py window orders.created --profile <profile> --region <region> --metrics-log-group <metrics_log_group> --by product.id --by OTelLib --since 30m
    cloudwatch-metrics.py series http.server.request.duration --profile <profile> --region <region> --namespace <namespace> --dimension http.request.method=GET --dimension http.route=/orders/{order_id} --dimension http.response.status_code=200 --dimension OTelLib=opentelemetry.instrumentation.fastapi --dimension url.scheme=http --dimension network.protocol.version=1.1 --since 30m

Whole surface - list: --profile, --region, --namespace (required), --metric
(repeatable, narrows to those names), --json. probe <metric> and window
<metric>: --profile, --region, --metrics-log-group (required: the raw EMF
records are read, never the extracted roll-up), --by (repeatable: the
dimension fields the series is grouped by) or --namespace (the full
dimension set is then read off list-metrics: every dimension name the
metric declares - a grouping coarser than the full set folds distinct
series together and yields garbage, routinely negative, deltas), a window,
--json; window adds --as auto|cumulative|delta|gauge (default auto: the
probe decides per series, a gauge is never detected and must be told) and
--top (rows printed, default 40). series <metric>: --profile, --region,
--namespace (required), --dimension Name=Value (repeatable: the whole
dimension set of one CloudWatch series, a {param} in a route value is fine
- the queries go through a JSON file), --stat (repeatable, default
SampleCount, Sum, Average, Minimum, Maximum), --period (seconds, multiple
of 60, default 60), --show (points printed per stat, the newest, default
10), a window, --json. Exit 0, 1 when a query failed (the failure is in the
output), 2 when the dimension set could not be settled.

An EMF histogram lands as a statistic set (Min/Max/Sum/Count under the
metric's name, fields `<metric>.Count` and `<metric>.Sum`), a counter or a
gauge as a scalar under the metric's name; probe reads which. The probe is
one stats pass per series (the full dimension set): min, max, earliest,
latest, sum, count - cumulative when min == earliest and max == latest
(every push carries the total since process start: the window's count is
latest - earliest, the edge diff), delta otherwise (each push one export's
increment: the window's count is sum()); a cumulative series whose max -
min differs from latest - earliest decreased inside the window - a process
restart reset it - and is flagged. The ispresent() guard on the resource
fields runs first: an edge diff is qualified by resource.service.instance.id
when the records carry it, and the output says when they do not (grouping
by an absent field errors nowhere - every record lands in one null group).
series reads the extracted metric through get-metric-data: on a cumulative
pipeline its SampleCount/Sum per period are snapshots, not per-period
counts (say so, never quote them as a rate); a percentile stat comes back
empty on a statistic set (percentiles come from the traces); and a gauge's
Max/Sum per period is unexplained on this exporter - never a run's
concurrency peak.
"""

from __future__ import annotations

import argparse
import collections
import itertools
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloudwatch_aws import (
    add_targeting,
    add_window,
    commands,
    cw_field,
    emit,
    exit_code,
    failures,
    fmt,
    insights_many,
    insights_query,
    iso,
    metric_data_file,
    parse_xray_ts,
    register_targets,
    render_commands,
    render_failures,
    resolve_window,
    run_aws,
    run_many,
    table,
    usage,
)

DEFAULT_STATS = ["SampleCount", "Sum", "Average", "Minimum", "Maximum"]


# --- list --------------------------------------------------------------------


def cmd_list(ns) -> dict:
    out: dict = {"namespace": ns.namespace, "metrics": [], "commands": [], "failed": []}
    calls = [["cloudwatch", "list-metrics", "--namespace", ns.namespace]]
    if ns.metric:
        calls = [[*calls[0], "--metric-name", m] for m in ns.metric]
    rs = run_many(calls, ns.profile, ns.region)
    per = collections.defaultdict(lambda: collections.Counter())
    for r in rs:
        if not r.ok:
            continue
        for mtr in (r.data or {}).get("Metrics", []):
            per[mtr.get("MetricName")][
                tuple(sorted(x.get("Name") for x in mtr.get("Dimensions", [])))
            ] += 1
    for name in sorted(per):
        sets = per[name]
        out["metrics"].append(
            {
                "metric": name,
                "series": sum(sets.values()),
                "full_dimension_set": list(max(sets, key=len)),
                "dimension_sets": [
                    {"dimensions": list(k), "series": v}
                    for k, v in sorted(sets.items(), key=lambda kv: -len(kv[0]))
                ],
            }
        )
    out["commands"] = commands(rs)
    out["failed"] = failures(rs)
    return out


def render_list(o: dict) -> str:
    out = [
        f"namespace {o['namespace']}: {len(o['metrics'])} metric names (one CloudWatch series per dimension-set variant)"
    ]
    for m in o["metrics"]:
        out.append(
            f"  {m['metric']}  {m['series']} series; full dimension set: {', '.join(m['full_dimension_set']) or '(none)'}"
        )
        for s in m["dimension_sets"]:
            out.append(f"      {s['series']:>3} x [{', '.join(s['dimensions'])}]")
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


# --- probe and window --------------------------------------------------------


def dimension_set(ns, metric: str, results: list) -> list[str]:
    if ns.by:
        return list(dict.fromkeys(ns.by))
    r = run_aws(
        [
            "cloudwatch",
            "list-metrics",
            "--namespace",
            ns.namespace,
            "--metric-name",
            metric,
        ],
        ns.profile,
        ns.region,
    )
    results.append(r)
    if not r.ok:
        return []
    names: set[str] = set()
    for mtr in (r.data or {}).get("Metrics", []):
        names.update(x.get("Name") for x in mtr.get("Dimensions", []))
    if not names:
        usage(
            f"list-metrics knows no series of {metric} in namespace {ns.namespace}: give --by explicitly, or check the name"
        )
    return sorted(names)


def shape_of(ns, metric: str, frm, to, results: list) -> tuple[str, dict]:
    """statset when `<metric>.Count` is present on the records, scalar when `<metric>` is."""
    q = f"stats sum(ispresent({cw_field(metric + '.Count')})) as statset, sum(ispresent({cw_field(metric)})) as scalar, sum(ispresent(`resource.service.name`)) as with_service, sum(ispresent(`resource.service.instance.id`)) as with_instance, count() as n"
    r = insights_query([ns.metrics_log_group], q, frm, to, ns.profile, ns.region)
    results.append(r)
    row = (r.data or [{}])[0] if r.ok else {}
    facts = {
        "records_in_group": row.get("n", 0),
        "statset_records": row.get("statset", 0),
        "scalar_records": row.get("scalar", 0),
        "with_instance_id": row.get("with_instance", 0),
        "with_service_name": row.get("with_service", 0),
    }
    if row.get("statset", 0):
        return "statset", facts
    if row.get("scalar", 0):
        return "scalar", facts
    return "absent", facts


def classify_values(vals: list[float]) -> tuple[str, bool, float | None]:
    """(temporality, reset_suspected, edge_diff) off a series' pushes in time order.

    Monotonic non-decreasing: cumulative when the level at the window's start is
    at least the window's increment, else ambiguous; unchanged: flat. A drop to
    near zero followed by a rise is a cumulative counter reset by a process
    restart: cumulative, reset_suspected, and the edge diff is the per-epoch
    deltas summed across the restart (the value after the drop counts from
    zero). Any other decrease is a delta series.
    """
    if len(vals) < 2:
        return "undetermined", False, None
    first, last = vals[0], vals[-1]
    increases = decreases = 0
    summed = 0.0
    running_max = first
    restart_shaped = True
    for a, b in itertools.pairwise(vals):
        if b > a + 1e-4:
            increases += 1
            summed += b - a
        elif b < a - 1e-4:
            decreases += 1
            if b > 0.1 * running_max:
                restart_shaped = False  # a bounce, not a counter back to zero
            summed += b
        running_max = max(running_max, b)
    if decreases == 0:
        if increases == 0:
            return "flat", False, 0.0
        if first >= last - first:
            return "cumulative", False, last - first
        return "ambiguous", False, last - first
    if restart_shaped and decreases <= 2 and increases >= decreases:
        return "cumulative", True, summed
    return "delta", False, None


def probe_series(ns, metric: str, frm, to, results: list) -> dict:
    if not ns.by and not ns.namespace:
        usage(
            "give --by <dimension> (repeatable) or --namespace <namespace> so the full dimension set can be read off list-metrics"
        )
    shape, facts = shape_of(ns, metric, frm, to, results)
    out = {
        "metric": metric,
        "shape": shape,
        "records": facts,
        "dimensions": [],
        "series": [],
    }
    if shape == "absent":
        out["note"] = (
            f"no record in the window carries {metric} (neither as a statistic set nor as a scalar)"
        )
        return out
    dims = dimension_set(ns, metric, results)
    out["dimensions"] = dims
    if not dims:
        return out
    fields = [metric + ".Count", metric + ".Sum"] if shape == "statset" else [metric]
    by = ", ".join(cw_field(d) for d in dims)
    if facts.get("with_instance_id"):
        by += ", `resource.service.instance.id`"
        out["qualified_by_instance"] = True
    else:
        out["qualified_by_instance"] = False
    group_fields = list(dims) + (
        ["resource.service.instance.id"] if out["qualified_by_instance"] else []
    )
    specs = []
    for f in fields:
        c = cw_field(f)
        specs.append(
            (
                [ns.metrics_log_group],
                f"filter ispresent({c}) | stats min({c}) as mn, max({c}) as mx, earliest({c}) as first, latest({c}) as last, sum({c}) as total, count() as n by {by}",
            )
        )
        specs.append(
            (
                [ns.metrics_log_group],
                f"filter ispresent({c}) | fields @timestamp, {c} as v, {by} | sort @timestamp asc | limit 10000",
            )
        )
    rs = insights_many(specs, frm, to, ns.profile, ns.region)
    results.extend(rs)
    count_kind: dict = {}  # a statistic set's temporality is its .Count's, applied to .Sum
    for i, f in enumerate(fields):
        r, rv = rs[2 * i], rs[2 * i + 1]
        if not r.ok:
            continue
        pushes: dict = {}
        capped = (
            rv.ok and len(rv.data or []) >= 10000
        )  # the listing hit its cap: the tail is unseen
        if rv.ok and not capped:
            for row in rv.data or []:
                key = _dimkey({d: row.get(d) for d in group_fields})
                pushes.setdefault(key, []).append(float(row.get("v") or 0))
        for row in r.data or []:
            key = {d: row.get(d) for d in group_fields}
            kind, reset, edge = classify_values(pushes.get(_dimkey(key), []))
            if not rv.ok or capped:
                kind, reset, edge = "undetermined", False, None
            if shape == "statset":
                if f.endswith(".Count"):
                    count_kind[_dimkey(key)] = kind
                else:
                    kind = count_kind.get(_dimkey(key), kind)
                    if kind == "cumulative" and edge is None:
                        edge = row.get("last", 0) - row.get("first", 0)
            out["series"].append(
                {
                    "field": f,
                    "dimensions": key,
                    "pushes": row.get("n", 0),
                    "min": row.get("mn"),
                    "max": row.get("mx"),
                    "earliest": row.get("first"),
                    "latest": row.get("last"),
                    "sum": row.get("total"),
                    "temporality": kind,
                    "reset_suspected": reset,
                    "edge_diff": edge if kind == "cumulative" else None,
                }
            )
    return out


def _dimkey(d: dict) -> str:
    return ", ".join(f"{k}={v if v is not None else '-'}" for k, v in d.items())


def cmd_probe(ns) -> dict:
    frm, to = resolve_window(ns)
    results: list = []
    o = probe_series(ns, ns.metric, frm, to, results)
    o["window"] = [iso(frm), iso(to)]
    o["commands"] = commands(results)
    o["failed"] = failures(results)
    return o


def render_probe(o: dict) -> str:
    out = [
        f"{o['metric']} in {o['window'][0]} .. {o['window'][1]}: shape {o['shape']} ({o['records']['statset_records']} statistic-set records, {o['records']['scalar_records']} scalar records of {o['records']['records_in_group']} in the group)"
    ]
    if o.get("note"):
        out.append("  " + o["note"])
    if o["dimensions"]:
        out.append(
            f"  full dimension set: {', '.join(o['dimensions'])}"
            + (
                "; qualified by resource.service.instance.id"
                if o.get("qualified_by_instance")
                else "; the records carry no resource.service.instance.id - a restart shows as reset_suspected only"
            )
        )
    rows = [
        {
            **s,
            "dimensions": _dimkey(s["dimensions"]),
            "reset": "RESET?" if s["reset_suspected"] else "",
        }
        for s in o["series"]
    ]
    out += table(
        rows,
        [
            "field",
            "dimensions",
            "pushes",
            "min",
            "earliest",
            "latest",
            "max",
            "sum",
            "temporality",
            "edge_diff",
            "reset",
        ],
    )
    out.append(
        "  read off the pushes in time order - cumulative: never decreasing and the level at the start >= the window's increment, the window's count is the edge diff (latest - earliest); cumulative RESET?: one drop to near zero then rising (a process restart), the edge diff is the per-epoch deltas summed across it; delta: decreases that are not a reset, the window's count is sum; ambiguous: monotonic but too low a level (both readings); flat: unchanged; a gauge is never detected - tell window --as gauge"
    )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_window(ns) -> dict:
    frm, to = resolve_window(ns)
    results: list = []
    p = probe_series(ns, ns.metric, frm, to, results)
    o: dict = {
        "metric": ns.metric,
        "window": [iso(frm), iso(to)],
        "shape": p["shape"],
        "dimensions": p["dimensions"],
        "qualified_by_instance": p.get("qualified_by_instance"),
        "as": ns.as_,
        "rows": [],
        "notes": [],
    }
    if p.get("note"):
        o["notes"].append(p["note"])
    per: dict = collections.OrderedDict()
    for s in p["series"]:
        key = _dimkey(s["dimensions"])
        row = per.setdefault(key, {"dimensions": key, "pushes": s["pushes"]})
        kind = ns.as_ if ns.as_ != "auto" else s["temporality"]
        if kind == "gauge":
            value = {
                "min": s["min"],
                "max": s["max"],
                "mean_of_pushes": (s["sum"] / s["pushes"]) if s["pushes"] else None,
            }
        elif kind == "cumulative":
            value = (
                s["edge_diff"]
                if s["edge_diff"] is not None
                else (s["latest"] - s["earliest"])
            )
        elif kind == "delta":
            value = s["sum"]
        elif kind == "flat":
            value = (
                0
                if not s["latest"]
                else {"level": s["latest"], "edge_diff": 0, "sum": s["sum"]}
            )
        elif kind == "ambiguous":
            value = {"edge_diff": s["latest"] - s["earliest"], "sum": s["sum"]}
        else:
            value = None
        label = (
            "count"
            if s["field"].endswith(".Count")
            else ("sum" if s["field"].endswith(".Sum") else "value")
        )
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        row[label] = value
        row["temporality"] = kind
        if s["reset_suspected"]:
            row["reset_suspected"] = True
    for row in per.values():
        if (
            isinstance(row.get("count"), (int, float))
            and isinstance(row.get("sum"), (int, float))
            and row["count"]
        ):
            row["mean"] = row["sum"] / row["count"]
    o["rows"] = sorted(
        per.values(),
        key=lambda r: (
            -(
                r.get("count")
                if isinstance(r.get("count"), (int, float))
                else (r.get("value") if isinstance(r.get("value"), (int, float)) else 0)
            )
        ),
    )[: ns.top]
    if ns.as_ == "gauge" or any(r.get("temporality") == "gauge" for r in o["rows"]):
        o["notes"].append(
            "gauge: the per-push min/max/mean of the exporter's samples - what the exporter samples and what CloudWatch's Max then aggregates was not ruled: unexplained, never the run's concurrency peak"
        )
    if any(r.get("temporality") == "ambiguous" for r in o["rows"]):
        o["notes"].append(
            "ambiguous: monotonic inside the window but its level at the start is below the window's increment - a cumulative series of a process started inside the window, or a delta series that happened to rise; both readings are printed (edge_diff, sum) - widen the window or tell --as"
        )
    if any(r.get("temporality") == "flat" for r in o["rows"]):
        o["notes"].append(
            "flat: every push carried the same value - 0 as a count when the value is 0, else a level (a cumulative counter nothing incremented, or a gauge)"
        )
    if any(r.get("reset_suspected") for r in o["rows"]):
        o["notes"].append(
            "reset_suspected: the series dropped to near zero inside the window (a process restart resets a cumulative counter) - the count is the per-epoch deltas summed across the restart, the value after the drop counting from zero"
        )
    if p["shape"] == "statset":
        o["notes"].append(
            "a statistic set: count is the requests, sum the seconds (mean = sum / count); percentiles are not computable from it - read them off the traces"
        )
    o["commands"] = commands(results)
    o["failed"] = failures(results)
    return o


def render_window(o: dict) -> str:
    out = [
        f"{o['metric']} over {o['window'][0]} .. {o['window'][1]} (shape {o['shape']}, grouped by {', '.join(o['dimensions']) or '-'}{', resource.service.instance.id' if o.get('qualified_by_instance') else ''}):"
    ]
    cols = ["dimensions", "temporality", "pushes"]
    if any("count" in r for r in o["rows"]):
        cols += ["count", "sum", "mean"]
    else:
        cols += ["value"]
    rows = []
    for r in o["rows"]:
        rr = dict(r)
        for col in ("value", "count", "sum"):
            v = rr.get(col)
            if isinstance(v, dict):
                if "mean_of_pushes" in v:
                    rr[col] = (
                        f"min {v['min']} max {v['max']} mean {v['mean_of_pushes']:.2f}"
                        if v["mean_of_pushes"] is not None
                        else str(v)
                    )
                elif "level" in v:
                    rr[col] = f"level {fmt(v['level'])} (edge 0, sum {fmt(v['sum'])})"
                else:
                    rr[col] = f"edge {fmt(v['edge_diff'])} | sum {fmt(v['sum'])}"
        if rr.get("reset_suspected"):
            rr["temporality"] += " RESET?"
        rows.append(rr)
    out += table(rows, cols)
    out += ["  " + n for n in o["notes"]]
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


# --- series (get-metric-data) -----------------------------------------------


def cmd_series(ns) -> dict:
    frm, to = resolve_window(ns)
    dims = []
    for d in ns.dimension or []:
        if "=" not in d:
            usage(f"--dimension takes Name=Value, got {d!r}")
        k, v = d.split("=", 1)
        dims.append({"Name": k, "Value": v})
    stats = ns.stat or DEFAULT_STATS
    if ns.period % 60:
        usage("--period is a multiple of 60 seconds")
    queries = []
    for i, st in enumerate(stats):
        qid = "q" + re.sub(r"[^a-z0-9]", "", st.lower()) + str(i)
        queries.append(
            {
                "Id": qid,
                "MetricStat": {
                    "Metric": {
                        "Namespace": ns.namespace,
                        "MetricName": ns.metric,
                        "Dimensions": dims,
                    },
                    "Period": ns.period,
                    "Stat": st,
                },
                "ReturnData": True,
            }
        )
    f = metric_data_file(queries)
    r = run_aws(
        [
            "cloudwatch",
            "get-metric-data",
            "--metric-data-queries",
            f,
            "--start-time",
            iso(frm),
            "--end-time",
            iso(to),
            "--scan-by",
            "TimestampAscending",
        ],
        ns.profile,
        ns.region,
    )
    try:
        os.unlink(f[len("file://") :])
    except OSError:
        pass
    o: dict = {
        "metric": ns.metric,
        "namespace": ns.namespace,
        "dimensions": dims,
        "period": ns.period,
        "window": [iso(frm), iso(to)],
        "metric_data_queries": queries,
        "stats": [],
        "notes": [],
        "commands": commands([r]),
        "failed": failures([r]),
    }
    by_id = {q["Id"]: q["MetricStat"]["Stat"] for q in queries}
    if r.ok:
        for res in (r.data or {}).get("MetricDataResults", []):
            st = by_id.get(res.get("Id"), res.get("Id"))
            pts = [
                (iso(parse_xray_ts(t)) if parse_xray_ts(t) else t, v)
                for t, v in zip(res.get("Timestamps", []), res.get("Values", []))
            ]
            entry = {
                "stat": st,
                "id": res.get("Id"),
                "status": res.get("StatusCode"),
                "datapoints": len(pts),
                "points": pts[-ns.show :],
            }
            if not pts:
                entry["note"] = (
                    "no datapoint: not extracted yet, no series of exactly these dimensions, or a percentile on a statistic set (empty by design)"
                )
            o["stats"].append(entry)
        msgs = (r.data or {}).get("Messages") or []
        if msgs:
            o["messages"] = msgs
    o["notes"] = [
        "on a cumulative pipeline SampleCount/Sum per period are snapshots of the total since process start, not per-period counts: the window's count is cloudwatch-metrics.py window (the edge diff on the raw records)",
        "a gauge's Maximum/Sum per period is unexplained on this exporter - never a run's concurrency peak",
    ]
    return o


def render_series(o: dict) -> str:
    out = [
        f"{o['namespace']} {o['metric']} [{_dimkey({d['Name']: d['Value'] for d in o['dimensions']})}] period {o['period']}s over {o['window'][0]} .. {o['window'][1]}"
    ]
    for s in o["stats"]:
        out.append(
            f"  {s['stat']}: {s['status']}, {s['datapoints']} datapoints"
            + (f" - {s['note']}" if s.get("note") else "")
        )
        for t, v in s["points"]:
            out.append(f"      {t}  {v}")
    if o.get("messages"):
        out.append(
            "  messages: " + "; ".join(m.get("Value", "") for m in o["messages"])
        )
    out += ["  " + n for n in o["notes"]]
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list")
    add_targeting(a)
    a.add_argument("--namespace", required=True)
    a.add_argument("--metric", action="append")
    a.add_argument("--json", action="store_true")
    for name in ("probe", "window"):
        p = sub.add_parser(name)
        p.add_argument("metric")
        add_targeting(p, metrics_log_group=True)
        p.add_argument("--by", action="append")
        p.add_argument("--namespace")
        if name == "window":
            p.add_argument(
                "--as",
                dest="as_",
                choices=["auto", "cumulative", "delta", "gauge"],
                default="auto",
            )
            p.add_argument("--top", type=int, default=40)
        add_window(p)
    s = sub.add_parser("series")
    s.add_argument("metric")
    add_targeting(s)
    s.add_argument("--namespace", required=True)
    s.add_argument("--dimension", action="append")
    s.add_argument("--stat", action="append")
    s.add_argument("--period", type=int, default=60)
    s.add_argument("--show", type=int, default=10)
    add_window(s)
    ns = ap.parse_args()
    register_targets(
        metrics_log_group=getattr(ns, "metrics_log_group", None),
        namespace=getattr(ns, "namespace", None),
    )
    if ns.cmd == "list":
        o = cmd_list(ns)
        emit(o, ns.json, render_list)
    elif ns.cmd == "probe":
        o = cmd_probe(ns)
        emit(o, ns.json, render_probe)
    elif ns.cmd == "window":
        o = cmd_window(ns)
        emit(o, ns.json, render_window)
    else:
        o = cmd_series(ns)
        emit(o, ns.json, render_series)
    return exit_code(o)


if __name__ == "__main__":
    sys.exit(main())
