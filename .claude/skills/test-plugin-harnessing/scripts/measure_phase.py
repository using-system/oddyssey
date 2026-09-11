#!/usr/bin/env python3
"""Measure one phase of an oddyssey run, driven headless by a coding-agent CLI.

Launches the mission under the CLI named (`opencode`, `claude` or
`copilot` - the three the launch-llms-benchmark command runs, launched
the way that command states), watches for the phase's end marker, stops
the run there, and writes the record. Everything here is mechanical -
and the traps it avoids are the ones that silently produce a wrong
number:

- opencode's log is shared with the user's own sessions, so this records
  OUR run id at launch and never reads the log's tail; claude and copilot
  take the session id this script generates, and their transcripts are
  read under that id alone;
- a `k6` process is only a drive when it is running a script: `k6
  version` and `k6 inspect` are not, and a k6 left over from a previous
  run is not this run's either - both are purged and excluded;
- a run that dies looks exactly like a run that thinks, so the watch
  fails loudly instead of returning a fast, wrong time.

    measure_phase.py --cli opencode --model google/gemini-3.7-flash --tag g1 \
        --phase preflight --prompt-file mission.txt --out /tmp/study

The model is the canonical `vendor/name` id whatever the CLI; each CLI is
handed its own form of it (`openrouter/<model>` for opencode, the
Anthropic id for claude, the bare name for copilot). Exit 0 with the
record printed, 1 when the phase never completed.
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

CLIS = ("opencode", "claude", "copilot")
HOME = Path.home()
# claude keeps its transcripts under the account's home whatever HOME says
HOMES = list(dict.fromkeys([HOME, Path(pwd.getpwuid(os.getuid()).pw_dir)]))
OPENCODE_LOG = HOME / ".local/share/opencode/log/opencode.log"
COPILOT_SESSIONS = HOME / ".copilot/session-state"
POLL = 2
# the variables a Claude Code session exports into its shells: a nested
# launch that inherits them is treated as part of the parent
CLAUDE_SESSION_VARS = (
    "CLAUDECODE",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_PID",
)


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cli_model(cli: str, model: str) -> str:
    """The CLI's own form of a canonical ``vendor/name`` model id."""
    vendor, _, name = model.rpartition("/")
    if cli == "opencode":
        return model if model.startswith("openrouter/") else f"openrouter/{model}"
    if cli == "claude":
        if vendor and vendor != "anthropic":
            raise SystemExit(f"claude runs Anthropic models only, not {model}")
        return name.replace(".", "-")
    return name  # copilot: the bare name its model picker lists


def claude_transcripts(session: str) -> list[Path]:
    """The root transcript and the subagents' beside it, wherever Claude
    Code keyed the directory (its encoding of the path is its own)."""
    for home in HOMES:
        for root in sorted((home / ".claude/projects").glob(f"*/{session}.jsonl")):
            return [root] + sorted(
                (root.parent / session / "subagents").glob("agent-*.jsonl")
            )
    return []


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


# --- the run's own lines, per CLI -------------------------------------------


def find_opencode_run_id(model: str, since: float) -> str | None:
    """Our run's id, from a log line naming our model after we launched."""
    if not OPENCODE_LOG.is_file():
        return None
    pattern = re.compile(r"run=([0-9a-f]+)")
    found = None
    with OPENCODE_LOG.open(errors="replace") as handle:
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


def run_lines(cli: str, run_id: str | None) -> list[str]:
    """Every line this run has written so far - opencode's log filtered to
    its id, claude's transcripts (root and subagents), copilot's events."""
    if not run_id:
        return []
    if cli == "opencode":
        if not OPENCODE_LOG.is_file():
            return []
        with OPENCODE_LOG.open(errors="replace") as handle:
            return [ln for ln in handle if f"run={run_id}" in ln]
    if cli == "claude":
        files = claude_transcripts(run_id)
    else:
        files = [COPILOT_SESSIONS / run_id / "events.jsonl"]
    lines: list[str] = []
    for path in files:
        if path.is_file():
            with path.open(errors="replace") as handle:
                lines.extend(handle)
    return lines


def run_errored(cli: str, lines: list[str], stderr: Path) -> bool:
    if cli == "opencode":
        return any("level=ERROR" in ln for ln in lines)
    # claude and copilot print a failed launch or a dead provider on stderr
    return stderr.is_file() and bool(
        re.search(r"\b(?:API Error|error:)", stderr.read_text(errors="replace"))
    )


def phase_reached(
    phase: str, lines: list[str], started: float, pattern: str | None
) -> bool:
    """The marker that closes the phase under measurement.

    A mission without a k6 drive needs its own marker - the first
    telemetry query, the dispatch of the agent - so a caller names it as
    a regular expression over the run's own lines, in that CLI's shape.
    """
    if pattern:
        needle = re.compile(pattern)
        return any(needle.search(ln) for ln in lines)
    if phase == "preflight":
        return k6_driving()
    if phase == "drive":
        return bool(lines) and not k6_driving() and time.time() - started > 30
    if phase in ("observation", "whole"):
        return False  # closed by the process exiting
    raise ValueError(f"unknown phase {phase}")


# --- the launch, per CLI -------------------------------------------------------


