"""Flag real identifiers and home paths in a file just written under .odd/.

AGENTS.md's no-secrets rule keeps tokens, credentials and real
identifiers - subscription, tenant, workspace, resource-group names and
GUIDs, account or login names, home-directory paths - out of every
committed report; a live ``odd_config_get`` or CLI excerpt is the
likeliest place for one to slip in. This hook runs after a tool wrote a
file: when the file lies under ``.odd/`` it scans it for GUID-shaped
values, home-directory paths, and the identifiers the global
configuration's ``stack_config`` carries, and exits 2 with one stderr
line per finding - file, line, kind, never the value - so the agent
replaces them with an obviously fake placeholder before persisting.

An OpenTelemetry ``service.instance.id`` is a GUID by SDK default and
the observation report contract records it, so a GUID is evidence, not
an identifier, when the report declares it on the frontmatter
``instance:`` field, cites one of those declared ids in its body, or
writes it right after ``service.instance.id=`` (or the ``_`` and
``resource.`` spellings, ``=`` or ``:``, the key closing the previous
line when markdown wrapped the value). A ``stack_config`` value is
flagged whatever its context: a cloud identifier never becomes evidence
by standing next to ``instance:``.

On most hosts a post-tool hook cannot undo the write: the message
reaches the model, and the rule in the persistence skills stays the
enforcement. It fails open on anything it does not understand.

Standard library only; python3 >= 3.10. Invoked as
``python3 scan_odd_identifiers.py PostToolUse`` by the hook entry in
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

BLOCK = 2
PASS = 0
MAX_LINES = 10

CONFIG_PATH = Path.home() / ".oddyssey" / "config.json"

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
GUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
HOME_PATH_RE = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)([^\s/\\'\"`]+)")
# What precedes a GUID that names an OTel instance identity: the key
# with its separator on the same line, or the key closing the previous
# line when markdown wrapped the value onto the next one.
INSTANCE_KEY = r"(?<![\w.])(?:resource[._])?service[._]instance[._]id"
INSTANCE_KEY_RE = re.compile(INSTANCE_KEY + r"\s*[=:]\s*[\"'`]?$")
WRAPPED_KEY_RE = re.compile(INSTANCE_KEY + r"[`'\"*]*\s*[=:]?\s*[`'\"*]*\s*$")
WRAPPED_LEAD_RE = re.compile(r"^[\s`'\"*|-]*$")
FRONTMATTER_FENCE = "---"
INSTANCE_FIELD = "instance:"

# stack_config keys and stacks whose values identify nothing by
# themselves: a region names a datacenter, the local stack carries the
# container's environment.
NEUTRAL_KEYS = {"region"}
NEUTRAL_STACKS = {"local"}
PLACEHOLDERS = {"contoso", "example-user", "example", "placeholder"}
MIN_VALUE_LENGTH = 4


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str


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


def in_odd(path: Path) -> bool:
    """True when the path lies under a .odd/ directory."""
    return ".odd" in path.parts[:-1]


GENERIC_USERS = {
    "runner",
    "root",
    "ubuntu",
    "vscode",
    "codespace",
    "jenkins",
    "ci",
    "user",
}


def _is_placeholder_guid(value: str) -> bool:
    digits = value.replace("-", "").lower()
    return len(set(digits)) <= 2 or "12345678" in digits or "abcdef" in digits


def _is_personal_home_path(match: re.Match) -> bool:
    user = match.group(1)
    return not user.startswith("<") and user.lower() not in GENERIC_USERS


def forbidden_values(config: object) -> list[str]:
    """The stack_config values that identify a real tenant, account or resource."""
    if not isinstance(config, dict):
        return []
    stacks = config.get("stack_config")
    if not isinstance(stacks, dict):
        return []
    values: list[str] = []
    for stack, fields in stacks.items():
        if stack in NEUTRAL_STACKS or not isinstance(fields, dict):
            continue
        for key, value in fields.items():
            if key in NEUTRAL_KEYS or not isinstance(value, str):
                continue
            value = value.strip()
            if len(value) < MIN_VALUE_LENGTH or value.lower() in PLACEHOLDERS:
                continue
            if GUID_RE.fullmatch(value) and _is_placeholder_guid(value):
                continue
            values.append(value)
    return values


def load_config(path: Path = CONFIG_PATH) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _declared_instance_ids(lines: list[str]) -> tuple[set[int], set[str]]:
    """The frontmatter ``instance:`` field's line numbers and the GUIDs it holds."""
    numbers: set[int] = set()
    ids: set[str] = set()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return numbers, ids
    inside = False
    for number, line in enumerate(lines[1:], 2):
        if line.strip() == FRONTMATTER_FENCE:
            break
        if line.startswith(INSTANCE_FIELD):
            inside = True
        elif inside and not (line[:1].isspace() or line.startswith("-")):
            inside = False
        if inside:
            numbers.add(number)
            ids.update(m.group(0).lower() for m in GUID_RE.finditer(line))
    return numbers, ids


