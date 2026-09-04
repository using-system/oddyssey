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

ODD_IN_COMMAND_RE = re.compile(r"(?<![\w./-])((?:[\w./~-]*/)?\.odd/[\w./-]+)")
GUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
HOME_PATH_RE = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)[^\s/\\'\"`]+")

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


def written_paths(payload: object) -> list[str]:
    """Return the file paths the payload names: a file tool's target, or the .odd/ paths a shell command mentions."""
    paths = _strings(payload, FILE_PATHS)
    for command in _strings(payload, COMMAND_PATHS):
        paths.extend(match.group(1) for match in ODD_IN_COMMAND_RE.finditer(command))
    seen: set[str] = set()
    return [p for p in paths if not (p in seen or seen.add(p))]


def payload_cwd(payload: object) -> str | None:
    strings = _strings(payload, CWD_PATHS)
    return strings[0] if strings else None


def in_odd(path: Path) -> bool:
    """True when the path lies under a .odd/ directory."""
    return ".odd" in path.parts[:-1]


def _is_placeholder_guid(value: str) -> bool:
    return len(set(value.replace("-", "").lower())) <= 2


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


def scan_text(text: str, forbidden: list[str]) -> list[Finding]:
    """Return one finding per line and kind, never the matched value."""
    patterns = [
        re.compile(r"(?<![\w/.-])" + re.escape(value) + r"(?![\w-])")
        for value in forbidden
    ]
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), 1):
        kinds: list[str] = []
        if any(not _is_placeholder_guid(m.group(0)) for m in GUID_RE.finditer(line)):
            kinds.append("GUID")
        if HOME_PATH_RE.search(line):
            kinds.append("home path")
        if any(pattern.search(line) for pattern in patterns):
            kinds.append("stack_config value")
        findings.extend(Finding("", number, kind) for kind in kinds)
    return findings


def decide(payload: object, process_cwd: str) -> tuple[int, list[str]]:
    """Return (exit code, stderr lines) for the payload."""
    if isinstance(payload, dict) and payload.get("tool_name") == "Read":
        return PASS, []
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
        "obviously fake placeholder before persisting or committing; a GUID that "
        "is an OTel service.instance.id is evidence and stays, a cloud identifier "
        "does not:"
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