def launch(
    cli: str,
    model: str,
    effort: str,
    tag: str,
    mission: str,
    command: str | None,
    out: Path,
    cwd: Path,
) -> tuple[subprocess.Popen, str | None, str]:
    """Start the run the way launch-llms-benchmark states for the CLI; the
    session id when this script chose it, and how the mission was handed
    over."""
    stdout = (out / f"{tag}.stdout.json").open("w")
    stderr = (out / f"{tag}.stderr").open("w")
    env = dict(os.environ)
    if cli == "opencode":
        # a slash command is launched through the host's own expansion:
        # passed as raw text, the run hunts for the command file first
        argv = [
            "opencode",
            "run",
            "--model",
            model,
            "--variant",
            effort,
            "--format",
            "json",
            "--auto",
            "--title",
            f"harness-study {tag}",
            *(["--command", command] if command else []),
            mission,
        ]
        session, form = None, ("host --command" if command else "text")
    elif cli == "claude":
        session = str(uuid.uuid4())
        for name in CLAUDE_SESSION_VARS:
            env.pop(name, None)
        # lifts print mode's ceiling on background tasks: a root that
        # dispatches the agent in the background is otherwise killed
        env["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"] = "0"
        text = f"/{command} {mission}".strip() if command else mission
        argv = [
            "claude",
            "-p",
            text,
            "--model",
            model,
            "--effort",
            effort,
            "--permission-mode",
            "bypassPermissions",
            "--output-format",
            "json",
            "--session-id",
            session,
        ]
        form = "text, expanded by the host" if command else "text"
    else:
        if not (cwd / ".github/mcp.json").is_file():
            raise SystemExit(
                "copilot: no .github/mcp.json in the working directory - install "
                "the package for the copilot target first"
            )
        session = str(uuid.uuid4())
        text = f"/{command} {mission}".strip() if command else mission
        argv = [
            "copilot",
            "-p",
            text,
            "--model",
            model,
            "--effort",
            effort,
            "--allow-all",
            "--no-ask-user",
            "--additional-mcp-config",
            "@.github/mcp.json",
            "--session-id",
            session,
            "--output-format",
            "json",
            "--usage-output-file",
            str(out / f"{tag}.usage.json"),
        ]
        form = "text, not expanded (copilot expands no slash command)"
    proc = subprocess.Popen(
        ["caffeinate", "-i", *argv],
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr if cli != "opencode" else subprocess.STDOUT,
        start_new_session=True,
        env=env,
        cwd=str(cwd),
    )
    return proc, session, form


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--cli",
        choices=CLIS,
        default="opencode",
        help="the CLI the run is driven by (default opencode)",
    )
    ap.add_argument("--model", required=True, help="the canonical vendor/name model id")
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
        help="a regular expression over this run's own lines (the CLI's log, "
        "transcript or events) that closes the phase - for a mission with "
        "no k6 drive to mark it",
    )
    ap.add_argument(
        "--effort",
        "--variant",
        dest="effort",
        default="medium",
        help="the effort level, the same on the three CLIs (default medium)",
    )
    ap.add_argument("--timeout", type=int, default=2700, help="seconds (default 2700)")
    ap.add_argument(
        "--keep-running",
        action="store_true",
        help="do not stop the run once the phase closes",
    )
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cwd = Path.cwd()
    mission = (
        Path(args.prompt_file).read_text().strip() if args.prompt_file else args.prompt
    )
    command = None
    match = re.match(r"^/([A-Za-z0-9_-]+)(?:\s+(.*))?$", mission, re.DOTALL)
    if match:
        command, mission = match.group(1), (match.group(2) or "").strip()
    model = cli_model(args.cli, args.model)

    purge_k6()
    started_at = time.time()
    start_utc = utc()
    proc, run_id, form = launch(
        args.cli, model, args.effort, args.tag, mission, command, out, cwd
    )
    stderr = out / f"{args.tag}.stderr"

    reached = False
    note = ""
    deadline = started_at + args.timeout
    while time.time() < deadline:
        if run_id is None and args.cli == "opencode":
            # the log names the model in its canonical form (modelID=...)
            run_id = find_opencode_run_id(args.model, started_at)
        lines = run_lines(args.cli, run_id)
        if run_id and run_errored(args.cli, lines, stderr):
            note = "the run logged an error - the number would be meaningless"
            break
        if proc.poll() is not None:
            # a run that dies is not a measured phase: an exit status other
            # than 0, or an error on stderr, fails loudly
            if proc.returncode != 0:
                note = f"the run exited with status {proc.returncode}"
            elif run_errored(args.cli, run_lines(args.cli, run_id), stderr):
                note = "the run exited after logging an error"
            else:
                reached = args.phase in ("observation", "whole")
                note = "the run exited" + (
                    "" if reached else " before the phase closed"
                )
            break
        if phase_reached(args.phase, lines, started_at, args.end_pattern):
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
        "cli": args.cli,
        "model": args.model,
        "model_as_passed": model,
        "effort": args.effort,
        "phase": args.phase,
        "run_id": run_id,
        "cwd": str(cwd),
        "start_utc": start_utc,
        "end_utc": end_utc,
        "seconds": seconds,
        "reached": reached,
        "note": note,
        "end_pattern": args.end_pattern,
        "command": command,
        "command_form": form,
        "stdout": str(out / f"{args.tag}.stdout.json"),
        "usage": str(out / f"{args.tag}.usage.json") if args.cli == "copilot" else None,
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
