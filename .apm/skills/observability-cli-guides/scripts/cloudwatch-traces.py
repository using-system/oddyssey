#!/usr/bin/env python3
"""Distributed tracing off X-Ray: the window's summaries split by identity, full traces, the service graph.

    cloudwatch-traces.py operations --profile <profile> --region <region> --service orders-api --since 30m
    cloudwatch-traces.py operations --profile <profile> --region <region> --user-agent odd-observe/<slug> --slow 3 --failed 3 --from ... --to ...
    cloudwatch-traces.py trace <trace_id> [<trace_id> ...] --profile <profile> --region <region>
    cloudwatch-traces.py graph --profile <profile> --region <region> --service orders-api --since 30m
    cloudwatch-traces.py watch --profile <profile> --region <region> --user-agent odd-bench/<name> --from <dispatch instant> --state <scratch>/<slug>-watch.json --length 2m --expect 240 [--to <deadline>]

Whole surface - every subcommand takes --profile, --region, --json;
operations and graph take a window (--from/--to or --since) that stays
under 24 h; watch takes --from and an optional --to (the deadline). operations: --service (repeatable, an X-Ray service name: the
summaries whose ServiceIds carry it), --user-agent (the run's identity as
read on Http.UserAgent, the -warmup suffix folded in and split out), --top
(operations printed, default 20), --slow N (the slowest traces listed as
exemplars, default 3), --failed N (the newest traces with an error or a
fault, default 3). trace: the trace ids (any number: batch-get-traces takes
five per call, the calls run concurrently), --xray-group is not a filter
here. graph: --service (repeatable: the nodes of that name and the edges
touching them), --xray-group (an X-Ray group name; omitted, the default
group). watch: --user-agent (the run's User-Agent prefix, `http.useragent
BEGINSWITH` in the filter expression), --state (its state file; the same
invocation again resumes it), --service (repeatable: the summaries whose
ServiceIds carry the name, client-side), --length (the manifest's
scheduled length: once it has elapsed since the first trace, one empty
closed bin ends the run), --expect (its scheduled request count: reached,
the run ended at its last trace, no empty bin needed), --bin (default
30s), --ended-after (empty closed bins that end a started run with no
schedule to read, default 4), --settle (a bin closes once its end is this
old; default auto: the store's visibility lag - how far behind the
dispatch the newest of the service's traces of the 10 minutes before it
was, one probe, then how far behind each poll the run's own newest trace
of the last bin is - plus one bin, recomputed at every poll), --every (the
floor between two polls, default 5s: the watch wakes when the next bin can
close), --max (one call's bound, default 8m; 0s is one whole poll). Exit 0
(watch: ended), 1 when a call failed (the failure is in the output; a watch
leaves the range unread for the next call), watch 3 still running at --max
or --to, 4 not started there.

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
edge's histogram (the client's view of that hop). watch reads its
identity's summaries over one range per poll - the cursor to now, one
get-trace-summaries call whatever the number of bins - and splits them into
bins client-side (X-Ray's range is inclusive at both ends, at the second:
the call starts a second early and the split is exact); the traces
younger than one bin say how far behind the store is.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone

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
    parse_duration,
    parse_ts,
    parse_xray_ts,
    percentiles,
    register_targets,
    render_commands,
    render_failures,
    resolve_window,
    run_aws,
    run_many,
    table,
    usage,
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


# --- watch: a driven run's start and end, polled bin by bin ------------------

WALK_BACK_BINS = 20
PROBE_MINUTES = 10


def _summaries(ns, x: datetime, y: datetime, expr: str | None):
    """One get-trace-summaries over [x, y] - X-Ray's range is inclusive at
    both ends, at the second, so the caller splits client-side."""
    args = [
        "xray",
        "get-trace-summaries",
        "--start-time",
        str(epoch_s(x)),
        "--end-time",
        str(epoch_s(y)),
    ]
    if expr:
        args += ["--filter-expression", expr]
    return run_aws(args, ns.profile, ns.region)


def _rows(ns, data) -> list[dict]:
    """The summaries the watch reads: start, identity, id, partial - scoped to
    --service when given."""
    out = []
    for s in (data or {}).get("TraceSummaries", []):
        if ns.service and not (
            {x.get("Name") for x in s.get("ServiceIds", [])} & set(ns.service)
        ):
            continue
        start = parse_xray_ts(s.get("StartTime"))
        if start is None:
            continue
        out.append(
            {
                "start": start.replace(microsecond=0),
                "identity": (s.get("Http") or {}).get("UserAgent"),
                "id": s.get("Id"),
                "partial": bool(s.get("IsPartial")),
            }
        )
    return sorted(out, key=lambda r: r["start"])


def _bin_of(rows: list[dict], x: datetime, y: datetime) -> dict:
    inside = [r for r in rows if x <= r["start"] < y]
    return {
        "n": len(inside),
        "first": iso(inside[0]["start"]) if inside else None,
        "last": iso(inside[-1]["start"]) if inside else None,
        "identities": sorted({r["identity"] for r in inside if r["identity"]}),
    }


def _clock() -> datetime:
    """The watch's clock at the second; ODD_WATCH_CLOCK pins it (the tests)."""
    pinned = os.environ.get("ODD_WATCH_CLOCK")
    if pinned:
        return parse_ts(pinned)
    return datetime.now(timezone.utc).replace(microsecond=0)


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


