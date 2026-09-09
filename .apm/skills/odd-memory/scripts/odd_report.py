#!/usr/bin/env python3
"""The observation report's deterministic steps, as one script.

The observe-run-report reference used to spell out, in prose, what the
inputs already fix: the file's name (the UTC stamp, the slug, the
observer suffix, the replay prefixes, the ordinal on a collision), the
frontmatter fields a repository answers (``date``, ``revision``,
``tree_anchor``, ``repository``), the seven numbered sections, the
ruling table a replay opens section 3 with, the work branch and the
lone commit, and the synthesis block a mission closes with. A run read
that prose right before writing its report, with the whole
investigation already in context, and rebuilt the format - differently
each time. This script is those steps; the reference keeps the
judgment.

It is also the one reader of the format: ``odd_status.py``,
``odd_recall.py`` and ``odd_ledger.py`` import their frontmatter,
section and table parsing from here, so the file format is written and
read by one module.

    odd_report.py new --service S [--service S ...] --stack S --env E
                      --mode M --depth D --window START/END | --from START --to END
                      --run-name SLUG
                      (prints the path, then the skeleton to fill)
                      [--verifies FILE] [--workload W] [--instance K=V ...]
                      [--process-restarted true|false|K=V ...]
                      [--repository VALUE] [--at UTC] [--no-revision] [--repo PATH]
    odd_report.py check PATH
    odd_report.py read PATH --sections 1,2,3,7 [--record]
    odd_report.py synthesis PATH
    odd_report.py show PATH
    odd_report.py persist PATH [--body DRAFT] [--no-commit]

Standard library and git only. stdout carries the answer (a path, the
report's text, the synthesis); stderr carries the notes and the
refusals; exit 2 on a refusal, nothing written.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

# --- the contract's constants --------------------------------------------------------

OBSERVATION_DIR = ".odd/observe-run-reports"
INSTRUMENTATION_DIR = ".odd/otel-instrumentation-reports"
KINDS = {
    "observe-run-reports": "observation",
    "otel-instrumentation-reports": "instrumentation",
}
REPORT_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-\d{4}-([a-z0-9][a-z0-9-]*)\.md$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
STAMP_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):\d{2}Z$")
WINDOW_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$"
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPORT_FILE_RE = re.compile(r"\d{4}-\d{2}-\d{2}-\d{4}-[a-z0-9][a-z0-9-]*\.md")
OBSERVATION_MODES = ("drive", "observe", "post-hoc", "verify", "re-measure")
REPLAY_MODES = ("verify", "re-measure")
DEPTHS = ("quick", "full")
PREFIXES = {"verify": "verify-", "re-measure": "remeasure-"}
SUBJECTS = {
    "verify": "verification report",
    "re-measure": "re-measure report",
}
SECTION_TITLES = (
    "Mission and run record",
    "Observed behavior",
    "Anomalies and probable causes",
    "Improvement opportunities",
    "Telemetry gaps",
    "Decisions the spec must settle",
    "Measurement protocol for the fix",
)
FIELD_ORDER = (
    "services",
    "stack",
    "environment",
    "mode",
    "depth",
    "window",
    "run_name",
    "date",
    "verifies",
    "revision",
    "tree_anchor",
    "repository",
    "workload",
    "instance",
    "process_restarted",
)
VERDICTS = ("fixed", "still present", "worse", "not ruled (quick)")
FATES = ("filled", "still missing", "new", "not ruled (quick)")
RULING_HEADER = ["#", "Baseline finding", "Verdict", "Evidence"]
PLACEHOLDER = "<fill>"
PLACEHOLDER_RE = re.compile(r"<fill\b[^>]*>")
LEGACY_PREFIX = "depth absent (predates"
MAX_FINDING_TITLE = 80
MAX_ROWS = 10  # the synthesis's cap per table, the rest behind "+N more"
MAX_LINE = 200
MAX_CELL = 48  # a severity, confidence or check cell on the screen
MAX_TITLE_CELL = 140
ELLIPSIS = "…"

SECTION_RE = re.compile(r"^##\s+(\d+)\.\s*(.*?)\s*$")
FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z_][\w.-]*):(.*)$")
TABLE_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")
SCENARIO_HEADING_RE = re.compile(r"^#{3,}\s+scenario record\b", re.IGNORECASE)
SCENARIO_LABEL_RE = re.compile(r"^\s*(?:-\s*)?\*\*scenario record", re.IGNORECASE)
BOLD_LABEL_RE = re.compile(r"^\s*(?:-\s*)?\*\*[A-Z]")
ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+")
BASELINE_RE = re.compile(
    r"recalled baseline|previous report|baseline report", re.IGNORECASE
)
BASELINE_LABEL_RE = re.compile(
    r"^\W*(?:recalled baseline|previous report|baseline report|baseline)\b",
    re.IGNORECASE,
)
BASELINE_NOTE_RE = re.compile(
    r"provisional|baseline .*dropped|newer quick report skipped", re.IGNORECASE
)
DELTA_RE = re.compile(
    r"^\W*deltas?\b|against the (?:recalled )?baseline|vs\.? (?:the )?baseline"
    r"|^\W*[^:—]{2,80}(?::|—)\s*\**(?:improved|regressed|unchanged|new)\b",
    re.IGNORECASE,
)
NOT_QUERIED_RE = re.compile(r"^\W*not queried\b", re.IGNORECASE)
NONE_RE = re.compile(r"^\W*none\b", re.IGNORECASE)
GAP_SPLIT = " — "
SEVERE_RE = re.compile(r"\b(?:high|critical)\b", re.IGNORECASE)
CONFIRMED_RE = re.compile(r"^\W*confirmed", re.IGNORECASE)
PASS_RE = re.compile(r"\bpass", re.IGNORECASE)
FAIL_RE = re.compile(r"\bfail", re.IGNORECASE)
NOT_RULED_RE = re.compile(r"not ruled", re.IGNORECASE)


class Refusal(Exception):
    """One reason, one stderr line, exit 2, nothing written."""


# --- the frontmatter, read as the contract writes it ----------------------------------


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


def frontmatter_lines(text: str) -> list[str]:
    """The frontmatter block as written, fences included, or nothing."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    return [] if end is None else lines[: end + 1]


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


# --- the frontmatter, written as the contract reads it --------------------------------

UNSAFE_SCALAR_RE = re.compile(r"[,:{}\[\]#'\"]|^\s|\s$|^[-*&!|>%@`?]")


def format_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    text = str(value)
    if (
        not text
        or text.lower() in ("true", "false", "null", "~")
        or UNSAFE_SCALAR_RE.search(text)
    ):
        quote = "'" if '"' in text else '"'
        return f"{quote}{text}{quote}"
    return text


