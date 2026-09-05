"""Refuse a git commit or push aimed at the repository's default branch.

The persistence skills say it in prose - never commit on the default
branch, create a work branch first - and a long mission can still skip
the check (#291). This hook makes the rule deterministic on every host
that runs a pre-tool hook: it reads the host's JSON payload on stdin,
finds the shell command about to run, and when that command commits
while the default branch is checked out, or pushes to it, it exits 2
with one line on stderr - the block signal every hooked host
understands. Everything else exits 0. A ``git switch`` or ``git
checkout`` earlier on the same line sets the branch a later commit
lands on: the contract's own ``git switch -c <work> && git commit``
passes on the default branch, ``git switch main && git commit`` is
blocked on any branch, and a switch whose destination the hook cannot
name (``git switch -``, ``--detach``, ``--track``) lets the commits
after it through - never a push whose refspec names the default
branch, wrong from anywhere. A bare ``git switch x`` or ``git checkout
x`` moves to a local branch, or to one a ``git branch x`` created
earlier on the line; a name that only resolves to a commit (a tag, a
sha, a remote-tracking ref) detaches, which is not the default branch;
a token that is neither a path, a branch nor a commit (a variable, a
deleted file) changes nothing.

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
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([^\s'\"<>|&;()]+)\1")
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
# git switch / checkout options whose value is the branch created.
SWITCH_CREATE = {"-c", "-C", "--create", "--force-create", "-b", "-B", "--orphan"}
# switch / checkout options after which the destination is git's choice.
SWITCH_UNKNOWN = {"-", "-d", "--detach"}
SWITCH_UNKNOWN_WITH_VALUE = {"-t", "--track"}
SHORT_WITH_VALUE = {"-c", "-C", "-b", "-B", "-t"}
# git branch options under which no branch is created.
BRANCH_NOT_CREATING = {
    "-d",
    "-D",
    "--delete",
    "-m",
    "-M",
    "--move",
    "-c",
    "-C",
    "--copy",
    "-l",
    "--list",
    "-a",
    "--all",
    "-r",
    "--remotes",
    "--show-current",
    "--edit-description",
    "-u",
    "--set-upstream-to",
    "--unset-upstream",
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


def _option_and_value(token: str) -> tuple[str, str]:
    """Split an option from the value stuck to it: ``--create=x``, ``-cx``,
    ``-qcx`` (a cluster whose value-taking flag is not the first)."""
    if token.startswith("--"):
        name, _, value = token.partition("=")
        return name, value
    if token.startswith("-") and len(token) > 2 and token[1] != "-":
        for index, char in enumerate(token[1:], 1):
            if f"-{char}" in SHORT_WITH_VALUE:
                return f"-{char}", token[index + 1 :]
    return token, ""


def _switch_target(arguments: list[str]) -> tuple[str, tuple[str, ...]] | None:
    """What a switch or checkout moves to: ("switch", (branch,)) for a branch
    the line creates, ("switch", ()) when only git knows the destination,
    ("unresolved", (x,)) for a bare ``git switch x`` or ``git checkout x`` that
    the caller resolves against the repository, None when no branch changes."""
    if "--" in arguments:
        return None  # paths follow: a file checkout never changes the branch
    created: str | None = None
    unknown = False
    positional: list[str] = []
    tokens = iter(arguments)
    for token in tokens:
        name, sticky = _option_and_value(token)
        if name in SWITCH_CREATE:
            created = sticky or next(tokens, None)
            if not created:
                return None
        elif name in SWITCH_UNKNOWN_WITH_VALUE:
            if not sticky:
                next(tokens, None)
            unknown = True
        elif name in SWITCH_UNKNOWN:
            unknown = True
        elif token.startswith("-"):
            continue
        else:
            positional.append(token)
    if created:
        return ("switch", (created,))
    if unknown:
        return ("switch", ())
    if not positional:
        return None
    return ("unresolved", (positional[0],))


def _created_branch(arguments: list[str]) -> str | None:
    """The branch a ``git branch`` call creates, when it creates one."""
    positional = [t for t in arguments if not t.startswith("-")]
    if not positional or any(t in BRANCH_NOT_CREATING for t in arguments):
        return None
    return positional[0]


def git_operations(command: str) -> list[tuple[str, tuple[str, ...], str | None]]:
    """Return (kind, targets, -C path) for each commit, push, branch switch, or
    branch creation in the line, in the order the shell runs them."""
    operations: list[tuple[str, tuple[str, ...], str | None]] = []
    for subcommand, arguments, hint in _git_invocations(command):
        if subcommand == "commit":
            operations.append(("commit", (), hint))
        elif subcommand == "push":
            operations.append(("push", _push_targets(arguments), hint))
        elif subcommand in ("switch", "checkout"):
            target = _switch_target(arguments)
            if target is not None:
                operations.append((target[0], target[1], hint))
        elif subcommand == "branch":
            created = _created_branch(arguments)
            if created is not None:
                operations.append(("branch", (created,), hint))
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


def branch_exists(repo: Path, name: str) -> bool:
    """True when the repository has a local branch of that name."""
    return (
        _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}") is not None
    )


def names_a_commit(repo: Path, name: str) -> bool:
    """True when the name resolves to a commit: a tag, a remote branch, a sha."""
    return (
        _git(repo, "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}") is not None
    )


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
    created: dict[Path, set[str]] = {}
    for kind, targets, hint in operations:
        repo = base / hint if hint else base
        if not repo.is_dir():
            continue
        if repo not in branches:
            current = current_branch(repo)
            branches[repo] = (current, default_branch(repo) if current else "")
        current, default = branches[repo]
        if kind == "branch":
            created.setdefault(repo, set()).add(targets[0])
            continue
        if kind == "unresolved":
            name = targets[0]
            if (repo / name).exists():
                continue  # a path, not a branch
            if name in created.get(repo, ()) or branch_exists(repo, name):
                kind, targets = "switch", (name,)
            elif names_a_commit(repo, name):
                kind, targets = "switch", ()  # a detached HEAD: not the default
            else:
                continue  # nothing git can move to
        if kind == "switch":
            moved_to = targets[0] if targets else None
            if moved_to:
                created.setdefault(repo, set()).add(moved_to)
            branches[repo] = (moved_to, default or default_branch(repo))
            continue
        if kind == "commit" and current is not None and current == default:
            return BLOCK, (
                f"odd-guards: never commit on the default branch (`{default}`, "
                "where this commit lands): create or switch to a work branch first."
            )
        if kind == "push" and default:
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
