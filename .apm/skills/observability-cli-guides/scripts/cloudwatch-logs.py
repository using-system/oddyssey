#!/usr/bin/env python3
"""Logs: counts and samples by severity, the simple filter, the route table off the access lines, and a checked CWLI pass-through.

    cloudwatch-logs.py count --profile <profile> --region <region> --log-group <log_group> --service orders-api --since 30m
    cloudwatch-logs.py sample --profile <profile> --region <region> --log-group <log_group> --min-severity 13 --show 20 --since 30m
    cloudwatch-logs.py sample --profile <profile> --region <region> --log-group <log_group> --trace-id <trace_id> --since 1h
    cloudwatch-logs.py filter --profile <profile> --region <region> --log-group <log_group> --pattern '{ $.severity_number >= 13 }' --limit 20 --since 30m
    cloudwatch-logs.py routes --profile <profile> --region <region> --log-group <log_group> --service orders-api --since 30m
    cloudwatch-logs.py query --profile <profile> --region <region> --log-group <log_group> 'stats count() as n by `scope.name`, severity_text' --since 30m

Whole surface - every subcommand takes --profile, --region, --log-group
(required; query accepts it repeated for a multi-group query), a window
(--from/--to or --since), --json. count: --service (repeatable, a
resource.service.name; none = every service), --bin (a duration: one row
per time bucket and severity, newest first - no sort on a bin). sample:
--service, --min-severity (an OTel severity_number: 1 TRACE, 5 DEBUG, 9
INFO, 13 WARN, 17 ERROR, 21 FATAL; default 1), --contains (a substring of
the body), --trace-id (the records of one trace), --show (records, the
newest, default 20). filter: --pattern (a CloudWatch Logs filter pattern,
run through filter-log-events - the simple case, no aggregation, one page
capped by --limit, default 50), --stream-prefix. routes: --service, --field
(the field holding the access line, default body), --bin - the chained
parse that normalizes the path (the numeric segment folded, the tail kept:
/orders/{n}/checkout reads as route /orders, tail /checkout), then the
count by method, route, tail and status; a record whose field is not an
access line lands in the row with no method. query: the CWLI string,
--log-group (repeatable) and --metrics-log-group (optional: the EMF group
joins the query, masked by its own field name), --show (rows printed,
default 50), --cap (the poll's bound in seconds, default 120) - the one
escape hatch, through the same transport (the window converted, the poll
bounded, a MalformedQueryException classified with its message); @log in a
result carries the account id, never copied into a report. Exit 0, 1 when a
query failed (the failure is in the output).

The records are the OTel log records the collector writes as JSON bodies:
Logs Insights exposes their keys as fields (trace_id, span_id,
severity_number, severity_text, body, resource.service.name, scope.name -
a dotted name is backquoted in a query), so no parse is needed to correlate
a line with its trace. Residual traps for a query composed by hand: a regex
literal is valid in parse and in filter ... like /.../ only, never in
replace(); sort takes no bin(); a parse-created field must not be re-listed
in a downstream fields (MalformedQueryException: Ephemeral field is already
defined).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloudwatch_aws import (
    add_targeting,
    add_window,
    commands,
    cw_in,
    cw_str,
    emit,
    exit_code,
    failures,
    filter_log_events,
    insights_query,
    iso,
    parse_duration,
    register_targets,
    render_commands,
    render_failures,
    resolve_window,
    severity_text,
    table,
)

FIELDS = "@timestamp, `resource.service.name`, severity_number, severity_text, body, trace_id, span_id, `scope.name`"


def _base(ns) -> tuple[dict, list]:
    frm, to = resolve_window(ns)
    return {"window": [iso(frm), iso(to)], "commands": [], "failed": []}, [frm, to]


def cmd_count(ns) -> dict:
    o, (frm, to) = _base(ns)
    by = "`resource.service.name`, severity_number"
    if ns.bin:
        parse_duration(ns.bin)
        by = f"bin({ns.bin}), " + by
    q = (
        cw_in("resource.service.name", ns.service or [])
        + f"| stats count() as n, max(@timestamp) as last by {by}"
    ).lstrip("| ")
    r = insights_query([ns.log_group], q, frm, to, ns.profile, ns.region)
    o["rows"] = (
        [
            {**row, "severity": severity_text(row.get("severity_number"))}
            for row in (r.data or [])
        ]
        if r.ok
        else []
    )
    if not ns.bin:
        o["rows"].sort(
            key=lambda r: (
                str(r.get("resource.service.name")),
                r.get("severity_number") or 0,
            )
        )
    o["total"] = sum(r.get("n", 0) for r in o["rows"])
    o["commands"], o["failed"] = commands([r]), failures([r])
    return o


def render_count(o: dict) -> str:
    out = [
        f"records by service and severity in {o['window'][0]} .. {o['window'][1]}: {o['total']}"
    ]
    cols = (["bin(" + o["bin"] + ")"] if o.get("bin") else []) + [
        "resource.service.name",
        "severity_number",
        "severity",
        "n",
        "last",
    ]
    out += table(o["rows"], cols)
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_sample(ns) -> dict:
    o, (frm, to) = _base(ns)
    filt = cw_in("resource.service.name", ns.service or [])
    if ns.min_severity and ns.min_severity > 1:
        filt += f"| filter severity_number >= {int(ns.min_severity)} "
    if ns.contains:
        filt += f"| filter body like {cw_str(ns.contains)} "
    if ns.trace_id:
        filt += f"| filter trace_id = {cw_str(ns.trace_id)} "
    q = (
        f"fields {FIELDS} " + filt + f"| sort @timestamp desc | limit {int(ns.show)}"
    ).strip()
    r = insights_query([ns.log_group], q, frm, to, ns.profile, ns.region)
    o["records"] = (
        [{k: v for k, v in row.items() if k != "@ptr"} for row in (r.data or [])]
        if r.ok
        else []
    )
    o["commands"], o["failed"] = commands([r]), failures([r])
    return o


def render_sample(o: dict) -> str:
    out = [
        f"{len(o['records'])} records, the newest first, in {o['window'][0]} .. {o['window'][1]}"
    ]
    for r in o["records"]:
        out.append(
            f"  {r.get('@timestamp')}  {r.get('severity_text') or severity_text(r.get('severity_number'))}  {r.get('resource.service.name')}  [{r.get('scope.name')}]  trace {r.get('trace_id') or '-'} span {r.get('span_id') or '-'}"
        )
        out.append(f"      {r.get('body')}")
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_filter(ns) -> dict:
    o, (frm, to) = _base(ns)
    r = filter_log_events(
        ns.log_group,
        frm,
        to,
        ns.profile,
        ns.region,
        pattern=ns.pattern,
        limit=ns.limit,
        stream_prefix=ns.stream_prefix,
    )
    events = (r.data or {}).get("events", []) if r.ok else []
    o["pattern"] = ns.pattern
    o["events"] = [
        {
            "timestamp": e.get("timestamp"),
            "stream": e.get("logStreamName"),
            "message": e.get("message"),
        }
        for e in events
    ]
    o["truncated"] = bool(r.ok and (r.data or {}).get("nextToken"))
    o["commands"], o["failed"] = commands([r]), failures([r])
    return o


def render_filter(o: dict) -> str:
    from datetime import datetime, timezone

    out = [
        f"filter-log-events {o['pattern']!r}: {len(o['events'])} events"
        + (
            " (one page; more exist - narrow the window or the pattern)"
            if o["truncated"]
            else ""
        )
    ]
    for e in o["events"]:
        ts = (
            datetime.fromtimestamp(e["timestamp"] / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%f"
            )[:-3]
            + "Z"
            if e.get("timestamp")
            else "-"
        )
        out.append(f"  {ts}  [{e['stream']}]  {e['message'][:400]}")
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_routes(ns) -> dict:
    o, (frm, to) = _base(ns)
    by = "method, route, tail, status"
    if ns.bin:
        parse_duration(ns.bin)
        by = f"bin({ns.bin}), " + by
    q = (
        cw_in("resource.service.name", ns.service or [])
        + f'| parse {ns.field} /"(?<method>[A-Z]+) (?<path>\\S+) HTTP\\/[0-9.]+" (?<status>[0-9]{{3}})/ '
        + "| parse path /^(?<route>\\/[a-z_-]+)(\\/[^\\/]+)?(?<tail>\\/[a-z_-]+)?$/ "
        + f"| stats count() as n by {by}"
    ).lstrip("| ")
    r = insights_query([ns.log_group], q, frm, to, ns.profile, ns.region)
    rows = (r.data or []) if r.ok else []
    o["rows"] = sorted(rows, key=lambda x: -x.get("n", 0))
    o["not_access_lines"] = sum(x.get("n", 0) for x in rows if not x.get("method"))
    o["commands"], o["failed"] = commands([r]), failures([r])
    return o


def render_routes(o: dict) -> str:
    out = [
        f"access lines by method, route, tail and status in {o['window'][0]} .. {o['window'][1]} (a numeric segment folded: /orders/{{n}}/checkout is route /orders, tail /checkout)"
    ]
    cols = (["bin(" + o["bin"] + ")"] if o.get("bin") else []) + [
        "method",
        "route",
        "tail",
        "status",
        "n",
    ]
    out += table([r for r in o["rows"] if r.get("method")], cols)
    if o["not_access_lines"]:
        out.append(
            f"  {o['not_access_lines']} records were not access lines (no method parsed)"
        )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_query(ns) -> dict:
    o, (frm, to) = _base(ns)
    r = insights_query(
        ns.log_group, ns.query, frm, to, ns.profile, ns.region, cap=ns.cap
    )
    rows = (r.data or []) if r.ok else []
    o["query"] = ns.query
    o["status"] = r.extra.get("status")
    o["statistics"] = r.extra.get("statistics")
    o["rows_total"] = len(rows)
    o["rows"] = [
        {k: v for k, v in row.items() if k != "@ptr"} for row in rows[: ns.show]
    ]
    o["commands"], o["failed"] = commands([r]), failures([r])
    return o


def render_query(o: dict) -> str:
    out = [
        f"query {o['status'] or '-'}: {o['rows_total']} rows"
        + (
            f", {o['rows_total'] - len(o['rows'])} not printed (--show)"
            if o["rows_total"] > len(o["rows"])
            else ""
        )
    ]
    cols = list(dict.fromkeys(k for row in o["rows"] for k in row))
    out += table(o["rows"], cols)
    st = o.get("statistics") or {}
    if st:
        out.append(
            f"  scanned {st.get('recordsScanned')} records, matched {st.get('recordsMatched')}, {st.get('bytesScanned')} bytes"
        )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    specs = {
        "count": [("--service", {"action": "append"}), ("--bin", {})],
        "sample": [
            ("--service", {"action": "append"}),
            ("--min-severity", {"type": int, "default": 1}),
            ("--contains", {}),
            ("--trace-id", {}),
            ("--show", {"type": int, "default": 20}),
        ],
        "filter": [
            ("--pattern", {}),
            ("--limit", {"type": int, "default": 50}),
            ("--stream-prefix", {}),
        ],
        "routes": [
            ("--service", {"action": "append"}),
            ("--field", {"default": "body"}),
            ("--bin", {}),
        ],
    }
    for name, flags in specs.items():
        p = sub.add_parser(name)
        add_targeting(p, log_group=True)
        for flag, kw in flags:
            p.add_argument(flag, **kw)
        add_window(p)
    q = sub.add_parser("query")
    q.add_argument("query")
    q.add_argument("--profile", required=True)
    q.add_argument("--region", required=True)
    q.add_argument("--log-group", action="append", required=True)
    q.add_argument("--metrics-log-group")
    q.add_argument("--show", type=int, default=50)
    q.add_argument("--cap", type=int, default=120)
    add_window(q)
    ns = ap.parse_args()
    groups = ns.log_group if isinstance(ns.log_group, list) else [ns.log_group]
    register_targets(
        log_group=groups[0], metrics_log_group=getattr(ns, "metrics_log_group", None)
    )
    for i, extra in enumerate(groups[1:], start=2):
        register_targets(**{f"log_group_{i}": extra})
    if getattr(ns, "metrics_log_group", None):
        ns.log_group = [*groups, ns.metrics_log_group]
    handlers = {
        "count": (cmd_count, render_count),
        "sample": (cmd_sample, render_sample),
        "filter": (cmd_filter, render_filter),
        "routes": (cmd_routes, render_routes),
        "query": (cmd_query, render_query),
    }
    run, render = handlers[ns.cmd]
    o = run(ns)
    if getattr(ns, "bin", None):
        o["bin"] = ns.bin
    emit(o, ns.json, render)
    return exit_code(o)


if __name__ == "__main__":
    sys.exit(main())
