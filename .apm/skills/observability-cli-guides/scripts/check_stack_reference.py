#!/usr/bin/env python3
"""Check stack reference files against the reference contract.

The contract (references/CONTRACT.md, next to this script's directory)
lists, in its first fenced block, the headings every stack file must
carry: ``##`` sections, each followed by the ``###`` subsections it must
contain. This script reads that block - the contract is the list - and
checks the files it is given. Order is free; a missing heading, or a
subsection found under another section, fails the check. The
contract's "linked, not remembered" rule is checked too: ``## Query by
signal`` carries at least one link - to the backend's documentation, or
to the file it routes to.

Two callers, one checker:

- no argument: every built-in reference under references/ except
  builtin-stacks.md and the contract itself (what CI runs on every
  pull request);
- ``--declaration <stack>``: a custom stack (issues #228, #525) - a
  **directory**, ``.odd/observability-stacks/<name>/``, holding
  ``guide.md`` (the reference: frontmatter plus the contract's
  sections) and ``scripts/`` (the query scripts the guide names). The
  guide's headings are checked the same way, every script
  ``## Query by signal`` names as ``scripts/<file>.py`` must exist
  under ``scripts/`` and compile, and every ``.py`` there must compile;
  the frontmatter declaration is printed as the ``odd_config_set``
  payload that switches to the stack, ``{"stack": "<name>", "custom":
  {"<name>": {"stack_config_fields": [...]}}}``, to pass as the tool's
  ``config`` argument verbatim (any other frontmatter key belongs to
  the guide and is not forwarded). The stack name must be the
  directory's name - the name is how the stack is found. A plain file
  is accepted too, checked as a guide on its own (a copy an agent
  fetched somewhere): its name is then the stack's when the file is a
  ``guide.md`` inside a directory of that name, else the file's stem.

A custom stack may **link** its guide instead of carrying it (issue
#323): ``guide.md`` carries the frontmatter only, naming the guide -
``source_url`` (a URL the guide is fetched from as-is: the guide
alone, no scripts) or ``source_repo`` + ``source_path`` (+ optional
``source_ref``: a git repository the user can clone, and the stack's
directory in it - ``guide.md`` and ``scripts/`` come whole; a path to
a file brings the guide alone) - and its body stays empty.
``--declaration`` then fetches the stack into ``--fetch-dir <dir>``
as ``<dir>/<name>/`` (a temporary directory when the option is
absent), checks the fetched copy - headings and scripts - and prints
the same payload; the fetched copy is what the skills read, never
committed.

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
GUIDE = "guide.md"
SCRIPTS = "scripts"
SCRIPT_RE = re.compile(r"scripts/([A-Za-z0-9_.-]+\.py)")


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


LINKED_SECTION = "Query by signal"
LINK_RE = re.compile(r"\]\((https?://|[^)\s]+\.md)")


def section_text(body: str, section: str) -> str | None:
    """The lines under ``## <section>`` up to the next ``##``, None if absent."""
    lines = body.splitlines()
    start = None
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match and match.group(1) == "##":
            if start is not None:
                return "\n".join(lines[start:index])
            if match.group(2) == section:
                start = index + 1
    return "\n".join(lines[start:]) if start is not None else None


