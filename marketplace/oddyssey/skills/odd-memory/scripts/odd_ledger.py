#!/usr/bin/env python3
"""Write the maintainer-ruling ledgers of the ODD memory, validated first.

The finding ledger ``.odd/decisions.md`` and the entry-classification
ledger ``.odd/entry-classifications.md`` are append-only evidence: a
row names what was ruled on - a stored report's finding, or a top-level
tree entry - the ruling, a rationale, and the day it was taken. This
script is the ledgers' only writer - it checks every rule the
odd-memory ``decisions`` reference states before one row lands, and
never touches the rows above. The commit stays the agent's: the script
prints the work branch and the commit subject the reference mandates,
and writes the file alone.

Standard library and git only; it imports no other skill's script.
Refusals are one stderr line and exit 2; nothing is written then.

    python3 odd_ledger.py [--repo PATH] resolve <ID> [--service S ...] [--stack S] [--env E]
    python3 odd_ledger.py [--repo PATH] decide <report>/<ID> <verdict> --rationale TEXT [--today YYYY-MM-DD]
    python3 odd_ledger.py [--repo PATH] reopen <report>/<ID> --rationale TEXT [--today YYYY-MM-DD]
    python3 odd_ledger.py [--repo PATH] classify <entry> runtime|non-runtime --rationale TEXT [--today YYYY-MM-DD]

``resolve`` prints ``<report> / <ID>\\t<title>`` per stored report that
carries the ID, newest first: exit 0 for one, 3 for several (ask, never
guess), 2 for none.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NoReturn

OBSERVATION_DIR = ".odd/observe-run-reports"
LEDGER_PATH = ".odd/decisions.md"
CLASSIFICATIONS_PATH = ".odd/entry-classifications.md"
CLASSES = ("runtime", "non-runtime")
CONFIG_PATH = Path.home() / ".oddyssey" / "config.json"

SKELETON = """\
# ODD finding decisions

Decisions the maintainer took on findings recorded in
`.odd/observe-run-reports/` — the committed memory that lets
`/odd-status` stop rendering a declined finding as open. Rows are
appended, never rewritten; a later row for the same finding supersedes
the earlier one. Reports themselves are never edited — this ledger is
the only place a decision lives.

| Date | Finding | Verdict | Rationale |
|---|---|---|---|
"""

CLASSIFICATIONS_SKELETON = """\
# ODD entry classifications

Rulings the maintainer took on the repository's top-level tree entries
— whether a change under one can alter the observed services' runtime
behavior — the committed memory that lets `/odd-status` settle a
report's code boundary without asking again. Rows are appended, never
rewritten; a later row for the same entry supersedes the earlier one.
A flag given to the status script overrides a row for one run and
persists nothing.

