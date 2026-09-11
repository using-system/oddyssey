"""Shared plumbing for the seq-* scripts: find seqcli, run it, read its envelopes.

Every trap this module absorbs was measured on seqcli 2026.1.2616 against
Seq 2026.1.17114 (2026-09-11) and is written down in guide.md; the scripts
import it so no agent has to re-apply one by hand:

- ``seqcli`` installed as a dotnet global tool lives in ``~/.dotnet/tools``,
  which is not always on PATH: the binary is looked up on PATH first, then
  there;
- ``search --json`` prints newline-delimited CLEF events, newest first, and
  ``-c`` defaults to **1** - a count is always passed; a malformed ``-f``
  filter prints nothing and exits 0, indistinguishable from an empty
  window, so an empty search is re-validated through ``query`` (which does
  report the syntax error, exit 1) before it is reported as empty;
- ``query --json`` prints one JSON object in three shapes: tabular
  (``Columns``/``Rows``), time-sliced (``group by time(...)``:
  ``Slices`` of ``{Time, Rows}``, no top-level ``Rows``), and keyed series
  (``group by <prop>, time(...)``: ``Series`` of ``{Key, Slices}``) - all
  three are normalised here; a query error is ``{"Error", "Reasons"}`` with
  exit 1 and is surfaced as an error, never as empty data;
- ``order by count(*)`` is refused: an aggregate must carry an ``as`` alias
  to be ordered on - the scripts alias every aggregate;
- ``@Elapsed`` (and every ``percentile``/``max`` of it) is in Seq's native
  100 ns ticks: divided by 10 000 here, once, into milliseconds;
- an event's ``@t`` is printed in the server's **local offset** while its
  ``@st`` (span start) is UTC: both are parsed with their offset and
  compared in UTC, and a span's duration is computed from the two;
- ``node health`` prints the bare word ``Unreachable`` (not JSON) and exits
  1 when the server does not answer;
- a histogram metric (kind ``Exponential``) aggregates to a bucket object
  (``{buckets:[{count, midpoint}], count, min, max, scale}``) under
  ``max()``, and ``mean``/``percentile`` on it are null: quantiles are
  derived from the buckets here.

Only the standard library is used, so the scripts run wherever python3 does.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

TIMEOUT = 180
WORKERS = 8
TICKS_PER_MS = 10_000
DOTNET_TOOL = os.path.join(os.path.expanduser("~"), ".dotnet", "tools", "seqcli")


def find_seqcli() -> tuple[str, str]:
    """(path, where) - PATH first, then the dotnet global tool directory."""
    on_path = shutil.which("seqcli")
    if on_path:
        return on_path, "PATH"
    if os.access(DOTNET_TOOL, os.X_OK):
        return DOTNET_TOOL, "~/.dotnet/tools"
    return "", ""


SEQCLI, SEQCLI_WHERE = find_seqcli()


@dataclass
class Result:
    args: list[str]
    ok: bool
    data: object = None
    error: str = ""
    exit_code: int = 0
    seconds: float = 0.0
    stderr: str = ""
    extra: list = field(default_factory=list)  # follow-up commands this call ran

    @property
    def command(self) -> str:
        return "seqcli " + " ".join(_quote(a) for a in self.args)


def _quote(a: str) -> str:
    return (
        a
        if a and all(c.isalnum() or c in "-_./:=,%@" for c in a)
        else "'" + a.replace("'", "'\\''") + "'"
    )


def _run_raw(
    args: list[str], timeout: int
) -> tuple[subprocess.CompletedProcess | None, Result | None]:
    if not SEQCLI:
        return None, Result(
            args,
            False,
            error="seqcli is not installed: not on PATH and not at ~/.dotnet/tools/seqcli",
            exit_code=127,
        )
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [SEQCLI, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, Result(
            args, False, error=f"timed out after {timeout}s", exit_code=124
        )
    proc.seconds = time.monotonic() - started  # type: ignore[attr-defined]
    return proc, None


def _error_text(proc: subprocess.CompletedProcess) -> str:
    text = (proc.stderr or proc.stdout or "").strip()
    if text.startswith("{"):
        try:
            obj = json.loads(text.splitlines()[0])
            reasons = obj.get("Reasons") or []
            return (obj.get("Error", "seqcli error") + " " + "; ".join(reasons)).strip()
        except ValueError:
            pass
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return (lines[0] if lines else f"exit {proc.returncode}")[:300]


def run(args: list[str], kind: str = "object", timeout: int = TIMEOUT) -> Result:
    """Run one seqcli command; kind is how stdout is read:
    'object' (one JSON document), 'ndjson' (one JSON value per line),
    'text' (verbatim)."""
    proc, failed = _run_raw(args, timeout)
    if failed:
        return failed
    seconds = proc.seconds  # type: ignore[attr-defined]
    out = proc.stdout or ""
    if kind == "text":
        if proc.returncode != 0:
            return Result(
                args,
                False,
                error=_error_text(proc),
                exit_code=proc.returncode,
                seconds=seconds,
                stderr=proc.stderr,
            )
        return Result(args, True, data=out.strip(), seconds=seconds, stderr=proc.stderr)
    if kind == "ndjson":
        rows = []
        for ln in out.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except ValueError:
                continue
        if proc.returncode != 0:
            return Result(
                args,
                False,
                error=_error_text(proc),
                exit_code=proc.returncode,
                seconds=seconds,
                stderr=proc.stderr,
            )
        return Result(args, True, data=rows, seconds=seconds, stderr=proc.stderr)
    body = out.strip()
    payload = None
    if body:
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
    if isinstance(payload, dict) and "Error" in payload and "Columns" not in payload:
        reasons = payload.get("Reasons") or []
        return Result(
            args,
            False,
            error=(payload["Error"] + " " + "; ".join(reasons)).strip(),
            exit_code=proc.returncode or 1,
            seconds=seconds,
        )
    if proc.returncode != 0:
        return Result(
            args,
            False,
            error=_error_text(proc),
            exit_code=proc.returncode,
            seconds=seconds,
            stderr=proc.stderr,
        )
    if payload is None:
        return Result(
            args,
            False,
            error=(body or "no JSON on stdout")[:300],
            exit_code=proc.returncode,
            seconds=seconds,
            stderr=proc.stderr,
        )
    return Result(args, True, data=payload, seconds=seconds, stderr=proc.stderr)


def run_many(
    calls: list[tuple], workers: int = WORKERS, timeout: int = TIMEOUT
) -> list[Result]:
    """Run (args, kind) pairs concurrently - measured safe, 8 side by side."""
    if not calls:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(calls))) as pool:
        return list(pool.map(lambda c: run(list(c[0]), c[1], timeout=timeout), calls))


def commands(results: list[Result]) -> list[str]:
    """The seqcli commands run, in order, follow-ups included."""
    out = []
    for r in results:
        out.append(r.command)
        out += r.extra
    return out


_POSITION = re.compile(r"line \d+, column \d+")


def errors(results: list[Result]) -> str:
    seen: dict[str, str] = {}
    for r in results:
        if not r.ok:
            seen.setdefault(_POSITION.sub("line N, column N", r.error), r.error)
    return "; ".join(seen.values())


# --- the query surface ----------------------------------------------------------


def window_flags(frm: str, to: str) -> list[str]:
    return [f"--start={frm}", f"--end={to}"]


def query(sql: str, frm: str = "", to: str = "", timeout: int = TIMEOUT) -> Result:
    """`seqcli query -q <sql> --json`, its three shapes normalised into
    data = {"columns": [...], "rows": [[...]]} |
           {"columns", "slices": [{"time", "rows"}]} |
           {"columns", "series": [{"key": [...], "slices": [...]}]}."""
    args = ["query", "-q", sql]
    if frm and to:
        args += window_flags(frm, to)
    args.append("--json")
    r = run(args, "object", timeout)
    if r.ok:
        r.data = _normalise_query(r.data)
    return r


def _normalise_query(d) -> dict:
    if not isinstance(d, dict):
        return {"columns": [], "rows": []}
    cols = d.get("Columns") or []
    if "Series" in d:
        return {
            "columns": cols,
            "series": [
                {
                    "key": s.get("Key") or [],
                    "slices": [
                        {
                            "time": _slice_time(sl.get("Time")),
                            "rows": sl.get("Rows") or [],
                        }
                        for sl in s.get("Slices") or []
                    ],
                }
                for s in d["Series"]
            ],
        }
    if "Slices" in d:
        return {
            "columns": cols,
            "slices": [
                {"time": _slice_time(sl.get("Time")), "rows": sl.get("Rows") or []}
                for sl in d["Slices"]
            ],
        }
    return {"columns": cols, "rows": d.get("Rows") or []}


def _slice_time(t) -> str:
    dt = parse_seq_ts(t or "")
    return iso(dt) if dt else (t or "")


def table(r: Result) -> list[dict]:
    """A tabular result as one dict per row, keyed by column name."""
    if not r.ok or not isinstance(r.data, dict) or "rows" not in r.data:
        return []
    cols = r.data["columns"]
    return [dict(zip(cols, row)) for row in r.data["rows"]]


def slices(r: Result) -> list[dict]:
    """A time-sliced result as [{"time": <iso>, <col>: <value>, ...}], one per
    interval (the first row of each slice - an ungrouped time query has one)."""
    if not r.ok or not isinstance(r.data, dict) or "slices" not in r.data:
        return []
    cols = r.data["columns"]
    out = []
    for sl in r.data["slices"]:
        row = sl["rows"][0] if sl["rows"] else [None] * len(cols)
        out.append({"time": sl["time"], **dict(zip(cols, row))})
    return out


def series(r: Result) -> list[dict]:
    """A keyed series result as [{"key": {...}, "slices": [{"time", <col>...}]}]."""
    if not r.ok or not isinstance(r.data, dict) or "series" not in r.data:
        return []
    cols = r.data["columns"]
    n_key = len(cols) - _n_value_columns(r.data)
    out = []
    for s in r.data["series"]:
        key = dict(zip(cols[:n_key], s["key"]))
        sls = []
        for sl in s["slices"]:
            row = sl["rows"][0] if sl["rows"] else [None] * (len(cols) - n_key)
            sls.append({"time": sl["time"], **dict(zip(cols[n_key:], row))})
        out.append({"key": key, "slices": sls})
    return out


def _n_value_columns(d: dict) -> int:
    for s in d.get("series") or []:
        for sl in s.get("slices") or []:
            if sl.get("rows"):
                return len(sl["rows"][0])
    return max(
        1,
        len(d.get("columns") or [])
        - len((d.get("series") or [{}])[0].get("key") or []),
    )


def search(
    filt: str, count: int, frm: str = "", to: str = "", timeout: int = TIMEOUT
) -> Result:
    """`seqcli search -f <filter> -c <count> --json` -> data = the events,
    newest first. An empty answer is re-validated: the same filter is run as
    `select count(*) from stream where <filter>`, and a syntax error there
    becomes this result's error (a malformed filter is otherwise silent)."""
    args = ["search", "-f", filt, "-c", str(count)]
    if frm and to:
        args += window_flags(frm, to)
    args.append("--json")
    r = run(args, "ndjson", timeout)
    if r.ok and not r.data:
        check = query(
            f"select count(*) as n from stream where {filt}", frm, to, timeout
        )
        r.extra.append(check.command)
        if not check.ok:
            r.ok = False
            r.error = "filter refused: " + check.error
            r.exit_code = 1
    return r


