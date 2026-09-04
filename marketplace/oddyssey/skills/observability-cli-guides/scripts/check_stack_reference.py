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

A custom file may **link** its guide instead of carrying it (issue
#323): its frontmatter names the guide - ``source_url`` (a URL the
file is fetched from as-is) or ``source_repo`` + ``source_path`` (+
optional ``source_ref``: a git repository the user can clone, the
path in it) - and its body stays empty. ``--declaration`` then fetches
the guide into ``--fetch-dir <dir>`` (``<dir>/<name>.md``; a
temporary directory when the option is absent), checks the fetched
copy's headings, and prints the same payload; the fetched copy is what
the skills read, never committed.

Problems go to stderr, one per line, prefixed by the file; the exit
code is 1 when any file breaks the contract. Standard library only.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REFERENCES = Path(__file__).resolve().parent.parent / "references"
CONTRACT = REFERENCES / "CONTRACT.md"
BUILTIN_STACKS = REFERENCES / "builtin-stacks.md"
NOT_A_STACK = {"CONTRACT.md", "builtin-stacks.md"}
COMMENT_RE = re.compile(r"\s+#.*$")
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


def builtin_stacks() -> set[str]:
    """The STACKS values builtin-stacks.md lists (a server test pins the two)."""
    return set(
        re.findall(r"^\| `([a-z-]+)` \| \[", BUILTIN_STACKS.read_text(), re.MULTILINE)
    )


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
    """A YAML list, flow (``[a, b]``) or block (``- a`` lines); None if neither.

    An empty scalar with no block items is None too: "persists nothing"
    is written ``[]``, a bare key is a file that forgot to fill it in.
    """
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [item.strip().strip("'\"") for item in inner.split(",")] if inner else []
    if value:
        return None
    items = []
    for line in following:
        stripped = COMMENT_RE.sub("", line.strip())
        if not stripped.startswith("- "):
            break
        items.append(stripped[2:].strip().strip("'\""))
    return items or None


SOURCE_KEYS = ("source_url", "source_repo", "source_path", "source_ref")


def frontmatter_values(frontmatter: str) -> dict[str, tuple[str, list[str]]]:
    """Top-level ``key: value`` lines, comments stripped, with the lines after each."""
    lines = frontmatter.splitlines()
    values: dict[str, tuple[str, list[str]]] = {}
    for index, line in enumerate(lines):
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$", line)
        if match:
            key, value = match.group(1), COMMENT_RE.sub("", match.group(2))
            values[key] = (value.strip().strip("'\""), lines[index + 1 :])
    return values


def source_of(values: dict) -> tuple[dict | None, list[str]]:
    """The linked guide's coordinates, None when the file carries its own body."""
    present = {k: values[k][0] for k in SOURCE_KEYS if k in values}
    if not present:
        return None, []
    problems = []
    if "source_url" in present and (
        "source_repo" in present or "source_path" in present
    ):
        problems.append(
            "frontmatter: `source_url` and `source_repo`/`source_path` exclude each other"
        )
    if "source_repo" in present and not present.get("source_path"):
        problems.append(
            "frontmatter: `source_repo` needs `source_path` (the guide's path in the repository)"
        )
    if "source_path" in present and not present.get("source_repo"):
        problems.append("frontmatter: `source_path` needs `source_repo`")
    if "source_url" in present and not present["source_url"]:
        problems.append("frontmatter: `source_url` is empty")
    return (present if not problems else None), problems


