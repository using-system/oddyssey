#!/usr/bin/env python3
"""Prometheus through gcx, the shapes an observation reads, envelopes handled.

    grafana-metrics.py histogram http_server_duration_milliseconds --by http_target --selector 'service_name="svc"' --from ... --to ...
    grafana-metrics.py counter catalog_orders_created_total --selector 'service_name="svc"' --by catalog_category --from ... --to ...
    grafana-metrics.py names --match '{service_name="svc"}' --from ... --to ...
    grafana-metrics.py instant 'sum by (span_name) (traces_spanmetrics_calls_total{service="svc"})' --at 2026-09-08T16:42:55Z
    grafana-metrics.py range 'sum(rate(http_server_duration_milliseconds_count[1m]))' --from ... --to ... --step 30s

Whole surface - histogram: BASE metric name (without _bucket), --by (comma
list of grouping labels), --selector (label matchers without the braces),
--quantiles (default 0.5,0.95,0.99), a window (--from/--to or --since),
--settle. counter: NAME, --by, --selector, a window, --settle. names:
--match SELECTOR (repeatable), a window. instant: EXPR, --at (RFC3339,
default now) - a raw PromQL expression, always with a selector or an
aggregation, or it lists every series. range: EXPR, a window, --step
(default 30s). --json on every subcommand. Every subcommand prints the gcx
commands it ran, so the report can record them. Reads GCX_CONFIG. Exit 0 on
success, 1 when gcx errored - and then nothing but the error is printed.

--settle (default 90s, histogram and counter) is the export lag: an SDK
exports every 60 s, so the sample carrying a run's last requests lands after
the window closes - a value read exactly at --to misses it. Both subcommands
evaluate at --to + settle over a range widened by the same amount, print the
instant they used, and print the raw cumulative values at the window's start
and after settling next to the increase(): on a store where the counter was
born inside the window, settled - start is the run's own count and
increase() only extrapolates it. A settled value below the start value is a
counter reset or an instance change inside the window, said as such.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grafana_gcx import (
    add_window,
    commands,
    emit,
    errors,
    iso,
    parse_duration,
    parse_ts,
    prom_result,
    prom_series,
    render_commands,
    resolve_window,
    run_gcx,
    run_many,
    window_seconds,
)


def _labels(metric: dict) -> str:
    return (
        ", ".join(f"{k}={v}" for k, v in sorted(metric.items()) if k != "__name__")
        or "{}"
    )


def _settled(frm: str, to: str, settle: str) -> tuple[str, str]:
    """(evaluation instant, range window) once the export lag is added."""
    lag = parse_duration(settle)
    return iso(
        parse_ts(to) + timedelta(seconds=lag)
    ), f"[{window_seconds(frm, to) + lag}s]"


def _rows_of(results, keys) -> dict[str, dict]:
    table: dict[str, dict] = {}
    for key, r in zip(keys, results):
        for x in prom_result(r.data) if r.ok else []:
            try:
                table.setdefault(_labels(x.get("metric", {})), {})[key] = float(
                    x["value"][1]
                )
            except (KeyError, IndexError, TypeError, ValueError):
                continue
    return table


def cmd_instant(ns) -> tuple[int, dict]:
    args = ["metrics", "query", ns.expr]
    if ns.at:
        args += ["--time", iso(parse_ts(ns.at))]
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
    return (0 if r.ok else 1), {"error": r.error, "rows": rows, "commands": [r.command]}


def cmd_range(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    r = run_gcx(
        ["metrics", "query", ns.expr, "--from", frm, "--to", to, "--step", ns.step]
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
    return (0 if r.ok else 1), {"error": r.error, "rows": rows, "commands": [r.command]}


def cmd_names(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    results = run_many(
        [["metrics", "series", m, "--from", frm, "--to", to] for m in ns.match]
    )
    names: dict[str, int] = {}
    for r in results:
        for s in prom_series(r.data) if r.ok else []:
            n = s.get("__name__", "")
            if n:
                names[n] = names.get(n, 0) + 1
    err = errors(results)
    return (1 if err else 0), {
        "error": err,
        "names": dict(sorted(names.items())),
        "commands": commands(results),
    }


def cmd_labels(ns) -> tuple[int, dict]:
    """A label's values (--label) or the label names behind a selector."""
    frm, to = resolve_window(ns)
    if ns.label:
        # An instant query at the window's end, over the whole window:
        # `count by` over `last_over_time` lists every value that carried
        # a sample in the window, stale series included.
        at, win = _settled(frm, to, "0s")
        expr = f"count by ({ns.label}) (last_over_time({ns.match}{win}))"
        r = run_gcx(["metrics", "query", expr, "--time", at])
        values: dict[str, int] = {}
        for x in prom_result(r.data) if r.ok else []:
            try:
                v = x.get("metric", {}).get(ns.label, "")
                values[v] = values.get(v, 0) + int(float(x["value"][1]))
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return (0 if r.ok else 1), {
            "error": r.error,
            "label": ns.label,
            "values": dict(sorted(values.items(), key=lambda kv: -kv[1])),
            "commands": [r.command],
        }
    r = run_gcx(["metrics", "series", ns.match, "--from", frm, "--to", to])
    names: dict[str, int] = {}
    for s in prom_series(r.data) if r.ok else []:
        for k in s:
            if k != "__name__":
                names[k] = names.get(k, 0) + 1
    return (0 if r.ok else 1), {
        "error": r.error,
        "label": None,
        "values": dict(sorted(names.items(), key=lambda kv: -kv[1])),
        "commands": [r.command],
    }


