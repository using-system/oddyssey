"""Shared plumbing for the azure-monitor-* scripts: run az, read its envelopes.

Every trap this module absorbs was measured on azure-cli 2.89.1 (extensions
application-insights 1.2.3, log-analytics 1.0.0b1) on 2026-09-11 and is
written down in guide.md; the scripts import it so no run re-applies one by
hand:

- ``az monitor app-insights query -o json`` answers ``{"tables": [{"columns":
  [{name, type}], "rows": [[...]]}]}`` with typed values, while ``az monitor
  log-analytics query -o json`` answers a flat list of row objects carrying a
  ``TableName`` key with every value stringified (``"n": "484782"``): one
  parser per shape, both yielding a list of dicts, the workspace's numbers
  coerced back;
- ``customDimensions`` (and ``customMeasurements``) come back as a JSON
  string, not an object: decoded here;
- the first use of an auto-installing extension prints ``WARNING:`` lines
  on stderr before the payload, exit 0, and ``list-namespaces`` prints a
  preview warning every time: stderr is read for ``ERROR:`` lines only;
- an error is on stderr, exit 1 for almost everything, exit 3 only for a
  resource that does not exist, exit 2 when az could not parse the command:
  the ``ERROR:`` line is the diagnosis, never the "unexpected error ... Here
  is the traceback" banner or the Python stack under it, and the line is
  classified: a tokenless ``BadArgumentError`` from the component (any
  unsupported function or alias - first, last, percentileif - or unknown
  column), the workspace's ``Inner error`` JSON (which does name the
  semantic error), a value that is not an appId GUID, an identity that must
  log in again, missing rights, an unknown platform metric (the valid ones
  are listed), an unsupported dimension;
- a window is always passed explicitly: ``--start-time``/``--end-time`` on
  the component (``--offset`` is ignored beside them), ``-t start/end`` on
  the workspace - the default offset would silently bound an older window
  to 0 rows;
- the persisted targeting values (``--app``, ``--workspace``,
  ``--resource-group``, ``--subscription``) and a resource id are replaced
  by their field names in angle brackets in the commands the scripts print,
  so the printed lines can go into a committed report as they are.

Only the standard library is used, so the scripts run wherever python3 does.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

TIMEOUT = 180
WORKERS = 6

MASKS = {
    "--app": "<app_insights_app>",
    "-a": "<app_insights_app>",
    "--apps": "<app_insights_app>",
    "--workspace": "<workspace>",
    "-w": "<workspace>",
    "--resource-group": "<resource_group>",
    "-g": "<resource_group>",
    "--subscription": "<subscription>",
    "--resource": "<resource>",
}


@dataclass
class Result:
    args: list[str]
    ok: bool
    data: object = None
    error: str = ""
    kind: str = ""  # a classification of the error, "" on success
    exit_code: int = 0
    seconds: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def command(self) -> str:
        """The az line for the report, targeting values masked by field name."""
        out, mask_next = [], None
        for a in self.args:
            if mask_next:
                out.append(mask_next)
                mask_next = None
                continue
            out.append(_quote(a))
            mask_next = MASKS.get(a)
        return "az " + " ".join(out)


def _quote(a: str) -> str:
    return (
        a
        if a and all(c.isalnum() or c in "-_./:=,%" for c in a)
        else "'" + a.replace("'", "'\\''") + "'"
    )


# --- error classification ----------------------------------------------------

BANNER = "The command failed with an unexpected error"


def _error_lines(stderr: str) -> list[str]:
    return [
        ln[len("ERROR:") :].strip()
        for ln in stderr.splitlines()
        if ln.startswith("ERROR:") and BANNER not in ln
    ]


def classify(stderr: str, code: int) -> tuple[str, str]:
    """(kind, message) read off az's stderr - the ERROR line, never the stack."""
    lines = _error_lines(stderr)
    msg = lines[0] if lines else ""
    text = stderr
    if code == 2:
        tail = [ln for ln in stderr.splitlines() if ln.strip()]
        return "usage", "az could not parse the command: " + (
            msg or (tail[0] if tail else "exit 2")
        )
    if code == 3 or "ApplicationNotFoundError" in text or "ResourceNotFound" in text:
        return "not-found", msg or "the resource does not exist (exit 3)"
    if "The Application Insight is not found" in text:
        return (
            "not-an-appid",
            (
                "the --app value is not an appId GUID (a resource name needs -g): "
                "persist the component's appId"
            ),
        )
    if "AADSTS" in text or "az login" in text or "re-authenticate" in text.lower():
        return (
            "identity",
            msg or "the identity must log in again (az login is yours to run)",
        )
    if (
        "AuthorizationFailed" in text
        or "Forbidden" in text
        or "does not have authorization" in text
    ):
        return "rights", msg or "the identity lacks rights on this resource"
    m = re.search(r"Inner error: (\{.*\})", text, re.DOTALL)
    if "BadArgumentError" in text and m:
        try:
            inner = json.loads(m.group(1))
            deepest = inner
            while isinstance(deepest.get("innererror"), dict):
                deepest = deepest["innererror"]
            return (
                "kql",
                f"{deepest.get('code', '')}: {deepest.get('message', '')}".strip(": "),
            )
        except ValueError:
            pass
    if "BadArgumentError" in text:
        return (
            "kql",
            (
                "BadArgumentError (the component names no token): an unsupported "
                "function or alias (first, last, percentileif, ...), an unknown "
                "column, or a bin converted inside the same summarize"
            ),
        )
    if "Valid metrics:" in text:
        valid = re.search(r"Valid metrics: ([^\n]*)", text)
        return "unknown-metric", "unknown metric; valid: " + (
            valid.group(1).strip() if valid else "?"
        )
    if "does not support requested dimension combination" in text:
        return "dimension", msg
    if "SemanticError" in text or "SyntaxError" in text:
        return "kql", msg
    if code == 124:
        return "timeout", msg
    return "error", msg or f"exit {code}"


