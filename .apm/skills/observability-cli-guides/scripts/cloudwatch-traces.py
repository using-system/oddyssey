#!/usr/bin/env python3
"""Distributed tracing off X-Ray: the window's summaries split by identity, full traces, the service graph.

    cloudwatch-traces.py operations --profile <profile> --region <region> --service orders-api --since 30m
    cloudwatch-traces.py operations --profile <profile> --region <region> --user-agent odd-observe/<slug> --slow 3 --failed 3 --from ... --to ...
    cloudwatch-traces.py trace <trace_id> [<trace_id> ...] --profile <profile> --region <region>
    cloudwatch-traces.py graph --profile <profile> --region <region> --service orders-api --since 30m

Whole surface - every subcommand takes --profile, --region, --json;
operations and graph take a window (--from/--to or --since) that stays
under 24 h. operations: --service (repeatable, an X-Ray service name: the
summaries whose ServiceIds carry it), --user-agent (the run's identity as
read on Http.UserAgent, the -warmup suffix folded in and split out), --top
(operations printed, default 20), --slow N (the slowest traces listed as
exemplars, default 3), --failed N (the newest traces with an error or a
fault, default 3). trace: the trace ids (any number: batch-get-traces takes
five per call, the calls run concurrently), --xray-group is not a filter
here. graph: --service (repeatable: the nodes of that name and the edges
touching them), --xray-group (an X-Ray group name; omitted, the default
group). Exit 0, 1 when a call failed (the failure is in the output).

operations is one unfiltered get-trace-summaries call over the window
(one summary per trace: the volume is the traffic's), split client-side by
Http.UserAgent - the population is len(TraceSummaries), never the per-page
TracesProcessedCount. Http.UserAgent reads whoever rooted the trace: null
on every summary when an instrumented client (a load generator tracing
itself) roots them, the run's User-Agent when the server's own segment
does; the run's t0 is min(StartTime) over its identity without the -warmup
suffix. The operation is the method and the URL's path with numeric or
UUID-like segments folded to {id} (a client-side stand-in: http.route is
not indexed on a summary - it is on the server segment's metadata, see
trace). The percentiles are computed client-side over Duration - the root
segment's span: the client's view of the request when the client is
instrumented, never shorter than the server's; the server-side
distribution is graph's per-node histogram - and over ResponseTime. A
summary with IsPartial or no Http block is counted apart, never as an
operation. trace renders each segment document as a tree (the segments
linked by parent_id, the subsegments nested): name, kind, milliseconds,
method, URL, status, error/fault/throttle, and the flat dotted
metadata.default keys that matter (http.route, error.type, peer.service,
otel.resource.service.name) plus the cause's exceptions. graph reads
get-service-graph: per node the counts, the error/fault/throttle rates,
the mean response time and the percentiles off its ResponseTimeHistogram
(the server's view, every operation folded); per edge the same off the
edge's histogram (the client's view of that hop).
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloudwatch_aws import (
    add_targeting,
    add_window,
    chunks,
    commands,
    emit,
    epoch_s,
    exit_code,
    failures,
    histogram_percentiles,
    iso,
    normalize_path,
    parse_xray_ts,
    percentiles,
    register_targets,
    render_commands,
    render_failures,
    resolve_window,
    run_aws,
    run_many,
    table,
    xray_range,
)

WARMUP = "-warmup"


# --- operations --------------------------------------------------------------


def _identity(ua: str | None) -> tuple[str, bool]:
    if ua is None:
        return "(null: an instrumented client roots the traces)", False
    if ua.endswith(WARMUP):
        return ua[: -len(WARMUP)], True
    return ua, False


def cmd_operations(ns) -> dict:
    frm, to = resolve_window(ns)
    xray_range(frm, to)
    r = run_aws(
        [
            "xray",
            "get-trace-summaries",
            "--start-time",
            str(epoch_s(frm)),
            "--end-time",
            str(epoch_s(to)),
        ],
        ns.profile,
        ns.region,
    )
    o: dict = {
        "window": [iso(frm), iso(to)],
        "services": ns.service or [],
        "user_agent": ns.user_agent,
        "traces": 0,
        "identities": [],
        "operations": [],
        "statuses": {},
        "partial": 0,
        "exemplars": {"slowest": [], "failed": []},
        "notes": [],
        "commands": commands([r]),
        "failed": failures([r]),
    }
    if not r.ok:
        return o
    summaries = (r.data or {}).get("TraceSummaries", [])
    o["traces"] = len(summaries)
    o["traces_processed_count_per_page"] = (r.data or {}).get("TracesProcessedCount")
    o["seconds"] = round(r.seconds, 1)
    if ns.service:
        summaries = [
            s
            for s in summaries
            if {x.get("Name") for x in s.get("ServiceIds", [])} & set(ns.service)
        ]
    o["traces_of_services"] = len(summaries)
    ids: dict = collections.OrderedDict()
    for s in summaries:
        base, warm = _identity((s.get("Http") or {}).get("UserAgent"))
        d = ids.setdefault(
            base,
            {
                "identity": base,
                "traces": 0,
                "warmup_traces": 0,
                "t0": None,
                "last": None,
            },
        )
        if warm:
            d["warmup_traces"] += 1
            continue
        d["traces"] += 1
        ts = parse_xray_ts(s.get("StartTime"))
        if ts and (d["t0"] is None or ts < d["t0"]):
            d["t0"] = ts
        if ts and (d["last"] is None or ts > d["last"]):
            d["last"] = ts
    o["identities"] = [
        {
            **d,
            "t0": iso(d["t0"]) if d["t0"] else None,
            "last": iso(d["last"]) if d["last"] else None,
        }
        for d in ids.values()
    ]
    if ns.user_agent:
        summaries = [
            s
            for s in summaries
            if _identity((s.get("Http") or {}).get("UserAgent"))[0] == ns.user_agent
        ]
        o["traces_of_identity"] = len(summaries)
        o["warmup_excluded"] = sum(
            1 for s in summaries if _identity((s.get("Http") or {}).get("UserAgent"))[1]
        )
        summaries = [
            s
            for s in summaries
            if not _identity((s.get("Http") or {}).get("UserAgent"))[1]
        ]
    ops: dict = collections.OrderedDict()
    statuses: collections.Counter = collections.Counter()
    partial = 0
    for s in summaries:
        http = s.get("Http") or {}
        if s.get("IsPartial") or not http.get("HttpMethod"):
            partial += 1
            continue
        key = f"{http.get('HttpMethod')} {normalize_path(http.get('HttpURL'))}"
        d = ops.setdefault(
            key,
            {
                "operation": key,
                "n": 0,
                "errors": 0,
                "faults": 0,
                "throttles": 0,
                "durations": [],
                "response_times": [],
                "statuses": collections.Counter(),
            },
        )
        d["n"] += 1
        d["errors"] += 1 if s.get("HasError") else 0
        d["faults"] += 1 if s.get("HasFault") else 0
        d["throttles"] += 1 if s.get("HasThrottle") else 0
        if s.get("Duration") is not None:
            d["durations"].append(float(s["Duration"]))
        if s.get("ResponseTime") is not None:
            d["response_times"].append(float(s["ResponseTime"]))
        d["statuses"][http.get("HttpStatus")] += 1
        statuses[http.get("HttpStatus")] += 1
    rows = []
    for d in ops.values():
        p = percentiles(d["durations"])
        pr = percentiles(d["response_times"])
        rows.append(
            {
                "operation": d["operation"],
                "n": d["n"],
                "errors": d["errors"],
                "faults": d["faults"],
                "throttles": d["throttles"],
                "p50_s": p["p50"],
                "p95_s": p["p95"],
                "p99_s": p["p99"],
                "max_s": max(d["durations"]) if d["durations"] else None,
                "rt_p95_s": pr["p95"],
                "statuses": dict(
                    sorted(d["statuses"].items(), key=lambda kv: str(kv[0]))
                ),
            }
        )
    rows.sort(key=lambda x: -x["n"])
    o["operations"] = rows[: ns.top]
    o["statuses"] = dict(sorted(statuses.items(), key=lambda kv: str(kv[0])))
    o["partial"] = partial
    complete = [
        s
        for s in summaries
        if not s.get("IsPartial") and (s.get("Http") or {}).get("HttpMethod")
    ]
    slow = sorted(complete, key=lambda s: -(s.get("Duration") or 0))[: ns.slow]
    failed = sorted(
        [
            s
            for s in complete
            if s.get("HasError") or s.get("HasFault") or s.get("HasThrottle")
        ],
        key=lambda s: s.get("StartTime") or "",
        reverse=True,
    )[: ns.failed]

    def ex(s):
        http = s.get("Http") or {}
        return {
            "id": s.get("Id"),
            "start": iso(parse_xray_ts(s.get("StartTime")))
            if parse_xray_ts(s.get("StartTime"))
            else s.get("StartTime"),
            "operation": f"{http.get('HttpMethod')} {normalize_path(http.get('HttpURL'))}",
            "status": http.get("HttpStatus"),
            "duration_s": s.get("Duration"),
            "error": bool(s.get("HasError")),
            "fault": bool(s.get("HasFault")),
            "throttle": bool(s.get("HasThrottle")),
        }

    o["exemplars"] = {
        "slowest": [ex(s) for s in slow],
        "failed": [ex(s) for s in failed],
    }
    o["notes"] = [
        "Duration is the root segment's span - the client's view when an instrumented client roots the trace (never shorter than the server's); the server-side distribution is graph's per-node histogram",
        "the operation's path is normalized client-side ({id} for numeric or UUID-like segments); the true http.route sits on the server segment's metadata (trace)",
        "the population is len(TraceSummaries) of one unfiltered call; TracesProcessedCount is per page",
    ]
    return o


def render_operations(o: dict) -> str:
    out = [
        f"{o['traces']} traces in {o['window'][0]} .. {o['window'][1]}"
        + (f" ({o.get('seconds')} s)" if o.get("seconds") is not None else "")
    ]
    if o["services"]:
        out.append(
            f"  of services {', '.join(o['services'])}: {o.get('traces_of_services')}"
        )
    out.append(
        "  identities (Http.UserAgent, the -warmup suffix split out; t0 = first non-warmup trace):"
    )
    out += table(
        o["identities"],
        ["identity", "traces", "warmup_traces", "t0", "last"],
        indent="    ",
    )
    if o.get("user_agent"):
        out.append(
            f"  identity {o['user_agent']}: {o.get('traces_of_identity')} traces, {o.get('warmup_excluded')} warmup excluded from the table"
        )
    out.append(
        "  operations (method + normalized path; percentiles over Duration, rt_p95 over ResponseTime, seconds):"
    )
    rows = [
        {**r, "statuses": " ".join(f"{k}:{v}" for k, v in r["statuses"].items())}
        for r in o["operations"]
    ]
    out += table(
        rows,
        [
            "operation",
            "n",
            "errors",
            "faults",
            "throttles",
            "p50_s",
            "p95_s",
            "p99_s",
            "max_s",
            "rt_p95_s",
            "statuses",
        ],
        indent="    ",
    )
    out.append(
        "  statuses overall: "
        + " ".join(f"{k}:{v}" for k, v in o["statuses"].items())
        + (
            f"; {o['partial']} partial summaries (no root yet) counted apart"
            if o["partial"]
            else ""
        )
    )
    if o["exemplars"]["slowest"]:
        out.append("  slowest:")
        out += table(
            o["exemplars"]["slowest"],
            ["id", "start", "operation", "status", "duration_s", "error", "fault"],
            indent="    ",
        )
    if o["exemplars"]["failed"]:
        out.append("  failed (newest):")
        out += table(
            o["exemplars"]["failed"],
            [
                "id",
                "start",
                "operation",
                "status",
                "duration_s",
                "error",
                "fault",
                "throttle",
            ],
            indent="    ",
        )
    out += ["  " + n for n in o["notes"]]
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


# --- trace -------------------------------------------------------------------

META_KEYS = [
    "http.route",
    "error.type",
    "peer.service",
    "otel.resource.service.name",
    "otel.resource.service.instance.id",
    "otel.resource.deployment.environment.name",
]


def _node(doc: dict, kind: str) -> dict:
    http = doc.get("http") or {}
    req, resp = http.get("request") or {}, http.get("response") or {}
    meta = (doc.get("metadata") or {}).get("default") or {}
    start, end = doc.get("start_time"), doc.get("end_time")
    n = {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "kind": kind,
        "start": iso(datetime.fromtimestamp(start, tz=timezone.utc)) if start else None,
        "ms": round((end - start) * 1000, 1) if start and end else None,
        "method": req.get("method"),
        "url": req.get("url"),
        "status": resp.get("status"),
        "error": doc.get("error"),
        "fault": doc.get("fault"),
        "throttle": doc.get("throttle"),
        "namespace": doc.get("namespace"),
        "metadata": {k: meta[k] for k in META_KEYS if k in meta},
        "metadata_keys": sorted(meta.keys()),
        "exceptions": [
            {"message": e.get("message"), "type": e.get("type")}
            for e in ((doc.get("cause") or {}).get("exceptions") or [])
        ]
        if isinstance(doc.get("cause"), dict)
        else [],
        "children": [],
    }
    for ss in doc.get("subsegments") or []:
        n["children"].append(_node(ss, "subsegment"))
    return n


def cmd_trace(ns) -> dict:
    o: dict = {"traces": [], "unprocessed": [], "commands": [], "failed": []}
    calls = [
        ["xray", "batch-get-traces", "--trace-ids", *chunk]
        for chunk in chunks(list(dict.fromkeys(ns.trace_id)))
    ]
    rs = run_many(calls, ns.profile, ns.region)
    for r in rs:
        if not r.ok:
            continue
        o["unprocessed"] += (r.data or {}).get("UnprocessedTraceIds", [])
        for t in (r.data or {}).get("Traces", []):
            docs = []
            for s in t.get("Segments", []):
                try:
                    docs.append(json.loads(s.get("Document") or "{}"))
                except ValueError:
                    continue
            nodes = {
                d.get("id"): _node(d, "inferred" if d.get("inferred") else "segment")
                for d in docs
            }
            index: dict = {}  # every node by id, subsegments included: an inferred segment's parent is a subsegment

            def walk(n, index=index):
                index[n["id"]] = n
                for c in n["children"]:
                    walk(c, index)

            for n in nodes.values():
                walk(n)
            roots = []
            for d in docs:
                n = nodes[d.get("id")]
                parent = d.get("parent_id")
                if parent and parent in index:
                    index[parent]["children"].append(n)
                elif parent:
                    n["kind"] += " (parent not in the trace)"
                    roots.append(n)
                else:
                    roots.append(n)
            o["traces"].append(
                {
                    "id": t.get("Id"),
                    "duration_s": t.get("Duration"),
                    "limit_exceeded": t.get("LimitExceeded"),
                    "segments": len(docs),
                    "tree": roots,
                }
            )
    o["commands"], o["failed"] = commands(rs), failures(rs)
    return o


def _render_node(n: dict, depth: int, out: list) -> None:
    flags = (
        "".join(
            f
            for f, on in (("E", n["error"]), ("F", n["fault"]), ("T", n["throttle"]))
            if on
        )
        or "-"
    )
    http = (
        f"{n['method']} {n['url']} -> {n['status']}"
        if n.get("method")
        else (f"namespace {n['namespace']}" if n.get("namespace") else "")
    )
    meta = " ".join(f"{k}={v}" for k, v in n["metadata"].items())
    out.append(
        f"{'    ' * depth}  {n['name']} [{n['kind']}] {n['ms']} ms {flags} {http} {meta}".rstrip()
    )
    for e in n["exceptions"]:
        out.append(
            f"{'    ' * depth}      exception: {e['message']} {('(' + e['type'] + ')') if e['type'] else ''}".rstrip()
        )
    for c in n["children"]:
        _render_node(c, depth + 1, out)


def render_trace(o: dict) -> str:
    out = []
    for t in o["traces"]:
        out.append(
            f"trace {t['id']}: {t['duration_s']} s, {t['segments']} segments"
            + (" (LIMIT EXCEEDED)" if t.get("limit_exceeded") else "")
        )
        for root in t["tree"]:
            _render_node(root, 0, out)
    if o["unprocessed"]:
        out.append("unprocessed ids: " + ", ".join(o["unprocessed"]))
    out.append(
        "  flags: E error (4xx), F fault (5xx / exception), T throttle; metadata.default keys are flat dotted strings (index the whole key)"
    )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


# --- graph -------------------------------------------------------------------


def _stats(st: dict) -> dict:
    total = st.get("TotalCount", 0) or 0
    err = (st.get("ErrorStatistics") or {}).get("TotalCount", 0) or 0
    fault = (st.get("FaultStatistics") or {}).get("TotalCount", 0) or 0
    thr = (st.get("ErrorStatistics") or {}).get("ThrottleCount", 0) or 0
    return {
        "requests": total,
        "ok": st.get("OkCount", 0),
        "errors": err,
        "faults": fault,
        "throttles": thr,
        "error_rate": round(err / total, 4) if total else None,
        "fault_rate": round(fault / total, 4) if total else None,
        "mean_s": round((st.get("TotalResponseTime") or 0) / total, 4)
        if total
        else None,
    }


def cmd_graph(ns) -> dict:
    frm, to = resolve_window(ns)
    xray_range(frm, to)
    args = [
        "xray",
        "get-service-graph",
        "--start-time",
        str(epoch_s(frm)),
        "--end-time",
        str(epoch_s(to)),
    ]
    if ns.xray_group:
        args += ["--group-name", ns.xray_group]
    r = run_aws(args, ns.profile, ns.region)
    o: dict = {
        "window": [iso(frm), iso(to)],
        "services": ns.service or [],
        "nodes": [],
        "edges": [],
        "commands": commands([r]),
        "failed": failures([r]),
    }
    if not r.ok:
        return o
    services = (r.data or {}).get("Services", [])
    names = {s.get("ReferenceId"): s.get("Name") for s in services}
    wanted = set(ns.service or [])
    for s in services:
        node = {
            "name": s.get("Name"),
            "type": s.get("Type") or "-",
            "root": bool(s.get("Root")),
            "state": s.get("State"),
            **_stats(s.get("SummaryStatistics") or {}),
            **histogram_percentiles(s.get("ResponseTimeHistogram") or []),
            "buckets": len(s.get("ResponseTimeHistogram") or []),
        }
        if not wanted or s.get("Name") in wanted:
            o["nodes"].append(node)
        for e in s.get("Edges", []):
            target = names.get(e.get("ReferenceId"), str(e.get("ReferenceId")))
            if wanted and not ({s.get("Name"), target} & wanted):
                continue
            o["edges"].append(
                {
                    "from": s.get("Name"),
                    "to": target,
                    **_stats(e.get("SummaryStatistics") or {}),
                    **histogram_percentiles(e.get("ResponseTimeHistogram") or []),
                    "buckets": len(e.get("ResponseTimeHistogram") or []),
                }
            )
    o["notes"] = [
        "a node's percentiles are read off its ResponseTimeHistogram (bucketed: the server's view, every operation folded); an edge's are the client's view of that hop",
        "a client node is the load generator's own root span (named by the method), a remote node an upstream the service calls",
    ]
    return o


def render_graph(o: dict) -> str:
    out = [
        f"service graph in {o['window'][0]} .. {o['window'][1]}"
        + (f", filtered to {', '.join(o['services'])}" if o["services"] else "")
    ]
    out.append("  nodes:")
    out += table(
        o["nodes"],
        [
            "name",
            "type",
            "state",
            "requests",
            "ok",
            "errors",
            "faults",
            "throttles",
            "error_rate",
            "fault_rate",
            "mean_s",
            "p50",
            "p95",
            "p99",
            "buckets",
        ],
        indent="    ",
    )
    out.append("  edges (from -> to):")
    out += table(
        o["edges"],
        [
            "from",
            "to",
            "requests",
            "errors",
            "faults",
            "throttles",
            "mean_s",
            "p50",
            "p95",
            "p99",
            "buckets",
        ],
        indent="    ",
    )
    out += ["  " + n for n in o.get("notes", [])]
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("operations")
    add_targeting(a)
    a.add_argument("--service", action="append")
    a.add_argument("--user-agent")
    a.add_argument("--top", type=int, default=20)
    a.add_argument("--slow", type=int, default=3)
    a.add_argument("--failed", type=int, default=3)
    add_window(a)
    t = sub.add_parser("trace")
    t.add_argument("trace_id", nargs="+")
    add_targeting(t)
    t.add_argument("--json", action="store_true")
    g = sub.add_parser("graph")
    add_targeting(g)
    g.add_argument("--service", action="append")
    g.add_argument("--xray-group")
    add_window(g)
    ns = ap.parse_args()
    register_targets(xray=getattr(ns, "xray_group", None))
    if ns.cmd == "operations":
        o = cmd_operations(ns)
        emit(o, ns.json, render_operations)
    elif ns.cmd == "trace":
        o = cmd_trace(ns)
        emit(o, ns.json, render_trace)
    else:
        o = cmd_graph(ns)
        emit(o, ns.json, render_graph)
    return exit_code(o)


if __name__ == "__main__":
    sys.exit(main())
