"""Refuse a tool call about to modify or delete a stored record of the .odd/ memory.

AGENTS.md says the ``.odd/`` memory is append-only - a stored report is
never edited or deleted, a new run writes a new file and the diff lives
there; a decision or a classification is a row the ledger script
appends, never a rewrite - and until now the rule was prose plus the
reviewer's eye. This hook makes it deterministic on every host that
runs a pre-tool hook: it reads the host's JSON payload on stdin, finds
the file a file tool is about to write or the shell command about to
run, and exits 2 with one line on stderr per file - the block signal
every hooked host understands - naming the file and the rule.
Everything else exits 0.

The scope is an allowlist, never ``.odd/`` as a whole: the two report
stores ``.odd/observe-run-reports/`` and
``.odd/otel-instrumentation-reports/``, and the two ruling ledgers
``.odd/decisions.md`` and ``.odd/entry-classifications.md``.
``.odd/benchmarks/`` and ``.odd/observability-stacks/`` are living
source, updated in place through reviewed diffs, and stay outside.

The rule is about committed reports, so the gate is git's, not the
filesystem's: a path under a report store is refused when HEAD holds
it, and stays the agent's to write, rewrite or remove while it does
not - a new run writing its file, and the same file edited again
before its commit when the identifier scan flagged it. A file tool
(Edit, Write, MultiEdit, NotebookEdit and the hosts' equivalents)
aimed at a ledger is refused whether the file exists or not: the
``odd-memory`` skill's ``scripts/odd_ledger.py`` is the ledgers' only
writer, and it validates the row before it lands. A shell command that
names a stored report, a report store, or a ledger together with a
write shape - a ``>``, ``>>``, ``>|`` or ``&>`` redirection onto it,
``sed -i``, ``tee``, ``mv`` or ``cp`` onto it (a positional
destination, or ``-t`` / ``--target-directory``), ``mv`` away from it,
``rm``, ``git rm``, ``git mv``, ``git checkout -- <path>`` and ``git
restore`` - is refused the same way, best effort: a ``cd`` earlier on
the line moves the base the paths resolve against; ``sudo``, ``env``
and a ``VAR=x`` prefix are transparent; a command the parser does not
understand passes. A removal under a store is refused whatever the
path names - a glob the hook cannot expand names stored reports - and
passes only for a file it can see and HEAD does not hold. Deleting a
whole store, or ``.odd/`` itself, is refused naming the stores it
holds. Moving or copying a file into a store is judged by the name it
lands on: a new name passes, a committed report's name is refused.

It fails open: a payload it cannot parse, a shape it does not know, a
path it cannot resolve, a path outside a repository, a git that does
not answer - none of them block anything. A hook that broke a host on
an unforeseen payload would cost more than the rule it enforces. It
reads the shell line as a shell would - quoted text and heredoc bodies
are data, not commands - and does not look inside a command an
interpreter wraps (``sh -c "..."``, ``python3 -c``) nor a path a
variable stands in for. It never reads the file and never echoes what
the tool carries: the message names the path and the rule, nothing
else. There is no bypass flag: the one legitimate rewrite is a
maintainer decision made outside the agent, with the hook removed for
that commit.

Standard library only; python3 >= 3.10. Invoked as
``python3 guard_append_only.py PreToolUse`` by the hook entry in
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

# The .odd/ entries the rule governs: the report stores (directories) and
# the ruling ledgers (files), each named relative to .odd/.
REPORT_STORES = ("observe-run-reports", "otel-instrumentation-reports")
LEDGERS = ("decisions.md", "entry-classifications.md")
LEDGER_SCRIPT = "odd-memory's scripts/odd_ledger.py"
ODD = ".odd"

# The payload keys the hosts put a written file's path or a shell
# command under (Claude Code, Codex, Gemini, Cursor, Kiro: tool_input;
# Copilot CLI: toolArgs; Windsurf: tool_info).
FILE_PATHS = (
    ("tool_input", "file_path"),
    ("tool_input", "path"),
    ("tool_input", "notebook_path"),
    ("toolArgs", "file_path"),
    ("toolArgs", "path"),
    ("tool_info", "file_path"),
)
COMMAND_PATHS = (
    ("tool_input", "command"),
    ("toolArgs", "command"),
    ("tool_info", "command_line"),
)
CWD_PATHS = (("cwd",), ("tool_info", "cwd"))

# A file tool's payload is a write when it carries what it writes, or
# when its tool name says so; a bare path is a read on every host.
WRITE_FIELDS = {
    "content",
    "contents",
    "new_string",
    "old_string",
    "edits",
    "newText",
    "new_str",
    "old_str",
    "text",
}
WRITE_TOOL_RE = re.compile(r"write|edit|create|patch|replace|save", re.IGNORECASE)

# The shell shapes that write onto, move, or remove a file.
REDIRECTIONS = {">", ">>", ">|", "&>", "&>>"}
PUNCTUATION = set("();<>|&")
# Prefixes the shell runs the rest of the line through unchanged.
TRANSPARENT_PREFIXES = {"sudo", "env", "command", "nice", "nohup", "time"}
PREFIX_WITH_VALUE = {"-u", "-g", "-C", "-S", "-n", "-D", "--user", "--group"}
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# A heredoc opener: the body that follows, up to the delimiter line, is
# data the shell never runs.
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([^\s'\"<>|&;()]+)\1")
# Commands whose last positional argument is a destination written onto,
# or whose -t / --target-directory names the directory the sources land in.
COPY_COMMANDS = {"cp", "install", "rsync"}
# Commands whose every positional argument is removed or replaced.
MOVE_COMMANDS = {"mv"}
TARGET_DIRECTORY = {"-t", "--target-directory"}
TARGET_DIRECTORY_LONG = "--target-directory="
DELETE_COMMANDS = {"rm", "unlink", "shred", "truncate"}
CHANGE_DIRECTORY = {"cd", "pushd"}
# sed writes in place under -i (alone, with a suffix, or clustered after
# flags that take no value) and --in-place; these options carry the
# script, so the first positional is then a file.
SED_IN_PLACE_RE = re.compile(r"^-[nrEszu]*i")
SED_IN_PLACE_LONG = "--in-place"
SED_SCRIPT_OPTIONS = {"-e", "--expression", "-f", "--file"}
SED_SCRIPT_LONG = ("--expression=", "--file=")
SED_WITH_VALUE = {"-l", "--line-length"}
# git restore options that consume the next token.
RESTORE_WITH_VALUE = {"-s", "--source"}
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

WRITE = "write"
REMOVE = "remove"
# A copy or move landing in a directory: judged by the name the source
# takes there, never listed among the paths the line names.
INTO = "into"


def _dig(payload: object, path: tuple[str, ...]) -> object:
    node = payload
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _strings(payload: object, paths: tuple[tuple[str, ...], ...]) -> list[str]:
    found = []
    for path in paths:
        value = _dig(payload, path)
        if isinstance(value, str) and value.strip():
            found.append(value)
    return found


def _is_write_tool(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    name = payload.get("tool_name") or payload.get("toolName") or ""
    if isinstance(name, str) and WRITE_TOOL_RE.search(name):
        return True
    for container in ("tool_input", "toolArgs", "tool_info"):
        fields = payload.get(container)
        if isinstance(fields, dict) and WRITE_FIELDS & set(fields):
            return True
    return False


def _strip_heredocs(command: str) -> str:
    """Drop every heredoc body: the shell feeds it to a command, never runs it."""
    kept: list[str] = []
    pending: list[str] = []
    for line in command.split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        kept.append(line)
        pending.extend(match.group(2) for match in HEREDOC_RE.finditer(line))
    return "\n".join(kept)


def _segments(command: str) -> list[list[str]]:
    """Split the shell line into commands, the way a shell reads it; a
    redirection stays a token of the command it belongs to."""
    text = _strip_heredocs(command).replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = text.split()
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token and set(token) <= PUNCTUATION and token not in REDIRECTIONS:
            if segments[-1]:
                segments.append([])
            continue
        segments[-1].append(token)
    return [segment for segment in segments if segment]


def _without_redirections(tokens: list[str]) -> list[str]:
    """The tokens minus every redirection and the target that follows it."""
    kept: list[str] = []
    skip = False
    for token in tokens:
        if skip:
            skip = False
            continue
        if token in REDIRECTIONS:
            skip = True
            continue
        kept.append(token)
    return kept


def _positionals(tokens: list[str]) -> list[str]:
    """The command's positional arguments: no options, no redirections."""
    body = _without_redirections(tokens)[1:]
    return [t for t in body if t and not t.startswith("-")]


