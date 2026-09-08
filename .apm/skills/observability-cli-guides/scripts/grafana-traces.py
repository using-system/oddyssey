#!/usr/bin/env python3
"""Tempo through gcx: per-operation latency with exemplars, span trees, exact counts.

    grafana-traces.py ops --service svc --from ... --to ... [--fetch DIR]
    grafana-traces.py get 9ed9a7b6ce4b233f8c6cf373c079811 [ID ...] [--out DIR] [--spans]
    grafana-traces.py search '{ status = error }' --from ... --to ... [--limit 1000]
    grafana-traces.py count '{ resource.service.name = "svc" }' --from ... --to ... [--bin 30s]

Whole surface - ops: --service (repeatable), window, --limit (default 1000,
the search ceiling), --name (repeatable; default: every root operation the
window shows), --fetch DIR (also fetch the p50 and worst exemplar of each
operation and summarise them). get: trace ids in either form gcx prints
(unpadded or padded hex), --out DIR to keep the raw documents, --spans to
print every span instead of the summary. search: TRACEQL, window, --limit.
count: TRACEQL, window, --bin (default 30s) - counts in bins deduplicated on
trace id, because a trace overlapping two bins is listed in both, and says
when a bin hit the ceiling. --json everywhere. Reads GCX_CONFIG. Exit 0 on
success, 1 when gcx errored.

Two readings of latency, both printed by `ops`, because they are not the
same number: a trace search returns the *trace* duration, so an operation
nested under a slow parent inherits the parent's time - the search-derived
figures are computed only over traces rooted at the operation, and the
worst trace *containing* it is listed separately (that is where a fan-out
shows). The span-level percentiles come from the span metrics the store
derives from traces (traces_spanmetrics_latency_bucket), when it has them.
durationMs from a search is a truncated integer: a sub-millisecond operation
reads 0 - the span metrics carry its real latency.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grafana_gcx import (
    TRACE_LIMIT,
    add_window,
    emit,
    flatten_trace,
    hex_trace_id,
    percentiles,
    prom_result,
    run_gcx,
    run_many,
    trace_summary,
    traces_list,
    window_args,
)

QUANTILES = (0.5, 0.95, 0.99)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _dur(s: str) -> timedelta:
    n, u = float(s[:-1]), s[-1]
    return timedelta(seconds=n * {"s": 1, "m": 60, "h": 3600}[u])


def fetch_traces(ids: list[str], out_dir: str | None) -> list[dict]:
    results = run_many([["traces", "get", i] for i in ids])
    docs = []
    for i, r in zip(ids, results):
        if not r.ok:
            docs.append({"trace_id": hex_trace_id(i), "error": r.error})
            continue
        spans = flatten_trace(r.data)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"trace-{hex_trace_id(i)}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(r.data, fh)
        docs.append({"summary": trace_summary(spans), "spans": spans})
    return docs


def _span_quantiles(keys: list[tuple[str, str]], ns) -> dict[tuple[str, str], dict]:
    """Span-level p50/p95/p99 and count from the store's span metrics, per operation."""
    if not (ns.frm and ns.to):
        return {}
    win = f"[{max(1, int((_parse(ns.to) - _parse(ns.frm)).total_seconds()))}s]"
    calls = []
    for s, n in keys:
        sel = f'{{service="{s}", span_name="{n}"}}'
        for q in QUANTILES:
            calls.append(
                [
                    "metrics",
                    "query",
                    f"histogram_quantile({q}, sum by (le) (rate(traces_spanmetrics_latency_bucket{sel}{win})))",
                    "--time",
                    ns.to,
                ]
            )
        calls.append(
            [
                "metrics",
                "query",
                f"sum(increase(traces_spanmetrics_calls_total{sel}{win}))",
                "--time",
                ns.to,
            ]
        )
    results = run_many(calls)
    per = len(QUANTILES) + 1
    out = {}
    for i, key in enumerate(keys):
        chunk = results[i * per : (i + 1) * per]
        e = {}
        for q, r in zip(QUANTILES, chunk):
            res = prom_result(r.data) if r.ok else []
            try:
                e[f"span_p{int(q * 100)}_ms"] = (
                    round(float(res[0]["value"][1]) * 1000, 2) if res else None
                )
            except (KeyError, IndexError, TypeError, ValueError):
                e[f"span_p{int(q * 100)}_ms"] = None
        res = prom_result(chunk[-1].data) if chunk[-1].ok else []
        try:
            e["span_calls"] = round(float(res[0]["value"][1])) if res else None
        except (KeyError, IndexError, TypeError, ValueError):
            e["span_calls"] = None
        out[key] = e
    return out


