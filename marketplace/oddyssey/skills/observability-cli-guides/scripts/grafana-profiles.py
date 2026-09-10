#!/usr/bin/env python3
"""Pyroscope through gcx: top frames by self and total time, types, labels, zero checks.

    grafana-profiles.py top '{service_name="svc"}' --from ... --to ... [-n 15] [--trace-id ID]
    grafana-profiles.py types
    grafana-profiles.py labels [--label service_name] --from ... --to ...
    grafana-profiles.py check '{service_name="svc", "process.runtime.version"="3.12"}' --from ... --to ...

Whole surface - top: SELECTOR (braces included), --type (default the CPU
profile process_cpu:cpu:nanoseconds:cpu:nanoseconds), a window (--from/--to
or --since), -n (default 15), --trace-id and --span-id (restrict the
flamegraph to the samples linked to one trace or span; a trace id is padded
to 32 hex for you). types: nothing. labels: --label NAME for its values
(names of every label store-wide without it), a window. check: SELECTOR,
--type, a window - runs the selector, then the same selector with each
label dropped in turn, so a zero that is a misspelt label or a wrong value
is told apart from a window that holds no data. --json everywhere. Every
subcommand prints the gcx commands it ran, so the report can record them.
Reads GCX_CONFIG. Exit 0 on success, 1 when gcx errored - and then nothing
but the error is printed.

Self time is what a report quotes ("62% in create_default_context"); total
time is the largest occurrence of the frame on the stack. Both are printed,
because a percentage read against the wrong one is a different number.
Frame names are the profiler's own (`Class.method`, a bare function name,
`<module>`), never a module path: a check that greps them uses anchored
names read off this output.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grafana_gcx import (
    CPU_PROFILE,
    add_window,
    commands,
    emit,
    errors,
    flame_frames,
    hex_trace_id,
    label_names,
    profile_types,
    render_commands,
    resolve_window,
    run_gcx,
    run_many,
)


def _unit(profile_type: str) -> tuple[str, float]:
    parts = profile_type.split(":")
    unit = parts[2] if len(parts) > 2 else ""
    return unit, (1e9 if unit == "nanoseconds" else 1.0)


def _selector(s: str) -> str:
    s = (s or "").strip()
    if not (s.startswith("{") and s.endswith("}") and len(s) >= 2):
        raise SystemExit(
            f'a profile selector is written inside braces, e.g. {{service_name="svc"}} - got {s!r}'
        )
    return s


def cmd_top(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    args = [
        "profiles",
        "query",
        _selector(ns.selector),
        "--profile-type",
        ns.type,
        "--from",
        frm,
        "--to",
        to,
    ]
    if ns.trace_id:
        args += ["--trace-id", hex_trace_id(ns.trace_id)]
    if ns.span_id:
        args += ["--span-id", ns.span_id]
    r = run_gcx(args)
    total, frames = flame_frames(r.data) if r.ok else (0, {})
    unit, div = _unit(ns.type)

    def rows(key):
        return [
            {
                "frame": n,
                key: e[key],
                "pct": round(100 * e[key] / total, 2) if total else 0.0,
            }
            for n, e in sorted(frames.items(), key=lambda kv: -kv[1][key])[: ns.n]
        ]

    return (0 if r.ok else 1), {
        "error": r.error,
        "selector": ns.selector,
        "type": ns.type,
        "unit": unit,
        "total": total,
        "total_seconds": round(total / div, 3) if unit == "nanoseconds" else None,
        "frames": len(frames),
        "top_self": rows("self"),
        "top_total": rows("total_max"),
        "note": "total 0 with exit 0 is also what a misspelt label, a wrong value, or a trace with no linked samples answers - run `check` before ruling an absence",
        "commands": [r.command],
    }


def cmd_types(ns) -> tuple[int, dict]:
    r = run_gcx(["profiles", "list-profile-types"])
    return (0 if r.ok else 1), {
        "error": r.error,
        "types": profile_types(r.data) if r.ok else [],
        "commands": [r.command],
    }


def cmd_labels(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    args = ["profiles", "labels", "--from", frm, "--to", to]
    if ns.label:
        args += ["--label", ns.label]
    r = run_gcx(args)
    names = label_names(r.data) if r.ok else []
    return (0 if r.ok else 1), {
        "error": r.error,
        "label": ns.label,
        "names": names,
        "note": "without --label the names are store-wide, every service's - a service's own labels are on one of its profiles"
        if not ns.label
        else ("a null answer means the label name does not exist" if not names else ""),
        "commands": [r.command],
    }


def cmd_check(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    sel = _selector(ns.selector)
    inner = sel[1:-1]
    parts = [
        p.strip() for p in re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', inner) if p.strip()
    ]
    variants = [("as given", sel)]
    for i in range(len(parts)):
        rest = [p for j, p in enumerate(parts) if j != i]
        variants.append((f"without {parts[i]}", "{" + ", ".join(rest) + "}"))
    results = run_many(
        [
            [
                "profiles",
                "query",
                s,
                "--profile-type",
                ns.type,
                "--from",
                frm,
                "--to",
                to,
            ]
            for _, s in variants
        ]
    )
    rows = []
    for (label, s), r in zip(variants, results):
        total, _ = flame_frames(r.data) if r.ok else (0, {})
        rows.append({"variant": label, "selector": s, "total": total, "error": r.error})
    given = rows[0]["total"]
    verdict = (
        "data present"
        if given
        else (
            "the window holds no data for the service"
            if not any(x["total"] for x in rows[1:])
            else "a label in the selector matches nothing - see which drop restores data"
        )
    )
    err = errors(results)
    return (1 if err else 0), {
        "type": ns.type,
        "verdict": verdict,
        "rows": rows,
        "error": err,
        "commands": commands(results),
    }


def render(o: dict) -> str:
    if o.get("error"):
        return "ERROR " + o["error"]
    out = []
    if "top_self" in o:
        out.append(
            f"{o['selector']}  {o['type']}  total {o['total']} {o['unit']}"
            + (f" = {o['total_seconds']} s" if o["total_seconds"] is not None else "")
            + f"  ({o['frames']} frames)"
        )
        if not o["total"]:
            out.append("  " + o["note"])
        out.append("  top by SELF")
        out += [
            f"   {r['pct']:6.2f}%  {r['self']:>14}  {r['frame']}" for r in o["top_self"]
        ]
        out.append("  top by TOTAL (largest occurrence)")
        out += [
            f"   {r['pct']:6.2f}%  {r['total_max']:>14}  {r['frame']}"
            for r in o["top_total"]
        ]
    elif "types" in o:
        out += o["types"] or ["(no profile types)"]
    elif "rows" in o:
        out.append(o["verdict"])
        out += [
            f"  total={r['total']:<14} {r['variant']}  {r['selector']}"
            for r in o["rows"]
        ]
    else:
        out.append(
            (f"values of {o['label']}: " if o["label"] else "label names: ")
            + (", ".join(o["names"]) or "(null)")
        )
        if o.get("note"):
            out.append("  " + o["note"])
    out += render_commands(o)
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("top")
    a.add_argument("selector")
    a.add_argument("--type", default=CPU_PROFILE)
    a.add_argument("-n", type=int, default=15)
    a.add_argument("--trace-id")
    a.add_argument("--span-id")
    add_window(a)
    b = sub.add_parser("types")
    b.add_argument("--json", action="store_true")
    c = sub.add_parser("labels")
    c.add_argument("--label")
    add_window(c)
    d = sub.add_parser("check")
    d.add_argument("selector")
    d.add_argument("--type", default=CPU_PROFILE)
    add_window(d)
    ns = ap.parse_args()
    code, out = {
        "top": cmd_top,
        "types": cmd_types,
        "labels": cmd_labels,
        "check": cmd_check,
    }[ns.cmd](ns)
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
