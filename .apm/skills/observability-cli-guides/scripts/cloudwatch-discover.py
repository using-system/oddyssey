#!/usr/bin/env python3
"""What the window holds per service, across the two log groups, the EMF namespaces and X-Ray, in one call.

    cloudwatch-discover.py --profile <profile> --region <region> --log-group <log_group> --metrics-log-group <metrics_log_group> --since 30m
    cloudwatch-discover.py --profile <profile> --region <region> --log-group <log_group> --metrics-log-group <metrics_log_group> --service orders-api --namespace <namespace> --from ... --to ... --json

Whole surface: --profile, --region, --log-group (the application logs
group), --metrics-log-group (the EMF group) - all four required -,
--service (repeatable; none = every resource.service.name the window
carries), --namespace (repeatable; none = every namespace the EMF group's
records declare in the window), --xray-group (an X-Ray group name for the
service graph; omitted, the default group), a window (--from/--to or
--since), --json. Exit 0 when every probe ran, 1 when one failed (the
failure is in the output).

The logs side reads each group's freshness (the Logs Insights
max(@timestamp) probe, never a stream's lastEventTimestamp), the records
per resource.service.name and severity, and the deployment environment off
the resource attributes the records carry (resource.deployment.environment.name,
falling back to resource.deployment.environment) with service.version and
the instance ids. The metrics side reads the namespaces the EMF records
declare, whether the records carry resource fields at all (the ispresent
guard the edge diff needs), then list-metrics per namespace for the metric
names and their dimension sets (one CloudWatch series per dimension-set
variant: the fan-out is counted, not listed). The traces side is the X-Ray
service graph: every node with its request count, error, fault and throttle
rates and mean response time, the ones named by --service marked. Profiles
are CodeGuru Profiler, a separate service: the profiling groups are listed,
and none is stated as the gap it is.
"""

from __future__ import annotations

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cloudwatch_aws import (
    add_targeting,
    add_window,
    commands,
    cw_in,
    emit,
    epoch_s,
    exit_code,
    failures,
    insights_many,
    iso,
    register_targets,
    render_commands,
    render_failures,
    resolve_window,
    run_many,
    severity_text,
    table,
    xray_range,
)


