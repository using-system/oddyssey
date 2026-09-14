"""Shared plumbing for the cloudwatch-* scripts: run aws, read its envelopes.

Every trap this module absorbs was measured on aws-cli 2.36.37 on 2026-09-11
against an account carrying real logs, EMF metrics and X-Ray traces; the
scripts import it so no run re-applies one by hand:

- every call carries ``--profile``/``--region`` (an SSO setup routinely has
  no default profile: a bare call answers for nobody) and ``--output json``,
  captured whole: the CLI auto-paginates a listing into one aggregated JSON
  document, and the result is filtered client-side - never ``--query`` with
  ``--output text`` on a paginated command (that re-applies the filter per
  page and yields a multi-line string), never ``--no-paginate`` beside
  ``--max-items`` (refused), never ``TracesProcessedCount`` as a count (per
  page: the population is ``len(TraceSummaries)``);
- the time units per command: ``filter-log-events`` takes epoch
  milliseconds, ``start-query`` epoch seconds, X-Ray epoch seconds - the
  scripts speak RFC 3339 UTC or ``--since`` and this module converts; an
  X-Ray range over 24 h is refused by the service, so it is refused here
  first (a usage error, exit 2); the timestamps X-Ray renders
  (``StartTime``, ``ApproximateTime``) carry the machine's local offset and
  are converted to UTC before any bucketing;
- a Logs Insights query is ``start-query`` then a bounded ``get-query-results``
  poll (every second, ``INSIGHTS_CAP`` seconds at most, then ``stop-query``):
  a terminal status other than ``Complete`` is the answer, never a partial
  page; the rows come back as ``[{"field", "value"}]`` lists of strings and
  are turned into dicts with the numbers coerced;
- ``get-metric-data`` takes its queries from a JSON file the caller writes
  through :func:`metric_data_file` (the ``Name=,Value=`` shorthand cannot
  parse a ``{param}`` in a route value);
- the errors are classified off stderr: the expired SSO token (``Token has
  expired and refresh failed``, kind ``identity-expired``), a missing
  profile (``no-profile``), no credentials at all (``no-credentials``), a
  ``MalformedQueryException`` with its message (``malformed-query``), an
  X-Ray ``InvalidRequestException`` (``invalid-request``), a
  ``ResourceNotFoundException`` on a log group (``not-found``), a missing
  right (``rights``), a throttle (``throttled``), a usage error the CLI
  refuses with exit 252 (``usage``), a timeout (``timeout``);
- independent calls run concurrently (``run_many``): verified safe on one
  SSO profile - the calls share the cached token without contention;
- the persisted targeting values (``--profile``, ``--region``, the log group
  names) are replaced by their field names in angle brackets in the
  commands the scripts print, so the printed lines can go into a committed
  report as they are.

Only the standard library is used, so the scripts run wherever python3 does.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import NoReturn

TIMEOUT = 300
WORKERS = 8
INSIGHTS_CAP = 120
INSIGHTS_EVERY = 1.0
XRAY_MAX_RANGE = 24 * 3600
XRAY_BATCH = 5

FLAG_MASKS = {"--profile": "<profile>", "--region": "<region>"}
_VALUE_MASKS: dict[str, str] = {}


def register_targets(**values: str | None) -> None:
    """Register field=value pairs so the value is masked as <field> in printed commands."""
    for name, value in values.items():
        if value and value not in _VALUE_MASKS:
            _VALUE_MASKS[value] = (
                f"<{name}>"  # the first field registered names a shared value
            )


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
        """The aws line for the report, targeting values masked by field name."""
        out, mask_next = [], None
        for a in self.args:
            if mask_next:
                out.append(mask_next)
                mask_next = None
                continue
            if a in _VALUE_MASKS:
                out.append(_VALUE_MASKS[a])
            elif a.startswith("file://"):
                out.append("file://<queries.json>")
            else:
                out.append(_quote(a))
            mask_next = FLAG_MASKS.get(a)
        return "aws " + " ".join(out)


def _quote(a: str) -> str:
    return (
        a
        if a and all(c.isalnum() or c in "-_./:=,%" for c in a)
        else "'" + a.replace("'", "'\\''") + "'"
    )


# --- error classification ----------------------------------------------------

ERROR_RE = re.compile(
    r"An error occurred \((\w+)\) when calling the (\w+) operation: (.*)"
)


def classify(stderr: str, code: int) -> tuple[str, str]:
    """(kind, message) read off aws's stderr."""
    text = stderr.strip()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    first = lines[0] if lines else ""
    if "Token has expired and refresh failed" in text or "ExpiredToken" in text:
        return (
            "identity-expired",
            "the profile's cached SSO token has expired: aws sso login --profile <profile> is yours to run",
        )
    if "could not be found" in text and "profile" in text:
        return "no-profile", first
    if "NoCredentials" in text or "Unable to locate credentials" in text:
        return (
            "no-credentials",
            "no credentials resolve for this call: pass the persisted --profile, or check aws configure list-profiles",
        )
    m = ERROR_RE.search(text)
    if m:
        exc, op, msg = m.group(1), m.group(2), m.group(3).strip()
        # the service's banner (request id, proxy) is noise, and a log-group
        # error names the account id: neither belongs in a report line
        msg = re.sub(r"\s*\(Service: .*?\)\s*$", "", msg)
        msg = re.sub(r"account ID '\d+'", "account ID '<account>'", msg)
        detail = f"{exc} on {op}: {msg}"
        if exc == "MalformedQueryException":
            return "malformed-query", detail
        if exc == "InvalidRequestException":
            return "invalid-request", detail
        if exc == "ResourceNotFoundException":
            return "not-found", detail
        if (
            exc
            in (
                "AccessDeniedException",
                "UnauthorizedException",
                "UnrecognizedClientException",
            )
            or "not authorized" in msg
        ):
            return "rights", detail
        if (
            exc in ("ThrottlingException", "LimitExceededException")
            or "Rate exceeded" in msg
        ):
            return "throttled", detail
        if exc in ("ExpiredTokenException", "InvalidIdentityTokenException"):
            return "identity-expired", detail
        return "error", detail
    if (
        code == 252
        or text.startswith("usage:")
        or "Unknown options" in text
        or "Parameter validation failed" in text
    ):
        tail = [
            ln
            for ln in lines
            if not ln.startswith("usage:") and "To see help text" not in ln
        ]
        return "usage", "aws refused the command: " + (tail[-1] if tail else first)
    if code == 124:
        return "timeout", first
    return "error", first or f"exit {code}"


