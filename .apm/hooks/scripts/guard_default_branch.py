"""Refuse a git commit or push aimed at the repository's default branch.

The persistence skills say it in prose - never commit on the default
branch, create a work branch first - and a long mission can still skip
the check (#291). This hook makes the rule deterministic on every host
that runs a pre-tool hook: it reads the host's JSON payload on stdin,
finds the shell command about to run, and when that command commits
while the default branch is checked out, or pushes to it, it exits 2
with one line on stderr - the block signal every hooked host
understands. Everything else exits 0.

It fails open: a payload it cannot parse, a shape it does not know, a
directory that is not a repository, a git that does not answer - none
of them block anything. A hook that broke a host on an unforeseen
payload would cost more than the rule it enforces.

Standard library only; python3 >= 3.10. Invoked as
``python3 guard_default_branch.py PreToolUse`` by the hook entry in
``.apm/hooks/odd-guards.json``; apm rewrites the path per target.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

BLOCK = 2
PASS = 0
GIT_TIMEOUT_S = 5

# The payload keys the hosts put the shell command under: Claude Code,
# Codex, Gemini, Cursor and Kiro (tool_input.command), Copilot CLI
# (toolArgs.command), Windsurf (tool_info.command_line).
COMMAND_PATHS = (
    ("tool_input", "command"),
    ("toolArgs", "command"),
    ("tool_info", "command_line"),
)
CWD_PATHS = (("cwd",), ("tool_info", "cwd"))

# A shell line is several commands: split on the operators that chain
# them so each git invocation is read on its own.
SEGMENT_RE = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")

# git's global options that consume the next token.
GIT_GLOBAL_WITH_VALUE = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--config-env",
}


def _dig(payload: object, path: tuple[str, ...]) -> object:
    node = payload
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def read_command(payload: object) -> str | None:
    """Return the shell command the payload carries, whatever the host."""
    for path in COMMAND_PATHS:
        value = _dig(payload, path)
        if isinstance(value, str) and value.strip():
            return value
    return None


def payload_cwd(payload: object) -> str | None:
    """Return the working directory the payload names, when it names one."""
    for path in CWD_PATHS:
        value = _dig(payload, path)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _tokens(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _git_invocations(command: str) -> list[tuple[str, list[str], str | None]]:
    """Yield (subcommand, arguments, -C path) for each git call in the line."""
    found = []
    for segment in SEGMENT_RE.split(command):
        tokens = _tokens(segment)
        if not tokens or Path(tokens[0]).name != "git":
            continue
        repo_hint = None
        index = 1
        while index < len(tokens) and tokens[index].startswith("-"):
            option = tokens[index]
            if option in GIT_GLOBAL_WITH_VALUE:
                if option == "-C" and index + 1 < len(tokens):
                    repo_hint = tokens[index + 1]
                index += 2
            elif option.startswith("-C") and len(option) > 2:
                repo_hint = option[2:]
                index += 1
            else:
                index += 1
        if index >= len(tokens):
            continue
        found.append((tokens[index], tokens[index + 1 :], repo_hint))
    return found


def _push_target(arguments: list[str]) -> str | None:
    """Return the branch a push writes to, or None for 'the current branch'."""
    positional = [token for token in arguments if not token.startswith("-")]
    if len(positional) < 2:
        return None
    refspec = positional[-1]
    destination = refspec.split(":", 1)[1] if ":" in refspec else refspec
    return destination.removeprefix("refs/heads/") or None


def git_operations(command: str) -> list[tuple[str, str | None]]:
    """Return the commits and pushes the command performs, in order."""
    operations: list[tuple[str, str | None]] = []
    for subcommand, arguments, _hint in _git_invocations(command):
        if subcommand == "commit":
            operations.append(("commit", None))
        elif subcommand == "push":
            operations.append(("push", _push_target(arguments)))
    return operations


def repository_hint(command: str) -> str | None:
    """Return the first ``git -C <path>`` the command names, if any."""
    for _subcommand, _arguments, hint in _git_invocations(command):
        if hint:
            return hint
    return None


def _git(repo: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def current_branch(repo: Path) -> str | None:
    """The checked-out branch, or None outside a repository or detached."""
    return _git(repo, "branch", "--show-current") or None


def default_branch(repo: Path) -> str:
    """origin/HEAD's branch; else main, or master when master is checked out."""
    head = _git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head.removeprefix("origin/")
    return "master" if current_branch(repo) == "master" else "main"


def decide(payload: object, process_cwd: str) -> tuple[int, str]:
    """Return (exit code, stderr line) for the payload."""
    command = read_command(payload)
    if command is None:
        return PASS, ""
    operations = git_operations(command)
    if not operations:
        return PASS, ""
    base = payload_cwd(payload) or process_cwd
    hint = repository_hint(command)
    repo = Path(base) / hint if hint else Path(base)
    if not repo.is_dir():
        return PASS, ""
    current = current_branch(repo)
    if current is None:
        return PASS, ""
    default = default_branch(repo)
    for operation, target in operations:
        if operation == "commit" and current == default:
            return BLOCK, (
                f"odd-guards: never commit on the default branch (`{default}` is "
                "checked out): create or switch to a work branch first."
            )
        if operation == "push":
            aimed_at_default = target == default or (
                target in (None, "HEAD") and current == default
            )
            if aimed_at_default:
                return BLOCK, (
                    f"odd-guards: never push to the default branch (`{default}`): "
                    "push a work branch and open a pull request."
                )
    return PASS, ""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except (ValueError, OSError):
        return PASS
    try:
        code, message = decide(payload, os.getcwd())
    except Exception as error:  # noqa: BLE001 - fail open, never break the host
        print(f"odd-guards: skipped ({error.__class__.__name__})", file=sys.stderr)
        return PASS
    if message:
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
