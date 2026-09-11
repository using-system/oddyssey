#!/usr/bin/env python3
"""What a Seq store holds for a set of services inside a window, in one call.

    seq-discover.py --from 2026-09-11T07:15:00Z --to 2026-09-11T07:20:00Z
    seq-discover.py --service "Roastery Web Frontend" --since 30m --json

Whole surface: --service NAME (repeatable, none = every service the window
carries), --service-key PROP (the property a service is named by, default
Application; @Resource.service.name on an OTel-instrumented service), a
window (--from/--to or --since), --bucket DURATION (the time slice the data
distribution is reported in, default 1m), --sample N (the newest events
whose property names are inventoried, default 200), --json. Per service
it reports the log-event count and its levels, the span count, the
distinct trace count, the exception count, the root-span operations (by
@MessageTemplate, with counts), the metric definitions the service emits
and its series point count, and the deployment environment's evidence:
how many events carry a @Resource object and the distinct identities it
names (service.name, service.instance.id, deployment.environment.name,
service.version, with counts - `none` when no event carries one), which
environment-naming properties are present when there is no resource
(Environment, EnvironmentName, MachineName, host.name,
deployment.environment.name, Origin - the count of each, and their
distinct values), and how many events carry a gen_ai.* attribute (event or
resource); for the window it reports which slices actually hold events
(where the data sits in time), the property names the newest --sample
events carry, and the signals the store serves at all. Profiles are never
served. Exit 0 when every probe ran, 2 when one failed (the failure is in
the output).
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
    emit,
    errors,
    render_commands,
    resolve_window,
    run_many,
    service_clause,
    slices,
    sql_where,
    table,
    window_flags,
)

NO_KEY = "(no value)"
# Where an event names its deployment environment when it carries no
# @Resource: the OTel resource attribute unflattened onto the event, the
# .NET and Serilog conventions, the host, and the sample data's own marker.
ENV_PROPS = ["Environment", "EnvironmentName", "MachineName", "host.name", "deployment.environment.name", "Origin"]
IDENTITY = ["service.name", "service.instance.id", "deployment.environment.name", "service.version"]


def _key(v) -> str:
    return NO_KEY if v is None else str(v)


def probe(services: list[str], key: str, frm: str, to: str, bucket: str, sample: int = 200) -> dict:
    svc = service_clause(services, key)
    w = sql_where(svc)
    id_cols = ", ".join(f"@Resource.{a}" for a in IDENTITY)
    env_flags = ", ".join(f"has({p})" for p in ENV_PROPS)
    gen_ai = "has(gen_ai) or has(@Resource.gen_ai) or has(@Properties['gen_ai.system'])"
    sql = [
        f"select count(*) as n, count(distinct(@TraceId)) as traces from stream{w} group by {key}, has(@Start)",
        f"select count(*) as n from stream{sql_where('not has(@Start)', svc)} group by {key}, @Level",
        f"select count(*) as n from stream{sql_where('has(@Start) and not has(@ParentId)', svc)} group by {key}, @MessageTemplate",
        f"select count(*) as n from stream{w} group by time({bucket})",
        f"select count(*) as n from stream{sql_where('has(@Exception)', svc)} group by {key}",
        f"select count(*) as n from series{w} group by {key}",
        f"select count(*) as n from stream{sql_where('has(@Resource)', svc)} group by {key}, {id_cols}",
        f"select count(*) as n from stream{w} group by {key}, has(@Resource), {env_flags}",
        f"select count(*) as n from stream{sql_where('(' + gen_ai + ')', svc)} group by {key}",
    ]
    n_sql = len(sql)
    calls = [(["query", "-q", q, *window_flags(frm, to), "--json"], "object") for q in sql]
    metrics_args = ["metrics", "search", "-c", "512", *window_flags(frm, to), "--json"]
    if svc:
        metrics_args[2:2] = ["-f", svc]
    calls.append((metrics_args, "object"))
    sample_args = ["search", "-c", str(sample), *window_flags(frm, to), "--json"]
    if svc:
        sample_args[1:1] = ["-f", svc]
    calls.append((sample_args, "ndjson"))
    results = run_many(calls)
    from seq_cli import _normalise_query  # the query envelope, normalised like query() does

    for r in results[:n_sql]:
        if r.ok:
            r.data = _normalise_query(r.data)
    counts, levels, roots, dist, exc, points, identities, envflags, genai, mdefs, sampled = results
    report: dict = {"window": [frm, to], "services": {}, "signals": {}, "data_slices": [], "failed": []}
    per: dict[str, dict] = {}

    def svc_entry(name):
        return per.setdefault(
            name,
            {
                "logs": 0,
                "spans": 0,
                "traces": 0,
                "levels": {},
                "exceptions": 0,
                "root_operations": {},
                "metric_points": 0,
                "resource_events": 0,
                "resource_identities": [],
                "environment_properties": {},
                "gen_ai_events": 0,
            },
        )

    for row in table(counts):
        e = svc_entry(_key(row.get(key)))
        if row.get("has(@Start)"):
            e["spans"] = row.get("n") or 0
            e["traces"] = max(e["traces"], row.get("traces") or 0)
        else:
            e["logs"] = row.get("n") or 0
            e["traces"] = max(e["traces"], row.get("traces") or 0)
    for row in table(levels):
        svc_entry(_key(row.get(key)))["levels"][_key(row.get("@Level"))] = row.get("n") or 0
    for row in table(roots):
        svc_entry(_key(row.get(key)))["root_operations"][_key(row.get("@MessageTemplate"))] = row.get("n") or 0
    for row in table(exc):
        svc_entry(_key(row.get(key)))["exceptions"] = row.get("n") or 0
    for row in table(points):
        svc_entry(_key(row.get(key)))["metric_points"] = row.get("n") or 0
    for row in table(identities):
        svc_entry(_key(row.get(key)))["resource_identities"].append(
            {a: row.get(f"@Resource.{a}") for a in IDENTITY} | {"events": row.get("n") or 0}
        )
    for row in table(envflags):
        e = svc_entry(_key(row.get(key)))
        n = row.get("n") or 0
        if row.get("has(@Resource)"):
            e["resource_events"] += n
        for p in ENV_PROPS:
            if row.get(f"has({p})"):
                e["environment_properties"][p] = e["environment_properties"].get(p, 0) + n
    for row in table(genai):
        svc_entry(_key(row.get(key)))["gen_ai_events"] = row.get("n") or 0
    present = sorted({p for e in per.values() for p in e["environment_properties"]})
    values = run_many([(["query", "-q", f"select distinct({p}) from stream{w}", *window_flags(frm, to), "--json"], "object") for p in present])
    for r in values:
        if r.ok:
            r.data = _normalise_query(r.data)
    report["environment_values"] = {
        p: sorted(str(v) for v in (row[0] for row in (r.data or {}).get("rows") or []) if v is not None)[:20]
        for p, r in zip(present, values)
    }
    keys: dict[str, int] = {}
    for ev in sampled.data or []:
        for k in ev:
            keys[k] = keys.get(k, 0) + 1
    report["sampled_keys"] = dict(sorted(keys.items(), key=lambda kv: (-kv[1], kv[0])))
    report["sampled_events"] = len(sampled.data or [])
    results = [*results, *values]
    if mdefs.ok and isinstance(mdefs.data, dict):
        cols = mdefs.data.get("Columns") or []
        defs = [dict(zip(cols, r)) for r in mdefs.data.get("Rows") or []]
        report["metric_definitions"] = [
            {"name": d.get("Name"), "kind": d.get("Kind"), "unit": d.get("Unit")} for d in defs
        ]
    for name, e in per.items():
        e["root_operations"] = dict(sorted(e["root_operations"].items(), key=lambda kv: -kv[1])[:15])
        e["levels"] = dict(sorted(e["levels"].items(), key=lambda kv: -kv[1]))
    for s in services:
        svc_entry(s)
    report["services"] = dict(sorted(per.items(), key=lambda kv: -(kv[1]["logs"] + kv[1]["spans"])))
    report["data_slices"] = [{"time": s["time"], "events": s.get("n") or 0} for s in slices(dist) if (s.get("n") or 0) > 0]
    total_logs = sum(e["logs"] for e in per.values())
    total_spans = sum(e["spans"] for e in per.values())
    total_points = sum(e["metric_points"] for e in per.values())
    report["signals"] = {
        "logs": total_logs,
        "traces": total_spans,
        "metrics": total_points,
        "profiles": "not served",
    }
    report["environment"] = {
        "resource_events": sum(e["resource_events"] for e in per.values()),
        "resource_identities": "none" if not any(e["resource_identities"] for e in per.values()) else "per service",
        "environment_properties": {p: sum(e["environment_properties"].get(p, 0) for e in per.values()) for p in present},
        "gen_ai_events": sum(e["gen_ai_events"] for e in per.values()),
        "read_from": (
            "@Resource (the OTel resource, unflattened: @Resource.deployment.environment.name)"
            if any(e["resource_events"] for e in per.values())
            else ("the event properties " + ", ".join(present) if present else "nothing: no event carries a resource or an environment-naming property")
        ),
    }
    report["failed"] = [{"command": r.command, "error": r.error} for r in results if not r.ok]
    report["error"] = errors(results)
    report["commands"] = commands(results)
    return report


def render(o: dict) -> str:
    out = [f"window {o['window'][0]} .. {o['window'][1]}"]
    sig = o["signals"]
    out.append(f"signals: logs={sig['logs']} spans={sig['traces']} metric points={sig['metrics']} profiles={sig['profiles']}")
    if o["data_slices"]:
        out.append("data sits in: " + ", ".join(f"{s['time'][11:16]}({s['events']})" for s in o["data_slices"]))
    else:
        out.append("data sits in: nothing in this window")
    env = o["environment"]
    out.append(
        f"environment: events with @Resource={env['resource_events']} (identities: {env['resource_identities']}); "
        + ("environment-naming properties: " + ", ".join(f"{p}={n}" for p, n in env["environment_properties"].items()) if env["environment_properties"] else "environment-naming properties: none")
        + f"; gen_ai events={env['gen_ai_events']}"
    )
    out.append("  read the environment from: " + env["read_from"])
    for p, vals in o.get("environment_values", {}).items():
        out.append(f"  {p} values: " + (", ".join(vals) if vals else "-"))
    out.append(f"  property names on the newest {o['sampled_events']} events: " + ", ".join(f"{k}({n})" for k, n in o["sampled_keys"].items()))
    for name, e in o["services"].items():
        out.append(f"{name}: logs={e['logs']} spans={e['spans']} traces={e['traces']} exceptions={e['exceptions']} metric points={e['metric_points']}")
        if e["levels"]:
            out.append("  levels: " + "  ".join(f"{k}={v}" for k, v in e["levels"].items()))
        for op, n in e["root_operations"].items():
            out.append(f"  root op {n:6d}  {op}")
        out.append(
            f"  resource events={e['resource_events']} gen_ai events={e['gen_ai_events']}"
            + (" env props: " + ", ".join(f"{p}={n}" for p, n in e["environment_properties"].items()) if e["environment_properties"] else " env props: none")
        )
        for ident in e["resource_identities"]:
            out.append("  identity " + " ".join(f"{a}={ident.get(a)}" for a in IDENTITY) + f" events={ident['events']}")
    if o.get("metric_definitions"):
        out.append("metrics: " + ", ".join(f"{m['name']} ({m['kind']}, {m['unit']})" for m in o["metric_definitions"]))
    for f in o["failed"]:
        out.append(f"FAILED {f['command']}: {f['error']}")
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_service(ap)
    ap.add_argument("--bucket", default="1m", help="time slice for the data distribution (default 1m)")
    ap.add_argument("--sample", type=int, default=200, help="newest events whose property names are inventoried (default 200)")
    add_window(ap)
    ns = ap.parse_args()
    frm, to = resolve_window(ns)
    out = probe(ns.service, ns.service_key, frm, to, ns.bucket, ns.sample)
    emit(out, ns.json, render)
    return 2 if out["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