def format_value(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(format_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return (
            "{"
            + ", ".join(
                f"{format_scalar(k)}: {format_value(v)}" for k, v in value.items()
            )
            + "}"
        )
    return format_scalar(value)


def format_frontmatter(fields: dict) -> str:
    lines = ["---"]
    for key in FIELD_ORDER:
        if key in fields and fields[key] is not None:
            lines.append(f"{key}: {format_value(fields[key])}")
    for key, value in fields.items():
        if key not in FIELD_ORDER and value is not None:
            lines.append(f"{key}: {format_value(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


# --- the body ------------------------------------------------------------------------


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


def extract_tables(lines: list[str]) -> tuple[list[dict], list[str]]:
    """The markdown tables in ``lines`` and the lines that are not tables."""
    tables, rest = [], []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            if len(block) >= 2 and is_separator_row(block[1]):
                tables.append(
                    {
                        "header": split_cells(block[0]),
                        "rows": [split_cells(r) for r in block[2:]],
                    }
                )
            else:
                rest.extend(block)
            continue
        rest.append(lines[i])
        i += 1
    return tables, rest


def paragraphs(lines: list[str]) -> list[str]:
    """Paragraphs as single lines, wrapped lines joined with a space."""
    out, buf = [], []
    for line in lines + [""]:
        if line.strip():
            buf.append(line.strip())
        elif buf:
            out.append(" ".join(buf))
            buf = []
    return out


def items(lines: list[str]) -> list[str]:
    """Paragraphs and list items as single lines: a bullet or a numbered
    item opens an item, its wrapped lines join it, a blank line closes it."""
    out: list[str] = []
    buf: list[str] = []
    for line in lines + [""]:
        if not line.strip():
            if buf:
                out.append(" ".join(buf))
                buf = []
            continue
        if ITEM_RE.match(line) and buf:
            out.append(" ".join(buf))
            buf = []
        buf.append(line.strip())
    return [i for i in out if i and not i.startswith("#")]


def cap(text: str, limit: int | None) -> tuple[str, bool]:
    if limit is None or len(text) <= limit:
        return text, False
    return text[:limit] + ELLIPSIS, True


def raw_sections(body: str) -> list[dict]:
    """The numbered ``## N.`` sections, uncapped: tables and prose lines."""
    sections: list[dict] = []
    current: dict | None = None
    buffer: list[str] = []

    def close() -> None:
        if current is not None:
            current["tables"], current["lines"] = extract_tables(buffer)
            current["raw"] = list(buffer)
            sections.append(current)

    for line in body.splitlines():
        if line.startswith("## "):
            close()
            match = SECTION_RE.match(line)
            current = (
                {"number": int(match.group(1)), "title": match.group(2)}
                if match
                else None
            )
            buffer = []
        elif current is not None:
            buffer.append(line)
    close()
    return sections


def section(sections: list[dict], number: int) -> dict | None:
    """The last section carrying ``number`` - the one a reader reaches."""
    found = None
    for candidate in sections:
        if candidate["number"] == number:
            found = candidate
    return found


def finding_ids(sections: list[dict]) -> tuple[list[str], str]:
    """The IDs section 3's tables name in their first column, and its prose."""
    ids: list[str] = []
    prose = ""
    for current in sections:
        if current["number"] != 3:
            continue
        for table in current["tables"]:
            for row in table["rows"]:
                if row and row[0].strip():
                    candidate = row[0].split()[0].strip("*`")
                    if candidate and candidate not in ids:
                        ids.append(candidate)
        prose = "\n".join(current["lines"])
    return ids, prose


def column(header: list[str], pattern: str) -> int | None:
    for index, cell in enumerate(header):
        if re.search(pattern, cell, re.IGNORECASE):
            return index
    return None


def verdict_column(header: list[str]) -> int | None:
    """The column a ruling lives in - never the pass criterion beside it."""
    for index, cell in enumerate(header):
        if re.search(r"criterion|before|baseline|expected", cell, re.IGNORECASE):
            continue
        if re.search(r"verdict|ruling|fate|pass|result|\bstate\b", cell, re.IGNORECASE):
            return index
    return None


def cell_at(row: list[str], index: int | None) -> str | None:
    if index is None or index >= len(row):
        return None
    return row[index].strip() or None


def findings_at_a_glance(
    sections: list[dict], replay: bool, max_title: int | None = MAX_FINDING_TITLE
) -> list[dict]:
    """The findings a report names, reduced to id, title, severity, ruling.

    Section 3's rows always; on a replay, the rows of every other table
    carrying a ruling column (a verification may rule in its protocol
    table).
    """
    out: list[dict] = []
    for current in sections:
        number = current["number"]
        for table in current["tables"]:
            header = table["header"]
            severity = column(header, r"sever")
            ruling = column(header, r"verdict|fate|ruling|state")
            if number != 3 and not (replay and ruling is not None):
                continue
            for row in table["rows"]:
                if not row or not row[0].strip():
                    continue
                title = cell_at(row, 1) if number == 3 else None
                out.append(
                    {
                        "id": row[0].split()[0].strip("*`"),
                        "title": cap(title, max_title)[0] if title else None,
                        "severity": cell_at(row, severity),
                        "ruling": cell_at(row, ruling),
                        "section": number,
                    }
                )
    return out


def headline(body: str) -> str | None:
    """The first paragraph between the title and the first section, if any."""
    lines = body.splitlines()
    start = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
    end = next(
        (i for i, line in enumerate(lines) if line.startswith("## ")), len(lines)
    )
    found = paragraphs(lines[start:end])
    return found[0] if found else None


def paragraphs_starting_with(body: str, prefix: str) -> list[str]:
    return [p for p in paragraphs(body.splitlines()) if p.startswith(prefix)]


def scenario_record(body: str) -> str | None:
    """The scenario record: under its ``### Scenario record`` heading, up to
    the next heading - or, when the report writes it as a bold label
    (``**Scenario record**``), from that line up to the next heading or
    the next bold-labelled paragraph."""
    lines = body.splitlines()
    start = next(
        (i + 1 for i, line in enumerate(lines) if SCENARIO_HEADING_RE.match(line)), None
    )
    if start is not None:
        end = next(
            (i for i in range(start, len(lines)) if lines[i].startswith("#")),
            len(lines),
        )
        return "\n".join(lines[start:end]).strip()
    start = next(
        (i for i, line in enumerate(lines) if SCENARIO_LABEL_RE.match(line)), None
    )
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("#") or BOLD_LABEL_RE.match(lines[i]):
            end = i
            break
    return "\n".join(lines[start:end]).strip()


# --- git -----------------------------------------------------------------------------


def git(root: Path, *args: str) -> str | None:
    """Run git in ``root``; the stripped stdout, or None when git fails."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def git_root(path: Path) -> Path | None:
    top = git(path, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


REMOTE_RE = re.compile(
    r"^(?P<scheme>[a-z][a-z0-9+.-]*://)?(?P<user>[^@/]+@)?(?P<host>[^:/@]+)"
    r"(?::\d+)?[:/](?P<path>.+)$",
    re.IGNORECASE,
)


def normalize_remote(url: str | None) -> str | None:
    """A remote URL as the memory contract writes ``repository``: the host
    lower-cased, then the remote's path as it is; scheme, user info and port
    dropped, one trailing ``/`` and one trailing ``.git`` stripped, the SSH
    form read the same way. None for anything that is not a remote (a local
    path, a bare word)."""
    text = (url or "").strip().split("#", 1)[0].split("?", 1)[0]
    match = REMOTE_RE.match(text)
    if not match:
        return None
    host, path = match.group("host").lower(), match.group("path")
    remote_marked = bool(match.group("scheme") or match.group("user"))
    if host.startswith(".") or (
        "." not in host and host != "localhost" and not remote_marked
    ):
        return None
    path = path.lstrip("/").removesuffix("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    if not path:
        return None
    return f"{host}/{path}"


def repo_identity(root: Path) -> str | None:
    """The repository's own identity: its origin remote, normalized."""
    return normalize_remote(git(root, "remote", "get-url", "origin"))


def ls_tree(root: Path, ref: str) -> dict[str, str] | None:
    out = git(root, "ls-tree", ref)
    if out is None:
        return None
    entries = {}
    for line in out.splitlines():
        meta, _, name = line.partition("\t")
        parts = meta.split()
        if len(parts) >= 3 and name:
            entries[name] = parts[2]
    return entries


def default_branch(root: Path) -> str:
    """The memory contract's reading: origin/HEAD stripped of ``origin/``,
    else ``main`` - or ``master`` when that is the checked-out branch."""
    head = git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head.removeprefix("origin/")
    current = git(root, "branch", "--show-current")
    return "master" if current == "master" else "main"


# --- a stored report, read and checked ---------------------------------------------


def report_kind(path: Path) -> str | None:
    """The kind of report a path names, or None when it is no report."""
    parents = [p.name for p in path.parents]
    if path.suffix != ".md" or len(parents) < 2 or parents[1] != ".odd":
        return None
    return KINDS.get(parents[0])


def read_report(path: Path, kind: str) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {
            "name": path.name,
            "path": str(path),
            "kind": kind,
            "unreadable": str(exc),
        }
    frontmatter, body, errors = split_frontmatter(text)
    return {
        "name": path.name,
        "path": str(path),
        "kind": kind,
        "frontmatter": frontmatter,
        "frontmatter_errors": errors,
        "body": body,
    }


def check_report(
    report: dict, stored_names: set[str], root: Path, written_now: bool = False
) -> list[str]:
    """What the report lacks against the memory contract's frontmatter.

    ``written_now`` is the write-time reading: ``depth`` is required. The
    status reads a stored report without it as a legacy file that
    predates the field (the problem starts with ``LEGACY_PREFIX``).
    """
    problems: list[str] = []
    name = Path(report.get("path") or report["name"]).name
    match = REPORT_NAME_RE.match(name)
    if not match:
        problems.append("filename is not YYYY-MM-DD-HHmm-<run_name>.md")
    if "unreadable" in report:
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
        if mode is not None and mode not in OBSERVATION_MODES:
            problems.append(f"mode {mode!r} is not one of {list(OBSERVATION_MODES)}")
        depth = fm.get("depth")
        if depth is None:
            problems.append(
                "depth absent"
                if written_now
                else "depth absent (predates the field: reads as full)"
            )
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
            # instrumentation baseline is named by its repo-relative path.
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
            mode = fm.get("mode") if kind == "observation" else None
            prefix = PREFIXES.get(str(mode), "")
            expected = f"{prefix}{run_name}"
            if match.group(2) != expected:
                with_prefix = f" with the {prefix} prefix" if prefix else ""
                problems.append(
                    f"filename slug {match.group(2)!r} is not {expected!r}"
                    f" (run_name {run_name!r}{with_prefix})"
                )
    return problems


def baseline_path(root: Path, verifies: str) -> Path:
    """Where a replay's baseline lives: a bare filename is a sibling
    observation report, a repo-relative path names the directory itself."""
    return root / verifies if "/" in verifies else root / OBSERVATION_DIR / verifies


def check_body(report: dict, root: Path) -> list[str]:
    """What the body lacks at write time: the numbered sections, no
    placeholder left, and on a replay one ruling per baseline finding."""
    problems: list[str] = []
    body = report.get("body") or ""
    sections = raw_sections(body)
    numbers = [s["number"] for s in sections]
    expected = list(range(1, 8)) if report["kind"] == "observation" else []
    for number in expected:
        if number not in numbers:
            problems.append(f"section {number} absent")
    seen = [n for n in numbers if n in expected]
    if seen != sorted(seen):
        problems.append("sections out of order")
    for number in expected:
        if numbers.count(number) > 1:
            problems.append(f"section {number} appears {numbers.count(number)} times")
    flagged: set[str] = set()
    current = "before section 1"
    for line in body.splitlines():
        match = SECTION_RE.match(line)
        if match:
            current = f"section {match.group(1)}"
        if PLACEHOLDER_RE.search(line) and current not in flagged:
            flagged.add(current)
            problems.append(f"placeholder left {current}")
    fm = report.get("frontmatter") or {}
    mode = str(fm.get("mode"))
    verifies = fm.get("verifies")
    if report["kind"] == "observation" and mode in REPLAY_MODES and verifies:
        target = baseline_path(root, str(verifies))
        if "/" not in str(verifies) and target.is_file():
            base = read_report(target, "observation")
            if "unreadable" not in base:
                problems.extend(check_rulings(sections, raw_sections(base["body"])))
    return problems


def ruling_rows(sections: list[dict]) -> dict[str, str]:
    """Section 3's ruling rows: the baseline id to the verdict cell."""
    rulings: dict[str, str] = {}
    current = section(sections, 3)
    if current is None:
        return rulings
    for table in current["tables"]:
        verdict = column(table["header"], r"verdict|fate|ruling")
        if verdict is None:
            continue
        for row in table["rows"]:
            if row and row[0].strip():
                rulings.setdefault(
                    row[0].split()[0].strip("*`"), (cell_at(row, verdict) or "")
                )
    return rulings


def check_rulings(sections: list[dict], baseline: list[dict]) -> list[str]:
    problems: list[str] = []
    ids = [
        f["id"]
        for f in findings_at_a_glance(baseline, replay=False, max_title=None)
        if f["section"] == 3
    ]
    rulings = ruling_rows(sections)
    for finding_id in ids:
        verdict = rulings.get(finding_id)
        if verdict is None:
            problems.append(
                f"section 3 carries no ruling row for the baseline's finding "
                f"{finding_id} (the ruling table keys it by the baseline's own id)"
            )
            continue
        word = verdict.strip().strip("*`").lower()
        if not any(word.startswith(v) for v in VERDICTS):
            problems.append(
                f"section 3: the verdict on {finding_id} reads {verdict!r}, not one of "
                + ", ".join(VERDICTS)
                + " (a nuance goes after the word)"
            )
    return problems


def check_file(path: Path, written_now: bool = False, body: bool = False) -> list[str]:
    """The report's problems: the hook's frontmatter and filename rules, and
    with ``body`` the write-time body rules. An empty list is a report the
    contract accepts; a file that is no report is a refusal."""
    kind = report_kind(path)
    if kind is None:
        raise Refusal(
            f"{path} is not a report: reports live under {OBSERVATION_DIR}/ or "
            f"{INSTRUMENTATION_DIR}/"
        )
    report = read_report(path, kind)
    if "unreadable" in report:
        return [f"unreadable: {report['unreadable']}"]
    observation_dir = path.parents[1] / "observe-run-reports"
    stored = (
        {p.name for p in observation_dir.glob("*.md")}
        if observation_dir.is_dir()
        else set()
    )
    root = path.parents[2]
    problems = check_report(report, stored, root, written_now=written_now)
    if body:
        problems.extend(check_body(report, root))
    return problems


# --- new -------------------------------------------------------------------------


def reduce_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def stamp_of(utc: str) -> tuple[str, str]:
    """``YYYY-MM-DD-HHmm`` and ``YYYY-MM-DD`` from a UTC instant."""
    match = STAMP_RE.match(utc)
    if not match:
        raise Refusal(f"not a UTC instant (YYYY-MM-DDTHH:MM:SSZ): {utc}")
    year, month, day, hour, minute = match.groups()
    return f"{year}-{month}-{day}-{hour}{minute}", f"{year}-{month}-{day}"


def parse_pairs(values: list[str], flag: str, booleans: bool = False) -> Any:
    """``K=V`` pairs into a mapping; with ``booleans``, a lone true/false too."""
    if booleans and len(values) == 1 and values[0].lower() in ("true", "false"):
        return values[0].lower() == "true"
    mapping: dict[str, Any] = {}
    for item in values:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise Refusal(f"{flag} takes KEY=VALUE, got {item!r}")
        mapping[key.strip()] = parse_scalar(value) if booleans else value.strip()
    return mapping


def gap_bullets(baseline: list[dict]) -> list[tuple[str, str]]:
    """The baseline's section 5 bullets as (gap, discovery query)."""
    current = section(baseline, 5)
    if current is None:
        return []
    found = []
    for item in items(current["lines"]):
        if not item.startswith("- ") or NOT_QUERIED_RE.match(item[2:]):
            continue
        parts = item[2:].split(GAP_SPLIT)
        if len(parts) >= 3:
            found.append((parts[0].strip(), GAP_SPLIT.join(parts[2:]).strip()))
        else:
            found.append((item[2:].strip(), ""))
    return found


def skeleton(fields: dict, baseline: list[dict] | None, verdict_fill: bool) -> str:
    """The body: the title, the headline placeholder, the seven sections -
    and on a replay, section 3's ruling table and section 5's gaps carried
    from the baseline, their verdicts and fates left to the run."""
    lines = [f"# Observation report — {fields['run_name']}", "", PLACEHOLDER, ""]
    for number, title in enumerate(SECTION_TITLES, start=1):
        lines += [f"## {number}. {title}", ""]
        if number == 3 and baseline is not None and verdict_fill:
            ids = [
                f
                for f in findings_at_a_glance(baseline, replay=False, max_title=None)
                if f["section"] == 3
            ]
            if ids:
                lines.append("| " + " | ".join(RULING_HEADER) + " |")
                lines.append("|" + "---|" * len(RULING_HEADER))
                for finding in ids:
                    title_cell = (finding["title"] or "").replace("|", "\\|")
                    lines.append(
                        f"| {finding['id']} | {title_cell} | "
                        f"<fill: {' | '.join(VERDICTS)}> | <fill> |"
                    )
                lines.append("")
        if number == 5 and baseline is not None and verdict_fill:
            gaps = gap_bullets(baseline)
            if gaps:
                for gap, query in gaps:
                    fate = f"<fill: {' | '.join(f for f in FATES if f != 'new')}>"
                    lines.append(f"- {gap}{GAP_SPLIT}{fate}{GAP_SPLIT}{query}".rstrip())
                lines.append("")
                continue
        lines += [PLACEHOLDER, ""]
    return "\n".join(lines)


def new_report(args: argparse.Namespace) -> tuple[Path, list[str]]:
    notes: list[str] = []
    if args.kind != "observation":
        raise Refusal(
            "new writes observation reports only; an instrumentation report keeps the "
            "otel-instrumentation-report reference's steps (check and read serve both kinds)"
        )
    services = [
        s.strip() for value in args.service for s in value.split(",") if s.strip()
    ]
    if not services:
        raise Refusal("--service is required (repeatable)")
    for flag, value in (
        ("--stack", args.stack),
        ("--env", args.env),
        ("--mode", args.mode),
    ):
        if not value:
            raise Refusal(f"{flag} is required")
    if args.mode not in OBSERVATION_MODES:
        raise Refusal(
            f"--mode is one of {', '.join(OBSERVATION_MODES)}, not {args.mode!r}"
        )
    if args.depth is not None and args.depth not in DEPTHS:
        raise Refusal(f"--depth is one of {', '.join(DEPTHS)}, not {args.depth!r}")
    # the two instants a query script printed (--from START --to END) are
    # the window as recorded, pasted as they are: never recomputed by hand
    if not args.window and args.start and args.end:
        args.window = f"{args.start.strip()}/{args.end.strip()}"
    window = WINDOW_RE.match(args.window or "")
    if not window:
        raise Refusal(
            "--window is <start>/<end> in UTC (YYYY-MM-DDTHH:MM:SSZ), or the "
            "--from START --to END a query script printed"
        )
    if window.group(2) < window.group(1):
        raise Refusal("--window ends before it starts")
    replay = args.mode in REPLAY_MODES
    if replay and not args.verifies:
        raise Refusal(f"--verifies is required on a {args.mode} run")
    if args.verifies and not replay:
        raise Refusal("--verifies applies to a verify or re-measure run only")

    if args.no_revision:
        root = Path(args.repo).resolve()
        repo_root = None
    else:
        repo_root = git_root(Path(args.repo))
        if repo_root is None:
            raise Refusal(
                f"not a git repository: {Path(args.repo).resolve()} (--no-revision when "
                "the observed code is in no repository the run can reach)"
            )
        root = repo_root

    baseline_sections: list[dict] | None = None
    baseline_kind = None
    run_name = args.run_name
    depth = args.depth
    if replay:
        target = baseline_path(root, args.verifies)
        if not target.is_file():
            raise Refusal(f"--verifies names no stored report: {args.verifies}")
        baseline_kind = "instrumentation" if "/" in args.verifies else "observation"
        base = read_report(target, baseline_kind)
        if "unreadable" in base:
            raise Refusal(
                f"--verifies names a report that cannot be read: {base['unreadable']}"
            )
        base_fm = base["frontmatter"]
        if run_name is None:
            run_name = base_fm.get("run_name")
            if not run_name:
                raise Refusal("the baseline carries no run_name; pass --run-name")
            notes.append(f"run_name {run_name} inherited from the baseline")
        if depth is None:
            if baseline_kind == "instrumentation":
                depth = "full"
                notes.append(
                    "depth full: an instrumentation baseline replays every signal"
                )
            elif base_fm.get("depth") is None:
                depth = "quick"
                notes.append(
                    "depth quick: the baseline predates the field (it ran full; a "
                    "replay of it is quick unless the caller says full)"
                )
            else:
                depth = str(base_fm["depth"])
                notes.append(f"depth {depth} inherited from the baseline")
        if baseline_kind == "observation":
            baseline_sections = raw_sections(base["body"])
    if depth is None:
        raise Refusal("--depth is required (quick or full)")
    if run_name is None:
        raise Refusal("--run-name is required")
    if not SLUG_RE.match(run_name):
        raise Refusal(
            f"the run name {run_name!r} is not a slug ([a-z0-9][a-z0-9-]*, kebab-case)"
        )
    if args.mode == "observe":
        suffix = f"-observe-{reduce_slug(args.stack)}"
        if not run_name.endswith(suffix):
            run_name += suffix

    stamp, date = stamp_of(args.at or window.group(1))
    store = root / OBSERVATION_DIR
    prefix = PREFIXES.get(args.mode, "")
    candidate = run_name
    ordinal = 1
    while (store / f"{stamp}-{prefix}{candidate}.md").exists():
        ordinal += 1
        candidate = f"{run_name}-{ordinal}"
    if candidate != run_name:
        notes.append(
            f"{stamp}-{prefix}{run_name}.md is taken: the next free ordinal, "
            f"run_name {candidate} (section 1 names the report it sits beside)"
        )
        run_name = candidate
    path = store / f"{stamp}-{prefix}{run_name}.md"

    fields: dict[str, Any] = {
        "services": services,
        "stack": args.stack,
        "environment": args.env,
        "mode": args.mode,
        "depth": depth,
        "window": args.window,
        "run_name": run_name,
        "date": date,
    }
    if replay:
        fields["verifies"] = args.verifies
    if repo_root is not None:
        fields["revision"] = git(repo_root, "rev-parse", "--short", "HEAD")
        fields["tree_anchor"] = ls_tree(repo_root, "HEAD")
        if args.repository:
            fields["repository"] = parse_value(args.repository)
        else:
            fields["repository"] = repo_identity(repo_root)
            if fields["repository"] is None:
                notes.append(
                    "no origin remote: repository omitted (never a local path)"
                )
    elif args.repository:
        fields["repository"] = parse_value(args.repository)
    if args.workload:
        fields["workload"] = args.workload
    if args.instance:
        fields["instance"] = parse_pairs(args.instance, "--instance")
    if args.process_restarted:
        fields["process_restarted"] = parse_pairs(
            args.process_restarted, "--process-restarted", booleans=True
        )

    store.mkdir(parents=True, exist_ok=True)
    body = skeleton(fields, baseline_sections, replay)
    path.write_text(format_frontmatter(fields) + "\n" + body, encoding="utf-8")
    return path, body, notes


# --- read ------------------------------------------------------------------------


def section_text(sections: list[dict], number: int, record_only: bool) -> str | None:
    current = section(sections, number)
    if current is None:
        return None
    raw = current["raw"]
    if record_only and number == 1:
        first = next((i for i, line in enumerate(raw) if line.startswith("### ")), None)
        if first is not None:
            raw = raw[first:]
        else:
            block = scenario_record("\n".join(raw))
            raw = block.splitlines() if block else raw
    heading = f"## {number}. {current['title']}"
    return "\n".join([heading, *raw]).rstrip() + "\n"


def read_sections(
    text: str, numbers: list[int], record_only: bool
) -> tuple[str, list[str]]:
    _, body, _ = split_frontmatter(text)
    sections = raw_sections(body)
    out = list(frontmatter_lines(text))
    missing = []
    for number in numbers:
        piece = section_text(sections, number, record_only)
        if piece is None:
            missing.append(f"section {number} absent")
        else:
            out += ["", piece.rstrip()]
    return "\n".join(out) + "\n", missing


# --- the synthesis ----------------------------------------------------------------


def rows_reduced(
    table: dict, patterns: list[tuple[str, int | None]]
) -> list[list[str]]:
    """Rows reduced to the columns the patterns name (a fallback index when
    the header names none), empty where a column is absent."""
    indexes = []
    for pattern, fallback in patterns:
        found = column(table["header"], pattern) if pattern else None
        indexes.append(fallback if found is None else found)
    reduced = []
    for row in table["rows"]:
        if not row or not row[0].strip():
            continue
        reduced.append([cell_at(row, i) or "" for i in indexes])
    return reduced


def synthesis_data(text: str) -> dict:
    fm, body, _ = split_frontmatter(text)
    sections = raw_sections(body)
    mode = str(fm.get("mode"))
    replay = mode in REPLAY_MODES
    data: dict[str, Any] = {
        "frontmatter": fm,
        "frontmatter_lines": [
            f"tree_anchor: <{len(fm['tree_anchor'])} entries, in the file>"
            if line.startswith("tree_anchor:")
            and isinstance(fm.get("tree_anchor"), dict)
            else line
            for line in frontmatter_lines(text)
        ],
        "mode": mode,
        "replay": replay,
        "quick": str(fm.get("depth")) == "quick",
        "baseline_lines": [],
        "baseline_name": None,
        "no_baseline": False,
        "deltas": [],
        "checks": [],
        "rulings": [],
        "findings": [],
        "not_queried": None,
        "gaps": [],
        "decisions": [],
        "decisions_none": None,
    }
    one = section(sections, 1)
    if one is not None:
        listed = items(one["lines"])
        found = [i for i in listed if BASELINE_LABEL_RE.match(i)] or [
            i for i in listed if BASELINE_RE.search(i)
        ]
        notes = [i for i in listed if BASELINE_NOTE_RE.search(i) and i not in found[:1]]
        data["baseline_lines"] = found[:1] + notes
        for line in data["baseline_lines"]:
            match = REPORT_FILE_RE.search(line)
            if match and data["baseline_name"] is None:
                data["baseline_name"] = match.group(0)
        if (
            found
            and data["baseline_name"] is None
            and re.search(r"no previous", found[0], re.IGNORECASE)
        ):
            data["no_baseline"] = True
    two = section(sections, 2)
    if two is not None and not replay:
        data["deltas"] = [i for i in items(two["lines"]) if DELTA_RE.search(i)][:20]
    if replay:
        for number in (2, 7):
            current = section(sections, number)
            if current is None:
                continue
            for table in current["tables"]:
                verdict = verdict_column(table["header"])
                if verdict is None:
                    continue
                reduced = rows_reduced(
                    table,
                    [
                        (r"check|item|planned|signal", 0),
                        (r"before|baseline", None),
                        (r"this run|after|measured|now|observed", None),
                    ],
                )
                data["checks"] += [
                    [*row, cell_at(raw, verdict) or ""]
                    for row, raw in zip(
                        reduced, [r for r in table["rows"] if r and r[0].strip()]
                    )
                ]
    three = section(sections, 3)
    if three is not None:
        for table in three["tables"]:
            if column(table["header"], r"verdict|fate|ruling") is not None:
                data["rulings"] += rows_reduced(
                    table, [("", 0), (r"finding", 1), (r"verdict|fate|ruling", None)]
                )
            elif column(table["header"], r"sever") is not None or not data["findings"]:
                data["findings"] += rows_reduced(
                    table,
                    [
                        ("", 0),
                        (r"finding|anomaly", 1),
                        (r"sever", None),
                        (r"confid", None),
                    ],
                )
    five = section(sections, 5)
    if five is not None:
        for item in items(five["lines"]):
            if NOT_QUERIED_RE.match(item) and data["not_queried"] is None:
                data["not_queried"] = item
            elif (
                item.startswith("- ")
                and NOT_QUERIED_RE.match(item[2:])
                and data["not_queried"] is None
            ):
                data["not_queried"] = item[2:]
            elif item.startswith("- "):
                data["gaps"].append(item[2:])
    six = section(sections, 6)
    if six is not None:
        listed = [i for i in items(six["lines"]) if ITEM_RE.match(i)]
        if listed:
            data["decisions"] = [ITEM_RE.sub("", i) for i in listed]
        else:
            prose = items(six["lines"])
            if prose and NONE_RE.match(prose[0]):
                data["decisions_none"] = prose[0]
            else:
                data["decisions"] = prose
    return data


def table_lines(
    header: list[str], rows: list[list[str]], limit: int | None = None
) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    shown = rows if limit is None else rows[:limit]
    for row in shown:
        lines.append("| " + " | ".join(c.replace("\n", " ") for c in row) + " |")
    if limit is not None and len(rows) > limit:
        lines.append(f"+{len(rows) - limit} more in the report")
    return lines


def synthesis_text(data: dict) -> str:
    out: list[str] = [
        "--- frontmatter",
        *data["frontmatter_lines"],
        "--- section 1: recalled baseline",
    ]
    out += data["baseline_lines"] or ["(no recalled-baseline line found in section 1)"]
    if data["replay"]:
        out.append("--- section 2/7: check rulings (check | before | after | verdict)")
        out += (
            table_lines(["Check", "Before", "After", "Verdict"], data["checks"])
            if data["checks"]
            else ["(no table with a verdict column in sections 2 or 7)"]
        )
        out.append("--- section 3: baseline rulings")
        out += (
            table_lines(["#", "Baseline finding", "Verdict"], data["rulings"])
            if data["rulings"]
            else ["(no ruling table in section 3)"]
        )
    else:
        out.append("--- section 2: deltas against the baseline")
        out += data["deltas"] or ["(no delta line found in section 2)"]
    out.append("--- section 3: findings")
    out += (
        table_lines(["#", "Finding", "Severity", "Confidence"], data["findings"])
        if data["findings"]
        else ["(no findings table in section 3)"]
    )
    out.append("--- section 5: telemetry gaps")
    if data["not_queried"]:
        out.append(data["not_queried"])
    out += [f"- {g}" for g in data["gaps"]]
    if not data["not_queried"] and not data["gaps"]:
        out.append("(no gap bullet in section 5)")
    out.append("--- section 6: open decisions")
    if data["decisions"]:
        out += [f"- {d}" for d in data["decisions"]]
    else:
        out.append(data["decisions_none"] or "(none stated)")
    return "\n".join(out) + "\n"


def file_commit(root: Path | None, rel: str) -> str | None:
    if root is None:
        return None
    return git(root, "log", "-1", "--format=%h", "--", rel) or None


def locate(path: Path) -> tuple[Path | None, str]:
    """The repository root (None outside git) and the report's path in it."""
    root = git_root(path.parent)
    if root is None:
        return None, "/".join(path.resolve().parts[-3:])
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        rel = Path("/".join(path.resolve().parts[-3:]))
    return root, rel.as_posix()


# --- show ------------------------------------------------------------------------


def verdict_counts(rows: list[list[str]]) -> tuple[int, int, int]:
    passed = sum(bool(PASS_RE.search(r[3])) and not FAIL_RE.search(r[3]) for r in rows)
    failed = sum(bool(FAIL_RE.search(r[3])) for r in rows)
    unruled = sum(bool(NOT_RULED_RE.search(r[3])) for r in rows)
    return passed, failed, unruled


def not_queried_summary(line: str | None) -> str | None:
    if not line:
        return None
    match = re.match(r"^\W*not queried \([^)]*\):\s*([^—.;]+)", line, re.IGNORECASE)
    if not match:
        return "some signals not queried"
    names = match.group(1).strip().rstrip(",")
    return f"{names} not queried"


def render_headline(data: dict) -> str:
    findings = data["findings"]
    high = sum(bool(SEVERE_RE.search(r[2])) for r in findings)
    confirmed = sum(bool(CONFIRMED_RE.match(r[3])) for r in findings)
    gaps = len(data["gaps"])
    mode = data["mode"]
    if mode == "verify":
        passed, failed, unruled = verdict_counts(data["checks"])
        total = len(data["checks"])
        if total:
            text = f"{'FAIL' if failed else 'PASS'} — {passed}/{total} checks passed"
            if failed:
                text = f"FAIL — {failed}/{total} checks red"
            if unruled:
                text += f", {unruled} not ruled (quick)"
        else:
            text = f"verify — {len(data['rulings'])} baseline findings ruled, no check table"
    elif mode == "re-measure":
        passed, failed, unruled = verdict_counts(data["checks"])
        total = len(data["checks"])
        text = (
            f"{'drift' if failed else 'no drift'} — {passed}/{total} checks within range"
            if total
            else f"re-measure — {len(data['findings'])} findings re-measured"
        )
    else:
        text = f"{len(findings)} anomalies ({high} high, {confirmed} confirmed), {gaps} telemetry gaps"
        if data["baseline_name"]:
            text += f", vs baseline {data['baseline_name']}"
        elif data["no_baseline"]:
            text += ", no previous report"
    if data["quick"]:
        summary = not_queried_summary(data["not_queried"])
        text = f"quick — {text}" + (f", {summary}" if summary else "")
    return f"**{text}**"


def render_show(data: dict, rel: str, commit: str | None) -> str:
    fm = data["frontmatter"]
    out = [render_headline(data), ""]
    out.append(
        f"Stored at `{rel}` — " + (f"commit {commit}" if commit else "not committed")
    )
    out.append("")
    baseline = fm.get("verifies") or data["baseline_name"] or "none"
    run = [
        ("services", ", ".join(as_list(fm.get("services")))),
        ("stack", fm.get("stack")),
        ("mode", fm.get("mode")),
        ("depth", fm.get("depth") or "full"),
        ("window", fm.get("window")),
        ("environment", fm.get("environment")),
    ]
    if fm.get("repository"):
        run.append(("repository", format_value(fm.get("repository"))))
    run.append(("baseline", baseline))
    out += [f"{key}: {value}" for key, value in run]
    out.append("")
    if data["replay"]:
        if data["checks"]:
            rows = [[cap(c, MAX_CELL)[0] for c in r] for r in data["checks"]]
            out += table_lines(
                ["Check", "Before", "After", "Pass/fail"], rows, MAX_ROWS
            )
            out.append("")
        if data["rulings"]:
            out.append("Baseline findings ruled:")
            for row in data["rulings"][:MAX_ROWS]:
                out.append(f"- {row[0]} — {cap(row[2], MAX_LINE)[0]}")
            if len(data["rulings"]) > MAX_ROWS:
                out.append(f"+{len(data['rulings']) - MAX_ROWS} more in the report")
            out.append("")
    else:
        rows = [
            [
                cap(r[2], MAX_CELL)[0],
                cap(r[3], MAX_CELL)[0],
                cap(r[1], MAX_TITLE_CELL)[0],
            ]
            for r in data["findings"]
        ]
        out += table_lines(["Severity", "Confidence", "Finding"], rows, MAX_ROWS)
        out.append("")
    if data["not_queried"]:
        out.append(cap(data["not_queried"], MAX_LINE)[0])
    if data["gaps"]:
        out.append("Telemetry gaps:")
        for gap in data["gaps"][:MAX_ROWS]:
            out.append(f"- {cap(gap, MAX_LINE)[0]}")
        if len(data["gaps"]) > MAX_ROWS:
            out.append(f"+{len(data['gaps']) - MAX_ROWS} more in the report")
    if data["not_queried"] or data["gaps"]:
        out.append("")
    count = len(data["decisions"])
    out.append(f"Decisions the spec must settle: {count}")
    for decision in data["decisions"][:MAX_ROWS]:
        out.append(f"- {cap(decision, MAX_LINE)[0]}")
    if count > MAX_ROWS:
        out.append(f"+{count - MAX_ROWS} more in the report")
    if not count and data["decisions_none"]:
        out.append(cap(data["decisions_none"], MAX_LINE)[0])
    out.append("")
    out.append("Next: " + next_action(data))
    return "\n".join(out) + "\n"


def next_action(data: dict) -> str:
    mode = data["mode"]
    if mode == "verify":
        _, failed, unruled = verdict_counts(data["checks"])
        if failed:
            return "back to the fix plan - the red checks name what did not land; replay the protocol with /odd-verify once it does."
        if unruled:
            return "replay the protocol with /odd-verify at full depth to rule what this quick run left unruled."
        return "nothing left to verify from this replay; the next observation when the loop's cadence is due."
    if mode == "re-measure":
        return "no fix was under test; build the fix plan from the baseline report, then replay its protocol with /odd-verify."
    if data["decisions"]:
        return f"settle the {len(data['decisions'])} open decisions, then build the fix plan from the report; replay its protocol with /odd-verify once the fix lands."
    return "build the fix plan from the report; replay its protocol with /odd-verify once the fix lands."


# --- persist ---------------------------------------------------------------------


def splice_body(path: Path, draft: Path) -> list[str]:
    """The draft's text under the report's frontmatter, replacing the body.

    The run writes its seven sections to a draft with its file tool and
    never edits the report file: the frontmatter stays the script's. A
    frontmatter block the draft opens with is dropped, and said."""
    notes: list[str] = []
    try:
        text = draft.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refusal(f"cannot read the draft {draft}: {exc}") from exc
    if text.lstrip().startswith("---"):
        _, text, _ = split_frontmatter(text.lstrip())
        notes.append(
            "the draft opened with a frontmatter block: dropped, the file's kept"
        )
    head = frontmatter_lines(path.read_text(encoding="utf-8"))
    if not head:
        raise Refusal(f"{path.name} carries no frontmatter to keep; run new first")
    path.write_text("\n".join(head) + "\n\n" + text.strip() + "\n", encoding="utf-8")
    return notes


def persist(
    path: Path, no_commit: bool, body: Path | None = None
) -> tuple[list[str], list[str]]:
    """The return value's lines (stdout) and the notes (stderr)."""
    spliced = splice_body(path, body) if body is not None else []
    problems = check_file(path, written_now=True, body=True)
    if problems:
        raise Refusal(
            "the report does not follow the memory contract - fix it before "
            "persisting:\n" + "\n".join(f"  {path.name}: {p}" for p in problems)
        )
    text = path.read_text(encoding="utf-8")
    fm, _, _ = split_frontmatter(text)
    run_name = str(fm.get("run_name"))
    mode = str(fm.get("mode"))
    root, rel = locate(path)
    notes: list[str] = list(spliced)
    lines = [f"path: {rel}"]
    commit = None
    if root is None:
        lines.append("commit: not committed (not a git repository)")
    elif no_commit:
        lines.append("commit: not committed (the caller said not to)")
    else:
        branch = git(root, "branch", "--show-current") or ""
        target = f"docs/odd-observe-run-report-{run_name}"
        if branch == default_branch(root):
            exists = git(
                root, "rev-parse", "--verify", "--quiet", f"refs/heads/{target}"
            )
            switched = (
                git(root, "checkout", "-q", target)
                if exists
                else git(root, "checkout", "-q", "-b", target)
            )
            if switched is None:
                lines.append(
                    f"commit: not committed (on the default branch {branch} and the work "
                    f"branch {target} could not be checked out)"
                )
                root = None
            else:
                notes.append(f"switched from {branch} to the work branch {target}")
                branch = target
        if root is not None:
            subject = (
                f"docs(odd): {SUBJECTS.get(mode, 'observation report')} {run_name}"
            )
            added = git(root, "add", "--", rel)
            committed = (
                None
                if added is None
                else git(root, "commit", "-q", "-m", subject, "--", rel)
            )
            if committed is None:
                lines.append("commit: not committed (git commit failed)")
            else:
                commit = git(root, "rev-parse", "--short", "HEAD")
                lines.append(f"commit: {commit}")
                lines.append(f"branch: {branch}")
                lines.append(f"subject: {subject}")
    lines.append(synthesis_text(synthesis_data(text)).rstrip())
    return lines, notes


# --- cli ---------------------------------------------------------------------------


class OneLineParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(f"{self.prog}: {message} (see --help)", file=sys.stderr)
        sys.exit(2)


def parse_numbers(text: str) -> list[int]:
    try:
        return [int(n) for n in text.split(",") if n.strip()]
    except ValueError as exc:
        raise Refusal(f"--sections takes numbers, comma-separated: {text!r}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = OneLineParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="write the frontmatter and the section skeleton")
    p.add_argument(
        "--kind",
        default="observation",
        choices=("observation", "instrumentation"),
        help="the report kind (default observation; instrumentation is not written here yet)",
    )
    p.add_argument("--repo", default=".", help="a path inside the observed repository")
    p.add_argument("--service", action="append", default=[], help="repeatable")
    p.add_argument("--stack")
    p.add_argument("--env", help="the detected environment (local, prod, unknown, ...)")
    p.add_argument(
        "--mode",
        metavar="MODE",
        help="drive | observe | post-hoc | verify | re-measure",
    )
    p.add_argument(
        "--depth",
        metavar="DEPTH",
        help="quick | full (a replay inherits the baseline's)",
    )
    p.add_argument(
        "--window",
        metavar="START/END",
        help="<start>/<end> in UTC (YYYY-MM-DDTHH:MM:SSZ)",
    )
    p.add_argument(
        "--from",
        dest="start",
        metavar="START",
        help="the window's start, as a query script printed it",
    )
    p.add_argument(
        "--to",
        dest="end",
        metavar="END",
        help="the window's end, as a query script printed it",
    )
    p.add_argument("--run-name", help="the slug (a replay inherits the baseline's)")
    p.add_argument(
        "--verifies", help="the replayed report: a filename, or a repo-relative path"
    )
    p.add_argument("--workload")
    p.add_argument(
        "--instance", action="append", default=[], help="SERVICE=IDENTITY, repeatable"
    )
    p.add_argument(
        "--process-restarted",
        action="append",
        default=[],
        help="true | false | SERVICE=true|false",
    )
    p.add_argument(
        "--repository",
        help="a value standing in for the origin remote (a per-service map when the run spans repositories)",
    )
    p.add_argument(
        "--at", help="the filename's UTC instant when it is not the window's start"
    )
    p.add_argument(
        "--no-revision",
        action="store_true",
        help="the observed code is in no repository the run can reach",
    )

    for name, doc in (
        ("check", "the memory contract's checks, one problem per stderr line"),
        ("synthesis", "the synthesis block, quoted from the file"),
        ("show", "the closing synthesis, rendered"),
    ):
        p = sub.add_parser(name, help=doc)
        p.add_argument("path")

    p = sub.add_parser("read", help="the frontmatter and the named sections")
    p.add_argument("path")
    p.add_argument(
        "--sections", default="1,2,3,7", help="comma-separated section numbers"
    )
    p.add_argument(
        "--record",
        action="store_true",
        help="section 1 reduced to its scenario record and replay notes",
    )

    p = sub.add_parser(
        "persist", help="the work branch, the lone commit, the return value"
    )
    p.add_argument("path")
    p.add_argument(
        "--body",
        help="a draft holding the report's body (the title, the headline and the "
        "seven sections): written under the frontmatter in place of the file's body",
    )
    p.add_argument(
        "--no-commit", action="store_true", help="write nothing to git; say so"
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            path, body, notes = new_report(args)
            # the path first, then the body as written: the run replaces
            # every <fill> from this text and never reads the file back
            print(path)
            print(
                "--- the file below its frontmatter: write it filled (every <fill> "
                "replaced, the headings kept) to a draft, then persist --body it:"
            )
            print(body.rstrip())
            for note in notes:
                print(note, file=sys.stderr)
            return 0
        path = Path(args.path)
        if not path.is_file():
            raise Refusal(f"no such file: {path}")
        if args.command == "check":
            problems = check_file(path, written_now=True, body=True)
            for problem in problems:
                print(f"{path.name}: {problem}", file=sys.stderr)
            if problems:
                return 2
            print(f"{path.name}: ok")
            return 0
        text = path.read_text(encoding="utf-8")
        if args.command == "read":
            out, missing = read_sections(
                text, parse_numbers(args.sections), args.record
            )
            sys.stdout.write(out)
            for line in missing:
                print(line, file=sys.stderr)
            return 0
        if args.command in ("synthesis", "show"):
            root, rel = locate(path)
            commit = file_commit(root, rel)
            data = synthesis_data(text)
            if args.command == "synthesis":
                sys.stdout.write(f"path: {rel}\ncommit: {commit or 'not committed'}\n")
                sys.stdout.write(synthesis_text(data))
            else:
                sys.stdout.write(render_show(data, rel, commit))
            return 0
        lines, notes = persist(
            path, args.no_commit, Path(args.body) if args.body else None
        )
        sys.stdout.write("\n".join(lines) + "\n")
        for note in notes:
            print(note, file=sys.stderr)
        return 0
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