def sort_key(kv) -> float:
    """Busiest row first: the run's own count, or the increase() when the
    count is withheld by a reset."""
    e = kv[1]
    count = e.get("count")
    return -(count if count is not None else (e.get("count_increase") or 0.0))


def cmd_histogram(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    sel = ("{" + ns.selector + "}") if ns.selector else ""
    at, win = _settled(frm, to, ns.settle)
    by_labels = [b.strip() for b in ns.by.split(",") if b.strip()]
    by = ", ".join(["le", *by_labels])
    group = ", ".join(by_labels)
    agg = f"sum by ({group})" if group else "sum"
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
    keys = [f"p{int(q * 100)}" for q in qs]
    for suffix in ("count", "sum"):
        calls += [
            ["metrics", "query", f"{agg}({ns.base}_{suffix}{sel})", "--time", frm],
            [
                "metrics",
                "query",
                f"{agg}(last_over_time({ns.base}_{suffix}{sel}{win}))",
                "--time",
                at,
            ],
            [
                "metrics",
                "query",
                f"{agg}(increase({ns.base}_{suffix}{sel}{win}))",
                "--time",
                at,
            ],
        ]
        keys += [f"{suffix}_at_start", f"{suffix}_settled", f"{suffix}_increase"]
    results = run_many(calls)
    table = _rows_of(results, keys)
    for e in table.values():
        c0, c1 = e.get("count_at_start"), e.get("count_settled")
        s0, s1 = e.get("sum_at_start"), e.get("sum_settled")
        # A raw value that fell inside the window is a reset: the
        # subtraction would print a negative request count, so it is
        # withheld like counter's delta, and the increase() stands in.
        if (c0 is not None and c1 is not None and c1 < c0) or (
            s0 is not None and s1 is not None and s1 < s0
        ):
            e["reset"] = True
            e["count"] = e["sum"] = None
            continue
        if c1 is not None:
            e["count"] = c1 - (c0 or 0.0)
        if s1 is not None:
            e["sum"] = s1 - (s0 or 0.0)
        if e.get("count") and e.get("sum") is not None:
            e["mean"] = e["sum"] / e["count"]
    err = errors(results)
    return (1 if err else 0), {
        "metric": ns.base,
        "window": win,
        "evaluated_at": at,
        "error": err,
        "rows": dict(sorted(table.items(), key=sort_key)),
        "note": "count and sum are raw settled - raw start (the run's own); *_increase is increase() over the window, an extrapolation; reset=true means the raw value fell inside the window - count and sum are withheld, take the increase then",
        "commands": commands(results),
    }


def cmd_counter(ns) -> tuple[int, dict]:
    frm, to = resolve_window(ns)
    sel = ("{" + ns.selector + "}") if ns.selector else ""
    at, win = _settled(frm, to, ns.settle)
    agg = f"sum by ({ns.by})" if ns.by else "sum"
    calls = [
        ["metrics", "query", f"{agg}({ns.name}{sel})", "--time", frm],
        ["metrics", "query", f"{agg}({ns.name}{sel})", "--time", to],
        [
            "metrics",
            "query",
            f"{agg}(last_over_time({ns.name}{sel}{win}))",
            "--time",
            at,
        ],
        ["metrics", "query", f"{agg}(increase({ns.name}{sel}{win}))", "--time", at],
    ]
    results = run_many(calls)
    table = _rows_of(results, ("at_start", "at_end", "settled", "increase"))
    for e in table.values():
        if e.get("settled") is None:
            continue
        start = e.get("at_start") or 0.0
        if e["settled"] < start or (
            e.get("at_end") is not None and e["at_end"] < start
        ):
            e["reset"] = True
            e["delta"] = None
        else:
            e["delta"] = e["settled"] - start
    err = errors(results)
    return (1 if err else 0), {
        "metric": ns.name,
        "window": win,
        "evaluated_at": at,
        "error": err,
        "rows": table,
        "note": "delta = settled - at_start, the run's own count; at_end misses the last export; increase() extrapolates a counter born inside the window; reset=true means the raw value fell inside the window (a counter reset or an instance change) - delta is withheld, take the increase",
        "commands": commands(results),
    }


def render(o: dict) -> str:
    if o.get("error"):
        return "ERROR " + o["error"]
    out = []
    if "names" in o:
        out += [f"{n}  ({c} series)" for n, c in o["names"].items()] or ["(no series)"]
    elif "values" in o:
        unit = "series" if o["label"] else "series carry it"
        out += [f"{v}  ({c} {unit})" for v, c in o["values"].items()] or ["(no series)"]
    elif isinstance(o.get("rows"), dict):
        cols = [
            c
            for c in (
                "p50",
                "p95",
                "p99",
                "count",
                "sum",
                "mean",
                "delta",
                "at_start",
                "at_end",
                "settled",
                "increase",
                "count_increase",
            )
            if any(c in e for e in o["rows"].values())
        ]
        out.append(
            f"{o.get('metric', '')} {o.get('window', '')} evaluated at {o.get('evaluated_at', '')}"
        )
        for k, e in o["rows"].items():
            cells = "  ".join(f"{c}={e[c]:.4g}" for c in cols if e.get(c) is not None)
            out.append(
                "  "
                + k
                + "  "
                + cells
                + ("  RESET inside the window" if e.get("reset") else "")
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
    out += render_commands(o)
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
    b.add_argument("--step", default="30s")
    add_window(b)
    c = sub.add_parser("names")
    c.add_argument("--match", action="append", required=True)
    add_window(c)
    lb = sub.add_parser("labels")
    lb.add_argument("--match", required=True)
    lb.add_argument("--label")
    add_window(lb)
    for name in ("histogram", "counter"):
        p = sub.add_parser(name)
        p.add_argument("base" if name == "histogram" else "name")
        p.add_argument("--by", default="")
        p.add_argument("--selector", default="")
        if name == "histogram":
            p.add_argument("--quantiles", default="0.5,0.95,0.99")
        p.add_argument("--settle", default="90s")
        add_window(p)
    ns = ap.parse_args()
    code, out = {
        "instant": cmd_instant,
        "range": cmd_range,
        "names": cmd_names,
        "labels": cmd_labels,
        "histogram": cmd_histogram,
        "counter": cmd_counter,
    }[ns.cmd](ns)
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
