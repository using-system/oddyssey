#!/usr/bin/env python3
"""Check stack reference files against the reference contract.

The contract (references/CONTRACT.md, next to this script's directory)
lists, in its first fenced block, the headings every stack file must
carry: ``##`` sections, each followed by the ``###`` subsections it must
contain. This script reads that block - the contract is the list - and
checks the files it is given. Order is free; a missing heading, or a
subsection found under another section, fails the check.

Two callers, one checker:

- no argument: every built-in reference under references/ except
  builtin-stacks.md and the contract itself (what CI runs on every
  pull request);
- ``--declaration <file>``: a custom stack file (issue #228) - its
  headings are checked the same way, and its frontmatter declaration is
  printed as the ``odd_config_set`` payload that switches to it,
  ``{"stack": "<name>", "custom": {"<name>": {"stack_config_fields":
  [...]}}}``, to pass as the tool's ``config`` argument verbatim (any
  other frontmatter key belongs to the file and is not forwarded). The
  stack name must be the file's stem - the name is how the file is
  found.

Problems go to stderr, one per line, prefixed by the file; the exit
code is 1 when any file breaks the contract. Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REFERENCES = Path(__file__).resolve().parent.parent / "references"
CONTRACT = REFERENCES / "CONTRACT.md"
NOT_A_STACK = {"CONTRACT.md", "builtin-stacks.md"}
HEADING_RE = re.compile(r"^(#{2,3}) (.+?)\s*$")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
FIELD_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def required_headings(contract: str) -> dict[str, list[str]]:
    """The contract's block as {section: [subsections]}, in the block's order."""
    match = re.search(r"```text\n(.*?)```", contract, re.DOTALL)
    if not match:
        sys.exit("CONTRACT.md carries no ```text block listing the headings")
    required: dict[str, list[str]] = {}
    section = None
    for line in match.group(1).splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            required[section] = []
        elif line.startswith("### ") and section:
            required[section].append(line[4:].strip())
    return required


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """(frontmatter block, body) - the block is None when the file has none."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text
    return text[4:end], text[end + 5 :]


def sections_of(text: str) -> dict[str, list[str]]:
    """The file's ``##`` headings with the ``###`` under each, fences skipped."""
    found: dict[str, list[str]] = {}
    section = None
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        level, title = match.groups()
        if level == "##":
            section = title
            found.setdefault(section, [])
        elif section is not None:
            found[section].append(title)
    return found


def check_headings(body: str, required: dict[str, list[str]]) -> list[str]:
    found = sections_of(body)
    problems = []
    for section, subsections in required.items():
        if section not in found:
            problems.append(f"missing `## {section}`")
            continue
        for subsection in subsections:
            if subsection not in found[section]:
                problems.append(f"missing `### {subsection}` under `## {section}`")
    return problems


def _parse_fields(value: str, following: list[str]) -> list | None:
    """A YAML list, flow (``[a, b]``) or block (``- a`` lines); None if neither."""
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [item.strip().strip("'\"") for item in inner.split(",")] if inner else []
    if value:
        return None
    items = []
    for line in following:
        stripped = line.strip()
        if not stripped.startswith("- "):
            break
        items.append(stripped[2:].strip().strip("'\""))
    return items


def declaration_of(frontmatter: str | None, stem: str) -> tuple[dict | None, list[str]]:
    """The odd_config_set payload for the switch, or the problems that prevent one."""
    if frontmatter is None:
        return None, [
            "no frontmatter: a custom stack file opens with `---`, `stack: <name>`, `stack_config_fields: [...]`, `---`"
        ]
    lines = frontmatter.splitlines()
    stack = None
    fields: list | None = None
    seen_fields = False
    for index, line in enumerate(lines):
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$", line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if key == "stack":
            stack = value.strip().strip("'\"")
        elif key == "stack_config_fields":
            seen_fields = True
            fields = _parse_fields(value, lines[index + 1 :])
    problems = []
    if stack is None:
        problems.append("frontmatter: missing `stack: <name>`")
    elif not NAME_RE.fullmatch(stack):
        problems.append(
            f"frontmatter: `stack` must be a kebab-case name, got {stack!r}"
        )
    elif stack != stem:
        problems.append(
            f"frontmatter: `stack: {stack}` does not match the file name `{stem}.md`"
        )
    if not seen_fields:
        problems.append(
            "frontmatter: missing `stack_config_fields: [...]` (an empty list when the stack persists nothing)"
        )
    elif fields is None:
        problems.append("frontmatter: `stack_config_fields` must be a list")
    else:
        bad = [f for f in fields if not FIELD_RE.fullmatch(f)]
        if bad:
            problems.append(
                f"frontmatter: `stack_config_fields` must be snake_case names, got {bad!r}"
            )
        if len(set(fields)) != len(fields):
            problems.append("frontmatter: `stack_config_fields` carries a duplicate")
    if problems:
        return None, problems
    return {"stack": stack, "custom": {stack: {"stack_config_fields": fields}}}, []


def report(path: Path, display: str, problems: list[str]) -> None:
    print(f"{display}:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)


def check_builtin(required: dict[str, list[str]]) -> int:
    files = sorted(p for p in REFERENCES.glob("*.md") if p.name not in NOT_A_STACK)
    failures = 0
    for path in files:
        _, body = split_frontmatter(path.read_text(encoding="utf-8"))
        problems = check_headings(body, required)
        if problems:
            failures += 1
            report(path, str(path.relative_to(REFERENCES.parent)), problems)
    if failures:
        print(
            f"{failures} of {len(files)} references break the contract", file=sys.stderr
        )
        return 1
    print(f"{len(files)} references follow the contract", file=sys.stderr)
    return 0


def check_custom(path: Path, required: dict[str, list[str]], declare: bool) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        report(path, str(path), [f"cannot read: {error.strerror}"])
        return 1
    frontmatter, body = split_frontmatter(text)
    problems = check_headings(body, required)
    declaration = None
    if declare:
        declaration, more = declaration_of(frontmatter, path.stem)
        problems.extend(more)
    if problems:
        report(path, str(path), problems)
        return 1
    if declare:
        print(json.dumps(declaration))
    else:
        print(f"{path} follows the contract", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    required = required_headings(CONTRACT.read_text(encoding="utf-8"))
    declare = "--declaration" in argv
    paths = [Path(a) for a in argv if a != "--declaration"]
    if declare and len(paths) != 1:
        print("--declaration takes exactly one custom stack file", file=sys.stderr)
        return 2
    if not paths:
        return check_builtin(required)
    failures = sum(check_custom(path, required, declare) for path in paths)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