# --- running az --------------------------------------------------------------


def run_az(args: list[str], timeout: int = TIMEOUT) -> Result:
    """Run one az command with -o json and return its parsed payload."""
    if "-o" not in args and "--output" not in args:
        args = [*args, "-o", "json"]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            ["az", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "AZURE_CORE_ONLY_SHOW_ERRORS": "true"},
            check=False,
        )
    except FileNotFoundError:
        return Result(
            args,
            False,
            error="az is not installed (command -v az is empty)",
            kind="missing",
            exit_code=127,
        )
    except subprocess.TimeoutExpired:
        return Result(
            args,
            False,
            error=f"timed out after {timeout}s",
            kind="timeout",
            exit_code=124,
        )
    seconds = time.monotonic() - started
    if proc.returncode != 0:
        kind, msg = classify(proc.stderr, proc.returncode)
        return Result(
            args,
            False,
            error=msg,
            kind=kind,
            exit_code=proc.returncode,
            seconds=seconds,
        )
    body = proc.stdout.strip()
    if not body:
        return Result(args, True, data=None, seconds=seconds)
    try:
        return Result(args, True, data=json.loads(body), seconds=seconds)
    except ValueError:
        return Result(
            args,
            False,
            error="no JSON on stdout: " + body[:200],
            kind="error",
            exit_code=0,
            seconds=seconds,
        )


def run_many(
    calls: list[list[str]], workers: int = WORKERS, timeout: int = TIMEOUT
) -> list[Result]:
    """Run az commands concurrently - verified safe on one login (2026-09-11)."""
    if not calls:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(calls))) as pool:
        return list(pool.map(lambda a: run_az(a, timeout=timeout), calls))


def commands(results: list[Result]) -> list[str]:
    return [r.command for r in results]


def failures(results: list[Result]) -> list[dict]:
    return [
        {"command": r.command, "error": r.error, "kind": r.kind}
        for r in results
        if not r.ok
    ]


# --- the two query commands --------------------------------------------------


def ai_call(
    app: str, kql: str, frm: str, to: str, subscription: str | None = None
) -> list[str]:
    """`app-insights query` with the explicit pair - the appId takes no -g and no subscription."""
    return [
        "monitor",
        "app-insights",
        "query",
        "--app",
        app,
        "--analytics-query",
        kql,
        "--start-time",
        frm,
        "--end-time",
        to,
    ]


def la_call(
    workspace: str, kql: str, frm: str, to: str, subscription: str | None = None
) -> list[str]:
    """`log-analytics query` with the timespan as an ISO 8601 interval."""
    args = [
        "monitor",
        "log-analytics",
        "query",
        "--workspace",
        workspace,
        "--analytics-query",
        kql,
        "--timespan",
        f"{frm}/{to}",
    ]
    if subscription:
        args += ["--subscription", subscription]
    return args


def ai_rows(data) -> list[dict]:
    """tables[0] -> one dict per row, keyed by column name, values typed."""
    if not isinstance(data, dict):
        return []
    tables = data.get("tables") or []
    if not tables:
        return []
    t = tables[0]
    names = [c.get("name") for c in t.get("columns") or []]
    return [dict(zip(names, row)) for row in t.get("rows") or []]