def _unwrapped(tokens: list[str]) -> list[str]:
    """The command once ``VAR=x``, ``sudo``, ``env`` and their options are
    peeled off: the shell runs the rest unchanged."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if ASSIGNMENT_RE.match(token):
            index += 1
        elif Path(token).name in TRANSPARENT_PREFIXES:
            index += 1
            while index < len(tokens) and tokens[index].startswith("-"):
                index += 2 if tokens[index] in PREFIX_WITH_VALUE else 1
        else:
            break
    return tokens[index:]


def _sed_targets(tokens: list[str]) -> list[str]:
    """The files a sed call rewrites in place; empty when it only reads."""
    in_place = False
    script_given = False
    positional: list[str] = []
    rest = iter(_without_redirections(tokens[1:]))
    for token in rest:
        if token in SED_SCRIPT_OPTIONS or token in SED_WITH_VALUE:
            script_given = script_given or token in SED_SCRIPT_OPTIONS
            next(rest, None)
        elif token.startswith(SED_SCRIPT_LONG) or (
            token.startswith(("-e", "-f")) and not token.startswith("--")
        ):
            script_given = True
        elif token.startswith(SED_IN_PLACE_LONG) or SED_IN_PLACE_RE.match(token):
            in_place = True
        elif token.startswith("-"):
            continue
        elif token:
            positional.append(token)
    if not in_place:
        return []
    return positional if script_given else positional[1:]


def _copy_targets(tokens: list[str], moving: bool) -> list[tuple[str, str]]:
    """Where a cp or mv lands: the positional destination as a write, and the
    name each source takes under a directory destination or under
    ``-t`` / ``--target-directory``; a move's sources are removed."""
    directory = ""
    arguments: list[str] = []
    rest = iter(_without_redirections(tokens)[1:])
    for token in rest:
        if token in TARGET_DIRECTORY:
            directory = next(rest, "") or directory
        elif token.startswith(TARGET_DIRECTORY_LONG):
            directory = token[len(TARGET_DIRECTORY_LONG) :]
        elif token and not token.startswith("-"):
            arguments.append(token)
    found: list[tuple[str, str]] = []
    if directory:
        sources = arguments
        found.extend((os.path.join(directory, Path(s).name), WRITE) for s in sources)
    elif len(arguments) >= 2:
        sources, destination = arguments[:-1], arguments[-1]
        found.append((destination, WRITE))
        found.extend((os.path.join(destination, Path(s).name), INTO) for s in sources)
    else:
        return []
    if moving:
        found.extend((s, REMOVE) for s in sources)
    return found