def health(timeout: int = 30) -> Result:
    """`seqcli node health --json` -> data = {"status", "description"};
    Unreachable (bare text, exit 1) becomes an error."""
    r = run(["node", "health", "--json"], "object", timeout)
    if not r.ok and "Unreachable" in (r.error or ""):
        r.error = "Unreachable: the server at the configured URL did not answer"
    return r


def trace(trace_id: str, logs: bool = True, timeout: int = TIMEOUT) -> Result:
    args = ["trace", "-i", trace_id]
    if logs:
        args += ["--logs", "--exceptions"]
    args.append("--json")
    return run(args, "object", timeout)


def flatten_trace(doc) -> list[dict]:
    """`trace --json` -> one dict per node, depth-first, with depth."""
    out: list[dict] = []

    def walk(node, depth):
        if not isinstance(node, dict):
            return
        kind = node.get("type") or ("span" if "start" in node else "log")
        out.append(
            {
                "depth": depth,
                "type": kind,
                "span_id": node.get("spanId", ""),
                "parent_id": node.get("parentSpanId", ""),
                "level": node.get("level", ""),
                "time": node.get("start") or node.get("timestamp"),
                "elapsed_ms": node.get("elapsedMs"),
                "message": node.get("message", ""),
                "exception": node.get("exception", ""),
            }
        )
        for child in node.get("children") or []:
            walk(child, depth + 1)

    if isinstance(doc, dict):
        walk(doc.get("root"), 0)
    return out


