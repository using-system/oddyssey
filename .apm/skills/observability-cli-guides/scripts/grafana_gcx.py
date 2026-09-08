"""Shared plumbing for the grafana-* scripts: run gcx, read its envelopes.

Every trap this module absorbs was measured on gcx 1.2.0 and is written
down in grafana.md's history; the scripts import it so no agent has to
re-apply one by hand:

- gcx prints a ``{"class":"hint",...}`` line before the payload - on stderr
  on the current build, on stdout on older ones - and pretty-prints its
  JSON over many lines: hint lines are dropped wherever they landed, then
  stdout is parsed whole, never line by line;
- a large answer is not on stdout at all: gcx writes a
  ``gcx.spill_reference`` object naming a file, which is read in its place;
- an error is a single ``gcx.error`` object on stdout with exit 1 - it is
  surfaced as an error, never mistaken for empty data;
- ``traces query`` prints trace ids unpadded (31 hex), ``traces get`` carries
  them as base64 - both are normalised to the padded 32-hex form;
- profile flamegraphs are flat string quadruples ``[offset, total, self,
  nameIndex]`` per level - summed per frame here, once;
- Loki answers at most 5 000 lines per query, server-side: a window that
  holds more is split until every piece fits, and the pieces are merged.

Only the standard library is used, so the scripts run wherever python3 does.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

TIMEOUT = 180
WORKERS = 8
# The one ceiling gcx enforces on a trace search (Grafana Cloud refuses more).
TRACE_LIMIT = 1000
# Loki's server-side maximum per query (max_entries_limit_per_query); a
# larger --limit is refused, so a bigger window is read in pieces instead.
LOG_LIMIT = 5000
LOG_SPLIT_DEPTH = 6
CPU_PROFILE = "process_cpu:cpu:nanoseconds:cpu:nanoseconds"
HINT_PREFIX = '{"class":"hint"'


@dataclass
class Result:
    args: list[str]
    ok: bool
    data: object = None
    error: str = ""
    exit_code: int = 0
    seconds: float = 0.0
    spilled_from: str = ""

    @property
    def command(self) -> str:
        return "gcx " + " ".join(_quote(a) for a in self.args)


def _quote(a: str) -> str:
    return (
        a
        if a and all(c.isalnum() or c in "-_./:=,%" for c in a)
        else "'" + a.replace("'", "'\\''") + "'"
    )


def _parse_stdout(text: str):
    """Drop hint lines wherever they landed, then parse the rest whole."""
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith(HINT_PREFIX)]
    body = "\n".join(lines).strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        pass
    # An error object on the last line after non-JSON noise.
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def run_gcx(args: list[str], timeout: int = TIMEOUT, env: dict | None = None) -> Result:
    """Run one gcx command and return its parsed payload, spill followed."""
    if "-o" not in args and "--output" not in args:
        args = [*args, "-o", "json"]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            ["gcx", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **(env or {})},
            check=False,
        )
    except FileNotFoundError:
        return Result(
            args,
            False,
            error="gcx is not installed (command -v gcx is empty)",
            exit_code=127,
        )
    except subprocess.TimeoutExpired:
        return Result(args, False, error=f"timed out after {timeout}s", exit_code=124)
    seconds = time.monotonic() - started
    payload = _parse_stdout(proc.stdout)
    spilled = ""
    if isinstance(payload, dict) and payload.get("type") == "gcx.spill_reference":
        spilled = payload.get("spilled_to", "")
        try:
            with open(spilled, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError) as exc:
            return Result(
                args,
                False,
                error=f"spilled response unreadable: {exc}",
                exit_code=proc.returncode,
                seconds=seconds,
            )
    if isinstance(payload, dict) and payload.get("type") == "gcx.error":
        err = payload.get("error", {})
        msg = err.get("summary", "gcx error")
        if err.get("details"):
            msg += " - " + str(err["details"])[:300]
        return Result(
            args, False, error=msg, exit_code=proc.returncode or 1, seconds=seconds
        )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        tail = [t for t in tail if not t.strip().startswith(HINT_PREFIX)]
        return Result(
            args,
            False,
            error=(tail[-1] if tail else f"exit {proc.returncode}")[:300],
            exit_code=proc.returncode,
            seconds=seconds,
        )
    if payload is None:
        return Result(
            args,
            False,
            error="no JSON on stdout",
            exit_code=proc.returncode,
            seconds=seconds,
        )
    return Result(args, True, data=payload, seconds=seconds, spilled_from=spilled)


def run_many(
    calls: list[list[str]], workers: int = WORKERS, timeout: int = TIMEOUT
) -> list[Result]:
    """Run gcx commands concurrently - verified safe on one context."""
    if not calls:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(calls))) as pool:
        return list(pool.map(lambda a: run_gcx(a, timeout=timeout), calls))


def commands(results: list[Result]) -> list[str]:
    """The gcx commands a subcommand ran, for the report's replay line."""
    return [r.command for r in results]