def _is_instance_id(
    line: str,
    match: re.Match,
    declared_here: bool,
    declared: set[str],
    previous: str,
) -> bool:
    """True when the report says this GUID is an OTel service.instance.id."""
    lead = line[: match.start()]
    return (
        declared_here
        or match.group(0).lower() in declared
        or INSTANCE_KEY_RE.search(lead) is not None
        or (
            WRAPPED_LEAD_RE.match(lead) is not None
            and WRAPPED_KEY_RE.search(previous) is not None
        )
    )


def scan_text(text: str, forbidden: list[str]) -> list[Finding]:
    """Return one finding per line and kind, never the matched value."""
    patterns = [
        re.compile(r"(?<![\w/.-])" + re.escape(value) + r"(?![\w-])")
        for value in forbidden
    ]
    lines = text.splitlines()
    instance_lines, instance_ids = _declared_instance_ids(lines)
    findings: list[Finding] = []
    for number, line in enumerate(lines, 1):
        kinds: list[str] = []
        previous = lines[number - 2] if number > 1 else ""
        if any(
            not _is_placeholder_guid(m.group(0))
            and not _is_instance_id(
                line, m, number in instance_lines, instance_ids, previous
            )
            for m in GUID_RE.finditer(line)
        ):
            kinds.append("GUID")
        if any(_is_personal_home_path(m) for m in HOME_PATH_RE.finditer(line)):
            kinds.append("home path")
        if any(pattern.search(line) for pattern in patterns):
            kinds.append("stack_config value")
        findings.extend(Finding("", number, kind) for kind in kinds)
    return findings


def decide(payload: object, process_cwd: str) -> tuple[int, list[str]]:
    """Return (exit code, stderr lines) for the payload."""
    candidates = written_paths(payload)
    if not candidates:
        return PASS, []
    base = Path(payload_cwd(payload) or process_cwd)
    forbidden: list[str] | None = None
    findings: list[Finding] = []
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if not path.is_absolute():
            path = base / path
        if not in_odd(path) or not path.is_file():
            continue
        if forbidden is None:
            forbidden = forbidden_values(load_config())
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        shown = _display_path(path, base)
        findings.extend(
            Finding(shown, f.line, f.kind) for f in scan_text(text, forbidden)
        )
    if not findings:
        return PASS, []
    header = (
        "odd-guards: a file under .odd/ carries what a committed report must "
        "never carry (AGENTS.md's no-secrets rule) - replace each value with an "
        "obviously fake placeholder (a zeroed or 1234-patterned GUID passes) "
        "before persisting or committing; a GUID that is an OTel "
        "service.instance.id is evidence and stays once the report says so "
        "(the frontmatter instance: field, or service.instance.id= before it), "
        "a cloud identifier does not:"
    )
    lines = [header]
    lines.extend(f"  {f.path}:{f.line}: {f.kind}" for f in findings[:MAX_LINES])
    if len(findings) > MAX_LINES:
        lines.append(f"  ... {len(findings)} findings in total, {MAX_LINES} shown")
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
