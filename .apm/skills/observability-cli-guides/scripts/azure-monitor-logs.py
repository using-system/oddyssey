#!/usr/bin/env python3
"""Logs: the workspace's console tables and the component's traces table, plus a checked KQL pass-through.

    azure-monitor-logs.py count --workspace <workspace> --from ... --to ...
    azure-monitor-logs.py sample --workspace <workspace> --container <collector> --level error --since 30m --show 20
    azure-monitor-logs.py schema --workspace <workspace> --table ContainerAppSystemLogs_CL
    azure-monitor-logs.py tables --workspace <workspace> --since 24h
    azure-monitor-logs.py traces --app <app_insights_app> --service orders-api --min-severity 2 --since 30m
    azure-monitor-logs.py kql --workspace <workspace> "ContainerAppSystemLogs_CL | summarize n=count() by Reason_s" --since 24h
    azure-monitor-logs.py kql --app <app_insights_app> "requests | summarize n=count() by resultCode" --since 30m

Whole surface - count and sample: --workspace (the customer ID GUID),
--table (default ContainerAppConsoleLogs_CL), --container-column (default
ContainerName_s), --message-column (default Log_s), --stream-column (default
Stream_s; pass '' for a table without one), --container (repeatable, a
value of the container column; none = every container), --level-regex (the
KQL regex whose first group is the level - default the collector's console
line, the second whitespace-separated field: ^\\S+\\s+(\\w+)\\s; a line that
opens with the level takes ^(\\w+)), a window, --json; sample adds --level
(case-insensitive equality on the extracted level), --contains (a substring
of the message), --show (lines, the newest, default 20). schema: --workspace,
--table, --json - the columns and their types, to confirm before a query
names one (a *_CL table's columns are not those of its sibling). tables:
--workspace, a window, --json - the *_CL tables holding rows. traces: --app
(the appId GUID), --service (repeatable), --min-severity (0 verbose, 1
information, 2 warning, 3 error, 4 critical; default 0), --contains, --show
(default 20), a window, --json. kql: exactly one of --workspace or --app,
the KQL string, --show (rows printed, default 50), a window, --json - the
one escape hatch, run through the same transport (explicit window, the
error classified, the rows parsed). Exit 0, 1 when a query failed.
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
    kql_in,
    kql_str,
    la_call,
    la_rows,
    render_commands,
    render_failures,
    resolve_window,
    run_az,
    run_many,
    table,
)

DEFAULT_LEVEL_REGEX = r"^\S+\s+(\w+)\s"
SEVERITY = {0: "verbose", 1: "information", 2: "warning", 3: "error", 4: "critical"}


def usage(message: str) -> None:
    """A usage error the way argparse reports one: the message on stderr, exit 2."""
    print(f"usage error: {message}", file=sys.stderr)
    sys.exit(2)


def _regex_literal(rx: str) -> str:
    if '"' in rx:
        usage(
            '--level-regex cannot carry a double quote (it is sent as a KQL @"..." literal)'
        )
    return f'@"{rx}"'


def _base(ns) -> str:
    return f"{ns.table} {kql_in(ns.container_column, ns.container or [])}| extend lvl=extract({_regex_literal(ns.level_regex)}, 1, {ns.message_column}) "


def cmd_count(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    by = ", ".join(x for x in [ns.container_column, "lvl", ns.stream_column] if x)
    r = run_az(
        la_call(
            ns.workspace,
            _base(ns)
            + f"| summarize n=count(), latest=max(TimeGenerated) by {by} | order by {ns.container_column} asc, n desc",
            frm,
            to,
        )
    )
    rows = la_rows(r.data) if r.ok else []
    for x in rows:
        x["level"] = x.pop("lvl", "") or "(no match)"
        x["container"] = x.pop(ns.container_column, "")
        if ns.stream_column:
            x["stream"] = x.pop(ns.stream_column, "")
    out = {
        "window": [frm, to],
        "table": ns.table,
        "level_regex": ns.level_regex,
        "rows": rows,
        "failed": failures([r]),
        "commands": commands([r]),
    }
    return exit_code(out), out


def render_count(o: dict) -> str:
    out = [
        f"{o['table']} lines per container and level, {o['window'][0]}..{o['window'][1]} (level = group 1 of {o['level_regex']})"
    ]
    cols = (
        ["container", "level"]
        + (["stream"] if o["rows"] and "stream" in o["rows"][0] else [])
        + ["n", "latest"]
    )
    out += table(o["rows"], cols)
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_sample(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    q = _base(ns)
    if ns.level:
        q += f"| where lvl =~ {kql_str(ns.level)} "
    if ns.contains:
        q += f"| where {ns.message_column} contains {kql_str(ns.contains)} "
    cols = ", ".join(
        x
        for x in [
            "TimeGenerated",
            ns.container_column,
            "lvl",
            ns.stream_column,
            ns.message_column,
        ]
        if x
    )
    calls = [
        la_call(ns.workspace, q + "| summarize matching=count()", frm, to),
        la_call(
            ns.workspace,
            q + f"| top {ns.show} by TimeGenerated desc | project {cols}",
            frm,
            to,
        ),
    ]
    res = run_many(calls)
    m = la_rows(res[0].data) if res[0].ok else []
    rows = la_rows(res[1].data) if res[1].ok else []
    samples = [
        {
            "time": x.get("TimeGenerated"),
            "container": x.get(ns.container_column),
            "level": x.get("lvl") or "",
            "stream": x.get(ns.stream_column, "") if ns.stream_column else "",
            "message": x.get(ns.message_column),
        }
        for x in rows
    ]
    out = {
        "window": [frm, to],
        "table": ns.table,
        "matching": m[0].get("matching") if m else None,
        "samples": samples,
        "failed": failures(res),
        "commands": commands(res),
    }
    return exit_code(out), out


def render_sample(o: dict) -> str:
    out = [
        f"{o['table']}: {o['matching']} matching lines in {o['window'][0]}..{o['window'][1]}, the newest {len(o['samples'])}:"
    ]
    for s in o["samples"]:
        out.append(
            f"  {str(s['time'])[:23]} {s['container']} {s['level'] or '-'} {s['stream']}  {str(s['message'])[:300]}"
        )
    if not o["samples"]:
        out.append("  (none)")
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_schema(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns, default_since="1h")
    r = run_az(
        la_call(
            ns.workspace,
            f"{ns.table} | getschema | project ColumnName, ColumnType",
            frm,
            to,
        )
    )
    rows = la_rows(r.data) if r.ok else []
    out = {
        "table": ns.table,
        "columns": [{"name": x["ColumnName"], "type": x["ColumnType"]} for x in rows],
        "failed": failures([r]),
        "commands": commands([r]),
    }
    return exit_code(out), out


def render_schema(o: dict) -> str:
    out = [f"{o['table']}: {len(o['columns'])} columns"]
    out.append("  " + ", ".join(f"{c['name']}:{c['type']}" for c in o["columns"]))
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_tables(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    r = run_az(
        la_call(
            ns.workspace,
            "union withsource=T *_CL | summarize n=count(), latest=max(TimeGenerated) by T | order by n desc",
            frm,
            to,
        )
    )
    rows = la_rows(r.data) if r.ok else []
    out = {
        "window": [frm, to],
        "tables": [{"table": x["T"], "n": x["n"], "latest": x["latest"]} for x in rows],
        "failed": failures([r]),
        "commands": commands([r]),
    }
    return exit_code(out), out


def render_tables(o: dict) -> str:
    out = [f"*_CL tables with rows in {o['window'][0]}..{o['window'][1]}:"]
    out += table(o["tables"], ["table", "n", "latest"])
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_traces(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    svc = kql_in("cloud_RoleName", ns.service or [])
    q = f"traces {svc}| where severityLevel >= {int(ns.min_severity)} "
    if ns.contains:
        q += f"| where message contains {kql_str(ns.contains)} "
    res = run_many(
        [
            ai_call(
                ns.app,
                f"traces {svc}| summarize n=count() by cloud_RoleName, severityLevel | order by cloud_RoleName asc, severityLevel asc",
                frm,
                to,
            ),
            ai_call(ns.app, q + "| summarize matching=count()", frm, to),
            ai_call(
                ns.app,
                q
                + f"| top {ns.show} by timestamp desc | project timestamp, cloud_RoleName, severityLevel, message, operation_Id, operation_ParentId, customDimensions",
                frm,
                to,
            ),
        ]
    )
    sev = [
        {
            "cloud_RoleName": x["cloud_RoleName"],
            "severity": SEVERITY.get(x["severityLevel"], x["severityLevel"]),
            "n": x["n"],
        }
        for x in (ai_rows(res[0].data) if res[0].ok else [])
    ]
    m = ai_rows(res[1].data) if res[1].ok else []
    samples = []
    for x in ai_rows(res[2].data) if res[2].ok else []:
        d = dims(x.get("customDimensions"))
        samples.append(
            {
                "time": x["timestamp"],
                "cloud_RoleName": x["cloud_RoleName"],
                "severity": SEVERITY.get(x["severityLevel"], x["severityLevel"]),
                "message": x["message"],
                "operation_Id": x["operation_Id"],
                "span_id": x["operation_ParentId"],
                "library": d.get("instrumentationlibrary.name", ""),
            }
        )
    out = {
        "window": [frm, to],
        "severities": sev,
        "matching": m[0].get("matching") if m else None,
        "samples": samples,
        "failed": failures(res),
        "commands": commands(res),
    }
    return exit_code(out), out


def render_traces(o: dict) -> str:
    out = [f"traces (the component's log table) in {o['window'][0]}..{o['window'][1]}:"]
    out += table(o["severities"], ["cloud_RoleName", "severity", "n"])
    out.append(f"{o['matching']} lines match; the newest {len(o['samples'])}:")
    for s in o["samples"]:
        out.append(
            f"  {str(s['time'])[:23]} {s['cloud_RoleName']} {s['severity']} [{s['library']}] {str(s['message'])[:240]}  operation_Id {s['operation_Id']}"
        )
    if not o["samples"]:
        out.append("  (none)")
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def cmd_kql(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    if bool(ns.workspace) == bool(ns.app):
        usage(
            "kql takes exactly one of --workspace <workspace> or --app <app_insights_app>"
        )
    if ns.workspace:
        r = run_az(la_call(ns.workspace, ns.kql, frm, to))
        rows = la_rows(r.data) if r.ok else []
    else:
        r = run_az(ai_call(ns.app, ns.kql, frm, to))
        rows = ai_rows(r.data) if r.ok else []
    out = {
        "window": [frm, to],
        "rows": rows[: ns.show],
        "total_rows": len(rows),
        "failed": failures([r]),
        "commands": commands([r]),
    }
    return exit_code(out), out


def render_kql(o: dict) -> str:
    out = [
        f"{o['total_rows']} rows in {o['window'][0]}..{o['window'][1]}"
        + (
            f" ({len(o['rows'])} printed, --show)"
            if o["total_rows"] > len(o["rows"])
            else ""
        )
    ]
    if o["rows"]:
        cols = list(o["rows"][0].keys())
        out += table(
            [
                {k: (str(v)[:80] if v is not None else None) for k, v in r.items()}
                for r in o["rows"]
            ],
            cols,
        )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("count")
    b = sub.add_parser("sample")
    b.add_argument("--level")
    b.add_argument("--contains")
    b.add_argument("--show", type=int, default=20)
    for p in (a, b):
        p.add_argument("--workspace", required=True)
        p.add_argument("--table", default="ContainerAppConsoleLogs_CL")
        p.add_argument("--container-column", default="ContainerName_s")
        p.add_argument("--message-column", default="Log_s")
        p.add_argument("--stream-column", default="Stream_s")
        p.add_argument("--container", action="append")
        p.add_argument("--level-regex", default=DEFAULT_LEVEL_REGEX)
        add_window(p)
    c = sub.add_parser("schema")
    c.add_argument("--workspace", required=True)
    c.add_argument("--table", required=True)
    add_window(c)
    d = sub.add_parser("tables")
    d.add_argument("--workspace", required=True)
    add_window(d)
    e = sub.add_parser("traces")
    e.add_argument("--app", required=True)
    e.add_argument("--service", action="append")
    e.add_argument("--min-severity", type=int, default=0)
    e.add_argument("--contains")
    e.add_argument("--show", type=int, default=20)
    add_window(e)
    f = sub.add_parser("kql")
    f.add_argument("kql")
    f.add_argument("--workspace")
    f.add_argument("--app")
    f.add_argument("--show", type=int, default=50)
    add_window(f)
    ns = ap.parse_args()
    fn = {
        "count": (cmd_count, render_count),
        "sample": (cmd_sample, render_sample),
        "schema": (cmd_schema, render_schema),
        "tables": (cmd_tables, render_tables),
        "traces": (cmd_traces, render_traces),
        "kql": (cmd_kql, render_kql),
    }[ns.cmd]
    code, o = fn[0](ns)
    emit(o, ns.json, fn[1])
    return code


if __name__ == "__main__":
    sys.exit(main())