# --- filters -------------------------------------------------------------------------


def quote(s: str) -> str:
    """A Seq single-quoted string literal, quotes doubled."""
    return "'" + str(s).replace("'", "''") + "'"


def service_clause(services: list[str], key: str) -> str:
    """`<key> in ['a', 'b']`, or '' for no selector."""
    if not services:
        return ""
    return f"{key} in [{', '.join(quote(s) for s in services)}]"


def contains_clause(text: str) -> str:
    """Case-insensitive substring on the message and the exception - works in
    both `search -f` and `query -q` (double-quoted text fragments do not)."""
    pat = quote("%" + text.replace("%", "%%") + "%")
    return f"(@Message like {pat} ci or @Exception like {pat} ci)"


def where(*clauses: str) -> str:
    parts = [c for c in clauses if c]
    return " and ".join(
        f"({c})" if " or " in c and not c.startswith("(") else c for c in parts
    )


def sql_where(*clauses: str) -> str:
    w = where(*clauses)
    return f" where {w}" if w else ""


# --- events --------------------------------------------------------------------------

_TEMPLATE_HOLE = re.compile(r"\{@?([A-Za-z0-9_]+)(?::[^}]*)?\}")


def render_message(ev: dict) -> str:
    """`@mt` with its holes filled from the event's properties."""
    mt = ev.get("@mt") or ev.get("@m") or ""

    def sub(m):
        v = ev.get(m.group(1))
        return (
            m.group(0)
            if v is None
            else (json.dumps(v) if isinstance(v, (dict, list)) else str(v))
        )

    return _TEMPLATE_HOLE.sub(sub, mt)


