#!/usr/bin/env python3
"""Spans in Seq: per-operation quantiles, exemplars above a threshold, child-span breakdown, one trace.

    seq-traces.py operations --service svc --group-by RequestMethod --group-by RouteTemplate --from ... --to ...
    seq-traces.py exemplars --above 100ms --service svc --since 30m --show 10
    seq-traces.py children --service svc --from ... --to ...
    seq-traces.py trace <trace id> [--no-logs] [--json]

Whole surface - operations, exemplars and children take --service NAME
(repeatable), --service-key PROP (default Application), a window
(--from/--to or --since), --all-spans (every span, instead of the root
spans only - those without a @ParentId), --kind KIND (a @SpanKind value:
Server, Client, Internal, Producer, Consumer) and --json. `operations`
adds --group-by PROP (repeatable, default @MessageTemplate - the span's
name; name the whole operation, e.g. the method and the templated route,
never one half of it) and --min-count N (rows below it dropped, default
1): per group it prints the span count, the error count (@Level = Error),
p50/p95/p99/max in milliseconds. `exemplars` adds --above DURATION (a Seq
duration literal such as 100ms or 1s, or a number of 100 ns ticks; default
0 = the slowest), --filter EXPR (a Seq filter, and-ed in) and --show N
(default 10): each exemplar carries its trace id, span id, start (UTC),
duration in ms, level and rendered message. `children` groups the non-root
spans by --group-by (default @MessageTemplate): count, distinct traces,
calls per trace, p50/p99 ms. `trace` prints one trace as an indented tree
(spans and, unless --no-logs, the log events inside them, exceptions
included) with a summary. Every subcommand prints the seqcli commands it
ran. Exit 0 on success, 1 when seqcli errored.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seq_cli import (
    add_service,
    add_window,
    commands,
    elapsed_ms,
    emit,
    errors,
    event_time,
    flatten_trace,
    fmt_ms,
    properties,
    query,
    quote,
    render_commands,
    render_message,
    resolve_window,
    search,
    service_clause,
    sql_where,
    table,
    ticks_ms,
    trace,
)

NO_KEY = "(no value)"


def _key(v) -> str:
    return NO_KEY if v is None else str(v)


def _span_clauses(ns, root_only_default=True) -> list[str]:
    c = ["has(@Start)"]
    if not ns.all_spans and root_only_default:
        c.append("not has(@ParentId)")
    if ns.all_spans is False and not root_only_default:
        c.append("has(@ParentId)")
    if ns.kind:
        c.append(f"@SpanKind = {quote(ns.kind)}")
    c.append(service_clause(ns.service, ns.service_key))
    return [x for x in c if x]


def cmd_operations(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    groups = ns.group_by or ["@MessageTemplate"]
    key = ns.service_key
    gb = ", ".join([key, *groups])
    base = _span_clauses(ns)
    q1 = query(
        f"select count(*) as n, percentile(@Elapsed, 50) as p50, percentile(@Elapsed, 95) as p95, "
        f"percentile(@Elapsed, 99) as p99, max(@Elapsed) as mx from stream{sql_where(*base)} group by {gb}",
        frm,
        to,
    )
    q2 = query(
        f"select count(*) as errors from stream{sql_where(*base, '@Level = ' + quote('Error'))} group by {gb}",
        frm,
        to,
    )
    err_by = {
        tuple(_key(row.get(g)) for g in [key, *groups]): row.get("errors") or 0
        for row in table(q2)
    }
    rows = []
    for row in table(q1):
        k = tuple(_key(row.get(g)) for g in [key, *groups])
        n = row.get("n") or 0
        if n < ns.min_count:
            continue
        rows.append(
            {
                "service": k[0],
                "operation": " ".join(k[1:]),
                "group": dict(zip(groups, k[1:])),
                "count": n,
                "errors": err_by.get(k, 0),
                "p50_ms": ticks_ms(row.get("p50")),
                "p95_ms": ticks_ms(row.get("p95")),
                "p99_ms": ticks_ms(row.get("p99")),
                "max_ms": ticks_ms(row.get("mx")),
            }
        )
    rows.sort(key=lambda r: -r["count"])
    err = errors([q1, q2])
    return (1 if err else 0), {
        "error": err,
        "window": [frm, to],
        "scope": "all spans" if ns.all_spans else "root spans",
        "group_by": groups,
        "operations": rows,
        "commands": commands([q1, q2]),
    }


_DURATION = re.compile(r"^\d+(\.\d+)?(ms|s|m|h|d)?$")


def cmd_exemplars(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    clauses = _span_clauses(ns)
    if ns.above and ns.above not in ("0", ""):
        if not _DURATION.match(ns.above):
            raise SystemExit(
                f"--above is a Seq duration literal (100ms, 1s) or ticks - got {ns.above!r}"
            )
        clauses.append(f"@Elapsed > {ns.above}")
    if ns.filter:
        clauses.append(f"({ns.filter})")
    filt = " and ".join(clauses)
    r = search(filt, ns.show, frm, to)
    results = [r]
    n = None
    if r.ok:
        total = query(f"select count(*) as n from stream where {filt}", frm, to)
        results.append(total)
        n = table(total)[0].get("n") if table(total) else None
    ex = [
        {
            "trace_id": ev.get("@tr", ""),
            "span_id": ev.get("@sp", ""),
            "parent_id": ev.get("@ps", ""),
            "start": ev.get("@st", ""),
            "end": event_time(ev),
            "elapsed_ms": elapsed_ms(ev),
            "kind": ev.get("@sk", ""),
            "level": ev.get("@l") or "Information",
            "message": render_message(ev)[:200],
            "properties": properties(ev),
        }
        for ev in (r.data or [])
    ]
    ex.sort(key=lambda e: -(e["elapsed_ms"] or 0))
    err = errors(results)
    return (1 if err else 0), {
        "error": err,
        "window": [frm, to],
        "filter": filt,
        "matching": n,
        "exemplars": ex,
        "note": "the search returns the newest matches, not the slowest: raise --above to reach the tail",
        "commands": commands(results),
    }


def cmd_children(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    groups = ns.group_by or ["@MessageTemplate"]
    key = ns.service_key
    gb = ", ".join([key, *groups])
    ns.all_spans = False
    clauses = _span_clauses(ns, root_only_default=False)
    q = query(
        f"select count(*) as n, count(distinct(@TraceId)) as traces, percentile(@Elapsed, 50) as p50, "
        f"percentile(@Elapsed, 99) as p99, max(@Elapsed) as mx from stream{sql_where(*clauses)} group by {gb}",
        frm,
        to,
    )
    rows = []
    for row in table(q):
        n, t = row.get("n") or 0, row.get("traces") or 0
        rows.append(
            {
                "service": _key(row.get(key)),
                "operation": " ".join(_key(row.get(g)) for g in groups),
                "count": n,
                "traces": t,
                "calls_per_trace": round(n / t, 2) if t else None,
                "p50_ms": ticks_ms(row.get("p50")),
                "p99_ms": ticks_ms(row.get("p99")),
                "max_ms": ticks_ms(row.get("mx")),
            }
        )
    rows.sort(key=lambda r: -r["count"])
    err = errors([q])
    return (1 if err else 0), {
        "error": err,
        "window": [frm, to],
        "group_by": groups,
        "children": rows,
        "commands": commands([q]),
    }


def cmd_trace(ns) -> tuple[int, dict]:
    r = trace(ns.trace_id, logs=not ns.no_logs)
    nodes = flatten_trace(r.data) if r.ok else []
    spans = [n for n in nodes if n["type"] == "span"]
    root = spans[0] if spans else None
    err = errors([r])
    return (1 if err else 0), {
        "error": err,
        "trace_id": ns.trace_id,
        "complete": (r.data or {}).get("complete") if r.ok else None,
        "summary": {
            "root": root["message"] if root else "",
            "duration_ms": root["elapsed_ms"] if root else None,
            "spans": len(spans),
            "logs": sum(1 for n in nodes if n["type"] == "log"),
            "errors": sum(
                1 for n in nodes if (n["level"] or "").lower() in ("error", "fatal")
            ),
            "longest": [
                {"message": s["message"][:80], "elapsed_ms": s["elapsed_ms"]}
                for s in sorted(spans, key=lambda s: -(s["elapsed_ms"] or 0))[:5]
            ],
        },
        "nodes": nodes,
        "commands": commands([r]),
    }


def render(o: dict) -> str:
    if o.get("error"):
        return "ERROR " + o["error"]
    out = []
    if "operations" in o:
        out.append(
            f"window {o['window'][0]} .. {o['window'][1]}  ({o['scope']}, grouped by {', '.join(o['group_by'])})"
        )
        out.append(
            f"  {'count':>6s} {'errors':>6s} {'p50ms':>8s} {'p95ms':>8s} {'p99ms':>8s} {'maxms':>8s}  service | operation"
        )
        for r in o["operations"]:
            out.append(
                f"  {r['count']:6d} {r['errors']:6d} {fmt_ms(r['p50_ms']):>8s} {fmt_ms(r['p95_ms']):>8s} "
                f"{fmt_ms(r['p99_ms']):>8s} {fmt_ms(r['max_ms']):>8s}  {r['service']} | {r['operation']}"
            )
    elif "exemplars" in o:
        out.append(
            f"window {o['window'][0]} .. {o['window'][1]}  {o['matching']} spans match (filter: {o['filter']})"
        )
        for e in o["exemplars"]:
            out.append(
                f"  {fmt_ms(e['elapsed_ms']):>8s} ms  {e['trace_id']}  {e['level']:11s} {e['message']}"
            )
        out.append("  " + o["note"])
    elif "children" in o:
        out.append(
            f"window {o['window'][0]} .. {o['window'][1]}  (child spans, grouped by {', '.join(o['group_by'])})"
        )
        out.append(
            f"  {'count':>6s} {'traces':>6s} {'/trace':>6s} {'p50ms':>8s} {'p99ms':>8s} {'maxms':>8s}  service | operation"
        )
        for r in o["children"]:
            out.append(
                f"  {r['count']:6d} {r['traces']:6d} {fmt_ms(r['calls_per_trace']):>6s} {fmt_ms(r['p50_ms']):>8s} "
                f"{fmt_ms(r['p99_ms']):>8s} {fmt_ms(r['max_ms']):>8s}  {r['service']} | {r['operation']}"
            )
    else:
        s = o["summary"]
        out.append(
            f"trace {o['trace_id']}  complete={o['complete']}  {s['spans']} spans, {s['logs']} logs, {s['errors']} errors, root {fmt_ms(s['duration_ms'])} ms: {s['root']}"
        )
        for n in o["nodes"]:
            pad = "  " * n["depth"]
            if n["type"] == "span":
                out.append(
                    f"  {pad}[span {fmt_ms(n['elapsed_ms']):>7s} ms] {n['level'][:3].upper():3s} {n['message'][:150]}"
                )
            else:
                out.append(
                    f"  {pad}  log {n['level'][:3].upper():3s} {n['message'][:150]}"
                )
            if n.get("exception"):
                out.append(f"  {pad}      {str(n['exception']).splitlines()[0][:150]}")
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("operations", "exemplars", "children"):
        p = sub.add_parser(name)
        add_service(p)
        p.add_argument(
            "--all-spans",
            action="store_true",
            help="every span, not only the root spans",
        )
        p.add_argument(
            "--kind",
            default="",
            help="a @SpanKind value: Server, Client, Internal, Producer, Consumer",
        )
        if name in ("operations", "children"):
            p.add_argument(
                "--group-by",
                action="append",
                default=[],
                help="a property naming the operation; repeatable (default @MessageTemplate)",
            )
        if name == "operations":
            p.add_argument(
                "--min-count",
                type=int,
                default=1,
                help="drop groups with fewer spans (default 1)",
            )
        if name == "exemplars":
            p.add_argument(
                "--above",
                default="",
                help="duration literal (100ms, 1s) or ticks; spans slower than it",
            )
            p.add_argument(
                "--filter", default="", help="a Seq filter expression, and-ed in"
            )
            p.add_argument(
                "--show", type=int, default=10, help="exemplars to print (default 10)"
            )
        add_window(p)
    p = sub.add_parser("trace")
    p.add_argument("trace_id")
    p.add_argument("--no-logs", action="store_true", help="spans only")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    ns = ap.parse_args()
    code, out = {
        "operations": cmd_operations,
        "exemplars": cmd_exemplars,
        "children": cmd_children,
        "trace": cmd_trace,
    }[ns.cmd](ns)
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
