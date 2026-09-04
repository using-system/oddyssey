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
payload would cost more than the rule it enforces. It reads the shell
line as a shell would - quoted text and heredoc bodies are data, not
commands - and does not look inside a command an interpreter wraps
(``sh -c "..."``, ``eval``).

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

# A heredoc opener: the body that follows, up to the delimiter line, is
# data the shell never runs.
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
# Everything shlex returns as pure punctuation ends a command.
PUNCTUATION = set("();<>|&")

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
# git push options that consume the next token.
PUSH_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}


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


def _strip_heredocs(command: str) -> str:
    """Drop every heredoc body: the shell feeds it to a command, never runs it."""
    lines = command.split("\n")
    kept: list[str] = []
    pending: list[str] = []
    for line in lines:
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        kept.append(line)
        pending.extend(match.group(2) for match in HEREDOC_RE.finditer(line))
    return "\n".join(kept)


def _segments(command: str) -> list[list[str]]:
    """Split the shell line into commands, the way a shell reads it."""
    text = _strip_heredocs(command).replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = text.split()
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token and set(token) <= PUNCTUATION:
            if segments[-1]:
                segments.append([])
            continue
        segments[-1].append(token)
    return [segment for segment in segments if segment]


def _git_invocations(command: str) -> list[tuple[str, list[str], str | None]]:
    """Yield (subcommand, arguments, -C path) for each git call in the line."""
    found = []
    for tokens in _segments(command):
        if Path(tokens[0]).name != "git":
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


def _push_targets(arguments: list[str]) -> tuple[str, ...]:
    """Return the branches a push writes to; empty means 'the current branch'."""
    positional: list[str] = []
    skip = False
    for token in arguments:
        if skip:
            skip = False
            continue
        if token in PUSH_WITH_VALUE:
            skip = True
            continue
        if token.startswith("-"):
            continue
        positional.append(token)
    targets = []
    for refspec in positional[1:]:
        destination = refspec.split(":", 1)[1] if ":" in refspec else refspec
        destination = destination.lstrip("+").removeprefix("refs/heads/")
        if destination:
            targets.append(destination)
    return tuple(targets)


def git_operations(command: str) -> list[tuple[str, tuple[str, ...], str | None]]:
    """Return (kind, push targets, -C path) for each commit or push in the line."""
    operations: list[tuple[str, tuple[str, ...], str | None]] = []
    for subcommand, arguments, hint in _git_invocations(command):
        if subcommand == "commit":
            operations.append(("commit", (), hint))
        elif subcommand == "push":
            operations.append(("push", _push_targets(arguments), hint))
    return operations


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
    base = Path(payload_cwd(payload) or process_cwd)
    branches: dict[Path, tuple[str | None, str]] = {}
    for kind, targets, hint in operations:
        repo = base / hint if hint else base
        if not repo.is_dir():
            continue
        if repo not in branches:
            current = current_branch(repo)
            branches[repo] = (current, default_branch(repo) if current else "")
        current, default = branches[repo]
        if current is None:
            continue
        if kind == "commit" and current == default:
            return BLOCK, (
                f"odd-guards: never commit on the default branch (`{default}` is "
                "checked out): create or switch to a work branch first."
            )
        if kind == "push":
            aimed_at_default = default in targets or (
                current == default and (not targets or "HEAD" in targets)
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
