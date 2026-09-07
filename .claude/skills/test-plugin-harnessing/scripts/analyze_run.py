#!/usr/bin/env python3
"""Say where a measured run's time went, and whether the number is usable.

Reads one run's own log lines and its opencode sessions, and separates
what the package controls from what it does not:

- **commands** and **turns**, which a harnessing change moves;
- **generation time**, summed per assistant message - the honest metric
  when the provider is slow, because it is measured message by message;
- **gaps** with no command in them, which are the model generating, not
  the package working. A gap far above the run's median turn is provider
  latency and invalidates a wall-clock comparison.

It also counts the behaviours a harnessing change is meant to remove:
shell scripts the run authored, stack resets, machine questions already
answered upstream, and `--help` calls on shipped scripts.

    analyze_run.py --run-id 85496389 --start 2026-09-07T19:35:50Z
    analyze_run.py --record /tmp/study/g6.record.json --json
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

LOG = Path.home() / ".local/share/opencode/log/opencode.log"
STORE = Path.home() / ".local/share/opencode/opencode.db"
REDUNDANT = re.compile(r'pattern="(ls -la|ls -l |docker ps|lsof|find \.)')
AUTHORED = re.compile(r'pattern="(cat > |cat >>|tee )[^"]*\.sh')
SHIPPED = (
    "preflight.py",
    "probe_services.py",
    "gcx_local.py",
    "replay_benchmark.py",
    "odd_recall.py",
)


def parse(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def log_lines(run_id: str) -> list[tuple[datetime, str]]:
    rows: list[tuple[datetime, str]] = []
    if not LOG.is_file():
        return rows
    with LOG.open(errors="replace") as handle:
        for line in handle:
            if f"run={run_id}" not in line:
                continue
            when = parse(line.partition("timestamp=")[2].split(" ", 1)[0])
            if when:
                rows.append((when, line))
    return rows


def sessions(rows: list[tuple[datetime, str]]) -> dict:
    """Turns and generation time across the run's own session tree.

    The sessions are the ones this run's log lines name - never a time
    window, which would sweep in whatever else the user was running at
    the same time.
    """
    if not STORE.is_file():
        return {}
    seen: set[str] = set()
    for _, line in rows:
        seen.update(re.findall(r"session\.id=(\S+)", line))
        seen.update(re.findall(r'"sessionID":"([^"]+)"', line))
    if not seen:
        return {}
    tmp = Path(tempfile.mkdtemp()) / "opencode.db"
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(STORE) + suffix)
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
    if not ids:
        return {}
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
    if not latencies:
        return {}
    return {
        "turns": len(latencies),
        "generation_seconds": round(sum(latencies)),
        "median_turn_seconds": round(statistics.median(latencies), 1),
        "slowest_turn_seconds": round(max(latencies)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", help="the run's own id (never the log's tail)")
    ap.add_argument("--record", help="a measure_phase.py record to read both from")
    ap.add_argument("--gap", type=int, default=60, help="report gaps over N seconds")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    run_id = args.run_id
    if args.record:
        record = json.loads(Path(args.record).read_text())
        run_id = run_id or record.get("run_id")
    if not run_id:
        print("no run id - pass --run-id or --record", file=sys.stderr)
        return 1

    rows = log_lines(run_id)
    if not rows:
        print(f"no log lines for run={run_id}", file=sys.stderr)
        return 1

    commands = [(w, ln) for w, ln in rows if 'pattern="' in ln]
    gaps = []
    previous = None
    for when, line in commands:
        if previous is not None:
            delta = (when - previous).total_seconds()
            if delta >= args.gap:
                snippet = line.partition('pattern="')[2][:56]
                gaps.append(
                    {
                        "at": when.strftime("%H:%M:%S"),
                        "seconds": int(delta),
                        "before": snippet,
                    }
                )
        previous = when

    report = {
        "run_id": run_id,
        "commands": len(commands),
        "authored_scripts": sum(bool(AUTHORED.search(ln)) for _, ln in rows),
        "stack_resets": sum("odd_stack_reset" in ln for _, ln in rows),
        "redundant_machine_questions": sum(
            bool(REDUNDANT.search(ln)) for _, ln in commands
        ),
        "help_calls_on_shipped_scripts": sum(
            "--help" in ln and any(s in ln for s in SHIPPED) for _, ln in commands
        ),
        "gaps_over_threshold": gaps,
        **sessions(rows),
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"run {run_id}")
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