# --- running aws -------------------------------------------------------------


def run_aws(
    args: list[str], profile: str, region: str, timeout: int = TIMEOUT
) -> Result:
    """Run one aws command with --profile/--region/--output json, the payload parsed whole."""
    full = [*args, "--profile", profile, "--region", region, "--output", "json"]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            ["aws", *full],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "AWS_PAGER": ""},
            check=False,
        )
    except FileNotFoundError:
        return Result(
            full,
            False,
            error="aws is not installed (command -v aws is empty)",
            kind="missing",
            exit_code=127,
        )
    except subprocess.TimeoutExpired:
        return Result(
            full,
            False,
            error=f"timed out after {timeout}s",
            kind="timeout",
            exit_code=124,
        )
    seconds = time.monotonic() - started
    if proc.returncode != 0:
        kind, msg = classify(proc.stderr, proc.returncode)
        return Result(
            full,
            False,
            error=msg,
            kind=kind,
            exit_code=proc.returncode,
            seconds=seconds,
        )
    body = proc.stdout.strip()
    if not body:
        return Result(full, True, data=None, seconds=seconds)
    try:
        return Result(full, True, data=json.loads(body), seconds=seconds)
    except ValueError:
        return Result(
            full,
            False,
            error="no JSON on stdout: " + body[:200],
            kind="error",
            exit_code=0,
            seconds=seconds,
        )


def run_many(
    calls: list[list[str]],
    profile: str,
    region: str,
    workers: int = WORKERS,
    timeout: int = TIMEOUT,
) -> list[Result]:
    """Run aws commands concurrently - verified safe on one SSO profile (2026-09-11)."""
    if not calls:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(calls))) as pool:
        return list(
            pool.map(lambda a: run_aws(a, profile, region, timeout=timeout), calls)
        )


def commands(results: list[Result]) -> list[str]:
    return [r.command for r in results]


def failures(results: list[Result]) -> list[dict]:
    return [
        {"command": r.command, "error": r.error, "kind": r.kind}
        for r in results
        if not r.ok
    ]


# --- Logs Insights -----------------------------------------------------------

TERMINAL = {"Complete", "Failed", "Cancelled", "Timeout", "Unknown"}


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


def insights_rows(data) -> list[dict]:
    """get-query-results' results -> one dict per row, keyed by field, numbers coerced."""
    if not isinstance(data, dict):
        return []
    out = []
    for row in data.get("results") or []:
        out.append(
            {
                c.get("field"): _coerce(c.get("value"))
                for c in row
                if isinstance(c, dict)
            }
        )
    return out


