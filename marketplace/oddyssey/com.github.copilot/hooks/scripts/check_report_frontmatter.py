"""Check a report just written under .odd/ against the memory contract.

Every stored report opens with the frontmatter its kind requires and
sits under a filename of the shape ``YYYY-MM-DD-HHmm-<run_name>.md``
(the ``verify-`` and ``remeasure-`` prefixes on a replay). The store is
append-only, so a malformed report is never repaired: it stays in the
history and the status flags it forever. This hook runs after a tool
wrote a file: when the file is a report under
``.odd/observe-run-reports/`` or ``.odd/otel-instrumentation-reports/``
it checks the filename shape, the required fields of the kind present
and non-empty, ``mode`` and ``depth`` among their values, ``window`` as
``<start>/<end>`` in UTC with the end after the start, ``date`` matching
the filename's date, ``run_name`` matching the filename's slug, and on
a ``verify`` or ``re-measure`` report a ``verifies`` naming a stored
report - and exits 2 with one stderr line per problem - file, problem,
never a line of the file - so the agent fixes the report before the
lone commit.

The checker is the one the ``get-status`` skill runs over the stored
history (``check_report`` in its ``odd_status.py``), copied here: a
hook script imports nothing outside itself, and a test runs both over
one fixture set so the two copies cannot drift. Two intended
differences: ``depth`` - the status reads a report without it as a
legacy file that predates the field; a report being written now has no
such excuse - and an unreadable file - the status lists it as a
violation (``unreadable: <error>``); the hook fails open on it, the
filename-shape problem included, since a file it cannot read is not a
report it can judge.

On most hosts a post-tool hook cannot undo the write: the message
reaches the model, and the rule in the persistence skills stays the
enforcement. It fails open on a payload it cannot read, a file outside
the two stores, and a file it cannot decode.

Standard library only; python3 >= 3.10. Invoked as
``python3 check_report_frontmatter.py PostToolUse`` by the hook entry in
``.apm/hooks/odd-guards.json``; apm rewrites the path per target.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BLOCK = 2
PASS = 0
MAX_LINES = 10

# The payload keys the hosts put a written file's path or a shell
# command under (Claude Code, Codex, Gemini, Cursor, Kiro: tool_input;
# Copilot CLI: toolArgs; Windsurf: tool_info).
FILE_PATHS = (
    ("tool_input", "file_path"),
    ("tool_input", "path"),
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
# Shell commands whose last positional argument is a destination.
COPYING_COMMANDS = {"cp", "mv", "install", "rsync"}
REDIRECTIONS = {">", ">>", ">|"}
PUNCTUATION = set("();<>|&")

# The two report stores, by the directory name under .odd/.
KINDS = {
    "observe-run-reports": "observation",
    "otel-instrumentation-reports": "instrumentation",
}
OBSERVATION_DIR = "observe-run-reports"
# A frontmatter error quotes the line it kept out; the message never does.
KEPT_OUT_RE = re.compile(r", kept out: .*$")


@dataclass(frozen=True)
class Finding:
    path: str
    problem: str


# --- the payload ----------------------------------------------------------------


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


def _segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(
        command.replace("\n", " ; "), posix=True, punctuation_chars=True
    )
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token and set(token) <= PUNCTUATION and token not in REDIRECTIONS:
            if segments[-1]:
                segments.append([])
            continue
        segments[-1].append(token)
    return [segment for segment in segments if segment]


def _command_write_targets(command: str) -> list[str]:
    """The .odd/ paths a shell line writes: redirections, tee, a copy's destination."""
    targets: list[str] = []
    for tokens in _segments(command):
        for index, token in enumerate(tokens):
            if token in REDIRECTIONS and index + 1 < len(tokens):
                targets.append(tokens[index + 1])
        arguments = [
            t for t in tokens[1:] if not t.startswith("-") and t not in REDIRECTIONS
        ]
        if tokens[0] == "tee":
            targets.extend(arguments)
        elif tokens[0] in COPYING_COMMANDS and len(arguments) >= 2:
            targets.append(arguments[-1])
    return [t for t in targets if "/.odd/" in t or t.startswith(".odd/")]


def written_paths(payload: object) -> list[str]:
    """The files the payload writes: a write tool's target, or a shell line's targets."""
    paths = _strings(payload, FILE_PATHS) if _is_write_tool(payload) else []
    for command in _strings(payload, COMMAND_PATHS):
        paths.extend(_command_write_targets(command))
    seen: set[str] = set()
    return [p for p in paths if not (p in seen or seen.add(p))]


def payload_cwd(payload: object) -> str | None:
    strings = _strings(payload, CWD_PATHS)
    return strings[0] if strings else None


