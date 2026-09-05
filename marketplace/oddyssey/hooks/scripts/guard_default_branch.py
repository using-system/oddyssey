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
``git checkout x`` with a path ``x`` and no branch and no commit of
that name restores the path - ``git switch`` never takes a path, and
a remote-only name next to a path is refused by git as ambiguous; a
name that exactly one remote carries (``origin/x`` and no local
``x``) is the branch git's guess creates from it, unless
``--no-guess`` says otherwise or several remotes carry it and
``checkout.defaultRemote`` picks none; anything else (a variable, a
deleted file) changes nothing.

A ``||`` splits the line: the command after it runs only when the
one before it failed, so neither can be assumed alone. When that
recovery command is a plain top-level ``exit``, what follows is read
as if the ``||`` were not there - the contract's ``git switch -c x
|| exit 1; git commit`` passes. Only that: ``return`` outside a
function is an error bash and sh survive, an ``exit`` inside
parentheses ends the subshell alone, and one inside braces is not
read. When the recovery switches to the very branch the failed
command aimed at (``git switch x || git switch -c x``), the line is
on that branch either way - provided the name resolves, as for any
switch. Anything else - ``|| true``, ``|| echo failed``, ``|| git
status``, a switch elsewhere, a commit - leaves the branch unknown:
from there the line is judged on the branch actually checked out,
until a later switch outside any ``||`` moves it again. So ``git
switch -c x || git commit`` and ``git switch -c x || true && git
commit`` are blocked on the default branch, and ``git switch -c x &&
git commit -m a || git commit -m b`` too, conservatively - the second
commit runs on whichever branch the first failed on.

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
from typing import NamedTuple

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
# A recovery command that ends the line: what follows never runs after it.
# ``exit`` alone - ``return`` outside a function is an error the line survives
# in bash and sh, and an ``exit`` inside parentheses ends only the subshell.
LINE_ABORTS = {"exit"}

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


class Segment(NamedTuple):
    """One command of the shell line: ``recovery`` when it follows a ``||``
    and so runs only if the command before it failed, ``subshell`` when it
    sits inside parentheses."""

    recovery: bool
    subshell: bool
    tokens: list[str]


def _segments(command: str) -> list[Segment]:
    """Split the shell line into commands, the way a shell reads it."""
    text = _strip_heredocs(command).replace("\\\n", " ").replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = text.split()
    segments = [Segment(False, False, [])]
    depth = 0
    for token in tokens:
        if not token.strip():
            continue  # an escaped blank: not a word, not an operator
        if set(token) <= PUNCTUATION:
            depth = max(0, depth + token.count("(") - token.count(")"))
            last = segments[-1]
            if last.tokens:
                last = Segment(False, False, [])
                segments.append(last)
            segments[-1] = Segment(
                last.recovery or "||" in token, depth > 0, last.tokens
            )
            continue
        segments[-1].tokens.append(token)
    return [segment for segment in segments if segment.tokens]


def _git_invocation(tokens: list[str]) -> tuple[str, list[str], str | None] | None:
    """(subcommand, arguments, -C path) when the command is a git call."""
    if Path(tokens[0]).name != "git":
        return None
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
        return None
    return tokens[index], tokens[index + 1 :], repo_hint


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


def _switch_target(
    subcommand: str, arguments: list[str]
) -> tuple[str, tuple[str, ...]] | None:
    """What a switch or checkout moves to: ("switch", (branch,)) for a branch
    the line creates, ("switch", ()) when only git knows the destination,
    ("unresolved", (x, subcommand[, "--no-guess"])) for a bare ``git switch x``
    or ``git checkout x`` that the caller resolves against the repository -
    the subcommand because only a checkout takes a path, the flag because it
    turns git's guess from a remote off - None when no branch changes."""
    if "--" in arguments:
        return None  # paths follow: a file checkout never changes the branch
    created: str | None = None
    unknown = False
    guess = True
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
        elif name in ("--guess", "--no-guess"):
            guess = name == "--guess"
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
    return (
        "unresolved",
        (positional[0], subcommand, *([] if guess else ["--no-guess"])),
    )


def _created_branch(arguments: list[str]) -> str | None:
    """The branch a ``git branch`` call creates, when it creates one."""
    positional = [t for t in arguments if not t.startswith("-")]
    if not positional or any(t in BRANCH_NOT_CREATING for t in arguments):
        return None
    return positional[0]


