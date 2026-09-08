#!/usr/bin/env python3
"""Prometheus through gcx, the four shapes an observation reads, envelopes handled.

    grafana-metrics.py instant 'sum by (span_name) (traces_spanmetrics_calls_total)' --at 2026-09-08T16:42:55Z
    grafana-metrics.py range 'sum(rate(http_server_duration_milliseconds_count[1m]))' --from ... --to ... --step 30s
    grafana-metrics.py names --match '{service_name="svc"}' --from ... --to ...
    grafana-metrics.py histogram http_server_duration_milliseconds --by http_target --selector 'service_name="svc"' --from ... --to ...
    grafana-metrics.py counter catalog_orders_created_total --selector 'service_name="svc"' --by catalog_category --from ... --to ...

Whole surface - instant: EXPR, --at (RFC3339, default now). range: EXPR,
--from/--to, --step (default 30s). names: --match SELECTOR (repeatable),
window. histogram: BASE metric name (without _bucket), --by LABELS (comma
list), --selector (label matchers without braces), --quantiles (default
0.5,0.95,0.99), --from/--to, --settle. counter: NAME, --selector, --by,
--from/--to, --settle - prints the raw cumulative value at the window's
start, at its end and after it settled, and the increase over the window,
because on a store holding one run the raw value is the total and
increase() only estimates it. --json on every subcommand. Reads
GCX_CONFIG. Exit 0 on success, 1 when gcx errored.

--settle (default 90s, histogram and counter) is the export lag: an SDK
exports every 60 s, so the sample carrying a run's last requests lands
after the window closes - a value read exactly at --to misses it. Both
subcommands evaluate at --to + settle over a range widened by the same
amount, and print the instant they used.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grafana_gcx import (
    add_window,
    emit,
    prom_result,
    prom_series,
    run_gcx,
    run_many,
    window_args,
)


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds(s: str) -> int:
    n, u = float(s[:-1]), s[-1]
    return int(n * {"s": 1, "m": 60, "h": 3600}[u])


def _labels(metric: dict) -> str:
    return (
        ", ".join(f"{k}={v}" for k, v in sorted(metric.items()) if k != "__name__")
        or "{}"
    )


def _settled(ns) -> tuple[str, str]:
    """(evaluation instant, range window) once the export lag is added."""
    span = max(1, int((_parse(ns.to) - _parse(ns.frm)).total_seconds()))
    settle = _seconds(ns.settle)
    return _iso(_parse(ns.to) + timedelta(seconds=settle)), f"[{span + settle}s]"


def cmd_instant(ns) -> tuple[int, dict]:
    args = ["metrics", "query", ns.expr]
    if ns.at:
        args += ["--time", ns.at]
    r = run_gcx(args)
    rows = (
        [
            {
                "labels": x.get("metric", {}),
                "value": float(x["value"][1]) if x.get("value") else None,
            }
            for x in prom_result(r.data)
        ]
        if r.ok
        else []
    )
    return (0 if r.ok else 1), {"command": r.command, "error": r.error, "rows": rows}


def cmd_range(ns) -> tuple[int, dict]:
    r = run_gcx(
        [
            "metrics",
            "query",
            ns.expr,
            "--from",
            ns.frm,
            "--to",
            ns.to,
            "--step",
            ns.step,
        ]
    )
    rows = []
    for x in prom_result(r.data) if r.ok else []:
        vals = [(int(t), float(v)) for t, v in x.get("values") or []]
        rows.append(
            {
                "labels": x.get("metric", {}),
                "samples": len(vals),
                "first": vals[0] if vals else None,
                "last": vals[-1] if vals else None,
                "max": max((v for _, v in vals), default=None),
                "values": vals,
            }
        )
    return (0 if r.ok else 1), {"command": r.command, "error": r.error, "rows": rows}


def cmd_names(ns) -> tuple[int, dict]:
    win = window_args(ns)
    results = run_many([["metrics", "series", m, *win] for m in ns.match])
    names: dict[str, int] = {}
    errors = [r.error for r in results if not r.ok]
    for r in results:
        for s in prom_series(r.data) if r.ok else []:
            n = s.get("__name__", "")
            if n:
                names[n] = names.get(n, 0) + 1
    return (1 if errors else 0), {
        "error": "; ".join(errors),
        "names": dict(sorted(names.items())),
    }


def cmd_histogram(ns) -> tuple[int, dict]:
    sel = ("{" + ns.selector + "}") if ns.selector else ""
    at, win = _settled(ns)
    by_labels = [b.strip() for b in ns.by.split(",") if b.strip()]
    by = ", ".join(["le", *by_labels])
    group = ", ".join(by_labels)
    qs = [float(q) for q in ns.quantiles.split(",")]
    calls = [
        [
            "metrics",
            "query",
            f"histogram_quantile({q}, sum by ({by}) (rate({ns.base}_bucket{sel}{win})))",
            "--time",
            at,
        ]
        for q in qs
    ]
    for suffix in ("count", "sum"):
        expr = (
            f"sum by ({group}) (increase({ns.base}_{suffix}{sel}{win}))"
            if group
            else f"sum(increase({ns.base}_{suffix}{sel}{win}))"
        )
        calls.append(["metrics", "query", expr, "--time", at])
    results = run_many(calls)
    errors = [r.error for r in results if not r.ok]
    table: dict[str, dict] = {}
    for q, r in zip(qs, results[: len(qs)]):
        for x in prom_result(r.data) if r.ok else []:
            table.setdefault(_labels(x.get("metric", {})), {})[f"p{int(q * 100)}"] = (
                float(x["value"][1])
            )
    for key, r in (("count", results[-2]), ("sum", results[-1])):
        for x in prom_result(r.data) if r.ok else []:
            table.setdefault(_labels(x.get("metric", {})), {})[key] = float(
                x["value"][1]
            )
    for e in table.values():
        if e.get("count") and e.get("sum") is not None:
            e["mean"] = e["sum"] / e["count"]
    return (1 if errors else 0), {
        "metric": ns.base,
        "window": win,
        "evaluated_at": at,
        "error": "; ".join(errors),
        "rows": dict(sorted(table.items(), key=lambda kv: -(kv[1].get("count") or 0))),
    }


def cmd_counter(ns) -> tuple[int, dict]:
    sel = ("{" + ns.selector + "}") if ns.selector else ""
    at, win = _settled(ns)
    agg = f"sum by ({ns.by})" if ns.by else "sum"
    calls = [
        ["metrics", "query", f"{agg}({ns.name}{sel})", "--time", ns.frm],
        ["metrics", "query", f"{agg}({ns.name}{sel})", "--time", ns.to],
        ["metrics", "query", f"{agg}({ns.name}{sel})", "--time", at],
        ["metrics", "query", f"{agg}(increase({ns.name}{sel}{win}))", "--time", at],
    ]
    results = run_many(calls)
    errors = [r.error for r in results if not r.ok]
    table: dict[str, dict] = {}
    for key, r in zip(("at_start", "at_end", "settled", "increase"), results):
        for x in prom_result(r.data) if r.ok else []:
            table.setdefault(_labels(x.get("metric", {})), {})[key] = float(
                x["value"][1]
            )
    for e in table.values():
        if e.get("settled") is not None:
            e["delta"] = e["settled"] - (e.get("at_start") or 0.0)
    return (1 if errors else 0), {
        "metric": ns.name,
        "window": win,
        "evaluated_at": at,
        "error": "; ".join(errors),
        "rows": table,
        "note": "delta = settled - at_start (the run's own count); at_end misses the last export; increase() extrapolates a counter born inside the window",
    }


def render(o: dict) -> str:
    out = []
    if o.get("error"):
        out.append("ERROR " + o["error"])
    if "names" in o:
        out += [f"{n}  ({c} series)" for n, c in o["names"].items()] or ["(no series)"]
    elif isinstance(o.get("rows"), dict):
        keys = sorted({k for e in o["rows"].values() for k in e})
        out.append(
            f"{o.get('metric', '')} {o.get('window', '')} evaluated at {o.get('evaluated_at', '')}"
        )
        for k, e in o["rows"].items():
            out.append(
                "  " + k + "  " + "  ".join(f"{c}={e[c]:.4g}" for c in keys if c in e)
            )
        if not o["rows"]:
            out.append(
                "  (empty - widen the window to two export intervals before ruling anything absent)"
            )
        if o.get("note"):
            out.append("  " + o["note"])
    else:
        for e in o.get("rows", []):
            if "value" in e:
                out.append(f"{e['value']!s:>14}  {_labels(e['labels'])}")
            else:
                out.append(
                    f"{_labels(e['labels'])}  samples={e['samples']} first={e['first']} last={e['last']} max={e['max']}"
                )
        if not o.get("rows"):
            out.append(
                "(empty result - on a window shorter than two export intervals, widen it before ruling anything absent)"
            )
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("instant")
    a.add_argument("expr")
    a.add_argument("--at")
    a.add_argument("--json", action="store_true")
    b = sub.add_parser("range")
    b.add_argument("expr")
    b.add_argument("--from", dest="frm", required=True)
    b.add_argument("--to", required=True)
    b.add_argument("--step", default="30s")
    b.add_argument("--json", action="store_true")
    c = sub.add_parser("names")
    c.add_argument("--match", action="append", required=True)
    add_window(c)
    for name in ("histogram", "counter"):
        p = sub.add_parser(name)
        p.add_argument("base" if name == "histogram" else "name")
        p.add_argument("--by", default="")
        p.add_argument("--selector", default="")
        if name == "histogram":
            p.add_argument("--quantiles", default="0.5,0.95,0.99")
        p.add_argument("--from", dest="frm", required=True)
        p.add_argument("--to", required=True)
        p.add_argument("--settle", default="90s")
        p.add_argument("--json", action="store_true")
    ns = ap.parse_args()
    code, out = {
        "instant": cmd_instant,
        "range": cmd_range,
        "names": cmd_names,
        "histogram": cmd_histogram,
        "counter": cmd_counter,
    }[ns.cmd](ns)
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
