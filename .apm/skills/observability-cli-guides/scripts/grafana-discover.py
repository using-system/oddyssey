#!/usr/bin/env python3
"""What a Grafana stack holds for a set of services inside a window, in one call.

The queries are fixed by the inputs - service names and a window - so nothing
here is for an agent to compose: per service it lists the metric names the
store carries, the operations its traces name (root spans, with counts), its
log line count and severities, and whether a CPU profile exists. Presence and
absence are reported with the same weight.

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
    LOG_LIMIT,
    TRACE_LIMIT,
    add_window,
    emit,
    flame_frames,
    label_names,
    logs_lines,
    prom_series,
    run_many,
    traces_list,
    window_args,
)


def probe(services: list[str], win: list[str], key: str = "service_name") -> dict:
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
                "logs",
                "query",
                f'{{{key}="{s}"}}',
                *win,
                "--limit",
                str(LOG_LIMIT),
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
    prof_services = label_names(results[-1].data) if results[-1].ok else []
    report = {
        "window": win,
        "services": {},
        "failed": [],
        "profiled_services": prof_services,
    }
    for i, s in enumerate(services):
        m, t, l, p = results[i * 4 : i * 4 + 4]
        entry: dict = {}
        for r in (m, t, l, p):
            if not r.ok:
                report["failed"].append({"command": r.command, "error": r.error})
        names = (
            sorted({x.get("__name__", "") for x in prom_series(m.data)} - {""})
            if m.ok
            else []
        )
        entry["metrics"] = {"names": len(names), "list": names}
        traces = traces_list(t.data) if t.ok else []
        ops: dict[str, int] = {}
        for x in traces:
            ops[x.get("rootTraceName", "")] = ops.get(x.get("rootTraceName", ""), 0) + 1
        entry["traces"] = {
            "roots": len(traces),
            "truncated": len(traces) >= TRACE_LIMIT,
            "operations": dict(sorted(ops.items(), key=lambda kv: -kv[1])),
        }
        lines = logs_lines(l.data) if l.ok else []
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
            "truncated": len(lines) >= LOG_LIMIT,
            "severity": sev,
        }
        total, frames = flame_frames(p.data) if p.ok else (0, {})
        entry["profile_cpu"] = {
            "present": total > 0,
            "total_ns": total,
            "frames": len(frames),
        }
        report["services"][s] = entry
    return report


def render(r: dict) -> str:
    out = []
    for s, e in r["services"].items():
        out.append(f"== {s}")
        out.append(
            f"  metrics   {e['metrics']['names']} names"
            + (
                ": "
                + ", ".join(e["metrics"]["list"][:12])
                + (" ..." if e["metrics"]["names"] > 12 else "")
                if e["metrics"]["names"]
                else "  (none)"
            )
        )
        t = e["traces"]
        out.append(
            f"  traces    {t['roots']} root traces{' (truncated at the search ceiling - count in bins)' if t['truncated'] else ''}"
        )
        for op, n in list(t["operations"].items())[:15]:
            out.append(f"              {n:6d}  {op}")
        lg = e["logs"]
        out.append(
            f"  logs      {lg['lines']} lines{' (truncated)' if lg['truncated'] else ''}  "
            + " ".join(f"{k}={v}" for k, v in sorted(lg["severity"].items()))
        )
        pc = e["profile_cpu"]
        out.append(
            f"  profiles  {'cpu ' + str(round(pc['total_ns'] / 1e9, 2)) + ' s over ' + str(pc['frames']) + ' frames' if pc['present'] else 'no cpu profile in the window'}"
        )
    if r["profiled_services"]:
        out.append(
            "profiled service names in the store: " + ", ".join(r["profiled_services"])
        )
    for f in r["failed"]:
        out.append(f"FAILED  {f['command']}\n        {f['error']}")
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
    r = probe(ns.services, window_args(ns), ns.label_key)
    emit(r, ns.json, render)
    return 2 if r["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