def check_links(body: str) -> list[str]:
    """The query section links its commands' documentation or its route."""
    text = section_text(body, LINKED_SECTION)
    if text is not None and not LINK_RE.search(text):
        return [
            (
                f"`## {LINKED_SECTION}` links nothing: every command traces to the "
                "backend's documentation (or the section routes to another file)"
            )
        ]
    return []


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
    return problems + check_links(body)


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
    clone = target.parent.parent / f".{target.parent.name}-repo"
    if clone.exists():
        shutil.rmtree(clone)
    command = ["git", "clone", "--quiet", "--depth", "1"]
    if source.get("source_ref"):
        command += ["--branch", source["source_ref"]]
    command += [source["source_repo"], str(clone)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return f"source_repo: cannot clone {source['source_repo']}: {result.stderr.strip()}"
    linked = clone / source["source_path"]
    if linked.is_dir():
        # the stack's directory: the guide and its scripts come whole
        if not (linked / GUIDE).is_file():
            return (
                f"source_path: {source['source_path']} of {source['source_repo']} "
                f"carries no {GUIDE}"
            )
        scripts = linked / SCRIPTS
        if scripts.is_dir():
            if (target.parent / SCRIPTS).exists():
                shutil.rmtree(target.parent / SCRIPTS)
            shutil.copytree(scripts, target.parent / SCRIPTS)
        target.write_bytes((linked / GUIDE).read_bytes())
        return None
    if not linked.is_file():
        return (
            f"source_path: {source['source_path']} is neither a directory nor a "
            f"file of {source['source_repo']}"
        )
    target.write_bytes(linked.read_bytes())
    return None


def declaration_of(frontmatter: str | None, stem: str) -> tuple[dict | None, list[str]]:
    """The odd_config_set payload for the switch, or the problems that prevent one."""
    if frontmatter is None:
        return None, [
            "no frontmatter: a custom stack's guide opens with `---`, `stack: <name>`, `stack_config_fields: [...]`, `---`"
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
            f"frontmatter: `stack: {stack}` does not match the stack's name `{stem}` "
            "(the directory holding guide.md)"
        )
    elif stack in builtin_stacks():
        problems.append(
            f"frontmatter: `stack: {stack}` is a built-in stack, never a custom one"
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


def stack_name_of(path: Path) -> str:
    """The stack's name a path stands for: the directory's, or a guide.md's
    parent's, or a plain file's stem."""
    if path.is_dir():
        return path.name
    if path.name == GUIDE:
        return path.parent.name
    return path.stem


def check_scripts(directory: Path, body: str) -> list[str]:
    """Every script the query section names exists under scripts/ and
    compiles, and so does every other script there."""
    problems: list[str] = []
    text = section_text(body, LINKED_SECTION) or ""
    named = sorted(set(SCRIPT_RE.findall(text)))
    scripts = directory / SCRIPTS
    for name in named:
        if not (scripts / name).is_file():
            problems.append(
                f"`## {LINKED_SECTION}` names {SCRIPTS}/{name}, which is not a file of "
                f"{directory}/{SCRIPTS}/"
            )
    if scripts.is_dir():
        for entry in sorted(scripts.iterdir()):
            if entry.name == "__pycache__" or entry.name.startswith("."):
                continue  # a cache running or linting the scripts left; never shipped
            if entry.is_file() and entry.suffix == ".py":
                try:
                    compile(entry.read_text(encoding="utf-8"), str(entry), "exec")
                except (SyntaxError, ValueError, UnicodeDecodeError) as error:
                    problems.append(f"{SCRIPTS}/{entry.name} does not compile: {error}")
            else:
                problems.append(
                    f"{SCRIPTS}/ holds .py files only, got {entry.name}"
                    + ("/" if entry.is_dir() else "")
                )
    return problems


def check_custom(
    path: Path, required: dict[str, list[str]], declare: bool, fetch_dir: Path | None
) -> int:
    name = stack_name_of(path)
    guide = path / GUIDE if path.is_dir() else path
    display = str(path)
    try:
        text = guide.read_text(encoding="utf-8")
    except OSError as error:
        problems = [f"cannot read {guide}: {error.strerror}"]
        if path.is_dir() and not guide.exists():
            problems = [
                f"a custom stack is a directory holding {GUIDE}: {guide} is absent"
            ]
        report(display, problems)
        return 1
    frontmatter, body = split_frontmatter(text)
    values = frontmatter_values(frontmatter or "")
    source, problems = source_of(values)
    linked = any(key in values for key in SOURCE_KEYS)
    checked_dir: Path | None = path if path.is_dir() else None
    if source:
        # A linked guide: the body lives at the link, the local file is
        # the pointer - a body here would fork the guide silently, and
        # so would scripts beside the pointer.
        if body.strip():
            problems.append(
                "a linked stack carries no body: the guide is the linked one"
            )
        if path.is_dir() and (path / SCRIPTS).exists():
            problems.append(
                f"a linked stack carries no {SCRIPTS}/ of its own: they come with the link"
            )
        else:
            base = fetch_dir or Path(tempfile.mkdtemp(prefix="odd-stack-"))
            target = base / name / GUIDE
            failure = fetch_source(source, target)
            if failure:
                problems.append(failure)
            else:
                origin = source.get("source_url") or (
                    f"{source['source_repo']} {source['source_path']}"
                )
                print(f"fetched {origin} to {target.parent}", file=sys.stderr)
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
                    checked_dir = target.parent
    elif not linked:
        problems.extend(check_headings(body, required))
    # A malformed link (source problems, no source): the body check is
    # skipped - the file is a pointer by intent, and six missing-heading
    # lines would bury the real cause.
    if checked_dir is not None and not problems:
        problems.extend(check_scripts(checked_dir, body))
    declaration = None
    if declare:
        declaration, more = declaration_of(frontmatter, name)
        problems.extend(more)
    if problems:
        report(display, problems)
        return 1
    if declare:
        print(json.dumps(declaration))
    else:
        print(f"{path} follows the contract", file=sys.stderr)
    return 0


USAGE = """usage: check_stack_reference.py [--declaration] [--fetch-dir DIR] [STACK ...]

No STACK: check the built-in references against the contract (CI).
STACK ...: check those stacks - a directory holding guide.md and scripts/,
  or a guide file on its own - headings and scripts.
--declaration STACK: check one custom stack and print the odd_config_set
  payload that switches to it; a linked guide is fetched into --fetch-dir
  (a temporary directory when absent) as <name>/guide.md, its scripts
  beside it, and checked there.
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
        print("--declaration takes exactly one custom stack", file=sys.stderr)
        return 2
    if not paths:
        return check_builtin(required)
    failures = sum(check_custom(path, required, declare, fetch_dir) for path in paths)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
