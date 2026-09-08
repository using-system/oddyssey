#!/usr/bin/env python3
"""Loki through gcx, on an OTLP-fed store: exact counts, severities, correlation, samples.

    grafana-logs.py count '{service_name="svc"}' --from ... --to ...
    grafana-logs.py severity '{service_name="svc"}' --from ... --to ...
    grafana-logs.py correlate '{service_name="svc"}' --from ... --to ...
    grafana-logs.py sample '{service_name="svc"}' --contains "rejected" --from ... --to ... [--limit 20]

Whole surface - every subcommand takes a LogQL stream SELECTOR, a window
(--from/--to or --since), --limit (default 5000 - the count is exact only
below it, and the output says when it was reached) and --json. sample adds
--contains TEXT (a line-body filter) and --severity REGEX (matched on the
severity_text structured metadata, the only place the level lives on an
OTLP store). Reads GCX_CONFIG. Exit 0 on success, 1 when gcx errored.

On an OTLP-fed Loki the level and the trace id are structured metadata, not
labels and not in the line: a `detected_level=~"warn"` matcher or a
`|= "<trace id>"` body match returns nothing. These commands read them where
they are.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grafana_gcx import (
    LOG_LIMIT,
    add_window,
    emit,
    logs_lines,
    run_gcx,
    run_many,
    window_args,
)


def _query(selector: str, win: list[str], limit: int, pipeline: str = ""):
    return [
        "logs",
        "query",
        selector + (" " + pipeline if pipeline else ""),
        *win,
        "--limit",
        str(limit),
    ]


def _level(ln: dict) -> str:
    return (
        ln["meta"].get("severity_text") or ln["meta"].get("detected_level") or "?"
    ).upper()


def cmd_count(ns) -> tuple[int, dict]:
    r = run_gcx(_query(ns.selector, window_args(ns), ns.limit))
    lines = logs_lines(r.data) if r.ok else []
    streams: dict[str, int] = {}
    for ln in lines:
        k = (
            ln["stream"].get("service_instance_id")
            or ln["stream"].get("service_name")
            or "?"
        )
        streams[k] = streams.get(k, 0) + 1
    return (0 if r.ok else 1), {
        "command": r.command,
        "error": r.error,
        "lines": len(lines),
        "truncated": len(lines) >= ns.limit,
        "by_stream": streams,
    }


def cmd_severity(ns) -> tuple[int, dict]:
    r = run_gcx(_query(ns.selector, window_args(ns), ns.limit))
    lines = logs_lines(r.data) if r.ok else []
    sev: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    for ln in lines:
        lv = _level(ln)
        sev[lv] = sev.get(lv, 0) + 1
        if lv not in ("INFO", "DEBUG", "?") and len(samples.setdefault(lv, [])) < 5:
            samples[lv].append(ln["line"][:200])
    return (0 if r.ok else 1), {
        "command": r.command,
        "error": r.error,
        "lines": len(lines),
        "truncated": len(lines) >= ns.limit,
        "severity": dict(sorted(sev.items(), key=lambda kv: -kv[1])),
        "samples": samples,
    }


def cmd_correlate(ns) -> tuple[int, dict]:
    win = window_args(ns)
    a, b = run_many(
        [
            _query(ns.selector, win, ns.limit),
            _query(ns.selector, win, ns.limit, '| trace_id != ""'),
        ]
    )
    total = logs_lines(a.data) if a.ok else []
    with_trace = logs_lines(b.data) if b.ok else []
    with_ids = {ln["timestamp"] + ln["line"] for ln in with_trace}
    orphans = [
        ln["line"][:160] for ln in total if ln["timestamp"] + ln["line"] not in with_ids
    ][:10]
    errs = [r.error for r in (a, b) if not r.ok]
    return (1 if errs else 0), {
        "error": "; ".join(errs),
        "lines": len(total),
        "with_trace_id": len(with_trace),
        "without": len(total) - len(with_trace),
        "truncated": max(len(total), len(with_trace)) >= ns.limit,
        "orphan_samples": orphans,
        "note": "startup and health-check lines legitimately carry no trace id - classify the orphans before calling this a gap",
    }


def cmd_sample(ns) -> tuple[int, dict]:
    pipe = []
    if ns.contains:
        pipe.append('|= "' + ns.contains.replace('"', '\\"') + '"')
    if ns.severity:
        pipe.append('| severity_text =~ "' + ns.severity + '"')
    r = run_gcx(_query(ns.selector, window_args(ns), ns.limit, " ".join(pipe)))
    lines = logs_lines(r.data) if r.ok else []
    return (0 if r.ok else 1), {
        "command": r.command,
        "error": r.error,
        "lines": len(lines),
        "truncated": len(lines) >= ns.limit,
        "samples": [
            {
                "ts": ln["timestamp"],
                "level": _level(ln),
                "trace_id": ln["meta"].get("trace_id", ""),
                "line": ln["line"][:300],
            }
            for ln in lines[: ns.show]
        ],
    }


def render(o: dict) -> str:
    out = []
    if o.get("error"):
        out.append("ERROR " + o["error"])
    if "with_trace_id" in o:
        out.append(
            f"{o['lines']} lines, {o['with_trace_id']} with a trace id, {o['without']} without{'  TRUNCATED' if o['truncated'] else ''}"
        )
        out += ["  orphan: " + s for s in o["orphan_samples"]]
        out.append("  " + o["note"])
    elif "severity" in o:
        out.append(
            f"{o['lines']} lines{'  TRUNCATED at --limit' if o['truncated'] else ''}  "
            + "  ".join(f"{k}={v}" for k, v in o["severity"].items())
        )
        for lv, ss in o["samples"].items():
            out += [f"  {lv}: {s}" for s in ss]
    elif "samples" in o:
        out.append(
            f"{o['lines']} matching lines{'  TRUNCATED at --limit' if o['truncated'] else ''}"
        )
        out += [
            f"  {s['level']:6s} {s['trace_id'][:16] or '-':16s} {s['line']}"
            for s in o["samples"]
        ]
    else:
        out.append(
            f"{o['lines']} lines{'  TRUNCATED at --limit - raise it or split the window' if o['truncated'] else ''}"
        )
        out += [
            f"  {n:6d}  {k}"
            for k, n in sorted(o["by_stream"].items(), key=lambda kv: -kv[1])
        ]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "severity", "correlate", "sample"):
        p = sub.add_parser(name)
        p.add_argument("selector")
        p.add_argument("--limit", type=int, default=LOG_LIMIT)
        if name == "sample":
            p.add_argument("--contains", default="")
            p.add_argument("--severity", default="")
            p.add_argument(
                "--show", type=int, default=20, help="lines to print (default 20)"
            )
        add_window(p)
    ns = ap.parse_args()
    code, out = {
        "count": cmd_count,
        "severity": cmd_severity,
        "correlate": cmd_correlate,
        "sample": cmd_sample,
    }[ns.cmd](ns)
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