def probe(ns, frm, to) -> dict:
    svc = cw_in("resource.service.name", ns.service or [])
    report: dict = {
        "window": [iso(frm), iso(to)],
        "services_asked": ns.service or [],
        "logs": {},
        "metrics": {},
        "traces": {},
        "profiles": {},
        "commands": [],
        "failed": [],
    }
    results = []

    # --- stage 1: everything independent, at once ---------------------------
    specs = [
        (
            [ns.log_group],
            "stats max(@timestamp) as newest, min(@timestamp) as oldest, count() as n",
        ),
        (
            [ns.log_group],
            (
                svc
                + "| stats count() as n, max(@timestamp) as last by `resource.service.name`, severity_number"
            ).lstrip("| "),
        ),
        (
            [ns.log_group],
            (
                svc
                + "| stats count() as n, max(@timestamp) as last by `resource.service.name`, `resource.deployment.environment.name`, `resource.deployment.environment`, `resource.service.version`, `resource.service.instance.id`"
            ).lstrip("| "),
        ),
        (
            [ns.metrics_log_group],
            "stats max(@timestamp) as newest, count() as n by `_aws.CloudWatchMetrics.0.Namespace`",
        ),
        (
            [ns.metrics_log_group],
            "stats sum(ispresent(`resource.service.name`)) as with_service, sum(ispresent(`resource.service.instance.id`)) as with_instance, count() as n",
        ),
    ]
    graph_args = [
        "xray",
        "get-service-graph",
        "--start-time",
        str(epoch_s(frm)),
        "--end-time",
        str(epoch_s(to)),
    ]
    if ns.xray_group:
        graph_args += ["--group-name", ns.xray_group]
    aws_calls = [
        ["logs", "describe-log-groups", "--log-group-name-prefix", ns.log_group],
        [
            "logs",
            "describe-log-groups",
            "--log-group-name-prefix",
            ns.metrics_log_group,
        ],
        graph_args,
        ["codeguruprofiler", "list-profiling-groups", "--include-description"],
    ]
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_ins = pool.submit(insights_many, specs, frm, to, ns.profile, ns.region)
        f_aws = pool.submit(run_many, aws_calls, ns.profile, ns.region)
        ins, aws = f_ins.result(), f_aws.result()
    results += ins + aws
    fresh_logs, by_sev, env, ns_rows, guard = ins
    g_logs, g_metrics, graph, prof = aws

    # --- logs ----------------------------------------------------------------
    def group_facts(r, name):
        if not r.ok:
            return {"error": r.error, "kind": r.kind}
        found = [
            g
            for g in (r.data or {}).get("logGroups", [])
            if g.get("logGroupName") == name
        ]
        if not found:
            return {"exists": False}
        g = found[0]
        return {
            "exists": True,
            "retention_days": g.get("retentionInDays"),
            "stored_bytes": g.get("storedBytes"),
        }

    logs = report["logs"]
    logs["group"] = group_facts(g_logs, ns.log_group)
    if fresh_logs.ok and fresh_logs.data:
        logs["freshness"] = {
            "newest": fresh_logs.data[0].get("newest"),
            "oldest": fresh_logs.data[0].get("oldest"),
            "records": fresh_logs.data[0].get("n", 0),
        }
    logs["by_service_severity"] = []
    if by_sev.ok:
        for row in by_sev.data or []:
            logs["by_service_severity"].append(
                {
                    "service": row.get("resource.service.name"),
                    "severity_number": row.get("severity_number"),
                    "severity": severity_text(row.get("severity_number")),
                    "records": row.get("n", 0),
                    "last": row.get("last"),
                }
            )
        logs["by_service_severity"].sort(
            key=lambda r: (str(r["service"]), r["severity_number"] or 0)
        )
    logs["services"] = sorted(
        {r["service"] for r in logs["by_service_severity"] if r["service"]}
    )
    logs["environment"] = []
    if env.ok:
        for row in env.data or []:
            logs["environment"].append(
                {
                    "service": row.get("resource.service.name"),
                    "environment": row.get("resource.deployment.environment.name")
                    or row.get("resource.deployment.environment"),
                    "version": row.get("resource.service.version"),
                    "instance_id": row.get("resource.service.instance.id"),
                    "records": row.get("n", 0),
                    "last": row.get("last"),
                }
            )

    # --- metrics -------------------------------------------------------------
    met = report["metrics"]
    met["group"] = group_facts(g_metrics, ns.metrics_log_group)
    met["namespaces"] = []
    if ns_rows.ok:
        for row in ns_rows.data or []:
            name = row.get("_aws.CloudWatchMetrics.0.Namespace")
            if name:
                met["namespaces"].append(
                    {
                        "namespace": name,
                        "records": row.get("n", 0),
                        "newest": row.get("newest"),
                    }
                )
    if guard.ok and guard.data:
        g0 = guard.data[0]
        met["resource_fields"] = {
            "records": g0.get("n", 0),
            "with_service_name": g0.get("with_service", 0),
            "with_instance_id": g0.get("with_instance", 0),
        }
        met["resource_fields"]["note"] = (
            "the EMF records carry no resource fields: an edge diff cannot be qualified by instance here - attribute a series through the log records' instance id (the environment table above) and check the probe's reset flag"
            if not g0.get("with_instance", 0)
            else "the EMF records carry resource.service.instance.id: the edge diff groups by it"
        )
    wanted = ns.namespace or [n["namespace"] for n in met["namespaces"]]
    for n in wanted:
        register_targets(
            namespace=n
        )  # a discovered namespace names the company as often as a persisted one
    met["by_namespace"] = []
    if wanted:
        lm = run_many(
            [["cloudwatch", "list-metrics", "--namespace", n] for n in wanted],
            ns.profile,
            ns.region,
        )
        results += lm
        for name, r in zip(wanted, lm):
            entry = {"namespace": name, "metrics": []}
            if not r.ok:
                entry["error"] = r.error
                met["by_namespace"].append(entry)
                continue
            per = collections.defaultdict(
                lambda: {"series": 0, "dimension_sets": collections.Counter()}
            )
            for mtr in (r.data or {}).get("Metrics", []):
                d = per[mtr.get("MetricName")]
                d["series"] += 1
                d["dimension_sets"][
                    tuple(sorted(x.get("Name") for x in mtr.get("Dimensions", [])))
                ] += 1
            for mname in sorted(per):
                sets = per[mname]["dimension_sets"]
                fullest = max(sets, key=len) if sets else ()
                entry["metrics"].append(
                    {
                        "metric": mname,
                        "series": per[mname]["series"],
                        "dimension_sets": len(sets),
                        "full_dimension_set": list(fullest),
                    }
                )
            met["by_namespace"].append(entry)

    # --- traces --------------------------------------------------------------
    tr = report["traces"]
    if graph.ok:
        nodes = []
        for s in (graph.data or {}).get("Services", []):
            st = s.get("SummaryStatistics") or {}
            total = st.get("TotalCount", 0) or 0
            err = (st.get("ErrorStatistics") or {}).get("TotalCount", 0) or 0
            fault = (st.get("FaultStatistics") or {}).get("TotalCount", 0) or 0
            thr = (st.get("ErrorStatistics") or {}).get("ThrottleCount", 0) or 0
            nodes.append(
                {
                    "name": s.get("Name"),
                    "type": s.get("Type") or "-",
                    "root": bool(s.get("Root")),
                    "state": s.get("State"),
                    "requests": total,
                    "error_rate": round(err / total, 4) if total else None,
                    "fault_rate": round(fault / total, 4) if total else None,
                    "throttle_rate": round(thr / total, 4) if total else None,
                    "mean_response_s": round(
                        (st.get("TotalResponseTime") or 0) / total, 4
                    )
                    if total
                    else None,
                    "edges_to": [e.get("ReferenceId") for e in s.get("Edges", [])],
                    "reference_id": s.get("ReferenceId"),
                    "asked": s.get("Name") in (ns.service or []),
                }
            )
        byref = {n["reference_id"]: n["name"] for n in nodes}
        for n in nodes:
            n["edges_to"] = [byref.get(r, str(r)) for r in n["edges_to"]]
        tr["services"] = nodes
        tr["window_note"] = (
            "the graph's counts are the segments X-Ray indexed in the window; the summaries (cloudwatch-traces.py operations) are the per-trace population"
        )
        tr["missing"] = [
            s for s in (ns.service or []) if s not in {n["name"] for n in nodes}
        ]
    else:
        tr["error"] = graph.error

    # --- profiles ------------------------------------------------------------
    pr = report["profiles"]
    if prof.ok:
        groups = (prof.data or {}).get("profilingGroups", [])
        pr["profiling_groups"] = [g.get("name") for g in groups]
        pr["gap"] = not groups
        pr["note"] = (
            "no CodeGuru Profiler profiling group: profiles are a telemetry gap on this backend - say so, never substitute CPU metrics"
            if not groups
            else "CodeGuru Profiler groups exist: get-profile is the read (not shipped here)"
        )
    else:
        pr["error"] = prof.error
        pr["kind"] = prof.kind
        pr["gap"] = True
        pr["note"] = (
            "the profiling-group listing failed: state profiles as unverified, not as absent"
        )

    report["commands"] = commands(results)
    report["failed"] = failures(results)
    return report