def errors(results: list[Result]) -> str:
    """The distinct errors, once each - nine identical parse errors are one."""
    return "; ".join(dict.fromkeys(r.error for r in results if not r.ok))


# --- envelopes ---------------------------------------------------------------


def prom_result(data) -> list:
    """`metrics query` -> the result vector/matrix, [] when empty."""
    if not isinstance(data, dict):
        return []
    return (data.get("data") or {}).get("result") or []


def prom_series(data) -> list:
    """`metrics series` -> the label-set list, [] when empty."""
    if not isinstance(data, dict):
        return []
    d = data.get("data")
    return d if isinstance(d, list) else []


def prom_value(data) -> float | None:
    """A scalar instant query -> its single value, None when empty."""
    res = prom_result(data)
    if not res:
        return None
    try:
        return float(res[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def traces_list(data) -> list:
    """`traces query` -> [{traceID, rootServiceName, rootTraceName, startTimeUnixNano, durationMs}]."""
    if not isinstance(data, dict):
        return []
    return data.get("traces") or []


def logs_lines(data) -> list[dict]:
    """`logs query` -> flat list of {timestamp, line, stream, meta}, oldest first."""
    out = []
    if not isinstance(data, dict):
        return out
    for stream in (data.get("data") or {}).get("result") or []:
        labels = stream.get("stream") or {}
        for v in stream.get("values") or []:
            if isinstance(v, dict):
                out.append(
                    {
                        "timestamp": v.get("timestamp"),
                        "line": v.get("line", ""),
                        "stream": labels,
                        "meta": v.get("structuredMetadata") or {},
                    }
                )
            elif isinstance(v, list) and len(v) >= 2:
                out.append(
                    {"timestamp": v[0], "line": v[1], "stream": labels, "meta": {}}
                )
    out.sort(key=lambda r: int(r["timestamp"] or 0))
    return out


def logs_all(
    selector: str, frm: str, to: str, pipeline: str = "", limit: int = LOG_LIMIT
) -> tuple[list[dict], list[Result], bool]:
    """Every line of a window, read in pieces when one query saturates the cap.

    Returns (lines, the gcx results run, still_truncated). A piece that comes
    back with exactly `limit` lines is split in two and read again, down to
    LOG_SPLIT_DEPTH; lines are deduplicated on (timestamp, line).
    """
    expr = selector + (" " + pipeline if pipeline else "")
    results: list[Result] = []
    lines: dict[tuple, dict] = {}
    truncated = False
    pending = [(parse_ts(frm), parse_ts(to), 0)]
    while pending:
        batch, pending = pending, []
        calls = [
            [
                "logs",
                "query",
                expr,
                "--from",
                iso(a),
                "--to",
                iso(b),
                "--limit",
                str(limit),
            ]
            for a, b, _ in batch
        ]
        got = run_many(calls)
        results += got
        for (a, b, depth), r in zip(batch, got):
            if not r.ok:
                continue
            got_lines = logs_lines(r.data)
            if (
                len(got_lines) >= limit
                and depth < LOG_SPLIT_DEPTH
                and (b - a) > timedelta(seconds=2)
            ):
                mid = a + (b - a) / 2
                pending += [(a, mid, depth + 1), (mid, b, depth + 1)]
                continue
            if len(got_lines) >= limit:
                truncated = True
            for ln in got_lines:
                lines[(ln["timestamp"], ln["line"])] = ln
    out = sorted(lines.values(), key=lambda r: int(r["timestamp"] or 0))
    return out, results, truncated


def profile_types(data) -> list[str]:
    if not isinstance(data, dict):
        return []
    return [p.get("ID") for p in data.get("profileTypes") or [] if p.get("ID")]


def label_names(data) -> list[str]:
    """`profiles labels` / `logs labels` -> the names list, [] for null."""
    if not isinstance(data, dict):
        return []
    names = data.get("names")
    if names is None:
        names = data.get("data")
    return [n for n in (names or []) if isinstance(n, str)]


# --- trace ids ---------------------------------------------------------------


def hex_trace_id(value: str) -> str:
    """Base64 (traces get) or unpadded hex (traces query) -> padded 32 hex."""
    if not value:
        return ""
    v = value.strip()
    if all(c in "0123456789abcdefABCDEF" for c in v):
        return v.lower().rjust(32, "0")
    try:
        return base64.b64decode(v + "=" * (-len(v) % 4)).hex().rjust(32, "0")
    except (ValueError, TypeError):
        return v


def short_trace_id(hexid: str) -> str:
    """The unpadded form `traces query` prints, for comparisons."""
    return hexid.lstrip("0") or "0"


# --- traces get --------------------------------------------------------------


def attr_value(v):
    if not isinstance(v, dict):
        return v
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in v:
            x = v[k]
            if k == "intValue":
                try:
                    return int(x)
                except (TypeError, ValueError):
                    return x
            return x
    if "arrayValue" in v:
        return [attr_value(e) for e in (v["arrayValue"].get("values") or [])]
    return v


def flatten_trace(doc) -> list[dict]:
    """`traces get` -> one dict per span, with service, parent and duration."""
    root = doc.get("trace", doc) if isinstance(doc, dict) else {}
    spans = []
    for rs in root.get("resourceSpans") or []:
        res = {
            a["key"]: attr_value(a.get("value"))
            for a in (rs.get("resource") or {}).get("attributes") or []
        }
        service = res.get("service.name", "")
        for ss in rs.get("scopeSpans") or []:
            scope = (ss.get("scope") or {}).get("name", "")
            for s in ss.get("spans") or []:
                try:
                    start, end = (
                        int(s.get("startTimeUnixNano", 0)),
                        int(s.get("endTimeUnixNano", 0)),
                    )
                except (TypeError, ValueError):
                    start, end = 0, 0
                spans.append(
                    {
                        "trace_id": hex_trace_id(s.get("traceId", "")),
                        "span_id": s.get("spanId", ""),
                        "parent_id": s.get("parentSpanId", ""),
                        "service": service,
                        "scope": scope,
                        "name": s.get("name", ""),
                        "kind": (s.get("kind") or "").replace("SPAN_KIND_", ""),
                        "start_ns": start,
                        "end_ns": end,
                        "duration_ms": round((end - start) / 1e6, 3),
                        "status": (s.get("status") or {}).get("code", "") or "UNSET",
                        "attrs": {
                            a["key"]: attr_value(a.get("value"))
                            for a in s.get("attributes") or []
                        },
                    }
                )
    spans.sort(key=lambda s: s["start_ns"])
    return spans


def trace_summary(spans: list[dict]) -> dict:
    """What a report quotes off one trace: root, totals, per (service, name) counts, tokens."""
    roots = [s for s in spans if not s["parent_id"]]
    root = roots[0] if roots else (spans[0] if spans else None)
    by = {}
    for s in spans:
        k = f"{s['service']} {s['name']}"
        e = by.setdefault(k, {"count": 0, "max_ms": 0.0, "sum_ms": 0.0})
        e["count"] += 1
        e["max_ms"] = max(e["max_ms"], s["duration_ms"])
        e["sum_ms"] += s["duration_ms"]
    tokens_in = sum(
        int(s["attrs"].get("gen_ai.usage.input_tokens") or 0) for s in spans
    )
    tokens_out = sum(
        int(s["attrs"].get("gen_ai.usage.output_tokens") or 0) for s in spans
    )
    return {
        "trace_id": root["trace_id"] if root else "",
        "root": f"{root['service']} {root['name']}" if root else "",
        "duration_ms": root["duration_ms"] if root else 0,
        "spans": len(spans),
        "services": sorted({s["service"] for s in spans}),
        "errors": sum(1 for s in spans if s["status"] == "STATUS_CODE_ERROR"),
        "by_name": dict(sorted(by.items(), key=lambda kv: -kv[1]["count"])),
        "longest": [
            {
                "service": s["service"],
                "name": s["name"],
                "duration_ms": s["duration_ms"],
            }
            for s in sorted(spans, key=lambda s: -s["duration_ms"])[:5]
        ],
        "gen_ai_tokens": {"input": tokens_in, "output": tokens_out}
        if tokens_in or tokens_out
        else None,
    }


# --- profiles ----------------------------------------------------------------


def flame_frames(data) -> tuple[int, dict[str, dict]]:
    """flamegraph -> (total, {frame: {self, total_max}}) in the profile's unit."""
    fg = (data or {}).get("flamegraph") or {}
    names = fg.get("names") or []
    try:
        total = int(fg.get("total") or 0)
    except (TypeError, ValueError):
        total = 0
    frames: dict[str, dict] = {}
    for level in fg.get("levels") or []:
        vals = level.get("values") if isinstance(level, dict) else level
        vals = vals or []
        for i in range(0, len(vals) - 3, 4):
            try:
                tot, slf, idx = int(vals[i + 1]), int(vals[i + 2]), int(vals[i + 3])
            except (TypeError, ValueError):
                continue
            if idx >= len(names):
                continue
            e = frames.setdefault(names[idx], {"self": 0, "total_max": 0})
            e["self"] += slf
            e["total_max"] = max(e["total_max"], tot)
    frames.pop("total", None)
    return total, frames


# --- numbers and time --------------------------------------------------------


def percentile_index(n: int, q: float) -> int:
    """The one index every percentile and every exemplar pick uses."""
    return min(n - 1, max(0, round(q * (n - 1))))


def percentiles(values: list[float], qs=(0.5, 0.95, 0.99)) -> dict:
    if not values:
        return {f"p{int(q * 100)}": None for q in qs} | {"max": None, "count": 0}
    v = sorted(values)
    out = {f"p{int(q * 100)}": v[percentile_index(len(v), q)] for q in qs}
    out["max"] = v[-1]
    out["count"] = len(v)
    return out


def parse_duration(s: str) -> int:
    """'90s', '30m', '2h' -> seconds; anything else is a usage error, not a traceback."""
    s = (s or "").strip()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if len(s) < 2 or s[-1] not in units:
        raise SystemExit(
            f"a duration is <number><s|m|h|d>, e.g. 90s or 30m - got {s!r}"
        )
    try:
        return int(float(s[:-1]) * units[s[-1]])
    except ValueError:
        raise SystemExit(
            f"a duration is <number><s|m|h|d>, e.g. 90s or 30m - got {s!r}"
        ) from None


def parse_ts(s: str) -> datetime:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit(
            f"a timestamp is RFC3339 UTC, e.g. 2026-09-08T16:40:53Z - got {s!r}"
        ) from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def add_window(ap):
    ap.add_argument(
        "--from",
        dest="frm",
        help="window start, RFC3339 UTC (e.g. 2026-09-08T16:40:53Z)",
    )
    ap.add_argument("--to", help="window end, RFC3339 UTC")
    ap.add_argument(
        "--since", help="lookback ending now instead of --from/--to (e.g. 30m)"
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")


def resolve_window(ns) -> tuple[str, str]:
    """--from/--to or --since -> concrete RFC3339 (from, to), always both."""
    if getattr(ns, "since", None):
        end = datetime.now(timezone.utc).replace(microsecond=0)
        return iso(end - timedelta(seconds=parse_duration(ns.since))), iso(end)
    if getattr(ns, "frm", None) and getattr(ns, "to", None):
        a, b = parse_ts(ns.frm), parse_ts(ns.to)
        if b <= a:
            raise SystemExit("--to must be after --from")
        return iso(a), iso(b)
    raise SystemExit(
        "a window is required: --from <RFC3339> --to <RFC3339>, or --since <duration>"
    )


def window_args(ns) -> list[str]:
    """The window as the --from/--to flags every gcx family accepts."""
    frm, to = resolve_window(ns)
    return ["--from", frm, "--to", to]


def window_seconds(frm: str, to: str) -> int:
    return max(1, int((parse_ts(to) - parse_ts(frm)).total_seconds()))


def emit(obj, as_json: bool, render=None) -> None:
    if as_json or render is None:
        print(json.dumps(obj, indent=1, default=str))
    else:
        print(render(obj))


def render_commands(o: dict) -> list[str]:
    cmds = o.get("commands") or []
    if not cmds:
        return []
    return ["queries run (record these):"] + ["  " + c for c in cmds]


def fmt_ms(x) -> str:
    return "-" if x is None else (f"{x:.0f}" if x >= 10 else f"{x:.2f}")
