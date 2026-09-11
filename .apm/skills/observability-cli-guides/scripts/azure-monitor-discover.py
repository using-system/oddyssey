#!/usr/bin/env python3
"""What the component and the workspace hold for a window, per service, in one call.

    azure-monitor-discover.py --app <app_insights_app> --workspace <workspace> --from ... --to ...
    azure-monitor-discover.py --app <app_insights_app> --service orders-api --since 30m --json

Whole surface: --app (the appId GUID), --workspace (the customer ID GUID) -
one of the two at least, --service (repeatable; none = every cloud_RoleName
the window carries), a window (--from/--to or --since), --console-table
(the workspace table holding a container platform's console lines, default
ContainerAppConsoleLogs_CL), --container-column (its container-name column,
default ContainerName_s), --top (operations listed per service, default 15),
--json. Exit 0 when every probe ran, 1 when one failed (the failure is in
the output).

The component side counts requests, dependencies, customMetrics, traces and
exceptions per service, lists the operations the requests are named by, the
customMetrics names, the trace severities, the exception types, and reads
the deployment environment off the resource attributes the rows carry
(customDimensions['deployment.environment.name'], falling back to
'deployment.environment'), with service.version and the instance ids. The
workspace side lists the *_CL tables that hold rows in the window and the
containers of the console table. A side not given is a stated gap, never
worked around: without --app the run is logs-only and distributed tracing is
a telemetry gap; without --workspace the platform's console lines are not
read. Profiles are never served on this backend's CLI.
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
    emit,
    exit_code,
    failures,
    kql_in,
    la_call,
    la_rows,
    render_commands,
    render_failures,
    resolve_window,
    run_many,
    table,
)

SEVERITY = {0: "verbose", 1: "information", 2: "warning", 3: "error", 4: "critical"}


def probe(ns, frm: str, to: str) -> dict:
    svc = kql_in("cloud_RoleName", ns.service or [])
    report: dict = {
        "window": [frm, to],
        "component": None,
        "workspace": None,
        "failed": [],
        "commands": [],
    }
    calls, tags = [], []
    if ns.app:
        kqls = {
            "tables": f"union requests, dependencies, traces, customMetrics, exceptions {svc}| summarize n=count() by cloud_RoleName, itemType",
            "environment": f"union requests, dependencies, traces, customMetrics {svc}| summarize n=count() by cloud_RoleName, env_name=tostring(customDimensions['deployment.environment.name']), env_old=tostring(customDimensions['deployment.environment']), version=tostring(customDimensions['service.version']), instance=tostring(customDimensions['service.instance.id'])",
            "operations": f"requests {svc}| summarize n=count(), failed=countif(success == false) by cloud_RoleName, name | order by n desc",
            "metrics": f"customMetrics {svc}| summarize rows=count(), points=sum(valueCount), max_value_count=max(valueCount) by cloud_RoleName, name | order by cloud_RoleName asc, name asc",
            "severities": f"traces {svc}| summarize n=count() by cloud_RoleName, severityLevel | order by cloud_RoleName asc, severityLevel asc",
            "exceptions": f"exceptions {svc}| summarize n=count() by cloud_RoleName, type | order by n desc",
        }
        for k, q in kqls.items():
            calls.append(ai_call(ns.app, q, frm, to))
            tags.append(("component", k))
    if ns.workspace:
        wq = {
            "cl_tables": "union withsource=T *_CL | summarize n=count() by T | order by n desc",
            "containers": f"{ns.console_table} | summarize n=count(), latest=max(TimeGenerated) by {ns.container_column} | order by n desc",
        }
        for k, q in wq.items():
            calls.append(la_call(ns.workspace, q, frm, to))
            tags.append(("workspace", k))
    results = run_many(calls)
    report["commands"] = commands(results)
    report["failed"] = failures(results)
    got = {tag: r for tag, r in zip(tags, results)}

    if ns.app:
        comp: dict = {"services": {}, "gap": None}
        rows = lambda k: (
            ai_rows(got[("component", k)].data) if got[("component", k)].ok else []
        )
        for r in rows("tables"):
            e = comp["services"].setdefault(r["cloud_RoleName"], _empty())
            e["tables"][r["itemType"]] = r["n"]
        for r in rows("environment"):
            e = comp["services"].setdefault(r["cloud_RoleName"], _empty())
            e["resource"].append(
                {
                    "environment": r["env_name"] or r["env_old"],
                    "environment_key": "deployment.environment.name"
                    if r["env_name"]
                    else ("deployment.environment" if r["env_old"] else None),
                    "version": r["version"],
                    "instance": r["instance"],
                    "rows": r["n"],
                }
            )
        for r in rows("operations"):
            e = comp["services"].setdefault(r["cloud_RoleName"], _empty())
            e["operations"].append(
                {"name": r["name"], "n": r["n"], "failed": r["failed"]}
            )
        for r in rows("metrics"):
            e = comp["services"].setdefault(r["cloud_RoleName"], _empty())
            e["metrics"].append(
                {
                    "name": r["name"],
                    "rows": r["rows"],
                    "points": r["points"],
                    "aggregated": (r.get("max_value_count") or 0) > 1,
                }
            )
        for r in rows("severities"):
            e = comp["services"].setdefault(r["cloud_RoleName"], _empty())
            e["severities"][
                SEVERITY.get(r["severityLevel"], str(r["severityLevel"]))
            ] = r["n"]
        for r in rows("exceptions"):
            e = comp["services"].setdefault(r["cloud_RoleName"], _empty())
            e["exceptions"].append({"type": r["type"], "n": r["n"]})
        for s in ns.service or []:
            comp["services"].setdefault(s, _empty())
        for e in comp["services"].values():
            envs = sorted({x["environment"] for x in e["resource"] if x["environment"]})
            e["environment"] = envs[0] if len(envs) == 1 else (envs or None)
            keys = sorted(
                {x["environment_key"] for x in e["resource"] if x["environment_key"]}
            )
            e["environment_read_from"] = (
                ", ".join(keys)
                if keys
                else "nothing (neither deployment.environment.name nor deployment.environment on the rows)"
            )
        report["component"] = comp
    else:
        report["component"] = {
            "gap": "no app_insights_app: requests, dependencies, customMetrics, traces and exceptions are not queryable - distributed tracing is a telemetry gap and the run is logs-only"
        }
    if ns.workspace:
        ws: dict = {
            "cl_tables": [],
            "containers": [],
            "console_table": ns.console_table,
        }
        r = got[("workspace", "cl_tables")]
        ws["cl_tables"] = (
            [{"table": x["T"], "n": x["n"]} for x in la_rows(r.data)] if r.ok else []
        )
        r = got[("workspace", "containers")]
        ws["containers"] = (
            [
                {
                    "container": x[ns.container_column],
                    "n": x["n"],
                    "latest": x["latest"],
                }
                for x in la_rows(r.data)
            ]
            if r.ok
            else []
        )
        report["workspace"] = ws
    else:
        report["workspace"] = {
            "gap": "no workspace: the platform's console and system tables are not read"
        }
    report["profiles"] = "not served on the CLI (portal-only Profiler)"
    return report


def _empty() -> dict:
    return {
        "tables": {},
        "resource": [],
        "operations": [],
        "metrics": [],
        "severities": {},
        "exceptions": [],
    }


def render(r: dict, top: int) -> str:
    out = [f"window {r['window'][0]}..{r['window'][1]}"]
    c = r["component"]
    if c.get("gap"):
        out.append("component  GAP: " + c["gap"])
    else:
        for s, e in c["services"].items():
            out.append(f"== {s}")
            t = e["tables"]
            out.append(
                "  tables     "
                + (
                    " ".join(f"{k}={v}" for k, v in sorted(t.items()))
                    or "(no rows in the window)"
                )
            )
            out.append(
                f"  environment {e['environment'] or '(none)'}  read from: {e['environment_read_from']}"
            )
            for x in e["resource"][:6]:
                out.append(
                    f"             version={x['version'] or '-'} instance={x['instance'] or '-'} rows={x['rows']}"
                )
            out.append(
                f"  operations {len(e['operations'])} names"
                + ("" if e["operations"] else "  (none)")
            )
            out += (
                table(e["operations"][:top], ["name", "n", "failed"], "             ")
                if e["operations"]
                else []
            )
            out.append(
                f"  metrics    {len(e['metrics'])} customMetrics names"
                + (
                    ""
                    if e["metrics"]
                    else "  (none - the service exports none, or the window is empty)"
                )
            )
            out += (
                table(
                    e["metrics"],
                    ["name", "rows", "points", "aggregated"],
                    "             ",
                )
                if e["metrics"]
                else []
            )
            out.append(
                "  traces     "
                + (" ".join(f"{k}={v}" for k, v in e["severities"].items()) or "(none)")
            )
            out.append(
                "  exceptions "
                + (
                    ", ".join(f"{x['type']}={x['n']}" for x in e["exceptions"][:8])
                    or "(none)"
                )
            )
    w = r["workspace"]
    if w.get("gap"):
        out.append("workspace  GAP: " + w["gap"])
    else:
        out.append(
            "workspace  *_CL tables with rows: "
            + (", ".join(f"{x['table']}={x['n']}" for x in w["cl_tables"]) or "(none)")
        )
        out.append(
            f"           containers in {w['console_table']}: "
            + (
                ", ".join(f"{x['container']}={x['n']}" for x in w["containers"])
                or "(none)"
            )
        )
    out.append("profiles   " + r["profiles"])
    out += render_failures(r)
    out += render_commands(r)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--app")
    ap.add_argument("--workspace")
    ap.add_argument("--service", action="append")
    ap.add_argument("--console-table", default="ContainerAppConsoleLogs_CL")
    ap.add_argument("--container-column", default="ContainerName_s")
    ap.add_argument("--top", type=int, default=15)
    add_window(ap)
    ns = ap.parse_args()
    if not ns.app and not ns.workspace:
        ap.error("--app <app_insights_app> and/or --workspace <workspace> is required")
    frm, to = resolve_window(ns)
    r = probe(ns, frm, to)
    emit(r, ns.json, lambda o: render(o, ns.top))
    return exit_code(r)


if __name__ == "__main__":
    sys.exit(main())