def render(o: dict) -> str:
    out = [
        f"window {o['window'][0]} .. {o['window'][1]}"
        + (
            f", services asked: {', '.join(o['services_asked'])}"
            if o["services_asked"]
            else ""
        )
    ]
    lg = o["logs"]
    g = lg.get("group", {})
    fr = lg.get("freshness") or {}
    out.append(
        f"logs  <log_group>: {'resolves' if g.get('exists') else 'NOT resolved: ' + str(g)}; {fr.get('records', '-')} records in the window, newest {fr.get('newest') or '-'}"
    )
    out += table(
        lg.get("by_service_severity", []),
        ["service", "severity_number", "severity", "records", "last"],
    )
    if lg.get("environment"):
        out.append("  deployment environment off the resource attributes:")
        out += table(
            lg["environment"],
            ["service", "environment", "version", "instance_id", "records", "last"],
            indent="    ",
        )
    mt = o["metrics"]
    g = mt.get("group", {})
    out.append(
        f"metrics  <metrics_log_group>: {'resolves' if g.get('exists') else 'NOT resolved: ' + str(g)}; namespaces declared by the EMF records in the window:"
    )
    out += table(mt.get("namespaces", []), ["namespace", "records", "newest"])
    rf = mt.get("resource_fields")
    if rf:
        out.append(
            f"  resource fields on the EMF records: service.name on {rf['with_service_name']} of {rf['records']}, instance.id on {rf['with_instance_id']} - {rf['note']}"
        )
    for entry in mt.get("by_namespace", []):
        out.append(
            f"  namespace {entry['namespace']}"
            + (
                f": FAILED {entry['error']}"
                if entry.get("error")
                else " (list-metrics):"
            )
        )
        rows = [
            {**m, "full_dimension_set": ", ".join(m["full_dimension_set"])}
            for m in entry.get("metrics", [])
        ]
        out += table(
            rows,
            ["metric", "series", "dimension_sets", "full_dimension_set"],
            indent="    ",
        )
    tr = o["traces"]
    if tr.get("error"):
        out.append(f"traces  service graph FAILED: {tr['error']}")
    else:
        out.append(
            "traces  X-Ray service graph (nodes; a client node is the load generator's own root span, a remote node an upstream the service calls):"
        )
        rows = [
            {
                **n,
                "edges_to": ", ".join(n["edges_to"]) or "-",
                "asked": "*" if n["asked"] else "",
            }
            for n in tr.get("services", [])
        ]
        out += table(
            rows,
            [
                "asked",
                "name",
                "type",
                "state",
                "requests",
                "error_rate",
                "fault_rate",
                "throttle_rate",
                "mean_response_s",
                "edges_to",
            ],
        )
        if tr.get("missing"):
            out.append(
                f"  NOT in the graph: {', '.join(tr['missing'])} - no segment of that name in the window"
            )
        out.append("  " + tr.get("window_note", ""))
    pr = o["profiles"]
    out.append(
        f"profiles  {pr.get('note')}"
        + (f" [{pr.get('kind')}] {pr.get('error')}" if pr.get("error") else "")
    )
    out += render_failures(o)
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_targeting(ap, log_group=True, metrics_log_group=True)
    ap.add_argument("--service", action="append")
    ap.add_argument("--namespace", action="append")
    ap.add_argument("--xray-group")
    add_window(ap)
    ns = ap.parse_args()
    register_targets(
        log_group=ns.log_group,
        metrics_log_group=ns.metrics_log_group,
        xray=ns.xray_group,
        namespace=(ns.namespace[0] if ns.namespace else None),
    )
    frm, to = resolve_window(ns)
    xray_range(frm, to)
    o = probe(ns, frm, to)
    emit(o, ns.json, render)
    return exit_code(o)


if __name__ == "__main__":
    sys.exit(main())