def parse_seq_ts(s: str) -> datetime | None:
    """A Seq timestamp (7-digit fraction, any offset) -> aware UTC datetime."""
    if not s:
        return None
    m = re.match(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?$",
        s.strip(),
    )
    if not m:
        return None
    base, frac, off = m.groups()
    micro = int((frac or "0")[:6].ljust(6, "0"))
    try:
        dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(
            microsecond=micro, tzinfo=timezone.utc
        )
    except ValueError:
        return None
    if off and off != "Z":
        sign = 1 if off[0] == "+" else -1
        tz = timezone(sign * timedelta(hours=int(off[1:3]), minutes=int(off[4:6])))
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def event_time(ev: dict) -> str:
    dt = parse_seq_ts(ev.get("@t", ""))
    return iso_ms(dt) if dt else ev.get("@t", "")


def elapsed_ms(ev: dict) -> float | None:
    """A span's duration from @t - @st (both offsets honoured), in ms."""
    end, start = parse_seq_ts(ev.get("@t", "")), parse_seq_ts(ev.get("@st", ""))
    if not end or not start:
        return None
    return round((end - start).total_seconds() * 1000, 3)


def ticks_ms(x) -> float | None:
    if x is None:
        return None
    try:
        return round(float(x) / TICKS_PER_MS, 3)
    except (TypeError, ValueError):
        return None


def properties(ev: dict) -> dict:
    return {k: v for k, v in ev.items() if not k.startswith("@")}


def is_span(ev: dict) -> bool:
    return "@st" in ev


# --- histograms ----------------------------------------------------------------------


def hist_quantiles(h, qs=(0.5, 0.95, 0.99)) -> dict:
    """An Exponential histogram object -> approximate quantiles from its
    bucket midpoints, plus the exact count, min and max it carries."""
    out = {f"p{int(q * 100)}": None for q in qs} | {
        "count": 0,
        "min": None,
        "max": None,
    }
    if not isinstance(h, dict):
        return out
    buckets = sorted(
        (
            (b.get("midpoint"), b.get("count") or 0)
            for b in h.get("buckets") or []
            if b.get("midpoint") is not None
        ),
        key=lambda b: b[0],
    )
    total = sum(c for _, c in buckets)
    out["count"] = h.get("count") or total
    out["min"], out["max"] = h.get("min"), h.get("max")
    if not total:
        return out
    for q in qs:
        target = q * total
        acc = 0
        for mid, c in buckets:
            acc += c
            if acc >= target:
                out[f"p{int(q * 100)}"] = round(mid, 3)
                break
    return out


def is_histogram(v) -> bool:
    return isinstance(v, dict) and "buckets" in v


# --- numbers and time -----------------------------------------------------------------


def parse_duration(s: str) -> int:
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
            f"a timestamp is RFC3339 UTC, e.g. 2026-09-11T07:15:00Z - got {s!r}"
        ) from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_ms(dt: datetime) -> str:
    return (
        dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.")
        + f"{dt.microsecond // 1000:03d}Z"
    )


def add_window(ap):
    ap.add_argument(
        "--from",
        dest="frm",
        help="window start, RFC3339 UTC (e.g. 2026-09-11T07:15:00Z)",
    )
    ap.add_argument("--to", help="window end, RFC3339 UTC")
    ap.add_argument(
        "--since", help="lookback ending now instead of --from/--to (e.g. 30m)"
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")


def add_service(ap):
    ap.add_argument(
        "--service",
        action="append",
        default=[],
        help="a service to select, by the value of --service-key; repeatable; none = every service",
    )
    ap.add_argument(
        "--service-key",
        default="Application",
        help="the property a service is named by (default Application; an OTel-instrumented service: @Resource.service.name)",
    )


def resolve_window(ns) -> tuple[str, str]:
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


def emit(obj, as_json: bool, render=None) -> None:
    if as_json or render is None:
        print(json.dumps(obj, indent=1, default=str))
    else:
        print(render(obj))


def render_commands(o: dict) -> list[str]:
    cmds = o.get("commands") or []
    if not cmds:
        return []
    return ["queries run (record these):"] + ["  " + c for c in dict.fromkeys(cmds)]


def fmt_ms(x) -> str:
    return "-" if x is None else (f"{x:.0f}" if x >= 10 else f"{x:.2f}")


def fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".")
    return str(v)