def _settle_seconds(ns, state: dict, step: timedelta) -> int:
    """The settle in force: the flag's duration, or the largest visibility
    lag observed so far plus one bin (one bin alone before any trace)."""
    if ns.settle != "auto":
        return parse_duration(ns.settle)
    return math.ceil(state.get("lag_max_s") or 0.0) + int(step.total_seconds())


def _walk_back(ns, expr: str, first_bin_start: datetime, step: timedelta):
    """The bins before the first polled one, back to an empty bin (or
    WALK_BACK_BINS): one call, split client-side, earliest first; the failed
    result third when aws failed - the walk then counts for nothing, and the
    next call does it again whole."""
    lo = first_bin_start - step * WALK_BACK_BINS
    r = _summaries(ns, lo, first_bin_start, expr)
    if not r.ok:
        return None, [r], r
    rows = _rows(ns, r.data)
    bins: list[dict] = []
    earliest = None
    identities: list[dict] = []
    y = first_bin_start
    for _ in range(WALK_BACK_BINS):
        x = y - step
        got = _bin_of(rows, x, y)
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
        return None, [r], None
    return {"bins": bins, "first": earliest, "identities": identities}, [r], None


def cmd_watch(ns) -> tuple[int, dict]:
    """Poll a driven run's identity, bin by bin, until it has started and
    then ended - the criteria the scenario skill's watch section states,
    shipped: the scheduled count landed, or one empty closed bin past the
    scheduled length, or --ended-after consecutive empty closed bins; before
    the first trace an empty bin means not started."""
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
    expr = f'http.useragent BEGINSWITH "{ns.user_agent}"'
    state = _load_watch_state(ns.state, ns.user_agent, iso(frm), ns.bin)
    results: list = []
    recorded = 0
    recorded_bins = 0  # bins closed by this call: --max never cuts the first
    began = time.monotonic()
    polls_this_call = 0
    while True:
        state["polls"] += 1
        polls_this_call += 1
        now = _clock()
        at_deadline = deadline is not None and now >= deadline
        if at_deadline:
            now = deadline
        error = None
        if ns.settle == "auto" and state["lag_probe"] is None:
            # the store's lag at the dispatch, once: how far behind --from
            # the newest of the service's traces of the 10 minutes before it
            lo = frm - timedelta(minutes=PROBE_MINUTES)
            r = _summaries(ns, lo, frm, None)
            results.append(r)
            if not r.ok:
                error = r
            else:
                rows = _rows(ns, r.data)
                newest = rows[-1]["start"] if rows else None
                lag = (frm - newest).total_seconds() if newest else None
                state["lag_probe"] = {
                    "window": [iso(lo), iso(frm)],
                    "n": len(rows),
                    "newest": iso(newest) if newest else None,
                    "lag_s": round(lag, 1) if lag is not None else None,
                }
                if lag is not None:
                    state["lag_max_s"] = max(state.get("lag_max_s") or 0.0, lag)
        cursor = parse_ts(state["cursor"])
        poll_rows: list[dict] = []
        if error is None and cursor < now and state["status"] != "ended":
            # one call for the whole unread range, the tail included: the
            # traces younger than a bin say how far behind the store is now
            r = _summaries(ns, cursor - timedelta(seconds=1), now, expr)
            results.append(r)
            if not r.ok:
                error = r  # the range stays unread: the next call reads it again
            else:
                poll_rows = [x for x in _rows(ns, r.data) if x["start"] >= cursor]
                recent = [x for x in poll_rows if x["start"] > now - step]
                if recent and ns.settle == "auto":
                    lag = (now - recent[-1]["start"]).total_seconds()
                    state["lag_max_s"] = max(state.get("lag_max_s") or 0.0, lag)
        settle = timedelta(seconds=_settle_seconds(ns, state, step))
        # a bin closes once its end is the settle old; at the deadline the
        # last settle is read all the same, flagged unsettled, so a run
        # that began inside it is never reported "not started"
        horizon = now if at_deadline else now - settle
        while error is None and cursor < horizon and state["status"] != "ended":
            if bound and recorded_bins and time.monotonic() - began >= bound:
                break  # --max binds the call, inside a poll as between two
            recorded_bins += 1
            x, y = cursor, min(cursor + step, horizon)
            partial = y < cursor + step
            got = _bin_of(poll_rows, x, y)
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
                # traces in the very first bin: the run may have begun before
                # --from - walk back, bin by bin, to its first trace, before
                # this bin is recorded: an aws error leaves both unread
                earlier, walked, walk_error = _walk_back(ns, expr, x, step)
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
                    # last trace, no empty bin needed
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
        if error is None and ns.expect and state["status"] != "ended":
            # the scheduled count reached inside the unsettled tail: every
            # row has landed, the run ended at the newest - the tail's bins
            # (a parked partial bin included: the state's cursor never moved
            # past it) go on the record unsettled, nothing waits for them
            tail_from = parse_ts(state["cursor"])
            tail = [x for x in poll_rows if x["start"] >= tail_from]
            if tail and state["rows"] + len(tail) >= ns.expect:
                t = tail_from
                while t < now:
                    x, y = t, min(t + step, now)
                    got = _bin_of(tail, x, y)
                    entry = {
                        "from": iso(x),
                        "to": iso(y),
                        "listed": got["n"],
                        "new": got["n"],
                        "capped": False,
                        "unsettled": True,
                    }
                    if y < t + step:
                        entry["partial"] = True
                    state["bins"].append(entry)
                    if got["n"]:
                        _note_identity(state, got)
                        if state["started"] is None:
                            state["started"] = got["first"]
                            state["status"] = "running"
                        state["last_row"] = got["last"]
                    t = y
                state["rows"] += len(tail)
                state["cursor"] = iso(now)
                state.pop("partial_bin", None)
                state["empty_since"] = 0
                state["status"] = "ended"
                state["ended"] = state["last_row"]
                state["ended_by"] = "count"
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
                    f"no trace on the identity up to the deadline (the last {settle_s}s read "
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
        "identity_prefix": ns.user_agent,
        "services": ns.service or [],
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
        "identity_attr": "Http.UserAgent" if state.get("identity") else None,
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
        "note": "one summaries call per poll, split into bins client-side - a trace falls in one bin, new equals listed and no bin is capped",
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
                " (SEVERAL identities on the traces - several runs, not one)"
                if o["several_identities"]
                else " (one identity on the traces)"
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
            f"(auto: the newest of {probe['n']} traces in the 10 min before the dispatch was {probe['lag_s']} s behind"
            + (
                f", the run's own {o['lag_max_s']} s at most"
                if o.get("lag_max_s") is not None
                and probe.get("lag_s") is not None
                and o["lag_max_s"] > probe["lag_s"]
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
    """The polls' calls differ by their range alone: one line, the range as
    placeholders, and the count - never one line per poll."""
    cmds = o.get("commands") or []
    if not cmds:
        return []
    import re as _re

    folded = list(
        dict.fromkeys(
            _re.sub(
                r"--end-time \d+",
                "--end-time <poll end>",
                _re.sub(r"--start-time \d+", "--start-time <poll start>", c),
            )
            for c in cmds
        )
    )
    n = len(cmds)
    return [
        f"queries run (record these; {n} call{'s' if n > 1 else ''}, one per poll, the range folded):"
    ] + ["  " + c for c in folded]


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
    w = sub.add_parser("watch")
    add_targeting(w)
    w.add_argument("--user-agent", required=True, help="the run's User-Agent prefix")
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
    w.add_argument("--json", action="store_true", help="machine-readable output")
    ns = ap.parse_args()
    register_targets(xray=getattr(ns, "xray_group", None))
    if ns.cmd == "operations":
        o = cmd_operations(ns)
        emit(o, ns.json, render_operations)
    elif ns.cmd == "trace":
        o = cmd_trace(ns)
        emit(o, ns.json, render_trace)
    elif ns.cmd == "watch":
        code, o = cmd_watch(ns)
        emit(o, ns.json, render_watch)
        return code
    else:
        o = cmd_graph(ns)
        emit(o, ns.json, render_graph)
    return exit_code(o)


if __name__ == "__main__":
    sys.exit(main())