def cmd_ops(ns) -> tuple[int, dict]:
    win = window_args(ns)
    services = ns.service
    first = run_many(
        [
            [
                "traces",
                "query",
                f'{{ resource.service.name = "{s}" }}',
                *win,
                "--limit",
                str(ns.limit),
            ]
            for s in services
        ]
    )
    errors = [r.error for r in first if not r.ok]
    ops: dict[tuple[str, str], None] = {}
    for s, r in zip(services, first):
        for t in traces_list(r.data) if r.ok else []:
            if t.get("rootServiceName") == s and t.get("rootTraceName"):
                ops[(s, t["rootTraceName"])] = None
    for s in services:
        for n in ns.name or []:
            ops[(s, n)] = None
    keys = list(ops)
    results = run_many(
        [
            [
                "traces",
                "query",
                f'{{ resource.service.name = "{s}" && name = "{n}" }}',
                *win,
                "--limit",
                str(ns.limit),
            ]
            for s, n in keys
        ]
    )
    spanq = _span_quantiles(keys, ns)
    table = {}
    for (s, n), r in zip(keys, results):
        if not r.ok:
            errors.append(r.error)
            continue
        traces = traces_list(r.data)
        rooted = [
            t
            for t in traces
            if t.get("rootServiceName") == s and t.get("rootTraceName") == n
        ]
        durs = [t.get("durationMs", 0) for t in rooted]
        st = percentiles(durs)
        by_dur = sorted(rooted, key=lambda t: t.get("durationMs", 0))
        containing = (
            max(traces, key=lambda t: t.get("durationMs", 0)) if traces else None
        )
        p50_t = by_dur[len(by_dur) // 2] if by_dur else None
        table[f"{s} {n}"] = {
            "rooted_traces": st["count"],
            "containing_traces": len(traces),
            "truncated": len(traces) >= ns.limit,
            "trace_p50_ms": st["p50"],
            "trace_p95_ms": st["p95"],
            "trace_p99_ms": st["p99"],
            "trace_max_ms": st["max"],
            **spanq.get((s, n), {}),
            "p50_trace": hex_trace_id(p50_t["traceID"]) if p50_t else None,
            "worst_rooted_trace": hex_trace_id(by_dur[-1]["traceID"])
            if by_dur
            else None,
            "worst_containing_trace": hex_trace_id(containing["traceID"])
            if containing
            else None,
            "worst_containing_ms": containing.get("durationMs") if containing else None,
        }
    out = {
        "window": win,
        "error": "; ".join(errors),
        "span_metrics_present": any(v.get("span_calls") for v in spanq.values()),
        "operations": dict(
            sorted(table.items(), key=lambda kv: -(kv[1]["containing_traces"] or 0))
        ),
    }
    if ns.fetch:
        ids = sorted(
            {
                e[k]
                for e in table.values()
                for k in ("p50_trace", "worst_rooted_trace", "worst_containing_trace")
                if e.get(k)
            }
        )
        docs = fetch_traces(ids, ns.fetch)
        out["exemplars"] = {
            (d.get("summary", {}).get("trace_id") or d.get("trace_id")): (
                d.get("summary") or {"error": d.get("error")}
            )
            for d in docs
        }
    return (1 if errors else 0), out


def cmd_get(ns) -> tuple[int, dict]:
    docs = fetch_traces(ns.ids, ns.out)
    errs = [d["error"] for d in docs if "error" in d]
    return (1 if errs else 0), {
        "traces": [
            d if ns.spans else {"summary": d.get("summary"), "error": d.get("error")}
            for d in docs
        ]
    }


def cmd_search(ns) -> tuple[int, dict]:
    r = run_gcx(
        ["traces", "query", ns.traceql, *window_args(ns), "--limit", str(ns.limit)]
    )
    rows = (
        [
            {**t, "traceID": hex_trace_id(t.get("traceID", ""))}
            for t in traces_list(r.data)
        ]
        if r.ok
        else []
    )
    return (0 if r.ok else 1), {
        "command": r.command,
        "error": r.error,
        "count": len(rows),
        "truncated": len(rows) >= ns.limit,
        "traces": rows,
    }


def cmd_count(ns) -> tuple[int, dict]:
    if not (ns.frm and ns.to):
        raise SystemExit("count needs --from and --to")
    a, b = _parse(ns.frm), _parse(ns.to)
    step = _dur(ns.bin)
    bins = []
    t = a
    while t < b:
        bins.append((t, min(t + step, b)))
        t += step
    results = run_many(
        [
            [
                "traces",
                "query",
                ns.traceql,
                "--from",
                _iso(x),
                "--to",
                _iso(y),
                "--limit",
                str(TRACE_LIMIT),
            ]
            for x, y in bins
        ]
    )
    seen: set[str] = set()
    rows = []
    errors = []
    for (x, y), r in zip(bins, results):
        if not r.ok:
            errors.append(r.error)
            rows.append({"from": _iso(x), "to": _iso(y), "error": r.error})
            continue
        ids = [hex_trace_id(t.get("traceID", "")) for t in traces_list(r.data)]
        new = [i for i in ids if i not in seen]
        seen.update(new)
        rows.append(
            {
                "from": _iso(x),
                "to": _iso(y),
                "listed": len(ids),
                "new": len(new),
                "capped": len(ids) >= TRACE_LIMIT,
            }
        )
    return (1 if errors else 0), {
        "traceql": ns.traceql,
        "bin": ns.bin,
        "total": len(seen),
        "capped_bins": sum(1 for r in rows if r.get("capped")),
        "bins": rows,
        "error": "; ".join(errors),
        "note": "total is deduplicated on trace id; a capped bin under-counts - narrow --bin or split the selector",
    }


def _f(v) -> str:
    return (
        "-"
        if v is None
        else (f"{v:.0f}" if isinstance(v, float) and v >= 10 else str(v))
    )


def render(o: dict) -> str:
    out = []
    if o.get("error"):
        out.append("ERROR " + o["error"])
    if "operations" in o:
        sm = o.get("span_metrics_present")
        out.append(
            f"{'operation':44s} {'rooted':>6} {'span p50':>8} {'p95':>7} {'p99':>7} {'calls':>6} | {'trace p50':>9} {'p95':>7} {'max':>7} | worst containing"
        )
        for k, e in o["operations"].items():
            out.append(
                f"{k:44s} {_f(e['rooted_traces']):>6} {_f(e.get('span_p50_ms')):>8} {_f(e.get('span_p95_ms')):>7} {_f(e.get('span_p99_ms')):>7} {_f(e.get('span_calls')):>6} | "
                f"{_f(e['trace_p50_ms']):>9} {_f(e['trace_p95_ms']):>7} {_f(e['trace_max_ms']):>7} | {e['worst_containing_trace']} ({_f(e['worst_containing_ms'])} ms)"
                f"{'  TRUNCATED' if e['truncated'] else ''}"
            )
        out.append(
            "  span p50/p95/p99 and calls: span metrics (exact span latency)"
            + (
                ""
                if sm
                else " - ABSENT on this store, only the trace-level reading is available"
            )
            + "; trace p50/p95/max: search over traces rooted at the operation (integer ms); exemplars: p50_trace / worst_rooted_trace / worst_containing_trace in --json"
        )
        for tid, s in (o.get("exemplars") or {}).items():
            tok = (
                f", gen_ai tokens in/out {s['gen_ai_tokens']['input']}/{s['gen_ai_tokens']['output']}"
                if s.get("gen_ai_tokens")
                else ""
            )
            out.append(
                f"\n-- {tid}: {s.get('root')}  {s.get('duration_ms')} ms, {s.get('spans')} spans, errors={s.get('errors')}{tok}"
            )
            for name, e in list((s.get("by_name") or {}).items())[:12]:
                out.append(f"     {e['count']:4d}  {name}  (max {e['max_ms']} ms)")
    elif "traces" in o and o.get("count") is not None:
        out.append(
            f"{o['count']} traces{'  TRUNCATED at --limit' if o['truncated'] else ''}"
        )
        for t in o["traces"][:50]:
            out.append(
                f"  {t['traceID']}  {t.get('rootServiceName')} {t.get('rootTraceName')}  {t.get('durationMs')} ms"
            )
    elif "traces" in o:
        for d in o["traces"]:
            s = d.get("summary")
            if not s:
                out.append(f"ERROR {d.get('error')}")
                continue
            tok = (
                f", gen_ai tokens in/out {s['gen_ai_tokens']['input']}/{s['gen_ai_tokens']['output']}"
                if s.get("gen_ai_tokens")
                else ""
            )
            out.append(
                f"== {s['trace_id']}  {s['root']}  {s['duration_ms']} ms, {s['spans']} spans over {', '.join(s['services'])}, errors={s['errors']}{tok}"
            )
            for name, e in list(s["by_name"].items())[:15]:
                out.append(f"   {e['count']:4d}  {name}  (max {e['max_ms']} ms)")
            for sp in d.get("spans") or []:
                attrs = " ".join(f"{k}={v}" for k, v in list(sp["attrs"].items())[:6])
                out.append(
                    f"      {sp['duration_ms']:>9} ms  {sp['service']:16s} {sp['name']}  [{sp['kind']}] parent={sp['parent_id'] or '-'}  {attrs}"
                )
    elif "bins" in o:
        out.append(
            f"{o['total']} traces (deduplicated) in {len(o['bins'])} bins of {o['bin']}; capped bins: {o['capped_bins']}"
        )
        for r in o["bins"]:
            out.append(
                f"  {r['from']} .. {r['to']}  listed={r.get('listed')} new={r.get('new')}{'  CAPPED' if r.get('capped') else ''}{'  ' + r['error'] if r.get('error') else ''}"
            )
        out.append("  " + o["note"])
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ops")
    a.add_argument("--service", action="append", required=True)
    a.add_argument("--name", action="append")
    a.add_argument("--limit", type=int, default=TRACE_LIMIT)
    a.add_argument("--fetch")
    add_window(a)
    b = sub.add_parser("get")
    b.add_argument("ids", nargs="+")
    b.add_argument("--out")
    b.add_argument("--spans", action="store_true")
    b.add_argument("--json", action="store_true")
    c = sub.add_parser("search")
    c.add_argument("traceql")
    c.add_argument("--limit", type=int, default=TRACE_LIMIT)
    add_window(c)
    d = sub.add_parser("count")
    d.add_argument("traceql")
    d.add_argument("--bin", default="30s")
    add_window(d)
    ns = ap.parse_args()
    code, out = {
        "ops": cmd_ops,
        "get": cmd_get,
        "search": cmd_search,
        "count": cmd_count,
    }[ns.cmd](ns)
    emit(out, ns.json, render)
    return code


if __name__ == "__main__":
    sys.exit(main())