def insights_query(
    groups: list[str],
    query: str,
    frm: datetime,
    to: datetime,
    profile: str,
    region: str,
    cap: int = INSIGHTS_CAP,
    every: float = INSIGHTS_EVERY,
    limit: int | None = None,
) -> Result:
    """start-query, poll get-query-results to a terminal status (bounded), rows parsed.

    The Result's ``args`` are the start-query call (the poll is folded into
    ``extra['polls']``); ``data`` is the list of row dicts; ``extra`` carries
    the query's statistics and status.
    """
    if len(groups) == 1:
        target = ["--log-group-name", groups[0]]
    else:
        target = ["--log-group-names", *groups]
    args = [
        "logs",
        "start-query",
        *target,
        "--start-time",
        str(epoch_s(frm)),
        "--end-time",
        str(epoch_s(to)),
        "--query-string",
        query,
    ]
    if limit:
        args += ["--limit", str(limit)]
    started = run_aws(args, profile, region)
    if not started.ok:
        return started
    qid = (started.data or {}).get("queryId")
    if not qid:
        started.ok, started.kind, started.error = (
            False,
            "error",
            "start-query returned no queryId",
        )
        return started
    t0 = time.monotonic()
    polls = 0
    status, data = "Scheduled", None
    while True:
        polls += 1
        r = run_aws(["logs", "get-query-results", "--query-id", qid], profile, region)
        if not r.ok:
            r.args = started.args
            r.extra["polls"] = polls
            return r
        data = r.data or {}
        status = data.get("status", "Unknown")
        if status in TERMINAL:
            break
        if time.monotonic() - t0 + every > cap:
            run_aws(["logs", "stop-query", "--query-id", qid], profile, region)
            status = "Stopped"
            break
        time.sleep(every)
    started.seconds = time.monotonic() - t0
    started.extra = {
        "polls": polls,
        "status": status,
        "statistics": (data or {}).get("statistics", {}),
    }
    if status != "Complete":
        started.ok = False
        started.kind = "query-" + status.lower()
        started.error = f"the query ended {status} after {polls} polls" + (
            f" (cap {cap}s reached, stopped)" if status == "Stopped" else ""
        )
        started.data = insights_rows(data)
        return started
    started.data = insights_rows(data)
    return started


def insights_many(
    specs: list[tuple[list[str], str]],
    frm: datetime,
    to: datetime,
    profile: str,
    region: str,
    workers: int = WORKERS,
    **kw,
) -> list[Result]:
    """Several Logs Insights queries at once, each polled on its own thread."""
    if not specs:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(specs))) as pool:
        return list(
            pool.map(
                lambda s: insights_query(s[0], s[1], frm, to, profile, region, **kw),
                specs,
            )
        )


def filter_log_events(
    group: str,
    frm: datetime,
    to: datetime,
    profile: str,
    region: str,
    pattern: str | None = None,
    limit: int = 50,
    stream_prefix: str | None = None,
) -> Result:
    """filter-log-events in epoch milliseconds, capped by its own --limit, one page."""
    args = [
        "logs",
        "filter-log-events",
        "--log-group-name",
        group,
        "--start-time",
        str(epoch_ms(frm)),
        "--end-time",
        str(epoch_ms(to)),
        "--limit",
        str(limit),
        "--no-paginate",
    ]
    if pattern:
        args += ["--filter-pattern", pattern]
    if stream_prefix:
        args += ["--log-stream-name-prefix", stream_prefix]
    return run_aws(args, profile, region)


def cw_field(name: str) -> str:
    """A field name for a CWLI query - backquoted when it carries a dot or a dash."""
    return f"`{name}`" if re.search(r"[^A-Za-z0-9_@]", name) else name


def cw_str(s: str) -> str:
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def cw_in(fld: str, values: list[str]) -> str:
    """`| filter <field> in [...]` - empty when no values."""
    if not values:
        return ""
    return f"| filter {cw_field(fld)} in [{', '.join(cw_str(v) for v in values)}] "


SEVERITY = [
    (1, "TRACE"),
    (5, "DEBUG"),
    (9, "INFO"),
    (13, "WARN"),
    (17, "ERROR"),
    (21, "FATAL"),
]


