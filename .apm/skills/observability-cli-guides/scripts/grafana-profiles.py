#!/usr/bin/env python3
"""Pyroscope through gcx: top frames by self and total time, types, labels, zero checks.

    grafana-profiles.py top '{service_name="svc"}' --from ... --to ... [-n 15]
    grafana-profiles.py types
    grafana-profiles.py labels [--label service_name] --from ... --to ...
    grafana-profiles.py check '{service_name="svc", "process.runtime.version"="3.12"}' --from ... --to ...

Whole surface - top: SELECTOR, --type (default the CPU profile
process_cpu:cpu:nanoseconds:cpu:nanoseconds), window, -n (default 15).
types: nothing. labels: --label NAME for its values (names of every label
store-wide without it), window. check: SELECTOR, --type, window - runs the
selector, then the same selector with each label dropped in turn, so a zero
that is a misspelt label or a wrong value is told apart from a window that
holds no data. --json everywhere. Reads GCX_CONFIG. Exit 0 on success, 1 when
gcx errored.

Self time is what a report quotes ("62% in create_default_context"); total
time is the largest occurrence of the frame on the stack. Both are printed,
because a percentage read against the wrong one is a different number.
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
    emit,
    flame_frames,
    label_names,
    profile_types,
    run_gcx,
    run_many,
    window_args,
)


def _unit(profile_type: str) -> tuple[str, float]:
    parts = profile_type.split(":")
    unit = parts[2] if len(parts) > 2 else ""
    return unit, (1e9 if unit == "nanoseconds" else 1.0)


def cmd_top(ns) -> tuple[int, dict]:
    r = run_gcx(
        ["profiles", "query", ns.selector, "--profile-type", ns.type, *window_args(ns)]
    )
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
        "command": r.command,
        "error": r.error,
        "selector": ns.selector,
        "type": ns.type,
        "unit": unit,
        "total": total,
        "total_seconds": round(total / div, 3) if unit == "nanoseconds" else None,
        "frames": len(frames),
        "top_self": rows("self"),
        "top_total": rows("total_max"),
        "note": "total 0 with exit 0 is also what a misspelt label answers - run `check` before ruling an absence",
    }


def cmd_types(ns) -> tuple[int, dict]:
    r = run_gcx(["profiles", "list-profile-types"])
    return (0 if r.ok else 1), {
        "command": r.command,
        "error": r.error,
        "types": profile_types(r.data) if r.ok else [],
    }


def cmd_labels(ns) -> tuple[int, dict]:
    args = ["profiles", "labels", *window_args(ns)]
    if ns.label:
        args += ["--label", ns.label]
    r = run_gcx(args)
    return (0 if r.ok else 1), {
        "command": r.command,
        "error": r.error,
        "label": ns.label,
        "names": label_names(r.data) if r.ok else [],
        "note": "without --label the names are store-wide, every service's - a service's own labels are on one exemplar"
        if not ns.label
        else (
            "a null answer means the label name does not exist"
            if not label_names(r.data)
            else ""
        ),
    }


def cmd_check(ns) -> tuple[int, dict]:
    inner = ns.selector.strip()[1:-1]
    parts = [
        p.strip()
        for p in re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", inner)
        if p.strip()
    ]
    variants = [("as given", ns.selector)]
    for i in range(len(parts)):
        rest = [p for j, p in enumerate(parts) if j != i]
        variants.append((f"without {parts[i]}", "{" + ", ".join(rest) + "}"))
    win = window_args(ns)
    results = run_many(
        [
            ["profiles", "query", sel, "--profile-type", ns.type, *win]
            for _, sel in variants
        ]
    )
    rows = []
    for (label, sel), r in zip(variants, results):
        total, _ = flame_frames(r.data) if r.ok else (0, {})
        rows.append(
            {"variant": label, "selector": sel, "total": total, "error": r.error}
        )
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
    return (1 if any(x["error"] for x in rows) else 0), {
        "type": ns.type,
        "verdict": verdict,
        "rows": rows,
    }


def render(o: dict) -> str:
    out = []
    if o.get("error"):
        out.append("ERROR " + o["error"])
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
            f"  total={r['total']:<14} {r['variant']}  {r['selector']}{'  ' + r['error'] if r['error'] else ''}"
            for r in o["rows"]
        ]
    else:
        out.append(
            (f"values of {o['label']}: " if o["label"] else "label names: ")
            + (", ".join(o["names"]) or "(null)")
        )
        if o.get("note"):
            out.append("  " + o["note"])
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("top")
    a.add_argument("selector")
    a.add_argument("--type", default=CPU_PROFILE)
    a.add_argument("-n", type=int, default=15)
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
