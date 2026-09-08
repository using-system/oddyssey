#!/usr/bin/env python3
"""Loki through gcx, on an OTLP-fed store: exact counts, severities, correlation, samples.

    grafana-logs.py count '{service_name="svc"}' --from ... --to ...
    grafana-logs.py severity '{service_name="svc"}' --from ... --to ...
    grafana-logs.py correlate '{service_name="svc"}' --from ... --to ...
    grafana-logs.py sample '{service_name="svc"}' --contains "rejected" --from ... --to ... [--show 20]

Whole surface - every subcommand takes a LogQL stream SELECTOR, a window
(--from/--to or --since) and --json; sample adds --contains TEXT (a
line-body filter), --severity REGEX (matched on the severity_text
structured metadata, the only place the level lives on an OTLP store) and
--show N (lines printed, default 20). Every subcommand prints the gcx
commands it ran, so the report can record them. Reads GCX_CONFIG. Exit 0 on
success, 1 when gcx errored - and then nothing but the error is printed.

Loki answers at most 5 000 lines per query, server-side (a larger --limit is
refused). A window holding more is read in pieces - split in halves until
each fits, lines deduplicated - so a count is exact; when a piece still
saturates after six splits the output says so and reports no ratio.

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
    add_window,
    commands,
    emit,
    errors,
    logs_all,
    render_commands,
    resolve_window,
)


def _level(ln: dict) -> str:
    return (
        ln["meta"].get("severity_text") or ln["meta"].get("detected_level") or "?"
    ).upper()


def _logql_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def cmd_count(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    lines, results, truncated = logs_all(ns.selector, frm, to)
    streams: dict[str, int] = {}
    for ln in lines:
        k = (
            ln["stream"].get("service_instance_id")
            or ln["stream"].get("service_name")
            or "?"
        )
        streams[k] = streams.get(k, 0) + 1
    err = errors(results)
    return (1 if err else 0), {
        "error": err,
        "lines": len(lines),
        "truncated": truncated,
        "by_stream": streams,
        "commands": commands(results),
    }


def cmd_severity(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    lines, results, truncated = logs_all(ns.selector, frm, to)
    sev: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    for ln in lines:
        lv = _level(ln)
        sev[lv] = sev.get(lv, 0) + 1
        if lv not in ("INFO", "DEBUG", "?") and len(samples.setdefault(lv, [])) < 5:
            samples[lv].append(ln["line"][:200])
    err = errors(results)
    return (1 if err else 0), {
        "error": err,
        "lines": len(lines),
        "truncated": truncated,
        "severity": dict(sorted(sev.items(), key=lambda kv: -kv[1])),
        "samples": samples,
        "commands": commands(results),
    }


def cmd_correlate(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    total, r1, t1 = logs_all(ns.selector, frm, to)
    with_trace, r2, t2 = logs_all(ns.selector, frm, to, '| trace_id != ""')
    keyed = {(ln["timestamp"], ln["line"]) for ln in with_trace}
    orphans = [ln for ln in total if (ln["timestamp"], ln["line"]) not in keyed]
    truncated = t1 or t2
    err = errors(r1 + r2)
    return (1 if err else 0), {
        "error": err,
        "lines": len(total),
        "with_trace_id": len(with_trace),
        "without": None if truncated else len(orphans),
        "truncated": truncated,
        "orphan_samples": [ln["line"][:160] for ln in orphans[:10]],
        "note": "startup and health-check lines legitimately carry no trace id - classify the orphans before calling this a gap"
        + (
            "; the window saturated after splitting, so the counts are partial and no ratio is reported - narrow the window"
            if truncated
            else ""
        ),
        "commands": commands(r1 + r2),
    }


def cmd_sample(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    pipe = []
    if ns.contains:
        pipe.append("|= " + _logql_string(ns.contains))
    if ns.severity:
        pipe.append("| severity_text =~ " + _logql_string(ns.severity))
    lines, results, truncated = logs_all(ns.selector, frm, to, " ".join(pipe))
    err = errors(results)
    return (1 if err else 0), {
        "error": err,
        "lines": len(lines),
        "truncated": truncated,
        "samples": [
            {
                "ts": ln["timestamp"],
                "level": _level(ln),
                "trace_id": ln["meta"].get("trace_id", ""),
                "line": ln["line"][:300],
            }
            for ln in lines[: ns.show]
        ],
        "commands": commands(results),
    }


def render(o: dict) -> str:
    if o.get("error"):
        return "ERROR " + o["error"]
    out = []
    trunc = (
        "  PARTIAL - the window saturated after splitting, narrow it"
        if o.get("truncated")
        else ""
    )
    if "with_trace_id" in o:
        if o["without"] is None:
            out.append(
                f"at least {o['lines']} lines and {o['with_trace_id']} with a trace id{trunc}"
            )
        else:
            out.append(
                f"{o['lines']} lines, {o['with_trace_id']} with a trace id, {o['without']} without"
            )
        out += ["  orphan: " + s for s in o["orphan_samples"]]
        out.append("  " + o["note"])
    elif "severity" in o:
        out.append(
            f"{o['lines']} lines{trunc}  "
            + "  ".join(f"{k}={v}" for k, v in o["severity"].items())
        )
        for lv, ss in o["samples"].items():
            out += [f"  {lv}: {s}" for s in ss]
    elif "samples" in o:
        out.append(f"{o['lines']} matching lines{trunc}")
        out += [
            f"  {s['level']:6s} {s['trace_id'][:16] or '-':16s} {s['line']}"
            for s in o["samples"]
        ]
    else:
        out.append(f"{o['lines']} lines{trunc}")
        out += [
            f"  {n:6d}  {k}"
            for k, n in sorted(o["by_stream"].items(), key=lambda kv: -kv[1])
        ]
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "severity", "correlate", "sample"):
        p = sub.add_parser(name)
        p.add_argument("selector")
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