def severity_text(n) -> str:
    """The OTel severity range a severity_number falls in."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "-"
    name = "UNSPECIFIED"
    for lo, label in SEVERITY:
        if n >= lo:
            name = label
    return name


# --- metrics -----------------------------------------------------------------


def metric_data_file(queries: list[dict]) -> str:
    """Write MetricDataQueries to a temporary JSON file; returns the file:// argument."""
    fd, path = tempfile.mkstemp(prefix="cloudwatch-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(queries, f)
    return "file://" + path


# --- X-Ray -------------------------------------------------------------------


def xray_range(frm: datetime, to: datetime) -> None:
    if (to - frm).total_seconds() > XRAY_MAX_RANGE:
        usage("an X-Ray range stays under 24 h: narrow --from/--to or --since")


def chunks(items: list, n: int = XRAY_BATCH) -> list[list]:
    return [items[i : i + n] for i in range(0, len(items), n)]


def parse_xray_ts(s: str | None) -> datetime | None:
    """An X-Ray timestamp (local offset as rendered by the CLI) -> aware UTC datetime."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except ValueError:
        return None


def percentiles(values: list[float], ps=(50, 95, 99)) -> dict:
    """Nearest-rank percentiles, client-side."""
    if not values:
        return {f"p{p}": None for p in ps}
    xs = sorted(values)
    out = {}
    for p in ps:
        k = max(1, math.ceil(p / 100 * len(xs)))
        out[f"p{p}"] = xs[min(k, len(xs)) - 1]
    return out


def histogram_percentiles(buckets: list[dict], ps=(50, 95, 99)) -> dict:
    """Percentiles read off a {Value, Count} histogram (X-Ray's bucketed shape)."""
    total = sum(int(b.get("Count", 0)) for b in buckets)
    if not total:
        return {f"p{p}": None for p in ps}
    xs = sorted(buckets, key=lambda b: float(b.get("Value", 0)))
    out, acc, i = {}, 0, 0
    for p in sorted(ps):
        need = p / 100 * total
        while i < len(xs) and acc + int(xs[i].get("Count", 0)) < need:
            acc += int(xs[i].get("Count", 0))
            i += 1
        out[f"p{p}"] = float(xs[min(i, len(xs) - 1)].get("Value", 0))
    return out


ROUTE_ID_RE = re.compile(r"/(\d+|[0-9a-fA-F-]{20,})(?=/|$)")


def normalize_path(url: str | None) -> str:
    """The path of a URL with numeric or UUID-like segments folded to {id} - a client-side stand-in for http.route."""
    if not url:
        return "-"
    path = url
    m = re.match(r"^[a-z]+://[^/]+(/.*)?$", url)
    if m:
        path = m.group(1) or "/"
    path = path.split("?", 1)[0]
    return ROUTE_ID_RE.sub("/{id}", path)


# --- time --------------------------------------------------------------------


def usage(message: str) -> NoReturn:
    """A usage error the way argparse reports one: the message on stderr, exit 2."""
    print(f"usage error: {message}", file=sys.stderr)
    sys.exit(2)


def parse_duration(s: str) -> int:
    s = (s or "").strip()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if len(s) < 2 or s[-1] not in units:
        usage(f"a duration is <number><s|m|h|d>, e.g. 90s or 30m - got {s!r}")
    try:
        return int(float(s[:-1]) * units[s[-1]])
    except ValueError:
        usage(f"a duration is <number><s|m|h|d>, e.g. 90s or 30m - got {s!r}")


def parse_ts(s: str) -> datetime:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        usage(f"a timestamp is RFC3339 UTC, e.g. 2026-09-11T10:40:00Z - got {s!r}")
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch_s(dt: datetime) -> int:
    return int(dt.timestamp())


def epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def add_targeting(
    ap,
    log_group: bool = False,
    metrics_log_group: bool = False,
    required_groups: bool = True,
):
    ap.add_argument(
        "--profile",
        required=True,
        help="the aws CLI profile (stack_config.cloudwatch.profile)",
    )
    ap.add_argument(
        "--region", required=True, help="the region (stack_config.cloudwatch.region)"
    )
    if log_group:
        ap.add_argument(
            "--log-group",
            required=required_groups,
            help="the application logs group (stack_config.cloudwatch.log_group)",
        )
    if metrics_log_group:
        ap.add_argument(
            "--metrics-log-group",
            required=required_groups,
            help="the EMF group (stack_config.cloudwatch.metrics_log_group)",
        )


def add_window(ap):
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


def resolve_window(ns, default_since: str | None = None) -> tuple[datetime, datetime]:
    """--from/--to or --since -> (from, to) aware UTC datetimes, always both."""
    if getattr(ns, "since", None):
        end = datetime.now(timezone.utc).replace(microsecond=0)
        return end - timedelta(seconds=parse_duration(ns.since)), end
    if getattr(ns, "frm", None) and getattr(ns, "to", None):
        a, b = parse_ts(ns.frm), parse_ts(ns.to)
        if b <= a:
            usage("--to must be after --from")
        return a, b
    if default_since:
        end = datetime.now(timezone.utc).replace(microsecond=0)
        return end - timedelta(seconds=parse_duration(default_since)), end
    usage(
        "a window is required: --from <RFC3339> --to <RFC3339>, or --since <duration>"
    )
    raise AssertionError


def targets(ns) -> None:
    """Register the namespace's targeting values for masking."""
    register_targets(
        log_group=getattr(ns, "log_group", None),
        metrics_log_group=getattr(ns, "metrics_log_group", None),
    )


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
