#!/usr/bin/env python3
"""Say where a measured run's time went, and whether the number is usable.

Reads one run's own lines under the CLI that drove it - opencode's log
and session store, claude's transcripts (root and subagents), copilot's
events and stdout stream - and separates what the package controls from
what it does not:

- **commands** and **turns**, which a harnessing change moves;
- **generation time**, summed per model request - the honest metric
  when the provider is slow, because it is measured request by request;
- **gaps** with no command in them, which are the model generating, not
  the package working. A gap far above the run's median turn is provider
  latency and invalidates a wall-clock comparison;
- **tokens and cost**, as far as the CLI states them for a run stopped
  at its phase marker: opencode's store carries both for the session
  tree; claude's transcripts carry the tokens per request and the cost
  only in the result the run prints at exit; copilot writes its usage
  file at exit and bills no dollars. A `null` says which, and why.

It also counts the behaviours a harnessing change is meant to remove:
shell scripts the run authored, stack resets, machine questions already
answered upstream, and `--help` calls on shipped scripts.

    analyze_run.py --record /tmp/study/g6.record.json [--json]
    analyze_run.py --cli opencode --run-id 85496389
    analyze_run.py --cli claude --run-id <session id> [--stdout <run.json>]
    analyze_run.py --cli copilot --run-id <session id> --stdout <run.jsonl> [--usage <usage.json>]

The record a measure_phase.py run wrote carries the CLI, the id, the
stdout stream and the usage file; the manual form names them.
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
from datetime import datetime
from pathlib import Path

CLIS = ("opencode", "claude", "copilot")
# claude keeps its transcripts under the account's home whatever HOME says
HOMES = list(dict.fromkeys([Path.home(), Path(pwd.getpwuid(os.getuid()).pw_dir)]))
OPENCODE_LOG = Path.home() / ".local/share/opencode/log/opencode.log"
OPENCODE_STORE = Path.home() / ".local/share/opencode/opencode.db"
COPILOT_SESSIONS = Path.home() / ".copilot/session-state"
REDUNDANT = re.compile(r"^(ls -la|ls -l |docker ps|lsof|find \.)")
AUTHORED = re.compile(r"(cat > |cat >>|tee )[^\n]*\.sh")
SHIPPED = (
    "preflight.py",
    "probe_services.py",
    "gcx_local.py",
    "replay_benchmark.py",
    "odd_recall.py",
    "odd_report.py",
    "odd_status.py",
)
NO_TOKENS = {"input_tokens": None, "output_tokens": None, "cache_tokens": None}


def parse(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def json_lines(path: Path | None) -> list[dict]:
    rows: list[dict] = []
    if path is None or not path.is_file():
        return rows
    with path.open(errors="replace") as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def claude_transcripts(session: str) -> list[Path]:
    """The root transcript and the subagents' beside it, wherever Claude
    Code keyed the directory (its encoding of the path is its own)."""
    for home in HOMES:
        for root in sorted((home / ".claude/projects").glob(f"*/{session}.jsonl")):
            return [root] + sorted(
                (root.parent / session / "subagents").glob("agent-*.jsonl")
            )
    return []


# --- one run, per CLI ------------------------------------------------------------
#
# Each reader returns the shell commands the run issued, dated, the
# latency of each model request, the stack resets, and the tokens and
# cost the CLI states.


def opencode_run(run_id: str) -> dict:
    rows: list[tuple[datetime, str]] = []
    if OPENCODE_LOG.is_file():
        with OPENCODE_LOG.open(errors="replace") as handle:
            for line in handle:
                if f"run={run_id}" not in line:
                    continue
                when = parse(line.partition("timestamp=")[2].split(" ", 1)[0])
                if when:
                    rows.append((when, line))
    # the commands: the permission lines, their pattern the command's head
    commands = [
        (w, ln.partition('pattern="')[2].partition('"')[0])
        for w, ln in rows
        if 'pattern="' in ln and "permission=bash" in ln
    ]
    latencies, tokens, cost = opencode_store(rows)
    return {
        "commands": commands,
        "latencies": latencies,
        "resets": sum("odd_stack_reset" in ln for _, ln in rows),
        **tokens,
        "cost_usd": cost,
        "cost_note": None if cost is not None else "no session found in the store",
    }


def opencode_store(
    rows: list[tuple[datetime, str]],
) -> tuple[list[float], dict, float | None]:
    """Turns, generation time, tokens and cost across the run's own session
    tree - the sessions its log lines name, never a time window - summed
    the way launch-llms-benchmark step 7 sums them."""
    if not OPENCODE_STORE.is_file():
        return [], NO_TOKENS, None
    seen: set[str] = set()
    for _, line in rows:
        seen.update(re.findall(r"session\.id=(\S+)", line))
        seen.update(re.findall(r'"sessionID":"([^"]+)"', line))
    if not seen:
        return [], NO_TOKENS, None
    tmp = Path(tempfile.mkdtemp()) / "opencode.db"
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(OPENCODE_STORE) + suffix)
        if src.is_file():
            shutil.copy(src, str(tmp) + suffix)
    con = sqlite3.connect(tmp)
    ids, frontier = list(seen), list(seen)
    while frontier:
        marks = ",".join("?" * len(frontier))
        children = [
            r[0]
            for r in con.execute(
                f"SELECT id FROM session WHERE parent_id IN ({marks})", frontier
            )
        ]
        frontier = [c for c in children if c not in ids]
        ids.extend(frontier)
    marks = ",".join("?" * len(ids))
    latencies: list[float] = []
    for (data,) in con.execute(
        f"SELECT data FROM message WHERE session_id IN ({marks})", ids
    ):
        try:
            payload = json.loads(data)
        except (TypeError, ValueError):
            continue
        if payload.get("role") != "assistant":
            continue
        clock = payload.get("time") or {}
        if clock.get("created") and clock.get("completed"):
            latencies.append((clock["completed"] - clock["created"]) / 1000)
    sums = con.execute(
        "SELECT SUM(tokens_input), SUM(tokens_output), SUM(tokens_reasoning), "
        "SUM(tokens_cache_read), SUM(tokens_cache_write), SUM(cost) "
        f"FROM session WHERE id IN ({marks})",
        ids,
    ).fetchone()
    con.close()
    for suffix in ("", "-wal", "-shm"):
        Path(str(tmp) + suffix).unlink(missing_ok=True)
    if sums is None or sums[0] is None:
        return latencies, NO_TOKENS, None
    inp, out, reasoning, cache_read, cache_write, cost = (v or 0 for v in sums)
    tokens = {
        "input_tokens": int(inp + cache_read + cache_write),
        "output_tokens": int(out + reasoning),
        "cache_tokens": int(cache_read + cache_write),
    }
    return latencies, tokens, round(float(cost), 4)


def claude_run(session: str, stdout: Path | None) -> dict:
    """The transcripts, root and subagents: a `Bash` tool_use is a command,
    a distinct requestId is a turn whose latency is the wait before its
    first assistant line; each request's usage is repeated per content
    block with the counters growing, so a counter is its largest value."""
    commands: list[tuple[datetime, str]] = []
    latencies: list[float] = []
    resets = 0
    usage: dict[str, dict[str, int]] = {}
    for path in claude_transcripts(session):
        previous: datetime | None = None
        seen_requests: set[str] = set()
        for row in json_lines(path):
            when = parse(str(row.get("timestamp") or ""))
            if row.get("type") == "assistant" and when:
                request = str(row.get("requestId") or "")
                message = row.get("message") or {}
                if request and request not in seen_requests:
                    seen_requests.add(request)
                    if previous:
                        latencies.append((when - previous).total_seconds())
                counters = message.get("usage") or {}
                if request and counters:
                    slot = usage.setdefault(request, {})
                    for key in (
                        "input_tokens",
                        "cache_creation_input_tokens",
                        "cache_read_input_tokens",
                        "output_tokens",
                    ):
                        slot[key] = max(slot.get(key, 0), int(counters.get(key) or 0))
                for block in message.get("content") or []:
                    if block.get("type") != "tool_use":
                        continue
                    name = str(block.get("name") or "")
                    if name == "Bash":
                        commands.append(
                            (when, str((block.get("input") or {}).get("command") or ""))
                        )
                    if "odd_stack_reset" in name:
                        resets += 1
            if when:
                previous = when
    commands.sort(key=lambda c: c[0])
    tokens: dict = dict(NO_TOKENS)
    if usage:
        cache = sum(
            u.get("cache_creation_input_tokens", 0)
            + u.get("cache_read_input_tokens", 0)
            for u in usage.values()
        )
        tokens = {
            "input_tokens": sum(u.get("input_tokens", 0) for u in usage.values())
            + cache,
            "output_tokens": sum(u.get("output_tokens", 0) for u in usage.values()),
            "cache_tokens": cache,
        }
    # the cost is in the result the run prints at exit - absent on a run
    # stopped at its phase marker
    cost = None
    for row in json_lines(stdout):
        if row.get("type") == "result" and row.get("total_cost_usd") is not None:
            cost = round(float(row["total_cost_usd"]), 4)
    return {
        "commands": commands,
        "latencies": latencies,
        "resets": resets,
        **tokens,
        "cost_usd": cost,
        "cost_note": None
        if cost is not None
        else "printed at exit only: a stopped run has none (reconstruct from the "
        "transcripts at list price, launch-llms-benchmark step 7)",
    }


def copilot_run(session: str, stdout: Path | None, usage_file: Path | None) -> dict:
    """The session's events for the commands, the stdout stream's
    `model.call_start` / `model.call_finished` pairs for the requests (an
    assistant turn spans its tool calls; a model call does not), the usage
    file for the tokens when the run reached its exit."""
    commands: list[tuple[datetime, str]] = []
    resets = 0
    for event in json_lines(COPILOT_SESSIONS / session / "events.jsonl"):
        data = event.get("data") or {}
        when = parse(str(event.get("timestamp") or ""))
        if event.get("type") != "tool.execution_start" or not when:
            continue
        tool = str(data.get("toolName") or "")
        if tool == "bash":
            commands.append(
                (when, str((data.get("arguments") or {}).get("command") or ""))
            )
        if "odd_stack_reset" in tool:
            resets += 1
    latencies: list[float] = []
    starts: list[datetime] = []
    for event in json_lines(stdout):
        kind = event.get("type")
        when = parse(str(event.get("timestamp") or ""))
        if not when:
            continue
        if kind == "model.call_start":
            starts.append(when)
        elif kind == "model.call_finished" and starts:
            latencies.append((when - starts.pop(0)).total_seconds())
    tokens: dict = dict(NO_TOKENS)
    note = "written at exit only: a stopped run has none (--keep-running, or a whole phase)"
    if usage_file and usage_file.is_file():
        try:
            metrics = json.loads(usage_file.read_text()).get("modelMetrics") or {}
        except ValueError:
            metrics = {}
        if metrics:
            used = [m.get("usage") or {} for m in metrics.values()]
            cache = sum(
                int(u.get("cacheReadTokens") or 0) + int(u.get("cacheWriteTokens") or 0)
                for u in used
            )
            tokens = {
                "input_tokens": sum(int(u.get("inputTokens") or 0) for u in used),
                "output_tokens": sum(int(u.get("outputTokens") or 0) for u in used),
                "cache_tokens": cache,
            }
            note = None
    return {
        "commands": commands,
        "latencies": latencies,
        "resets": resets,
        **tokens,
        "tokens_note": note,
        "cost_usd": None,
        "cost_note": "copilot bills premium requests, not dollars: reconstruct at the "
        "vendor's list price (launch-llms-benchmark step 7)",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", help="a measure_phase.py record: the CLI, id and files")
    ap.add_argument("--cli", choices=CLIS, help="the CLI that drove the run")
    ap.add_argument("--run-id", help="the run's own id (never the log's tail)")
    ap.add_argument("--stdout", help="the run's stdout stream (claude, copilot)")
    ap.add_argument("--usage", help="copilot: the usage file the run wrote at exit")
    ap.add_argument("--gap", type=int, default=60, help="report gaps over N seconds")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cli, run_id, stdout, usage = args.cli, args.run_id, args.stdout, args.usage
    if args.record:
        record = json.loads(Path(args.record).read_text())
        cli = cli or record.get("cli") or "opencode"
        run_id = run_id or record.get("run_id")
        stdout = stdout or record.get("stdout")
        usage = usage or record.get("usage")
    cli = cli or "opencode"
    if not run_id:
        print("no run id - pass --run-id or --record", file=sys.stderr)
        return 1
    if cli == "copilot" and not stdout:
        print(
            "copilot: pass --stdout (or a record) for the model requests",
            file=sys.stderr,
        )
        return 1

    if cli == "opencode":
        run = opencode_run(run_id)
    elif cli == "claude":
        run = claude_run(run_id, Path(stdout) if stdout else None)
    else:
        run = copilot_run(run_id, Path(stdout), Path(usage) if usage else None)
    commands, latencies = run["commands"], run["latencies"]
    if not commands and not latencies:
        print(f"no lines for {cli} run {run_id}", file=sys.stderr)
        return 1

    gaps = []
    previous = None
    for when, text in commands:
        if previous is not None:
            delta = (when - previous).total_seconds()
            if delta >= args.gap:
                gaps.append(
                    {
                        "at": when.strftime("%H:%M:%S"),
                        "seconds": int(delta),
                        "before": " ".join(text.split())[:56],
                    }
                )
        previous = when

    report = {
        "cli": cli,
        "run_id": run_id,
        "commands": len(commands),
        "authored_scripts": sum(bool(AUTHORED.search(t)) for _, t in commands),
        "stack_resets": run["resets"],
        "redundant_machine_questions": sum(
            bool(REDUNDANT.search(t)) for _, t in commands
        ),
        "help_calls_on_shipped_scripts": sum(
            "--help" in t and any(s in t for s in SHIPPED) for _, t in commands
        ),
        "gaps_over_threshold": gaps,
        "input_tokens": run["input_tokens"],
        "output_tokens": run["output_tokens"],
        "cache_tokens": run["cache_tokens"],
        "cost_usd": run["cost_usd"],
    }
    for key in ("tokens_note", "cost_note"):
        if run.get(key):
            report[key] = run[key]
    if latencies:
        report.update(
            {
                "turns": len(latencies),
                "generation_seconds": round(sum(latencies)),
                "median_turn_seconds": round(statistics.median(latencies), 1),
                "slowest_turn_seconds": round(max(latencies)),
            }
        )

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"{cli} run {run_id}")
    print(f"  commands                {report['commands']}")
    for key in (
        "turns",
        "generation_seconds",
        "median_turn_seconds",
        "slowest_turn_seconds",
    ):
        if key in report:
            print(f"  {key:<23} {report[key]}")
    for key in ("input_tokens", "output_tokens", "cache_tokens", "cost_usd"):
        value = report[key]
        shown = value if value is not None else "null"
        print(f"  {key:<23} {shown}")
    for key in ("tokens_note", "cost_note"):
        if key in report:
            print(f"    ({key.split('_')[0]}: {report[key]})")
    print("  what harnessing removes:")
    for key in (
        "authored_scripts",
        "stack_resets",
        "redundant_machine_questions",
        "help_calls_on_shipped_scripts",
    ):
        print(f"    {key:<34} {report[key]}")
    if gaps:
        print(f"  gaps over {args.gap}s (no command running - the model generating):")
        for gap in gaps:
            print(f"    {gap['at']}  {gap['seconds']:4d}s  before: {gap['before']}")
        worst = max(g["seconds"] for g in gaps)
        median = report.get("median_turn_seconds")
        if median and worst > 20 * median:
            print(f"\n  ! the slowest gap is {worst}s against a {median}s median turn:")
            print("    that is provider latency, and a wall-clock comparison")
            print("    against another run is not meaningful. Compare generation")
            print("    time and commands instead, or re-measure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