def _coerce(v):
    if not isinstance(v, str):
        return v
    s = v.strip()
    if re.fullmatch(r"-?\d+", s):
        try:
            return int(s)
        except ValueError:
            return v
    if re.fullmatch(r"-?\d+\.\d*(e[-+]?\d+)?", s, re.IGNORECASE):
        try:
            return float(s)
        except ValueError:
            return v
    return v


def la_rows(data) -> list[dict]:
    """The flat stringified list -> one dict per row, TableName dropped, numbers coerced."""
    if not isinstance(data, list):
        return []
    out = []
    for row in data:
        if not isinstance(row, dict):
            continue
        out.append({k: _coerce(v) for k, v in row.items() if k != "TableName"})
    return out


def dims(value) -> dict:
    """customDimensions as a dict - a JSON string under -o json, decoded here."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            d = json.loads(value)
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}
    return {}


def kql_str(s: str) -> str:
    """A KQL single-quoted string literal."""
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def kql_in(column: str, values: list[str]) -> str:
    """`| where <column> in ('a', 'b')` - empty when no values (no filter)."""
    if not values:
        return ""
    return f"| where {column} in ({', '.join(kql_str(v) for v in values)}) "


# --- time --------------------------------------------------------------------


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
            f"a timestamp is RFC3339 UTC, e.g. 2026-09-11T10:40:00Z - got {s!r}"
        ) from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def add_window(ap, required: bool = True):
    ap.add_argument(
        "--from",
        dest="frm",
        help="window start, RFC3339 UTC (e.g. 2026-09-11T10:40:00Z)",
    )
    ap.add_argument("--to", help="window end, RFC3339 UTC")
    ap.add_argument(
        "--since", help="lookback ending now instead of --from/--to (e.g. 30m)"
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")


def resolve_window(ns, default_since: str | None = None) -> tuple[str, str]:
    """--from/--to or --since -> (from, to) RFC3339, always both."""
    if getattr(ns, "since", None):
        end = datetime.now(timezone.utc).replace(microsecond=0)
        return iso(end - timedelta(seconds=parse_duration(ns.since))), iso(end)
    if getattr(ns, "frm", None) and getattr(ns, "to", None):
        a, b = parse_ts(ns.frm), parse_ts(ns.to)
        if b <= a:
            raise SystemExit("--to must be after --from")
        return iso(a), iso(b)
    if default_since:
        end = datetime.now(timezone.utc).replace(microsecond=0)
        return iso(end - timedelta(seconds=parse_duration(default_since))), iso(end)
    raise SystemExit(
        "a window is required: --from <RFC3339> --to <RFC3339>, or --since <duration>"
    )


def kql_bin(duration: str) -> str:
    """'30s', '5m', '1h' -> the KQL timespan literal for bin()."""
    parse_duration(duration)
    return duration


# --- output ------------------------------------------------------------------


def emit(obj, as_json: bool, render=None) -> None:
    if as_json or render is None:
        print(json.dumps(obj, indent=1, default=str))
    else:
        print(render(obj))


def render_commands(o: dict) -> list[str]:
    cmds = o.get("commands") or []
    if not cmds:
        return []
    folded = list(dict.fromkeys(cmds))
    head = "queries run (record these):"
    if len(folded) < len(cmds):
        head = f"queries run (record these; {len(cmds)} calls, exact repeats folded):"
    return [head] + ["  " + c for c in folded]


def render_failures(o: dict) -> list[str]:
    return [
        f"FAILED  {f['command']}\n        [{f['kind']}] {f['error']}"
        for f in o.get("failed") or []
    ]


def fmt(x) -> str:
    if x is None or x == "":
        return "-"
    if isinstance(x, float):
        if abs(x) >= 100:
            return f"{x:.0f}"
        if abs(x) >= 10:
            return f"{x:.1f}"
        if abs(x) >= 0.01 or x == 0:
            return f"{x:.2f}"
        return f"{x:.3g}"
    return str(x)


def table(rows: list[dict], cols: list[str], indent: str = "  ") -> list[str]:
    """Fixed-width text rows, the header first."""
    if not rows:
        return [indent + "(none)"]
    cells = [[fmt(r.get(c)) for c in cols] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(cols)]
    out = [indent + "  ".join(c.ljust(widths[i]) for i, c in enumerate(cols))]
    for row in cells:
        out.append(indent + "  ".join(v.ljust(widths[i]) for i, v in enumerate(row)))
    return out


def exit_code(o: dict) -> int:
    return 1 if o.get("failed") else 0
