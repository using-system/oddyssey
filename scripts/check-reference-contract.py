#!/usr/bin/env python3
"""Check every stack reference against the reference contract.

The contract (.apm/skills/observability-cli-guides/references/CONTRACT.md)
lists, in its first fenced block, the headings every stack file must
carry: ``##`` sections, each followed by the ``###`` subsections it must
contain. This script reads that block - the contract is the list - and
checks each reference under references/ except builtin-stacks.md and the
contract itself. Order is free; a missing heading, or a subsection found
under another section, fails the check. Run by ci-apm on every pull
request; standard library only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REFERENCES = (
    Path(__file__).resolve().parents[1]
    / ".apm/skills/observability-cli-guides/references"
)
CONTRACT = REFERENCES / "CONTRACT.md"
NOT_A_STACK = {"CONTRACT.md", "builtin-stacks.md"}
HEADING_RE = re.compile(r"^(#{2,3}) (.+?)\s*$")


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


def check(path: Path, required: dict[str, list[str]]) -> list[str]:
    found = sections_of(path.read_text(encoding="utf-8"))
    problems = []
    for section, subsections in required.items():
        if section not in found:
            problems.append(f"missing `## {section}`")
            continue
        for subsection in subsections:
            if subsection not in found[section]:
                problems.append(f"missing `### {subsection}` under `## {section}`")
    return problems


def main() -> int:
    required = required_headings(CONTRACT.read_text(encoding="utf-8"))
    failures = 0
    for path in sorted(REFERENCES.glob("*.md")):
        if path.name in NOT_A_STACK:
            continue
        problems = check(path, required)
        if problems:
            failures += 1
            print(f"{path.relative_to(REFERENCES.parents[3])}:")
            for problem in problems:
                print(f"  {problem}")
    checked = len([p for p in REFERENCES.glob("*.md") if p.name not in NOT_A_STACK])
    if failures:
        print(f"{failures} of {checked} references break the contract")
        return 1
    print(f"{checked} references follow the contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