| Date | Entry | Class | Rationale |
|---|---|---|---|
"""

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# the section and table shapes exactly as get-status reads a report, so the
# ledger never accepts a row the memory invariant would flag at status time
SECTION_RE = re.compile(r"^##\s+(\d+)\.\s*(.*?)\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")
# the shapes the .odd/ identifier scan refuses, with its exemptions - a
# rationale is memory too, and a command is not a file-tool write the hook sees
GUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
HOME_PATH_RE = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)([^\s/\\'\"`]+)")
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
NEUTRAL_KEYS = {"region"}
NEUTRAL_STACKS = {"local"}
PLACEHOLDERS = {"contoso", "example-user", "example", "placeholder"}
MIN_VALUE_LENGTH = 4


class Refusal(Exception):
    """One reason, one stderr line, exit 2, nothing written."""


# --- git and files -------------------------------------------------------------------


def git_root(path: Path) -> Path:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise Refusal(f"git is not available: {exc}") from exc
    if proc.returncode != 0:
        raise Refusal(f"not a git repository: {path.resolve()}")
    return Path(proc.stdout.strip())


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refusal(f"cannot read {path.name}: {exc}") from exc


# --- the report's findings, read exactly as get-status reads them --------------------


def split_cells(line: str) -> list[str]:
    cells = [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", line)]
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return cells


def is_separator_row(line: str) -> bool:
    cells = split_cells(line)
    return bool(cells) and all(TABLE_SEPARATOR_RE.match(c) for c in cells)


def extract_tables(lines: list[str]) -> tuple[list[list[str]], list[str]]:
    """The rows of the markdown tables in ``lines`` (headers excluded) and the
    lines that are not tables - a pipe block without a separator line is prose."""
    rows: list[list[str]] = []
    rest: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            if len(block) >= 2 and is_separator_row(block[1]):
                rows.extend(split_cells(r) for r in block[2:])
            else:
                rest.extend(block)
            continue
        rest.append(lines[i])
        i += 1
    return rows, rest


def section_3(text: str) -> tuple[list[list[str]], str]:
    """Section 3's table rows (as cells) and its prose, tables excluded - every
    ``## 3.`` section as get-status numbers them: the rows of all of them, the
    prose of the last one, exactly as its finding_ids reads a report."""
    rows: list[list[str]] = []
    prose: list[str] = []
    buffer: list[str] = []
    inside = False

    def close() -> None:
        nonlocal prose
        if inside:
            block_rows, block_prose = extract_tables(buffer)
            rows.extend(block_rows)
            prose = block_prose

    for line in text.splitlines():
        if line.startswith("## "):
            close()
            match = SECTION_RE.match(line)
            inside = bool(match) and int(match.group(1)) == 3
            buffer = []
        elif inside:
            buffer.append(line)
    close()
    return rows, "\n".join(prose)


def row_id(cells: list[str]) -> str:
    return cells[0].split()[0].strip("*`") if cells and cells[0].strip() else ""


def finding_in_report(text: str, finding_id: str) -> bool:
    """The ID is a first cell of a section 3 table row, or a word of its prose -
    the same two checks get-status's invariant applies to a ledger row."""
    rows, prose = section_3(text)
    if any(row_id(cells) == finding_id for cells in rows):
        return True
    return bool(re.search(rf"\b{re.escape(finding_id)}\b", prose))


def finding_title(text: str, finding_id: str) -> str:
    rows, _ = section_3(text)
    for cells in rows:
        if row_id(cells) == finding_id:
            return cells[1] if len(cells) > 1 else ""
    return "(named in section 3 prose)"


# --- the frontmatter, read without parsing prose -------------------------------------


def frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def as_list(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [v.strip().strip("'\"") for v in value.split(",") if v.strip()]


# --- the rules, as code --------------------------------------------------------------


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def branch_name(finding_id: str, verdict: str) -> str:
    return f"docs/odd-finding-decision-{normalize(finding_id)}-{normalize(verdict)}"


def classification_branch_name(entry: str, klass: str) -> str:
    return f"docs/odd-entry-classification-{normalize(entry)}-{normalize(klass)}"


def top_level_entries(root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise Refusal(f"git is not available: {exc}") from exc
    if proc.returncode != 0:
        raise Refusal("the repository has no HEAD commit to classify entries of")
    return proc.stdout.splitlines()


def check_entry(root: Path, text: str) -> str:
    entry = text.strip().strip("/")
    if entry == ".odd":
        raise Refusal("the tree anchor always ignores .odd - nothing to classify")
    entries = top_level_entries(root)
    if entry not in entries:
        raise Refusal(
            f"{text.strip()!r} is not a top-level entry of HEAD (git ls-tree HEAD "
            "names them)"
        )
    return entry


def check_class(text: str) -> str:
    klass = text.strip().lower()
    if klass not in CLASSES:
        raise Refusal("the class is runtime or non-runtime")
    return klass


def parse_key(text: str) -> tuple[str, str]:
    """``<report>/<ID>`` or ``<report> / <ID>``, the report a name or a path."""
    ref = text.strip().replace(" / ", "/")
    report, sep, finding_id = ref.rpartition("/")
    name = Path(report.strip()).name
    finding_id = finding_id.strip()
    if not sep or not name.endswith(".md") or not finding_id:
        raise Refusal(f"finding {text!r} is not <report>/<ID>")
    return name, finding_id


def _is_placeholder_guid(value: str) -> bool:
    digits = value.replace("-", "").lower()
    return len(set(digits)) <= 2 or "12345678" in digits or "abcdef" in digits


def _is_personal_home_path(match: re.Match) -> bool:
    user = match.group(1)
    return not user.startswith("<") and user.lower() not in GENERIC_USERS


def forbidden_values(config: object) -> list[str]:
    """The stack_config values that identify a real tenant, account or resource
    - the global configuration's, read the way the identifier scan reads it."""
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


def load_config(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # no configuration is no identifier to protect: fail open


def check_rationale(text: str, forbidden: list[str] | tuple[str, ...] = ()) -> str:
    rationale = text.strip()
    if not rationale:
        raise Refusal("a rationale is required: one sentence saying why")
    if "\n" in rationale:
        raise Refusal("the rationale is one line")
    if "|" in rationale:
        raise Refusal("the rationale carries no '|' (a table cell)")
    if any(not _is_placeholder_guid(m.group(0)) for m in GUID_RE.finditer(rationale)):
        raise Refusal("the rationale carries an identifier (GUID) - use a placeholder")
    if any(_is_personal_home_path(m) for m in HOME_PATH_RE.finditer(rationale)):
        raise Refusal("the rationale carries a home-directory path - use a placeholder")
    for value in forbidden:
        if re.search(r"(?<![\w/.-])" + re.escape(value) + r"(?![\w-])", rationale):
            raise Refusal(
                "the rationale carries a value of the global configuration's "
                "stack_config - use a placeholder"
            )
    return rationale


def check_verdict(text: str) -> str:
    verdict = text.strip()
    if not verdict or len(verdict.split()) != 1 or "|" in verdict:
        raise Refusal("the verdict is one word (wontfix, accepted-by-design, ...)")
    if verdict.lower() == "open":
        raise Refusal("the verdict 'open' is a reversal: use reopen")
    return verdict


def check_date(text: str | None) -> str:
    if text is None:
        return utc_today()
    if not DATE_RE.match(text):
        raise Refusal("--today is YYYY-MM-DD")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise Refusal(f"--today is not a date: {text}") from exc
    return text


def stored_report(root: Path, name: str) -> str:
    path = root / OBSERVATION_DIR / name
    if not path.is_file():
        raise Refusal(f"no stored report named {name} under {OBSERVATION_DIR}/")
    return read_text(path)


# --- the write ---------------------------------------------------------------------


def append_row(root: Path, rel: str, skeleton: str, row: str) -> str:
    path = root / rel
    current = read_text(path) if path.is_file() else ""
    if not current.strip():
        path.parent.mkdir(parents=True, exist_ok=True)
        current = skeleton
    elif not current.endswith("\n"):
        current += "\n"
    path.write_text(current + row + "\n", encoding="utf-8")
    return rel


def record(
    root: Path,
    key: str,
    verdict: str,
    rationale: str,
    today: str | None,
    config_path: Path = CONFIG_PATH,
) -> str:
    name, finding_id = parse_key(key)
    rationale = check_rationale(rationale, forbidden_values(load_config(config_path)))
    day = check_date(today)
    text = stored_report(root, name)
    if not finding_in_report(text, finding_id):
        raise Refusal(f"{name} carries no finding {finding_id}")
    row = f"| {day} | {name} / {finding_id} | {verdict} | {rationale} |"
    path = append_row(root, LEDGER_PATH, SKELETON, row)
    return "\n".join(
        [
            f"path: {path}",
            f"row: {row}",
            f"branch: {branch_name(finding_id, verdict)}",
            f"subject: docs(odd): finding decision {finding_id} {verdict}",
        ]
    )


def classify(
    root: Path,
    entry: str,
    klass: str,
    rationale: str,
    today: str | None,
    config_path: Path = CONFIG_PATH,
) -> str:
    klass = check_class(klass)
    rationale = check_rationale(rationale, forbidden_values(load_config(config_path)))
    day = check_date(today)
    entry = check_entry(root, entry)
    row = f"| {day} | {entry} | {klass} | {rationale} |"
    path = append_row(root, CLASSIFICATIONS_PATH, CLASSIFICATIONS_SKELETON, row)
    return "\n".join(
        [
            f"path: {path}",
            f"row: {row}",
            f"branch: {classification_branch_name(entry, klass)}",
            f"subject: docs(odd): entry classification {entry} {klass}",
        ]
    )


def resolve(
    root: Path,
    finding_id: str,
    services: list[str],
    stack: str | None,
    environment: str | None,
) -> tuple[list[str], int]:
    store = root / OBSERVATION_DIR
    matches: list[str] = []
    for path in sorted(store.glob("*.md"), reverse=True) if store.is_dir() else []:
        text = read_text(path)
        fm = frontmatter(text)
        if services and not set(services) & set(as_list(fm.get("services", ""))):
            continue
        if stack and fm.get("stack") != stack:
            continue
        if environment and fm.get("environment") != environment:
            continue
        if finding_in_report(text, finding_id):
            matches.append(
                f"{path.name} / {finding_id}\t{finding_title(text, finding_id)}"
            )
    if not matches:
        raise Refusal(f"no stored report carries {finding_id}")
    return matches, 0 if len(matches) == 1 else 3


# --- cli ---------------------------------------------------------------------------


class OneLineParser(argparse.ArgumentParser):
    """A usage error is a refusal like any other: one stderr line, exit 2."""

    def error(self, message: str) -> NoReturn:
        print(f"{self.prog}: {message} (see --help)", file=sys.stderr)
        sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    parser = OneLineParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="a path inside the repository (default: the working directory)",
    )
    parser.add_argument(
        "--config",
        default=str(CONFIG_PATH),
        help="the global configuration whose stack_config values a rationale must "
        "not carry (default: ~/.oddyssey/config.json; absent means nothing to protect)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("resolve", help="list the stored reports carrying a finding ID")
    p.add_argument("id")
    p.add_argument("--service", action="append", default=[], help="repeatable")
    p.add_argument("--stack")
    p.add_argument("--env")

    for name, doc in (
        ("decide", "append a decision on a finding"),
        ("reopen", "append the reversal of a decision (verdict open)"),
        ("classify", "append a runtime / non-runtime ruling on a top-level tree entry"),
    ):
        p = sub.add_parser(name, help=doc)
        if name == "classify":
            p.add_argument(
                "entry", help="a top-level entry of HEAD, as git ls-tree names it"
            )
            p.add_argument("klass", metavar="CLASS", help="runtime or non-runtime")
        else:
            p.add_argument("key", metavar="REPORT/ID")
        if name == "decide":
            p.add_argument("verdict")
        p.add_argument("--rationale", required=True)
        p.add_argument(
            "--today",
            help="the decision's date, YYYY-MM-DD, for a decision taken on an earlier "
            "day (default: today, UTC)",
        )

    args = parser.parse_args(argv)
    try:
        root = git_root(Path(args.repo))
        if args.command == "resolve":
            lines, code = resolve(root, args.id, args.service, args.stack, args.env)
            sys.stdout.write("\n".join(lines) + "\n")
            return code
        if args.command == "classify":
            sys.stdout.write(
                classify(
                    root,
                    args.entry,
                    args.klass,
                    args.rationale,
                    args.today,
                    config_path=Path(args.config),
                )
                + "\n"
            )
            return 0
        verdict = check_verdict(args.verdict) if args.command == "decide" else "open"
        sys.stdout.write(
            record(
                root,
                args.key,
                verdict,
                args.rationale,
                args.today,
                config_path=Path(args.config),
            )
            + "\n"
        )
        return 0
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
