#!/usr/bin/env python3
"""Log events in Seq: counts by level, matching lines with samples, trace-id correlation.

    seq-logs.py count --service "Roastery Web Frontend" --from ... --to ...
    seq-logs.py sample --level Error --contains "deadlock" --since 30m --show 20
    seq-logs.py sample --filter "StatusCode >= 500" --from ... --to ...
    seq-logs.py correlate --service svc --from ... --to ... --json

Whole surface - every subcommand takes --service NAME (repeatable),
--service-key PROP (default Application), a window (--from/--to or
--since) and --json. `count` reports, per service, the log-event count by
@Level and the count carrying an @Exception, and the same for the
service's spans (a request's level and exception land on its span, not on
a log event). `sample` adds --level LEVEL
(exact @Level value, e.g. Error), --contains TEXT (case-insensitive
substring of the message or the exception), --filter EXPR (any Seq filter
expression, and-ed in), --spans (include span events, excluded by default),
--show N (events printed, default 20 - the search's -c); each sample is
printed with its UTC time, level, trace id and the rendered message.
`correlate` reports, per service, how many log events carry a @TraceId and
how many do not, with samples of the orphans. Every subcommand prints the
seqcli commands it ran. Exit 0 on success, 1 when seqcli errored.
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
    contains_clause,
    emit,
    errors,
    event_time,
    query,
    quote,
    render_commands,
    render_message,
    resolve_window,
    search,
    service_clause,
    sql_where,
    table,
)

NO_KEY = "(no value)"


def _key(v) -> str:
    return NO_KEY if v is None else str(v)


def cmd_count(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    svc = service_clause(ns.service, ns.service_key)
    key = ns.service_key
    r1 = query(
        f"select count(*) as n from stream{sql_where('not has(@Start)', svc)} group by {key}, @Level",
        frm,
        to,
    )
    r2 = query(
        f"select count(*) as n from stream{sql_where('has(@Exception)', svc)} group by {key}, has(@Start)",
        frm,
        to,
    )
    r3 = query(
        f"select count(*) as n from stream{sql_where('has(@Start)', svc)} group by {key}, @Level",
        frm,
        to,
    )
    per: dict[str, dict] = {}

    def entry(name):
        return per.setdefault(
            name,
            {
                "lines": 0,
                "levels": {},
                "exceptions": 0,
                "span_levels": {},
                "span_exceptions": 0,
            },
        )

    for row in table(r1):
        e = entry(_key(row.get(key)))
        e["levels"][_key(row.get("@Level"))] = row.get("n") or 0
        e["lines"] += row.get("n") or 0
    for row in table(r2):
        entry(_key(row.get(key)))[
            "span_exceptions" if row.get("has(@Start)") else "exceptions"
        ] = row.get("n") or 0
    for row in table(r3):
        entry(_key(row.get(key)))["span_levels"][_key(row.get("@Level"))] = (
            row.get("n") or 0
        )
    for e in per.values():
        e["levels"] = dict(sorted(e["levels"].items(), key=lambda kv: -kv[1]))
        e["span_levels"] = dict(sorted(e["span_levels"].items(), key=lambda kv: -kv[1]))
    err = errors([r1, r2, r3])
    return (1 if err else 0), {
        "error": err,
        "window": [frm, to],
        "lines": sum(e["lines"] for e in per.values()),
        "services": dict(sorted(per.items(), key=lambda kv: -kv[1]["lines"])),
        "note": "a request's level and exception land on its span, not on a log event - the span_levels line is where an instrumented service's errors show; `sample --spans` reaches them",
        "commands": commands([r1, r2, r3]),
    }


def cmd_sample(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    clauses = [] if ns.spans else ["not has(@Start)"]
    clauses.append(service_clause(ns.service, ns.service_key))
    if ns.level:
        clauses.append(f"@Level = {quote(ns.level)}")
    if ns.contains:
        clauses.append(contains_clause(ns.contains))
    if ns.filter:
        clauses.append(f"({ns.filter})")
    filt = " and ".join(c for c in clauses if c) or "not has(@Start)"
    r = search(filt, ns.show, frm, to)
    results = [r]
    n = None
    if r.ok:
        total = query(f"select count(*) as n from stream where {filt}", frm, to)
        results.append(total)
        n = table(total)[0].get("n") if table(total) else None
    err = errors(results)
    return (1 if err else 0), {
        "error": err,
        "window": [frm, to],
        "filter": filt,
        "matching": n,
        "note": ""
        if ns.spans
        else "span events are excluded; an instrumented service's request errors sit on its spans - pass --spans to reach them",
        "samples": [
            {
                "ts": event_time(ev),
                "level": ev.get("@l") or "Information",
                "trace_id": ev.get("@tr", ""),
                "span_id": ev.get("@sp", ""),
                "message": render_message(ev)[:300],
                "exception": (ev.get("@x") or "")[:200],
                "properties": {k: v for k, v in ev.items() if not k.startswith("@")},
            }
            for ev in (r.data or [])
        ],
        "commands": commands(results),
    }


def cmd_correlate(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    svc = service_clause(ns.service, ns.service_key)
    key = ns.service_key
    r1 = query(
        f"select count(*) as n from stream{sql_where('not has(@Start)', svc)} group by {key}, has(@TraceId)",
        frm,
        to,
    )
    orphan_filter = " and ".join(
        c for c in ["not has(@Start) and not has(@TraceId)", svc] if c
    )
    r2 = search(orphan_filter, 10, frm, to)
    per: dict[str, dict] = {}
    for row in table(r1):
        e = per.setdefault(
            _key(row.get(key)), {"lines": 0, "with_trace_id": 0, "without": 0}
        )
        n = row.get("n") or 0
        e["lines"] += n
        e["with_trace_id" if row.get("has(@TraceId)") else "without"] += n
    err = errors([r1, r2])
    return (1 if err else 0), {
        "error": err,
        "window": [frm, to],
        "services": dict(sorted(per.items(), key=lambda kv: -kv[1]["lines"])),
        "orphan_samples": [
            {
                "ts": event_time(ev),
                "service": _key(ev.get(key)),
                "message": render_message(ev)[:160],
            }
            for ev in (r2.data or [])
        ],
        "note": "startup, batch and health-check lines legitimately carry no trace id - classify the orphans before calling this a gap",
        "commands": commands([r1, r2]),
    }


def render(o: dict) -> str:
    if o.get("error"):
        return "ERROR " + o["error"]
    out = [f"window {o['window'][0]} .. {o['window'][1]}"]
    if "samples" in o:
        out.append(f"{o['matching']} matching events (filter: {o['filter']})")
        for s in o["samples"]:
            out.append(
                f"  {s['ts']} {s['level']:11s} {s['trace_id'][:16] or '-':16s} {s['message']}"
            )
            if s["exception"]:
                out.append("      " + s["exception"].splitlines()[0][:150])
        if o.get("note") and not o["samples"]:
            out.append("  " + o["note"])
    elif "orphan_samples" in o:
        for name, e in o["services"].items():
            out.append(
                f"{name}: {e['lines']} log events, {e['with_trace_id']} with a trace id, {e['without']} without"
            )
        for s in o["orphan_samples"]:
            out.append(f"  orphan {s['ts']} {s['service']}: {s['message']}")
        out.append("  " + o["note"])
    else:
        out.append(f"{o['lines']} log events")
        for name, e in o["services"].items():
            out.append(
                f"{name}: {e['lines']} log events, exceptions={e['exceptions']}  "
                + "  ".join(f"{k}={v}" for k, v in e["levels"].items())
            )
            if e["span_levels"]:
                out.append(
                    f"  span levels: exceptions={e['span_exceptions']}  "
                    + "  ".join(f"{k}={v}" for k, v in e["span_levels"].items())
                )
        out.append("  " + o["note"])
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "sample", "correlate"):
        p = sub.add_parser(name)
        add_service(p)
        if name == "sample":
            p.add_argument("--level", default="", help="exact @Level value, e.g. Error")
            p.add_argument(
                "--contains",
                default="",
                help="case-insensitive substring of the message or the exception",
            )
            p.add_argument(
                "--filter", default="", help="a Seq filter expression, and-ed in"
            )
            p.add_argument(
                "--spans",
                action="store_true",
                help="include span events (default: log events only)",
            )
            p.add_argument(
                "--show", type=int, default=20, help="events to print (default 20)"
            )
        add_window(p)
    ns = ap.parse_args()
    code, out = {"count": cmd_count, "sample": cmd_sample, "correlate": cmd_correlate}[
        ns.cmd
    ](ns)
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