def _checkout_paths(subcommand: str, tokens: list[str]) -> list[str]:
    """The files a ``git checkout`` or ``git restore`` rewrites from a
    commit; empty for a branch switch."""
    body = _without_redirections(tokens)
    if subcommand == "checkout":
        if "--" in body:
            return [t for t in body[body.index("--") + 1 :] if t]
        positional = [t for t in body[1:] if t and not t.startswith("-")]
        return positional[1:]  # ``git checkout <rev> <path>...``
    paths: list[str] = []
    rest = iter(body[1:])
    for token in rest:
        if token in RESTORE_WITH_VALUE:
            next(rest, None)
        elif token and not token.startswith("-"):
            paths.append(token)
    return paths


def _git_targets(tokens: list[str]) -> list[tuple[str, str]]:
    """What a ``git rm``, ``git mv``, ``git checkout -- <path>`` or ``git
    restore`` removes or rewrites, under its -C path."""
    hint = ""
    index = 1
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index]
        if option in GIT_GLOBAL_WITH_VALUE:
            if option == "-C" and index + 1 < len(tokens):
                hint = tokens[index + 1]
            index += 2
        elif option.startswith("-C") and len(option) > 2:
            hint = option[2:]
            index += 1
        else:
            index += 1
    if index >= len(tokens):
        return []
    subcommand, arguments = tokens[index], _positionals(tokens[index:])
    if subcommand == "rm":
        found = [(a, REMOVE) for a in arguments]
    elif subcommand == "mv" and len(arguments) >= 2:
        found = [(a, REMOVE) for a in arguments[:-1]] + [(arguments[-1], WRITE)]
    elif subcommand in ("checkout", "restore"):
        found = [(p, WRITE) for p in _checkout_paths(subcommand, tokens[index:])]
    else:
        return []
    return [(_under(hint, target), shape) for target, shape in found]