def report_kind(path: Path) -> str | None:
    """The kind of report the path is, or None outside the two stores."""
    parts = path.parts
    if path.suffix != ".md" or len(parts) < 3 or parts[-3] != ".odd":
        return None
    return KINDS.get(parts[-2])


# --- frontmatter (copied from get-status's odd_status.py) ---------------------


def split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` outside quotes and outside nested brackets.

    A quote opens a quoted run only where a YAML scalar can start - at
    the beginning of an item or right after a mapping colon - so an
    apostrophe inside a bare word is just a character.
    """
    parts, buf, depth, quote = [], [], 0, None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"') and scalar_can_start(buf):
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf)
    if tail.strip() or parts:
        parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


def scalar_can_start(buf: list[str]) -> bool:
    before = "".join(buf).rstrip()
    return before == "" or before.endswith(":")


def parse_scalar(text: str) -> Any:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "~", ""):
        return None
    return text


def parse_value(text: str) -> Any:
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return [parse_value(item) for item in split_top_level(text[1:-1])]
    if text.startswith("{") and text.endswith("}"):
        mapping = {}
        for item in split_top_level(text[1:-1]):
            key, _, value = item.partition(":")
            mapping[parse_scalar(key)] = parse_value(value)
        return mapping
    return parse_scalar(text)


FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z_][\w.-]*):(.*)$")


def split_frontmatter(text: str) -> tuple[dict, str, list[str]]:
    """The frontmatter mapping, the body, and the lines it could not read.

    The contract writes flow style (``[a, b]``, ``{k: v}``) on one line,
    with wrapped continuations indented. A block-style value (``- item``
    lines, nested ``key: value`` lines) is outside the contract: it is
    reported and read as null rather than mangled into a string.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, ["no frontmatter block"]
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, text, ["unterminated frontmatter block"]
    raw: list[list[Any]] = []  # [key, value, block_style]
    errors: list[str] = []
    for number, line in enumerate(lines[1:end], start=2):
        if not line.strip():
            continue
        match = FRONTMATTER_LINE_RE.match(line)
        if match:
            raw.append([match.group(1), match.group(2), False])
        elif line[0].isspace() and raw:
            stripped = line.strip()
            block = stripped.startswith("- ") or stripped == "-" or ": " in stripped
            if block and not raw[-1][1].strip():
                raw[-1][2] = True
            else:
                raw[-1][1] = raw[-1][1] + " " + stripped
        else:
            errors.append(
                f"line {number}: no colon-separated key, kept out: {line.strip()!r}"
            )
    frontmatter = {}
    for key, value, block_style in raw:
        if block_style:
            errors.append(
                f"{key}: block-style value (the contract is flow style), read as null"
            )
            frontmatter[key] = None
        else:
            frontmatter[key] = parse_value(value)
    body = "\n".join(lines[end + 1 :])
    return frontmatter, body, errors


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def read_report(path: Path, kind: str) -> dict:
    """What the report says by itself: the shape get-status's parse_report builds."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"path": str(path), "kind": kind, "unreadable": str(exc)}
    frontmatter, _body, errors = split_frontmatter(text)
    return {
        "path": str(path),
        "kind": kind,
        "frontmatter": frontmatter,
        "frontmatter_errors": errors,
    }


# --- the memory invariant (copied from get-status's odd_status.py) -----------

REPORT_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-\d{4}-([a-z0-9][a-z0-9-]*)\.md$")
WINDOW_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$"
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
OBSERVATION_MODES_ALL = ("drive", "observe", "post-hoc", "verify", "re-measure")
REPLAY_MODES = ("verify", "re-measure")
DEPTHS = ("quick", "full")


def check_report(report: dict, stored_names: set[str], root: Path) -> list[str]:
    """What the report lacks against the memory contract's frontmatter.

    The one line that differs from get-status's copy: ``depth`` is
    required - a report written now does not predate the field.
    """
    problems: list[str] = []
    name = Path(report["path"]).name
    match = REPORT_NAME_RE.match(name)
    if not match:
        problems.append("filename is not YYYY-MM-DD-HHmm-<run_name>.md")
    if "unreadable" in report:
        # Verbatim-copy artifact: check_file never passes an unreadable
        # report here (it fails open); kept so the copy stays exact.
        problems.append(f"unreadable: {report['unreadable']}")
        return problems
    fm = report["frontmatter"]
    for error in report.get("frontmatter_errors", []):
        problems.append(f"frontmatter: {error}")
    if not fm:
        problems.append("frontmatter absent")
        return problems

    def scalar(key: str) -> str | None:
        value = fm.get(key)
        if value is None or value == "" or value == []:
            problems.append(f"{key} absent")
            return None
        return str(value)

    kind = report["kind"]
    required = (
        ("project", "stack", "run_name", "date")
        if kind == "instrumentation"
        else ("services", "stack", "environment", "mode", "window", "run_name", "date")
    )
    values = {key: scalar(key) for key in required}
    if kind == "observation":
        if fm.get("services") is not None and not as_list(fm.get("services")):
            problems.append("services empty")
        mode = values.get("mode")
        if mode is not None and mode not in OBSERVATION_MODES_ALL:
            problems.append(
                f"mode {mode!r} is not one of {list(OBSERVATION_MODES_ALL)}"
            )
        depth = fm.get("depth")
        if depth is None:
            problems.append("depth absent")
        elif str(depth) not in DEPTHS:
            problems.append(f"depth {str(depth)!r} is not one of {list(DEPTHS)}")
        window = values.get("window")
        if window is not None:
            wm = WINDOW_RE.match(window)
            if not wm:
                problems.append(
                    "window is not <start>/<end> in UTC (YYYY-MM-DDTHH:MM:SSZ)"
                )
            elif wm.group(2) < wm.group(1):
                problems.append("window end precedes its start")
        verifies = fm.get("verifies")
        if mode in REPLAY_MODES and not verifies:
            problems.append(f"verifies absent on a {mode} report")
        elif verifies:
            # A bare filename names a sibling observation report; an
            # instrumentation baseline is named by its repo-relative path
            # (the report reference: the value's shape says the directory).
            target = str(verifies)
            exists = (
                (root / target).is_file() if "/" in target else target in stored_names
            )
            if not exists:
                problems.append(f"verifies names no stored report: {target}")
    date = values.get("date")
    if date is not None and not DATE_RE.match(date):
        problems.append(f"date {date!r} is not YYYY-MM-DD")
    if match:
        if date is not None and DATE_RE.match(date) and date != match.group(1):
            problems.append(f"date {date} differs from the filename's {match.group(1)}")
        run_name = values.get("run_name")
        if run_name is not None:
            # A replay keeps the replayed report's run_name and prefixes
            # its filename (the report reference's filename rules).
            mode = fm.get("mode") if kind == "observation" else None
            prefix = {"verify": "verify-", "re-measure": "remeasure-"}.get(
                str(mode), ""
            )
            expected = f"{prefix}{run_name}"
            if match.group(2) != expected:
                with_prefix = f" with the {prefix} prefix" if prefix else ""
                problems.append(
                    f"filename slug {match.group(2)!r} is not {expected!r}"
                    f" (run_name {run_name!r}{with_prefix})"
                )
    return problems


# --- the decision ----------------------------------------------------------------


def check_file(path: Path) -> list[str] | None:
    """The report's problems; None when the file is out of scope or unreadable.

    The stored names a bare ``verifies`` resolves against are the
    observation reports beside the file, and the repository root a
    repo-relative one resolves from is the parent of ``.odd/`` - the
    same sets get-status builds, without git.
    """
    kind = report_kind(path)
    if kind is None:
        return None
    report = read_report(path, kind)
    if "unreadable" in report:
        return None
    observation_dir = path.parents[1] / OBSERVATION_DIR
    stored = (
        {p.name for p in observation_dir.glob("*.md")}
        if observation_dir.is_dir()
        else set()
    )
    return check_report(report, stored, path.parents[2])


def decide(payload: object, process_cwd: str) -> tuple[int, list[str]]:
    """Return (exit code, stderr lines) for the payload."""
    candidates = written_paths(payload)
    if not candidates:
        return PASS, []
    base = Path(payload_cwd(payload) or process_cwd)
    findings: list[Finding] = []
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if not path.is_absolute():
            path = base / path
        if not path.is_file():
            continue
        problems = check_file(path)
        if not problems:
            continue
        shown = _display_path(path, base)
        findings.extend(
            Finding(shown, KEPT_OUT_RE.sub("", problem)) for problem in problems
        )
    if not findings:
        return PASS, []
    header = (
        "odd-guards: a report under .odd/ does not follow the memory contract "
        "(docs/guide/reports.md: the filename shape, the frontmatter fields its "
        "kind requires and their values, the report a replay's verifies names) - "
        "fix the file before persisting or committing; the store is append-only, "
        "so nothing repairs it later and the status flags it on every run:"
    )
    lines = [header]
    lines.extend(f"  {f.path}: {f.problem}" for f in findings[:MAX_LINES])
    if len(findings) > MAX_LINES:
        lines.append(f"  ... {len(findings)} problems in total, {MAX_LINES} shown")
    return BLOCK, lines


def _display_path(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        pass
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


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
