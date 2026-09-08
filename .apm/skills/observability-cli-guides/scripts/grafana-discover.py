#!/usr/bin/env python3
"""What a Grafana stack holds for a set of services inside a window, in one call.

The queries are fixed by the inputs - service names and a window - so nothing
here is for an agent to compose: per service it lists the metric names the
store carries, the operations its traces are rooted at (with counts), its
log line count and severities, and whether a CPU profile exists. Presence
and absence are reported with the same weight, and every gcx command run is
printed so the report can record it.

    grafana-discover.py svc-a svc-b --from 2026-09-08T16:40:53Z --to 2026-09-08T16:42:55Z
    grafana-discover.py svc-a --since 30m --json

Whole surface: service names (positional, required), a window (--from/--to or
--since), --label-key (the label a service is named by on metrics, logs and
profiles - default service_name, the OTel resource convention; a scrape-based
Prometheus names it job), --json. Traces are always selected on the resource
attribute service.name. Reads GCX_CONFIG. Exit 0 when every probe ran, 2 when
one failed outright (the failure is in the output).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grafana_gcx import (
    CPU_PROFILE,
    TRACE_LIMIT,
    add_window,
    commands,
    emit,
    flame_frames,
    label_names,
    logs_all,
    prom_series,
    resolve_window,
    run_many,
    traces_list,
)


def probe(services: list[str], frm: str, to: str, key: str = "service_name") -> dict:
    win = ["--from", frm, "--to", to]
    calls = []
    for s in services:
        calls += [
            ["metrics", "series", f'{{{key}="{s}"}}', *win],
            [
                "traces",
                "query",
                f'{{ resource.service.name = "{s}" }}',
                *win,
                "--limit",
                str(TRACE_LIMIT),
            ],
            [
                "profiles",
                "query",
                f'{{{key}="{s}"}}',
                "--profile-type",
                CPU_PROFILE,
                *win,
            ],
        ]
    calls.append(["profiles", "labels", "--label", key, *win])
    results = run_many(calls)
    all_results = list(results)
    prof_services = label_names(results[-1].data) if results[-1].ok else []
    report = {
        "window": [frm, to],
        "services": {},
        "failed": [],
        "profiled_services": prof_services,
    }
    for i, s in enumerate(services):
        m, t, p = results[i * 3 : i * 3 + 3]
        lines, log_results, log_truncated = logs_all(f'{{{key}="{s}"}}', frm, to)
        all_results += log_results
        entry: dict = {}
        for r in (m, t, p, *log_results):
            if not r.ok:
                report["failed"].append({"command": r.command, "error": r.error})
        names = (
            sorted({x.get("__name__", "") for x in prom_series(m.data)} - {""})
            if m.ok
            else []
        )
        entry["metrics"] = {"names": len(names), "list": names}
        traces = traces_list(t.data) if t.ok else []
        rooted = [x for x in traces if x.get("rootServiceName") == s]
        ops: dict[str, int] = {}
        for x in rooted:
            ops[x.get("rootTraceName", "")] = ops.get(x.get("rootTraceName", ""), 0) + 1
        entry["traces"] = {
            "matching": len(traces),
            "rooted_here": len(rooted),
            "truncated": len(traces) >= TRACE_LIMIT,
            "operations": dict(sorted(ops.items(), key=lambda kv: -kv[1])),
        }
        sev: dict[str, int] = {}
        for ln in lines:
            k = (
                ln["meta"].get("severity_text")
                or ln["meta"].get("detected_level")
                or "?"
            ).upper()
            sev[k] = sev.get(k, 0) + 1
        entry["logs"] = {
            "lines": len(lines),
            "truncated": log_truncated,
            "severity": sev,
        }
        total, frames = flame_frames(p.data) if p.ok else (0, {})
        entry["profile_cpu"] = {
            "present": total > 0,
            "total_ns": total,
            "frames": len(frames),
        }
        report["services"][s] = entry
    report["commands"] = commands(all_results)
    return report


def render(r: dict) -> str:
    out = []
    for s, e in r["services"].items():
        out.append(f"== {s}")
        m = e["metrics"]
        out.append(
            f"  metrics   {m['names']} names"
            + (
                ": " + ", ".join(m["list"][:12]) + (" ..." if m["names"] > 12 else "")
                if m["names"]
                else "  (none)"
            )
        )
        t = e["traces"]
        out.append(
            f"  traces    {t['matching']} traces carry a span of this service, {t['rooted_here']} rooted at it"
            + (
                " (search ceiling reached - count with grafana-traces.py count)"
                if t["truncated"]
                else ""
            )
        )
        for op, n in list(t["operations"].items())[:15]:
            out.append(f"              {n:6d}  {op}")
        lg = e["logs"]
        out.append(
            f"  logs      {lg['lines']} lines"
            + (
                " (still truncated after splitting - narrow the window)"
                if lg["truncated"]
                else ""
            )
            + "  "
            + " ".join(f"{k}={v}" for k, v in sorted(lg["severity"].items()))
        )
        pc = e["profile_cpu"]
        out.append(
            "  profiles  "
            + (
                f"cpu {round(pc['total_ns'] / 1e9, 2)} s over {pc['frames']} frames"
                if pc["present"]
                else "no cpu profile in the window"
            )
        )
    if r["profiled_services"]:
        out.append(
            "profiled service names in the store: " + ", ".join(r["profiled_services"])
        )
    for f in r["failed"]:
        out.append(f"FAILED  {f['command']}\n        {f['error']}")
    out += ["queries run (record these):"] + ["  " + c for c in r.get("commands", [])]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("services", nargs="+")
    ap.add_argument(
        "--label-key",
        default="service_name",
        help="label naming a service on metrics, logs and profiles (default service_name)",
    )
    add_window(ap)
    ns = ap.parse_args()
    frm, to = resolve_window(ns)
    r = probe(ns.services, frm, to, ns.label_key)
    emit(r, ns.json, render)
    return 2 if r["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