Operation = tuple[str, tuple[str, ...], str | None]


def _operation(tokens: list[str]) -> Operation | None:
    """(kind, targets, -C path) when the command commits, pushes, switches
    branch, or creates one."""
    invocation = _git_invocation(tokens)
    if invocation is None:
        return None
    subcommand, arguments, hint = invocation
    if subcommand == "commit":
        return ("commit", (), hint)
    if subcommand == "push":
        return ("push", _push_targets(arguments), hint)
    if subcommand in ("switch", "checkout"):
        target = _switch_target(subcommand, arguments)
        return None if target is None else (target[0], target[1], hint)
    if subcommand == "branch":
        created = _created_branch(arguments)
        return None if created is None else ("branch", (created,), hint)
    return None


def _aimed_at(operation: Operation | None) -> tuple[str, ...]:
    """The branch a switch names, as (name,); () for anything else."""
    if operation and operation[0] in ("switch", "unresolved"):
        return operation[1][:1]
    return ()


def git_operations(command: str) -> list[Operation]:
    """Return (kind, targets, -C path) for each commit, push, branch switch, or
    branch creation in the line, in the order the shell runs them. A command
    that runs only because the one before it failed (after ``||``) is read for
    what it leaves behind: a plain top-level ``exit`` ends the line and leaves
    no entry; anything else leaves a ("||", (), None) entry - the branch is
    unknown from there - followed by the command's own operation when it is a
    commit, a push, or a switch to the very branch the failed switch aimed at
    (the line is on it either way, if the name resolves); a switch elsewhere
    may not have run and is dropped."""
    operations: list[Operation] = []
    previous: Operation | None = None
    for recovery, subshell, tokens in _segments(command):
        operation = _operation(tokens)
        if not recovery:
            if operation is not None:
                operations.append(operation)
        elif tokens[0] in LINE_ABORTS and not subshell:
            pass  # on failure the line ends here: what follows ran the sequenced way
        else:
            operations.append(("||", (), None))
            same_aim = _aimed_at(operation) == _aimed_at(previous) != ()
            if operation is not None and (
                operation[0] in ("commit", "push") or same_aim
            ):
                operations.append(operation)
        previous = operation
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


def guessed_from_remote(repo: Path, name: str) -> bool:
    """True when git's guess creates ``name`` from a remote-tracking branch:
    exactly one configured remote carries ``refs/remotes/<remote>/<name>``, or
    ``checkout.defaultRemote`` picks one of the several that do."""
    carrying = [
        remote
        for remote in (_git(repo, "remote") or "").splitlines()
        if _git(
            repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{name}"
        )
        is not None
    ]
    if len(carrying) == 1:
        return True
    return len(carrying) > 1 and (
        _git(repo, "config", "--get", "checkout.defaultRemote") in carrying
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
    checked_out: dict[Path, tuple[str | None, str]] = {}  # what the repository says
    branches: dict[Path, tuple[str | None, str]] = {}  # what the line moved it to
    created: dict[Path, set[str]] = {}
    for kind, targets, hint in operations:
        if kind == "||":
            # Which command ran is unknowable: from here the line is judged on
            # the branch checked out, until a switch moves it again.
            branches = dict(checked_out)
            continue
        repo = base / hint if hint else base
        if not repo.is_dir():
            continue
        if repo not in branches:
            current = current_branch(repo)
            checked_out[repo] = (current, default_branch(repo) if current else "")
            branches[repo] = checked_out[repo]
        current, default = branches[repo]
        if kind == "branch":
            created.setdefault(repo, set()).add(targets[0])
            continue
        if kind == "unresolved":
            name, subcommand, *flags = targets
            if name in created.get(repo, ()) or branch_exists(repo, name):
                kind, targets = "switch", (name,)
            elif names_a_commit(repo, name):
                kind, targets = "switch", ()  # a detached HEAD: not the default
            elif subcommand == "checkout" and (repo / name).exists():
                continue  # a path: restored, not switched to - or refused as ambiguous
            elif "--no-guess" not in flags and guessed_from_remote(repo, name):
                kind, targets = "switch", (name,)  # git creates it from the remote
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
