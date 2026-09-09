#!/usr/bin/env python3
"""Measure one phase of an oddyssey run, driven headless by opencode.

Launches the mission, watches for the phase's end marker, stops the run
there, and writes the record. Everything here is mechanical - and the
traps it avoids are the ones that silently produce a wrong number:

- the opencode log is shared with the user's own sessions, so this
  records OUR run id at launch and never reads the log's tail;
- a `k6` process is only a drive when it is running a script: `k6
  version` and `k6 inspect` are not, and a k6 left over from a previous
  run is not this run's either - both are purged and excluded;
- a run that dies looks exactly like a run that thinks, so the watch
  fails loudly instead of returning a fast, wrong time.

    measure_phase.py --model google/gemini-3.7-flash --tag g1 \
        --phase preflight --prompt-file mission.txt --out /tmp/study

Exit 0 with the record printed, 1 when the phase never completed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LOG = Path.home() / ".local/share/opencode/log/opencode.log"
POLL = 2


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def k6_driving() -> bool:
    """A k6 that is running a script - not `k6 version`, not `k6 inspect`."""
    out = subprocess.run(
        ["ps", "-eo", "comm,args"], capture_output=True, text=True, check=False
    ).stdout
    for line in out.splitlines():
        comm = line.split(maxsplit=1)[0] if line.split() else ""
        if Path(comm).name == "k6" and " run " in line and ".js" in line:
            return True
    return False


def purge_k6() -> None:
    """A leftover drive would be read as this run's, and time it at zero."""
    subprocess.run(["pkill", "-x", "k6"], capture_output=True, check=False)
    for _ in range(30):
        if not k6_driving():
            return
        time.sleep(1)


def find_run_id(model: str, since: float) -> str | None:
    """Our run's id, from a log line naming our model after we launched."""
    if not LOG.is_file():
        return None
    pattern = re.compile(r"run=([0-9a-f]+)")
    found = None
    with LOG.open(errors="replace") as handle:
        for line in handle:
            if model not in line:
                continue
            # "2026-09-07T20:26:06.229Z" - 23 characters before the Z;
            # a shorter slice ends on the separator and never parses.
            stamp = line.partition("timestamp=")[2][:23]
            try:
                when = (
                    datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%f")
                    .replace(tzinfo=timezone.utc)
                    .timestamp()
                )
            except ValueError:
                continue
            if when + 2 < since:
                continue
            match = pattern.search(line)
            if match:
                found = match.group(1)
    return found


def log_has(run_id: str, needle: str) -> bool:
    if not LOG.is_file():
        return False
    with LOG.open(errors="replace") as handle:
        return any(f"run={run_id}" in ln and needle in ln for ln in handle)


def run_errored(run_id: str) -> bool:
    return log_has(run_id, "level=ERROR")


def phase_reached(
    phase: str, run_id: str | None, started: float, pattern: str | None
) -> bool:
    """The marker that closes the phase under measurement.

    A mission without a k6 drive needs its own marker - the first
    telemetry query, the one request it was told to send - so a caller
    can name it as a regular expression over the run's log lines.
    """
    if pattern:
        if not run_id or not LOG.is_file():
            return False
        needle = re.compile(pattern)
        with LOG.open(errors="replace") as handle:
            return any(f"run={run_id}" in ln and needle.search(ln) for ln in handle)
    if phase == "preflight":
        return k6_driving()
    if phase == "drive":
        return bool(run_id) and not k6_driving() and time.time() - started > 30
    if phase in ("observation", "whole"):
        return False  # closed by the process exiting
    raise ValueError(f"unknown phase {phase}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True, help="OpenRouter model id")
    ap.add_argument("--tag", required=True, help="names this measurement's files")
    ap.add_argument(
        "--phase",
        required=True,
        choices=["preflight", "drive", "observation", "whole"],
        help="which phase is under measurement",
    )
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt", help="the mission, verbatim")
    group.add_argument("--prompt-file", help="a file holding the mission")
    ap.add_argument("--out", required=True, help="directory for this study's records")
    ap.add_argument(
        "--end-pattern",
        help="a regular expression over this run's log lines that closes the "
        "phase - for a mission with no k6 drive to mark it",
    )
    ap.add_argument("--variant", default="medium")
    ap.add_argument("--timeout", type=int, default=2700, help="seconds (default 2700)")
    ap.add_argument(
        "--keep-running",
        action="store_true",
        help="do not stop the run once the phase closes",
    )
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    mission = (
        Path(args.prompt_file).read_text().strip() if args.prompt_file else args.prompt
    )

    # A mission that opens with a slash command is launched through the
    # host's own expansion (`--command <name>`, the rest as its arguments):
    # passed as raw text, the run hunts for the command file first - globs,
    # reads of the command and of the agent it dispatches - a cost no host
    # pays when the command is typed, and one that pollutes every phase
    # number. The record says which form was used.
    command = None
    match = re.match(r"^/([A-Za-z0-9_-]+)\s*(.*)$", mission, re.DOTALL)
    if match:
        command, mission = match.group(1), match.group(2).strip()

    purge_k6()
    started_at = time.time()
    start_utc = utc()

    proc = subprocess.Popen(
        [
            "caffeinate",
            "-i",
            "opencode",
            "run",
            "--model",
            f"openrouter/{args.model}",
            "--variant",
            args.variant,
            "--format",
            "json",
            "--auto",
            "--title",
            f"harness-study {args.tag}",
            *(["--command", command] if command else []),
            mission,
        ],
        stdin=subprocess.DEVNULL,
        stdout=(out / f"{args.tag}.stdout.json").open("w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    run_id = None
    reached = False
    note = ""
    deadline = started_at + args.timeout
    while time.time() < deadline:
        if run_id is None:
            run_id = find_run_id(args.model, started_at)
        if proc.poll() is not None:
            reached = args.phase in ("observation", "whole")
            note = "the run exited" + ("" if reached else " before the phase closed")
            break
        if run_id and run_errored(run_id):
            note = "the run logged an error - the number would be meaningless"
            break
        if phase_reached(args.phase, run_id, started_at, args.end_pattern):
            reached = True
            break
        time.sleep(POLL)
    else:
        note = f"no phase marker within {args.timeout}s"

    end_utc = utc()
    seconds = int(time.time() - started_at)

    if not args.keep_running and proc.poll() is None:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

    record = {
        "tag": args.tag,
        "model": args.model,
        "phase": args.phase,
        "run_id": run_id,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "seconds": seconds,
        "reached": reached,
        "note": note,
        "end_pattern": args.end_pattern,
        "command": command,
    }
    (out / f"{args.tag}.record.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))
    if not reached:
        print(f"\nphase not measured: {note}", file=sys.stderr)
        return 1
    print(f"\n{args.tag}: {args.phase} {seconds // 60}m{seconds % 60:02d}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