def fetch_source(source: dict, target: Path) -> str | None:
    """Fetch the linked guide to ``target``; the problem when it cannot be."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if "source_url" in source:
        try:
            with urllib.request.urlopen(source["source_url"], timeout=30) as response:
                target.write_bytes(response.read())
        except Exception as error:  # noqa: BLE001
            return f"source_url: cannot fetch {source['source_url']}: {error}"
        return None
    clone = target.parent / f".{target.stem}-repo"
    if clone.exists():
        shutil.rmtree(clone)
    command = ["git", "clone", "--quiet", "--depth", "1"]
    if source.get("source_ref"):
        command += ["--branch", source["source_ref"]]
    command += [source["source_repo"], str(clone)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return f"source_repo: cannot clone {source['source_repo']}: {result.stderr.strip()}"
    guide = clone / source["source_path"]
    if not guide.is_file():
        return f"source_path: {source['source_path']} is not a file of {source['source_repo']}"
    target.write_bytes(guide.read_bytes())
    return None


def declaration_of(frontmatter: str | None, stem: str) -> tuple[dict | None, list[str]]:
    """The odd_config_set payload for the switch, or the problems that prevent one."""
    if frontmatter is None:
        return None, [
            "no frontmatter: a custom stack file opens with `---`, `stack: <name>`, `stack_config_fields: [...]`, `---`"
        ]
    values = frontmatter_values(frontmatter)
    stack = values["stack"][0] if "stack" in values else None
    fields: list | None = None
    seen_fields = "stack_config_fields" in values
    if seen_fields:
        fields = _parse_fields(*values["stack_config_fields"])
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
    elif stack in builtin_stacks():
        problems.append(
            f"frontmatter: `stack: {stack}` is a built-in stack, never a custom file"
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


def report(display: str, problems: list[str]) -> None:
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
            report(str(path.relative_to(REFERENCES.parent)), problems)
    if failures:
        print(
            f"{failures} of {len(files)} references break the contract", file=sys.stderr
        )
        return 1
    print(f"{len(files)} references follow the contract", file=sys.stderr)
    return 0


def check_custom(
    path: Path, required: dict[str, list[str]], declare: bool, fetch_dir: Path | None
) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        report(str(path), [f"cannot read: {error.strerror}"])
        return 1
    frontmatter, body = split_frontmatter(text)
    values = frontmatter_values(frontmatter or "")
    source, problems = source_of(values)
    linked = any(key in values for key in SOURCE_KEYS)
    if source:
        # A linked guide: the body lives at the link, the local file is
        # the pointer - a body here would fork the guide silently.
        if body.strip():
            problems.append(
                "a linked stack file carries no body: the guide is the linked file"
            )
        else:
            target = (
                fetch_dir or Path(tempfile.mkdtemp(prefix="odd-stack-"))
            ) / f"{path.stem}.md"
            failure = fetch_source(source, target)
            if failure:
                problems.append(failure)
            else:
                origin = source.get("source_url") or (
                    f"{source['source_repo']} {source['source_path']}"
                )
                print(f"fetched {origin} to {target}", file=sys.stderr)
                guide_front, body = split_frontmatter(
                    target.read_text(encoding="utf-8")
                )
                if any(
                    key in frontmatter_values(guide_front or "") for key in SOURCE_KEYS
                ):
                    problems.append(
                        "the linked guide is itself a link: link the guide, not a pointer"
                    )
                else:
                    problems.extend(check_headings(body, required))
    elif not linked:
        problems.extend(check_headings(body, required))
    # A malformed link (source problems, no source): the body check is
    # skipped - the file is a pointer by intent, and six missing-heading
    # lines would bury the real cause.
    declaration = None
    if declare:
        declaration, more = declaration_of(frontmatter, path.stem)
        problems.extend(more)
    if problems:
        report(str(path), problems)
        return 1
    if declare:
        print(json.dumps(declaration))
    else:
        print(f"{path} follows the contract", file=sys.stderr)
    return 0


USAGE = """usage: check_stack_reference.py [--declaration] [--fetch-dir DIR] [FILE ...]

No FILE: check the built-in references against the contract (CI).
FILE ...: check those files' headings.
--declaration FILE: check one custom stack file and print the odd_config_set
  payload that switches to it; a linked guide is fetched into --fetch-dir
  (a temporary directory when absent) as <name>.md and checked there.
"""


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(USAGE, end="")
        return 0
    required = required_headings(CONTRACT.read_text(encoding="utf-8"))
    declare = "--declaration" in argv
    fetch_dir: Path | None = None
    rest: list[str] = []
    skip = False
    for index, arg in enumerate(argv):
        if skip:
            skip = False
            continue
        if arg == "--fetch-dir":
            if index + 1 >= len(argv):
                print("--fetch-dir takes a directory", file=sys.stderr)
                return 2
            fetch_dir = Path(argv[index + 1])
            skip = True
        elif arg != "--declaration":
            rest.append(arg)
    paths = [Path(a) for a in rest]
    if declare and len(paths) != 1:
        print("--declaration takes exactly one custom stack file", file=sys.stderr)
        return 2
    if not paths:
        return check_builtin(required)
    failures = sum(check_custom(path, required, declare, fetch_dir) for path in paths)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
