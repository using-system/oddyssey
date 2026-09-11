#!/usr/bin/env python3
"""Say where a measured run's time went, and whether the number is usable.

Reads one run's own lines under the CLI that drove it - opencode's log
and session store, claude's transcripts (root and subagents), copilot's
events - and separates what the package controls from what it does not:

- **commands** and **turns**, which a harnessing change moves;
- **generation time**, summed per model request - the honest metric
  when the provider is slow, because it is measured request by request;
- **gaps** with no command in them, which are the model generating, not
  the package working. A gap far above the run's median turn is provider
  latency and invalidates a wall-clock comparison.

It also counts the behaviours a harnessing change is meant to remove:
shell scripts the run authored, stack resets, machine questions already
answered upstream, and `--help` calls on shipped scripts.

    analyze_run.py --record /tmp/study/g6.record.json [--json]
    analyze_run.py --cli opencode --run-id 85496389
    analyze_run.py --cli copilot --run-id <session id>
    analyze_run.py --cli claude --run-id <session id> --cwd <the run's directory>

The record a measure_phase.py run wrote carries the CLI, the id and the
directory; the manual form names them.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
from datetime import datetime
from pathlib import Path

CLIS = ("opencode", "claude", "copilot")
HOME = Path.home()
OPENCODE_LOG = HOME / ".local/share/opencode/log/opencode.log"
OPENCODE_STORE = HOME / ".local/share/opencode/opencode.db"
CLAUDE_PROJECTS = HOME / ".claude/projects"
COPILOT_SESSIONS = HOME / ".copilot/session-state"
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


def parse(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def json_lines(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    with path.open(errors="replace") as handle:
        for line in handle:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


# --- one run's commands and turns, per CLI --------------------------------------
#
# Each reader returns the shell commands the run issued, dated, the
# latency of each model request, and the counts of the two behaviours
# the lines can show directly (stack resets, tool-level `--help`).


def opencode_run(run_id: str) -> tuple[list[tuple[datetime, str]], list[float], int]:
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
    resets = sum("odd_stack_reset" in ln for _, ln in rows)
    return commands, opencode_latencies(rows), resets


def opencode_latencies(rows: list[tuple[datetime, str]]) -> list[float]:
    """Turns and generation time across the run's own session tree - the
    sessions its log lines name, never a time window."""
    if not OPENCODE_STORE.is_file():
        return []
    seen: set[str] = set()
    for _, line in rows:
        seen.update(re.findall(r"session\.id=(\S+)", line))
        seen.update(re.findall(r'"sessionID":"([^"]+)"', line))
    if not seen:
        return []
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
    con.close()
    for suffix in ("", "-wal", "-shm"):
        Path(str(tmp) + suffix).unlink(missing_ok=True)
    return latencies


def claude_run(
    session: str, cwd: Path
) -> tuple[list[tuple[datetime, str]], list[float], int]:
    """The transcripts, root and subagents: a `Bash` tool_use is a command,
    a distinct requestId is a turn whose latency is the wait before its
    first assistant line."""
    project = CLAUDE_PROJECTS / str(cwd.resolve()).replace("/", "-")
    files = [project / f"{session}.jsonl"] + sorted(
        (project / session / "subagents").glob("agent-*.jsonl")
    )
    commands: list[tuple[datetime, str]] = []
    latencies: list[float] = []
    resets = 0
    for path in files:
        previous: datetime | None = None
        seen_requests: set[str] = set()
        for row in json_lines(path):
            when = parse(str(row.get("timestamp") or ""))
            if row.get("type") == "assistant" and when:
                request = row.get("requestId")
                if request and request not in seen_requests and previous:
                    seen_requests.add(request)
                    latencies.append((when - previous).total_seconds())
                for block in (row.get("message") or {}).get("content") or []:
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
    return commands, latencies, resets


def copilot_run(session: str) -> tuple[list[tuple[datetime, str]], list[float], int]:
    """The session's events: a `bash` execution is a command, an assistant
    turn's start/end pair its latency."""
    events = json_lines(COPILOT_SESSIONS / session / "events.jsonl")
    commands: list[tuple[datetime, str]] = []
    latencies: list[float] = []
    resets = 0
    starts: dict[str, datetime] = {}
    for event in events:
        kind = event.get("type")
        data = event.get("data") or {}
        when = parse(str(event.get("timestamp") or ""))
        if not when:
            continue
        if kind == "tool.execution_start":
            tool = str(data.get("toolName") or "")
            if tool == "bash":
                commands.append(
                    (when, str((data.get("arguments") or {}).get("command") or ""))
                )
            if "odd_stack_reset" in tool:
                resets += 1
        elif kind == "assistant.turn_start":
            starts[str(data.get("turnId"))] = when
        elif kind == "assistant.turn_end":
            started = starts.pop(str(data.get("turnId")), None)
            if started:
                latencies.append((when - started).total_seconds())
    return commands, latencies, resets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", help="a measure_phase.py record: the CLI, id and cwd")
    ap.add_argument("--cli", choices=CLIS, help="the CLI that drove the run")
    ap.add_argument("--run-id", help="the run's own id (never the log's tail)")
    ap.add_argument("--cwd", help="claude: the directory the run was launched from")
    ap.add_argument("--gap", type=int, default=60, help="report gaps over N seconds")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cli, run_id, cwd = args.cli, args.run_id, args.cwd
    if args.record:
        record = json.loads(Path(args.record).read_text())
        cli = cli or record.get("cli") or "opencode"
        run_id = run_id or record.get("run_id")
        cwd = cwd or record.get("cwd")
    cli = cli or "opencode"
    if not run_id:
        print("no run id - pass --run-id or --record", file=sys.stderr)
        return 1
    if cli == "claude" and not cwd:
        print(
            "claude: pass --cwd (or a record) to find the transcripts", file=sys.stderr
        )
        return 1

    if cli == "opencode":
        commands, latencies, resets = opencode_run(run_id)
    elif cli == "claude":
        commands, latencies, resets = claude_run(run_id, Path(cwd))
    else:
        commands, latencies, resets = copilot_run(run_id)
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
                        "before": text[:56],
                    }
                )
        previous = when

    report = {
        "cli": cli,
        "run_id": run_id,
        "commands": len(commands),
        "authored_scripts": sum(bool(AUTHORED.search(t)) for _, t in commands),
        "stack_resets": resets,
        "redundant_machine_questions": sum(
            bool(REDUNDANT.search(t)) for _, t in commands
        ),
        "help_calls_on_shipped_scripts": sum(
            "--help" in t and any(s in t for s in SHIPPED) for _, t in commands
        ),
        "gaps_over_threshold": gaps,
    }
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
