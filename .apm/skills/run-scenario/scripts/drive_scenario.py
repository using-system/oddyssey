#!/usr/bin/env python3
"""Drive an ad-hoc request scenario and print the record the report needs.

The drive itself has no judgement in it: warm every operation up, send N
requests per operation with the run's identity on each, take t0 after the
warmup, record failures as data, wait the flush out once, and print the
record. This does that, so no agent writes the curl loops or derives the
slug's hash by hand - and so two drives of one scenario are the same
command.

    python3 drive_scenario.py http://127.0.0.1:8000 --run-slug <slug> --prompt observe --op 'GET /api/users' --op 'POST /api/orders {"sku": "A1"}' --count 30 --out <dir>
    python3 drive_scenario.py <base url> ... --out <dir> --detach            # a scenario longer than a tool call: start, return at once
    python3 drive_scenario.py --status <dir> --wait 10m                      # block until it finishes (exit 3 at the bound, run again)
    python3 drive_scenario.py <base url> ... --dry-run                       # print the plan, send nothing

An operation is `METHOD PATH [COUNT] [BODY]`: the count overrides
--count for that operation, the body goes out as application/json (a -H
Content-Type overrides that). --ops <file> holds one per line, `#`
comments and blank lines ignored.

Every request carries `User-Agent: odd-<prompt>/<slug>` (`-warmup`
appended on the warmup) and `traceparent:
00-<prefix><sha256(slug)[:8]><seq:016x>-<seq:016x>-01`, the sequence one
run-wide counter from 1, warmup included. Started is the first load
request, Ended the last response; the flush wait (--wait-for: 60 s for
traces, 10 s for metrics, 0 for none) is paid once after Ended, inside
the call. A failed request is a row in the record, never retried. A
`localhost` base URL is refused: a dual-stack host may resolve it to
another listener - use 127.0.0.1.

The record is the block SKILL.md step 4 shows, its Listeners line from
the script's own lsof probe of the base URL's port (fields only, never
the USER column), its Commands line the invocation verbatim, then one
Requests line per operation. --json prints the same as one object.
Backend, Instance and Not reproducible are printed as `<yours: ...>`
placeholders: the caller fills them. The files land in --out: drive-record.json,
requests.jsonl (one row per request: seq, phase, method, path, status,
ms, error), and under --detach runner.pid, drive-stdout.log,
drive-stderr.log and done.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import http.client
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_PREFIX = "0ddc0ffe"
WAITS = {"traces": 60, "metrics": 10, "none": 0}
SECRET_HEADER = re.compile(
    r"authorization|cookie|token|secret|key|password", re.IGNORECASE
)
BACKEND_PLACEHOLDER = (
    '<yours: odd_stack_reset, env: {...} - or "no reset - separated by the slug '
    'and the window">'
)
INSTANCE_PLACEHOLDER = "<yours: read from the run's own rows after the wait>"
NOT_REPRODUCIBLE_PLACEHOLDER = (
    '<yours: auth token / seeded data / time-dependent input, or "none">'
)


def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def wait_seconds(signal: str) -> int:
    return WAITS[signal]


def parse_op(text: str, default_count: int) -> dict:
    """`METHOD PATH [COUNT] [BODY]` - the count when the third token is a
    number, the rest of the line the body, verbatim."""
    parts = text.strip().split(maxsplit=2)
    if len(parts) < 2:
        raise ValueError(f"an operation is `METHOD PATH [COUNT] [BODY]`, got {text!r}")
    method, path = parts[0], parts[1]
    if not re.fullmatch(r"[A-Z]+", method):
        raise ValueError(f"the method is upper-case (GET, POST, ...), got {method!r}")
    if not path.startswith("/"):
        raise ValueError(f"the path starts with `/`, got {path!r}")
    count, body = default_count, None
    if len(parts) == 3:
        rest = parts[2].strip()
        m = re.match(r"(\d+)(?:\s+(.*))?$", rest, re.DOTALL)
        if m:
            count = int(m.group(1))
            body = (m.group(2) or "").strip() or None
        else:
            body = rest
    if count < 1:
        raise ValueError(f"a count is at least 1, got {count} in {text!r}")
    return {"method": method, "path": path, "count": count, "body": body}


def parse_header(text: str) -> tuple[str, str]:
    if ":" not in text:
        raise ValueError(f"-H takes `Name: value`, got {text!r}")
    name, value = text.split(":", 1)
    return name.strip(), value.strip()


def parse_lsof(out: str, port: int) -> list[dict]:
    """`lsof -F pcn` output: one p/c/n field per line, grouped per process."""
    rows: list[dict] = []
    current: dict = {}
    for line in out.splitlines():
        if not line:
            continue
        tag, value = line[0], line[1:]
        if tag == "p":
            current = {"pid": int(value)}
        elif tag == "c":
            current["command"] = value
        elif tag == "n" and value.rsplit(":", 1)[-1].split(" ")[0] == str(port):
            rows.append(
                {
                    "pid": current.get("pid"),
                    "command": current.get("command", "?"),
                    "bind": value.rsplit(":", 1)[0],
                }
            )
    return rows


def probe_listeners(port: int) -> list[dict] | None:
    """Who listens on the port - None when lsof is not there to ask."""
    if shutil.which("lsof") is None:
        return None
    p = subprocess.run(
        ["lsof", "-nP", "-F", "pcn", f"-iTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0 or not p.stdout.strip():
        return []
    return parse_lsof(p.stdout, port)


def format_listeners(port: int, rows: list[dict] | None) -> str:
    if rows is None:
        return "lsof not found - probe the port by hand"
    if not rows:
        return "none"
    return f":{port} served by " + " and ".join(
        f"{r['pid']} {r['command']} ({r['bind']})" for r in rows
    )


def listeners_line(port: int) -> str:
    return format_listeners(port, probe_listeners(port))


def parse_wait(value: str) -> int:
    """A bounded wait as seconds: 20m, 300s, 1h - a bare number is seconds."""
    m = re.fullmatch(r"(\d+)([smh]?)", value.strip())
    if not m:
        raise SystemExit(f"--wait takes <number>[s|m|h], got {value!r}")
    return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(2)]


# --- sending ---------------------------------------------------------------------


class Counter:
    def __init__(self) -> None:
        self.value = 0
        self.lock = threading.Lock()

    def next(self) -> int:
        with self.lock:
            self.value += 1
            return self.value


def traceparent(prefix: str, run8: str, seq: int) -> str:
    return f"00-{prefix}{run8}{seq:016x}-{seq:016x}-01"


def send_one(
    target: dict, op: dict, headers: dict, seq: int, phase: str, timeout: float
) -> dict:
    row = {
        "seq": seq,
        "phase": phase,
        "method": op["method"],
        "path": op["path"],
        "status": None,
        "ms": None,
        "error": None,
    }
    conn_cls = (
        http.client.HTTPSConnection
        if target["scheme"] == "https"
        else http.client.HTTPConnection
    )
    body = op["body"].encode() if op["body"] is not None else None
    sent = dict(headers)
    if body is not None and not any(k.lower() == "content-type" for k in sent):
        sent["Content-Type"] = "application/json"
    started = time.perf_counter()
    conn = conn_cls(target["host"], target["port"], timeout=timeout)
    try:
        conn.request(
            op["method"], target["path_prefix"] + op["path"], body=body, headers=sent
        )
        resp = conn.getresponse()
        resp.read()
        row["status"] = resp.status
    except (OSError, http.client.HTTPException) as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:200]
    finally:
        conn.close()
    row["ms"] = round((time.perf_counter() - started) * 1000, 1)
    return row


def run_phase(
    phase: str,
    target: dict,
    ops: list[dict],
    per_op: int | None,
    identity: dict,
    counter: Counter,
    concurrency: int,
    timeout: float,
    sink,
) -> list[dict]:
    """One phase - warmup or load - over every operation, in order; the
    sequence is taken at send time so it is disjoint under concurrency."""
    ua = identity["user_agent"] + ("-warmup" if phase == "warmup" else "")
    summaries = []
    for op in ops:
        n = per_op if per_op is not None else op["count"]
        summary = {
            "method": op["method"],
            "path": op["path"],
            "count": n,
            "seq_first": None,
            "seq_last": None,
            "statuses": {},
            "failed": 0,
        }

        def one(_: int, op=op) -> dict:
            seq = counter.next()
            headers = {
                **identity["extra"],
                "User-Agent": ua,
                "traceparent": traceparent(identity["prefix"], identity["run8"], seq),
            }
            return send_one(target, op, headers, seq, phase, timeout)

        if concurrency > 1:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                rows = list(pool.map(one, range(n)))
        else:
            rows = [one(i) for i in range(n)]
        for row in rows:
            sink.write(json.dumps(row) + "\n")
            key = str(row["status"]) if row["status"] is not None else "error"
            summary["statuses"][key] = summary["statuses"].get(key, 0) + 1
            if row["error"] is not None:
                summary["failed"] += 1
        seqs = [r["seq"] for r in rows]
        summary["seq_first"], summary["seq_last"] = min(seqs), max(seqs)
        summaries.append(summary)
    return summaries


# --- the record ------------------------------------------------------------------


def invocation(args, ops: list[dict]) -> str:
    """The Commands line: the inputs in one fixed order, every operation
    with its count, defaults spelled out - so the replay re-runs it
    unchanged and two drives print the same."""
    parts = ["python3", str(Path(__file__).resolve()), args.base_url]
    parts += ["--run-slug", args.run_slug, "--prompt", args.prompt]
    if args.scenario:
        parts += ["--scenario", args.scenario]
    for op in ops:
        body = f" {op['body']}" if op["body"] else ""
        parts += ["--op", f"{op['method']} {op['path']} {op['count']}{body}"]
    for name, value in args.header:
        shown = "<not recorded>" if SECRET_HEADER.search(name) else value
        parts += ["-H", f"{name}: {shown}"]
    parts += ["--count", str(args.count), "--warmup", str(args.warmup)]
    parts += ["--concurrency", str(args.concurrency), "--prefix", args.prefix]
    parts += ["--timeout", f"{args.timeout:g}", "--wait-for", args.wait_for]
    parts += ["--out", str(Path(args.out).resolve()) if args.out else "<dir>"]
    return " ".join(shlex.quote(p) for p in parts)


def render(record: dict) -> str:
    warm = record["warmup"]
    n = record["count"]
    lines = [
        f"Scenario: {record['scenario']}",
        f"Base URL: {record['base_url']}",
        f"Listeners: {record['listeners_line']}",
        f"Backend:  {record['backend']}",
        f"Instance: {record['instance']}",
        (
            "Identity: "
            f'User-Agent "{record["user_agent"]}" (+ "-warmup" on the warmup); '
            f'traceparent "00-{record["prefix"]}<run8><seq:016x>-<seq:016x>-01", '
            f"run8 = sha256({record['run_slug']})[:8] = {record['run8']}, "
            f"trace ids start {record['trace_id_prefix']}; one sequence run-wide from 1"
        ),
    ]
    ws = record.get("warmup_seq")
    lines.append(
        f"Warmup:   {warm} request{'s' if warm != 1 else ''} per operation "
        + (f"(discarded; seq {ws[0]}-{ws[1]})" if ws else "(none)")
    )
    load = (
        "sequential"
        if record["concurrency"] == 1
        else f"concurrency {record['concurrency']}"
    )
    ls = record.get("load_seq")
    lines.append(
        f"Load:     {n} requests per operation, {load}"
        + (f" (seq {ls[0]}-{ls[1]})" if ls else "")
    )
    lines.append(f"Started (UTC): {record.get('start_utc') or '<not run>'}")
    lines.append(f"Ended   (UTC): {record.get('end_utc') or '<not run>'}")
    if record["wait_seconds"]:
        wait = (
            f"after the {record['wait_seconds']} s flush wait for {record['wait_for']}"
        )
    else:
        wait = "no flush wait, --wait-for none"
    lines.append(f"Query points: 1 (after Ended; {wait})")
    lines.append("Commands:")
    lines.append(f"  {record['command']}")
    lines.append("Requests:")
    for r in record.get("requests") or []:
        body = f" {r['body']}" if r.get("body") else ""
        tally = ", ".join(f"{k}:{v}" for k, v in r["statuses"].items())
        lines.append(
            f"  {r['method']} {record['base_url']}{r['path']}{body} x{r['count']} "
            f"(seq {r['seq_first']}-{r['seq_last']}) -> {tally}"
        )
    lines.append(f"Not reproducible: {record['not_reproducible']}")
    return "\n".join(lines) + "\n"


def plan(record: dict, ops: list[dict]) -> str:
    lines = [f"would send to {record['base_url']} as {record['user_agent']}:"]
    for op in ops:
        body = f" {op['body']}" if op["body"] else ""
        lines.append(
            f"  {op['method']} {record['base_url']}{op['path']}{body} "
            f"x{op['count']} (+ x{record['warmup']} warmup)"
        )
    lines.append(f"trace ids start {record['trace_id_prefix']}")
    lines.append(
        f"then wait {record['wait_seconds']} s ({record['wait_for']}) after Ended"
    )
    lines.append("command:")
    lines.append(f"  {record['command']}")
    return "\n".join(lines) + "\n"


def emit(record: dict, as_json: bool) -> None:
    print(json.dumps(record, indent=2) if as_json else render(record), end="")


# --- detached mode ---------------------------------------------------------------


def detach(out: Path, record: dict, as_json: bool) -> int:
    """Start the drive in its own session and return at once; --status
    --wait is the wait, shipped instead of authored."""
    out.mkdir(parents=True, exist_ok=True)
    # a directory reused by a retry still holds the previous drive's
    # outcome, and --status would report it one second after launch
    for stale in ("done", "requests.jsonl", "drive-stdout.log", "drive-stderr.log"):
        (out / stale).unlink(missing_ok=True)
    record = {
        **record,
        "finished": False,
        "detached_in": str(out),
        "launched_utc": utc(),
    }
    record.pop("requests", None)
    (out / "drive-record.json").write_text(json.dumps(record, indent=2))
    argv = [a for a in sys.argv[1:] if a not in ("--detach", "--json")]
    so = (out / "drive-stdout.log").open("w")
    se = (out / "drive-stderr.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), *argv, "--json"],
        stdin=subprocess.DEVNULL,
        stdout=so,
        stderr=se,
        start_new_session=True,
    )
    so.close()
    se.close()
    (out / "runner.pid").write_text(str(proc.pid))
    if as_json:
        print(json.dumps(record, indent=2))
    else:
        print(f"started {record['scenario']} detached, pid {proc.pid}")
        print(f"record   {out / 'drive-record.json'}")
        print(f"wait     {Path(__file__).name} --status {out} --wait <duration>")
    return 0


def runner_alive(out: Path) -> bool:
    try:
        pid = int((out / "runner.pid").read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def report_status(out: Path, as_json: bool, wait: str | None) -> int:
    record_path = out / "drive-record.json"
    if not record_path.is_file():
        print(f"no detached drive in {out}", file=sys.stderr)
        return 1
    timed_out = False
    if wait is not None:
        limit = parse_wait(wait)
        started = time.monotonic()
        while not (out / "done").is_file():
            if not runner_alive(out) and not (out / "done").is_file():
                print(
                    f"the detached drive in {out} is gone without a record - its "
                    "process was killed or the machine restarted; drive again",
                    file=sys.stderr,
                )
                return 1
            if time.monotonic() - started >= limit:
                timed_out = True
                break
            time.sleep(min(1.0, max(limit, 0.1)))
    record = json.loads(record_path.read_text())
    record["finished"] = (out / "done").is_file()
    if not record["finished"] and (out / "drive-stderr.log").is_file():
        err = (out / "drive-stderr.log").read_text().strip()
        if err and not runner_alive(out):
            print(err, file=sys.stderr)
    if as_json:
        print(json.dumps(record, indent=2))
    elif record["finished"]:
        print(render(record), end="")
    else:
        print(
            f"{record['scenario']}: still running (launched {record['launched_utc']})"
        )
        print(f"  record   {record_path}")
    if timed_out:
        print(
            f"still running after --wait {wait}: the wait is bounded on purpose - "
            "run --status --wait again, or raise the bound",
            file=sys.stderr,
        )
        return 3
    return 0


# --- main ------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", help="http://127.0.0.1:<port>[/prefix]")
    parser.add_argument(
        "--run-slug", help="identifies this run; without it every run merges"
    )
    parser.add_argument(
        "--prompt", help="observe, verify, ... - the User-Agent's odd-<prompt>"
    )
    parser.add_argument(
        "--op",
        action="append",
        default=[],
        metavar="'METHOD PATH [COUNT] [BODY]'",
        help="an operation, repeatable",
    )
    parser.add_argument("--ops", metavar="FILE", help="operations, one per line")
    parser.add_argument(
        "--count", type=int, default=30, help="requests per operation (default 30)"
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=5,
        help="warmup requests per operation, discarded (default 5)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="parallel senders (default 1: sequential)",
    )
    parser.add_argument(
        "--prefix", default=DEFAULT_PREFIX, help="the trace id's 8-hex protocol prefix"
    )
    parser.add_argument(
        "-H",
        dest="header",
        action="append",
        default=[],
        metavar="'Name: value'",
        help="an extra header on every request, repeatable",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="per-request timeout in seconds (default 60)",
    )
    parser.add_argument(
        "--wait-for",
        choices=sorted(WAITS),
        default="traces",
        help="the flush wait after Ended: traces 60 s (default), metrics 10 s, none",
    )
    parser.add_argument(
        "--scenario", help="the record's Scenario line (default: the slug)"
    )
    parser.add_argument(
        "--out",
        metavar="DIR",
        help="the run's own scratchpad subdirectory: the record and the request rows land there",
    )
    parser.add_argument(
        "--detach",
        action="store_true",
        help="start the drive in the background and return at once",
    )
    parser.add_argument(
        "--status",
        metavar="DIR",
        help="report on a --detach drive: still running, or its finished record",
    )
    parser.add_argument(
        "--wait",
        metavar="DURATION",
        help="with --status: block until the drive finishes or DURATION (10m, 300s) passes - exit 3 when still running at the bound",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and the command, send nothing",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.wait and not args.status:
        parser.error("--wait goes with --status")
    if args.wait:
        try:
            parse_wait(args.wait)
        except SystemExit as bad:
            parser.error(str(bad))
    if args.status:
        return report_status(Path(args.status), args.json, args.wait)

    if not args.base_url:
        parser.error("the base URL is required unless --status is given")
    if not args.run_slug:
        parser.error("--run-slug is required: without it every run merges")
    if not args.prompt:
        parser.error("--prompt is required: the User-Agent is odd-<prompt>/<slug>")
    if not args.op and not args.ops:
        parser.error(
            "at least one --op 'METHOD PATH [COUNT] [BODY]' (or --ops FILE) is required"
        )
    if not args.out and not args.dry_run:
        parser.error("--out DIR is required: the run's own scratchpad subdirectory")
    for name in ("count", "warmup", "concurrency"):
        if getattr(args, name) < (0 if name == "warmup" else 1):
            parser.error(f"--{name} takes a positive number")

    url = urlsplit(args.base_url)
    if url.scheme not in ("http", "https") or not url.hostname:
        print(
            f"the base URL is http[s]://host:port[/prefix], got {args.base_url!r}",
            file=sys.stderr,
        )
        return 1
    if url.hostname == "localhost":
        print(
            "refused: `localhost` may resolve to another listener on a dual-stack "
            "host - drive 127.0.0.1:<port> (the Machine line's base URL when it "
            "carries one)",
            file=sys.stderr,
        )
        return 1
    target = {
        "scheme": url.scheme,
        "host": url.hostname,
        "port": url.port or (443 if url.scheme == "https" else 80),
        "path_prefix": url.path.rstrip("/"),
    }

    try:
        ops = [parse_op(o, args.count) for o in args.op]
        if args.ops:
            for line in Path(args.ops).read_text().splitlines():
                if line.strip() and not line.lstrip().startswith("#"):
                    ops.append(parse_op(line, args.count))
        args.header = [parse_header(h) for h in args.header]
    except (ValueError, OSError) as bad:
        print(str(bad), file=sys.stderr)
        return 1

    run8 = hashlib.sha256(args.run_slug.encode()).hexdigest()[:8]
    identity = {
        "user_agent": f"odd-{args.prompt}/{args.run_slug}",
        "prefix": args.prefix,
        "run8": run8,
        "extra": dict(args.header),
    }
    secret_headers = [n for n, _ in args.header if SECRET_HEADER.search(n)]
    record = {
        "scenario": args.scenario or args.run_slug,
        "base_url": args.base_url,
        "port": target["port"],
        "listeners": None,
        "listeners_line": None,
        "backend": BACKEND_PLACEHOLDER,
        "instance": INSTANCE_PLACEHOLDER,
        "run_slug": args.run_slug,
        "prompt": args.prompt,
        "user_agent": identity["user_agent"],
        "prefix": args.prefix,
        "run8": run8,
        "trace_id_prefix": args.prefix + run8,
        "warmup": args.warmup,
        "count": args.count,
        "concurrency": args.concurrency,
        "timeout": args.timeout,
        "headers": [
            [n, "<not recorded>" if SECRET_HEADER.search(n) else v]
            for n, v in args.header
        ],
        "operations": ops,
        "wait_for": args.wait_for,
        "wait_seconds": wait_seconds(args.wait_for),
        "command": invocation(args, ops),
        "not_reproducible": "; ".join(
            [f"header {n} (value not recorded)" for n in secret_headers]
            + [NOT_REPRODUCIBLE_PLACEHOLDER]
        ),
    }

    if args.dry_run:
        if args.json:
            emit(record, True)
        else:
            print(plan(record, ops), end="")
        return 0

    out = Path(args.out)
    if args.detach:
        return detach(out, record, args.json)

    out.mkdir(parents=True, exist_ok=True)
    (out / "done").unlink(missing_ok=True)
    listeners = probe_listeners(target["port"])
    record["listeners"] = listeners if listeners is not None else []
    record["listeners_line"] = format_listeners(target["port"], listeners)
    counter = Counter()
    with (out / "requests.jsonl").open("w") as sink:
        if args.warmup:
            run_phase(
                "warmup",
                target,
                ops,
                args.warmup,
                identity,
                counter,
                args.concurrency,
                args.timeout,
                sink,
            )
            record["warmup_seq"] = [1, counter.value]
        first_load = counter.value + 1
        record["start_utc"] = utc()
        summaries = run_phase(
            "load",
            target,
            ops,
            None,
            identity,
            counter,
            args.concurrency,
            args.timeout,
            sink,
        )
        record["end_utc"] = utc()
        record["load_seq"] = [first_load, counter.value]
    for s, op in zip(summaries, ops):
        s["body"] = op["body"]
    record["requests"] = summaries
    if record["wait_seconds"]:
        time.sleep(record["wait_seconds"])
    record["finished"] = True
    (out / "drive-record.json").write_text(json.dumps(record, indent=2))
    (out / "done").write_text("1")
    emit(record, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