def _under(base: str, target: str) -> str:
    """The target as seen from a directory the line moved to; absolute and
    home-relative targets stand on their own."""
    if not base or target.startswith(("/", "~")):
        return target
    return os.path.join(base, target)


def _governed_shape(token: str) -> bool:
    """True when the token names something under .odd/, or .odd/ itself."""
    return (
        f"/{ODD}/" in token
        or token.startswith(f"{ODD}/")
        or token == ODD
        or token.endswith(f"/{ODD}")
    )


def _command_targets(command: str) -> list[tuple[str, str]]:
    """The .odd/ paths a shell line writes onto or removes, with the shape."""
    targets: list[tuple[str, str]] = []
    moved_to = ""
    for tokens in _segments(command):
        found: list[tuple[str, str]] = []
        for index, token in enumerate(tokens):
            if token in REDIRECTIONS and index + 1 < len(tokens):
                found.append((tokens[index + 1], WRITE))
        tokens = _unwrapped(tokens)
        if not tokens:
            continue
        name = Path(tokens[0]).name
        arguments = _positionals(tokens)
        if name in CHANGE_DIRECTORY:
            moved_to = _under(moved_to, arguments[0]) if arguments else "~"
            continue
        if name == "tee":
            found.extend((a, WRITE) for a in arguments)
        elif name in COPY_COMMANDS or name in MOVE_COMMANDS:
            found.extend(_copy_targets(tokens, moving=name in MOVE_COMMANDS))
        elif name in DELETE_COMMANDS:
            found.extend((a, REMOVE) for a in arguments)
        elif name == "sed":
            found.extend((a, WRITE) for a in _sed_targets(tokens))
        elif name == "git":
            found.extend(_git_targets(tokens))
        targets.extend((_under(moved_to, t), shape) for t, shape in found)
    return [(t, shape) for t, shape in targets if _governed_shape(t)]


def _targets(payload: object) -> list[tuple[str, str]]:
    """The files the payload writes or removes: a write tool's target, or a
    shell line's targets, each with its shape."""
    targets = [(p, WRITE) for p in _strings(payload, FILE_PATHS)]
    if not _is_write_tool(payload):
        targets = []
    for command in _strings(payload, COMMAND_PATHS):
        targets.extend(_command_targets(command))
    seen: set[tuple[str, str]] = set()
    return [t for t in targets if not (t in seen or seen.add(t))]


def written_paths(payload: object) -> list[str]:
    """The paths the payload writes onto or removes, in the order it names them."""
    seen: set[str] = set()
    return [
        p
        for p, shape in _targets(payload)
        if shape != INTO and not (p in seen or seen.add(p))
    ]


def payload_cwd(payload: object) -> str | None:
    strings = _strings(payload, CWD_PATHS)
    return strings[0] if strings else None


def classify(path: Path) -> str | None:
    """\"report\" for a report store or anything under it, \"ledger\" for a
    ruling ledger, None for everything else - the living-source stores,
    the rest of .odd/, the rest of the tree."""
    parts = path.parts
    if ODD not in parts[:-1]:
        return None
    rest = parts[len(parts) - 1 - parts[::-1].index(ODD) + 1 :]
    if len(rest) == 1 and rest[0] in LEDGERS:
        return "ledger"
    if rest and rest[0] in REPORT_STORES:
        return "report"
    return None


def _resolve(candidate: str, base: Path) -> Path:
    path = Path(candidate).expanduser()
    if not path.is_absolute():
        path = base / path
    return Path(os.path.normpath(path))


def _expand(path: Path, shape: str) -> list[Path]:
    """Removing .odd/ itself removes every store and ledger it holds."""
    if shape != REMOVE or path.name != ODD or not path.is_dir():
        return [path]
    return [path / name for name in REPORT_STORES + LEDGERS if (path / name).exists()]


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


def committed(path: Path) -> bool | None:
    """True when HEAD holds the path (a file or a tree), False when the
    repository does not, None outside a repository or without a git that
    answers - the caller fails open on None."""
    anchor = path
    while not anchor.is_dir():
        if anchor.parent == anchor:
            return None
        anchor = anchor.parent
    top = _git(anchor, "rev-parse", "--show-toplevel")
    if not top:
        return None
    try:
        relative = Path(os.path.realpath(path)).relative_to(os.path.realpath(top))
    except ValueError:
        return None
    if not relative.parts:
        return None
    return _git(Path(top), "cat-file", "-e", f"HEAD:{relative.as_posix()}") is not None


def _display_path(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        pass
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _message(kind: str, path: Path, shown: str) -> str:
    if kind == "ledger":
        return (
            f"odd-guards: {shown} is a ruling ledger of the .odd/ memory, written "
            f"only by {LEDGER_SCRIPT} (AGENTS.md's append-only rule) - run the "
            "script to record a decision or a classification, never edit the file."
        )
    if path.is_dir():
        what = "holds stored reports"
    elif path.exists():
        what = "is a stored report"
    else:
        what = "names stored reports"
    return (
        f"odd-guards: {shown} {what} of the .odd/ memory, never modified or "
        "deleted once committed (AGENTS.md's append-only rule) - a new run "
        "writes a new file, and the diff lives there."
    )


def _refused(path: Path, shape: str) -> bool:
    """Whether a write or removal under a report store is refused: a removal
    of anything but a file the hook can see and HEAD does not hold, a write
    onto a file HEAD holds."""
    if shape == REMOVE:
        return not path.exists() or committed(path) is True
    return path.is_file() and committed(path) is True


def decide(payload: object, process_cwd: str) -> tuple[int, list[str]]:
    """Return (exit code, stderr lines) for the payload."""
    targets = _targets(payload)
    if not targets:
        return PASS, []
    base = Path(os.path.normpath(payload_cwd(payload) or process_cwd))
    lines: list[str] = []
    named: set[Path] = set()
    for candidate, shape in targets:
        for path in _expand(_resolve(candidate, base), shape):
            kind = classify(path)
            if kind is None or path in named:
                continue
            if kind == "report" and not _refused(path, shape):
                continue
            named.add(path)
            lines.append(_message(kind, path, _display_path(path, base)))
    return (BLOCK, lines) if lines else (PASS, [])


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except (ValueError, OSError):
        return PASS
    try:
        code, lines = decide(payload, os.getcwd())
    except Exception as error:  # noqa: BLE001 - fail open, never break the host
        print(f"odd-guards: skipped ({error.__class__.__name__})", file=sys.stderr)
        return PASS
    for line in lines:
        print(line, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
