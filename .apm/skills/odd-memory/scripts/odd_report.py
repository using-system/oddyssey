#!/usr/bin/env python3
"""The observation and instrumentation reports' deterministic steps, as one script.

The two report references used to spell out, in prose, what the
inputs already fix: the file's name (the UTC stamp, the slug, the
observer suffix, the replay prefixes, the ordinal on a collision), the
frontmatter fields a repository answers (``date``, ``revision``,
``tree_anchor``, ``repository``), the numbered sections (seven, eight
on a custom stack), the
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
    odd_report.py new --kind instrumentation --project SCOPE --stack S --run-name SLUG
                      [--genai SERVICE ...] [--repository VALUE] [--at UTC]
                      [--no-revision] [--repo PATH]
    odd_report.py check PATH
    odd_report.py read PATH [--sections 1,2,3,7] [--record]
    odd_report.py synthesis PATH
    odd_report.py show PATH
    odd_report.py persist PATH [--body DRAFT] [--no-commit]
    odd_report.py baseline [TARGET] [--service S ...] [--stack S] [--env E]
                           [--depth D] [--own-protocol] [--repo PATH]
                           (a replay's baseline, mode and depth; exit 3 with an
                           ``ask:`` line when only the user can settle it)
    odd_report.py boundary PATH [--runtime NAME ...] [--non-runtime NAME ...] [--repo PATH]
                           (verification, re-measure or undecidable - exit 3)

Standard library and git only. stdout carries the answer (a path, the
report's text, the synthesis); stderr carries the notes and the
refusals; exit 2 on a refusal, nothing written.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
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
# The eighth section, present only when the mission ran against a custom
# stack: one bullet per point of friction with the stack as shipped, or a
# `none` bullet; the frontmatter's stack_friction counts the entries.
FRICTION_NUMBER = 8
FRICTION_TITLE = "Stack friction"
FRICTION_KEY = "stack_friction"
INSTRUMENTATION_TITLES = (
    "Stack inventory",
    "Summary table",
    "Decisions made, with rationale",
    "Decisions the spec must settle",
    "Verification protocol",
)
INSTRUMENTATION_FIELDS = ("project", "stack", "run_name", "date")
SUMMARY_HEADER = [
    "Service",
    "Language + version",
    "Runtime shape",
    "Approach",
    "Signals (maturity)",
    "Key packages (pinned)",
    "OTLP endpoint",
    "Effort (S/M/L)",
    "Risk flags",
]
SUMMARY_PATTERNS = (
    r"service",
    r"language",
    r"runtime",
    r"approach",
    r"signal",
    r"package",
    r"endpoint",
    r"effort",
    r"risk",
)
CHECK_HEADER = ["Check", "Query", "Expected outcome", "Attribution evidence"]
CHECK_PATTERNS = (
    r"check|item|planned",
    r"query",
    r"expect",
    r"attribut|identity|evidence",
)
GENAI_TITLE = "GenAI approach"
# printed after the skeleton by new --kind instrumentation: what persist
# checks the draft for, so the run reads neither this file nor the check's
# code to learn the shapes
INSTRUMENTATION_RULES = (
    "--- persist checks the draft for: the title and one headline paragraph before "
    "section 1; the five headings in order, no <fill> left; section 2's table under "
    "the header row above, `Service` first, one row per service, and the "
    "`Implementation order:` line; section 5's checks as rows of the table above "
    "(or bullets `- <check> — <query> — <expected outcome> — <attribution "
    "evidence>`); no credential value in a check (an env var name, a secret "
    "reference or a <placeholder> is wiring, and passes); the GenAI approach as "
    "prose under its heading, never a table row."
)
GENAI_HEADING_RE = re.compile(r"^#{3,}\s+GenAI approach\b", re.IGNORECASE)
GENAI_CELL_RE = re.compile(r"gen\s?ai", re.IGNORECASE)
ORDER_RE = re.compile(r"implementation order", re.IGNORECASE)
# a credential written as a value: a key word, a separator, then a literal
# that is neither a variable, a placeholder nor a redaction
CREDENTIAL_RE = re.compile(
    r"(?i)(?:instrumentation[_ -]?key|connection[_ -]?string|api[_ -]?key|secret|"
    r"password|passwd|token|bearer|authorization)\s*[:=]\s*[\"']?(?:(?:bearer|basic)\s+)?"
    r"(?![$<{*`]|redacted|none|\(|from |the )([A-Za-z0-9+/=._-]{12,})"
)
# what a credential's slot may hold without being one: an env var name, a
# secret reference written as hyphenated words, a placeholder
WIRING_RE = re.compile(r"^(?:[A-Z][A-Z0-9_]{3,}|[a-z]+(?:[-_][a-z]+)+|<[^>]+>)$")
# what starts the value after a `Key=` prefix when it is wired, not written:
# a placeholder, a variable, a template - never a span delimiter (a backtick
# or an asterisk closes the span the value sits in) nor the empty string,
# which is what follows a base64 value's `=` padding
WIRING_OPENERS = ("<", "$", "{")
CREDENTIAL_PROJECTION_RE = re.compile(
    r"(?i)--query\s+\S*(?:instrumentationKey|connectionString|primaryKey|secretKey|"
    r"apiKey|accessKey)"
)
SECRET_LITERAL_RE = re.compile(
    r"\bsk-[A-Za-z0-9]{20,}|\bInstrumentationKey=[0-9a-f-]{36}"
)
FIELD_ORDER = (
    "project",
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
    "stack_friction",
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


class Ask(Exception):
    """A question only the user can answer: printed as ``ask: ...``, exit 3."""


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


# --- the code boundary: a report's revision against HEAD (shared with get-status) ---

LEDGER_PATH = ".odd/decisions.md"
CLASSIFICATIONS_PATH = ".odd/entry-classifications.md"
BENCHMARKS_DIR = ".odd/benchmarks"
CLASSES = ("runtime", "non-runtime")
EXECUTION_MODES = ("drive", "observe", "post-hoc")
# The loop's own memory: a commit touching nothing else is never a fix.
MEMORY_PATHS = (OBSERVATION_DIR, INSTRUMENTATION_DIR, LEDGER_PATH, CLASSIFICATIONS_PATH)

# Top-level tree entries that cannot change a service's runtime behavior
# in any repository: editor and CI configuration, and the documentation
# files every project carries. Conservative on purpose - a directory a
# service could live in (agents/, assets/, marketplace/, ...) is never
# listed, and anything not listed is reported as unclassified for the
# skill to decide. Matched on the lower-cased name. The repository's own
# rulings (.odd/entry-classifications.md) come before this list, and a
# flag given for one run comes before both.
NON_RUNTIME_NAMES = {
    ".editorconfig",
    ".gitattributes",
    ".github",
    ".gitignore",
    ".idea",
    ".vscode",
    "agents.md",
    "changelog",
    "changelog.md",
    "claude.md",
    "code_of_conduct.md",
    "contributing.md",
    "doc",
    "docs",
    "license",
    "license.md",
    "license.txt",
    "readme",
    "readme.md",
    "security.md",
}

MAX_CHANGED_PATHS = 10
BENCHMARK_RE = re.compile(r"\.odd/benchmarks/([A-Za-z0-9_.-]+)")
BASE_URL_RE = re.compile(r"^\W*base url\W+(\S+)", re.IGNORECASE | re.MULTILINE)
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0")


def head_facts(root: Path) -> dict | None:
    line = git(root, "log", "-1", "--format=%H%x1f%cI")
    if not line:
        return None
    sha, date = line.split("\x1f")
    return {"sha": sha, "date": date}


def added_commit(root: Path, rel: str) -> dict | None:
    """The commit that added the file - the oldest one, when re-added."""
    out = git(root, "log", "--diff-filter=A", "--format=%H%x1f%cI", "--", rel)
    if not out:
        return None
    sha, date = out.splitlines()[-1].split("\x1f")
    return {"sha": sha, "date": date}


def resolve_revision(root: Path, value: Any) -> dict | None:
    if value is None:
        return None
    text = str(value)
    sha = git(root, "rev-parse", "--verify", "--quiet", f"{text}^{{commit}}")
    return {"value": text, "resolves": bool(sha), "sha": sha or None}


def parse_log(out: str | None) -> list[dict]:
    """Commits from ``git log --format=%H%x1f%cI%x1f%s --name-only``."""
    commits: list[dict] = []
    for line in (out or "").splitlines():
        if "\x1f" in line:
            sha, date, subject = line.split("\x1f", 2)
            commits.append(
                {"sha": sha, "date": date, "subject": subject, "entries": set()}
            )
        elif line.strip() and commits:
            commits[-1]["entries"].add(line.strip().split("/", 1)[0])
    for commit in commits:
        commit["entries"] = sorted(commit["entries"])
    return commits


def commits_after(
    root: Path,
    boundary: dict,
    pathspec: list[str],
    exclude_sha: str | None = None,
) -> list[dict] | None:
    """Commits after ``boundary`` touching ``pathspec``, newest first.

    None when there is no boundary to count from. ``exclude_sha`` (the
    report's own commit) only applies to a commit-date boundary, where
    ``--since`` would count it: after a resolvable revision, the squash
    that landed both the fix and the report is a change like any other.
    """
    if boundary["kind"] == "revision":
        selector = [f"{boundary['sha']}..HEAD"]
        exclude_sha = None
    elif boundary["kind"] == "commit-date":
        selector = [f"--since={boundary['date']}"]
    else:
        return None
    out = git(
        root,
        "log",
        "--format=%H%x1f%cI%x1f%s",
        "--name-only",
        *selector,
        "--",
        *pathspec,
    )
    commits = parse_log(out)
    if exclude_sha:
        commits = [c for c in commits if c["sha"] != exclude_sha]
    return commits


def report_boundary(revision: dict | None, commit: dict | None) -> dict:
    if revision and revision["resolves"]:
        return {"kind": "revision", "sha": revision["sha"]}
    if commit:
        return {"kind": "commit-date", "date": commit["date"]}
    return {"kind": "none"}


def changed_paths(root: Path, revision_sha: str, entry: str) -> dict:
    out = git(root, "diff", "--name-only", revision_sha, "HEAD", "--", entry) or ""
    paths = [p for p in out.splitlines() if p.strip()]
    return {"count": len(paths), "paths": paths[:MAX_CHANGED_PATHS]}


def benchmark_mentions(sections: list[dict], body: str) -> list[dict]:
    """Every distinct benchmark path the body names, with the section naming it."""
    found: list[dict] = []
    seen: set[str] = set()

    def scan(text: str, number: int | None) -> None:
        for match in BENCHMARK_RE.finditer(text):
            path = f"{BENCHMARKS_DIR}/{match.group(1).rstrip('.')}"
            if path not in seen:
                seen.add(path)
                found.append({"path": path, "section": number})

    for section in sections:
        table_text = "\n".join(
            c for t in section["tables"] for r in t["rows"] for c in r
        )
        scan("\n".join(section["lines"]) + "\n" + table_text, section["number"])
    scan(body, None)
    return found


def classify_entry(name: str, opts: dict) -> tuple[str, str | None]:
    """An entry's class and the source that settled it - a flag for this run,
    the repository's classification ledger, the built-in list - or
    ``("unclassified", None)`` when none does."""
    low = name.lower()
    if low in opts["runtime"]:
        return "runtime", "flag"
    if low in opts["non_runtime"]:
        return "non-runtime", "flag"
    ruling = opts.get("classifications", {}).get(low)
    if ruling:
        return ruling["class"], "file"
    if low in NON_RUNTIME_NAMES:
        return "non-runtime", "built-in"
    return "unclassified", None


def tree_anchor_diff(
    root: Path,
    anchor: Any,
    candidate: dict[str, str] | None,
    revision: dict | None,
    opts: dict,
) -> dict | None:
    if not isinstance(anchor, dict) or candidate is None:
        return None
    diff: dict[str, Any] = {
        "candidate": "HEAD",
        "root": str(root),
        "ignored": [],
        "unchanged": 0,
        "runtime": [],
        "non_runtime": [],
        "unclassified": [],
        "classified_by": {},
        "only_in_anchor": [],
        "only_at_candidate": sorted(set(candidate) - set(anchor) - {".odd"}),
        "changed_paths": None,
    }
    if ".odd" in anchor or ".odd" in candidate:
        diff["ignored"].append(".odd")
    differing: list[str] = []
    for name, digest in sorted(anchor.items()):
        if name == ".odd":
            continue
        if name not in candidate:
            diff["only_in_anchor"].append(name)
        elif candidate[name] == str(digest):
            diff["unchanged"] += 1
        else:
            differing.append(name)
            klass, source = classify_entry(name, opts)
            if klass == "runtime":
                diff["runtime"].append(name)
            elif klass == "non-runtime":
                diff["non_runtime"].append(name)
            else:
                diff["unclassified"].append(name)
            if source:
                diff["classified_by"][name] = source
    if revision and revision["resolves"]:
        diff["changed_paths"] = {
            name: changed_paths(root, revision["sha"], name) for name in differing
        }
    return diff


def load_classifications(root: Path, head_tree: dict[str, str] | None) -> dict:
    """The entry-classification ledger, read the way the finding ledger is:
    every row reported, a bad one skipped with its reason, the latest row
    for an entry winning. Keyed on the lower-cased entry."""
    path = root / CLASSIFICATIONS_PATH
    if not path.is_file():
        return {"present": False, "rows": [], "effective": {}}
    known = {name.lower() for name in (head_tree or {})}
    rows: list[dict] = []
    effective: dict[str, dict] = {}
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.lstrip().startswith("|") or is_separator_row(line):
            continue
        cells = split_cells(line)
        if cells and cells[0].lower() == "date":
            continue
        row: dict[str, Any] = {"line": number}
        if len(cells) != 4:
            row.update(
                status="skipped",
                reason=f"expected 4 columns, got {len(cells)}",
                raw=line.strip(),
            )
            rows.append(row)
            continue
        date, entry, klass, rationale = cells
        row.update(date=date, entry=entry, **{"class": klass}, rationale=rationale)
        if klass.lower() not in CLASSES:
            row.update(
                status="skipped",
                reason=f"class is neither runtime nor non-runtime: {klass}",
            )
        elif not entry or entry.lower() not in known:
            row.update(
                status="skipped", reason=f"no top-level entry named {entry} at HEAD"
            )
        else:
            row["status"] = "ok"
            effective[entry.lower()] = {
                "line": number,
                "date": date,
                "class": klass.lower(),
                "rationale": rationale,
            }
        rows.append(row)
    return {"present": True, "rows": rows, "effective": effective}


def instrumentation_services(sections: list[dict]) -> list[str]:
    """The services an instrumentation plan covers: its summary table.

    Only a table whose first column is ``Service`` counts - a plan's
    section 2 may compare destinations or options instead.
    """
    for section in sections:
        if section["number"] != 2:
            continue
        for table in section["tables"]:
            if table["header"] and table["header"][0].strip("*` ").lower() == "service":
                return [row[0] for row in table["rows"] if row and row[0].strip()]
    return []


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
        INSTRUMENTATION_FIELDS
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


LOCAL_PATH_RE = re.compile(r"^(?:[/.~]|[A-Za-z]:[\\/])")


def local_paths(value: Any) -> list[str]:
    """The values of a ``repository`` field that name a local path."""
    values = value.values() if isinstance(value, dict) else [value]
    return [str(v) for v in values if v and LOCAL_PATH_RE.match(str(v).strip())]


def friction_entries(sections: list[dict]) -> tuple[list[str], str | None]:
    """Section 8's friction bullets (the `- ` items that are not the none
    line), and the none line when the section carries one."""
    current = section(sections, FRICTION_NUMBER)
    if current is None:
        return [], None
    entries: list[str] = []
    none: str | None = None
    for item in items(current["lines"]):
        if not item.startswith("- "):
            continue
        text = item[2:].strip()
        if NONE_RE.match(text):
            none = none or text
        elif text:
            entries.append(text)
    return entries, none


def recount_friction(path: Path) -> int | None:
    """Rewrite the frontmatter's stack_friction from section 8's bullets;
    the count, or None when the report carries no such field."""
    text = path.read_text(encoding="utf-8")
    fm, body, _ = split_frontmatter(text)
    if FRICTION_KEY not in fm:
        return None
    entries, _ = friction_entries(raw_sections(body))
    head = frontmatter_lines(text)
    rewritten = [
        f"{FRICTION_KEY}: {len(entries)}"
        if line.startswith(f"{FRICTION_KEY}:")
        else line
        for line in head
    ]
    rest = text[len("\n".join(head)) :]
    path.write_text("\n".join(rewritten) + rest, encoding="utf-8")
    return len(entries)


def check_body(report: dict, root: Path) -> list[str]:
    """What the body lacks at write time: the numbered sections, no
    placeholder left, and on a replay one ruling per baseline finding."""
    problems: list[str] = []
    body = report.get("body") or ""
    sections = raw_sections(body)
    numbers = [s["number"] for s in sections]
    fm = report.get("frontmatter") or {}
    custom = FRICTION_KEY in fm
    expected = (
        list(range(1, 8))
        if report["kind"] == "observation"
        else list(range(1, len(INSTRUMENTATION_TITLES) + 1))
    )
    if report["kind"] == "observation" and custom:
        expected.append(FRICTION_NUMBER)
    if report["kind"] == "observation" and not custom and FRICTION_NUMBER in numbers:
        problems.append(
            f"section {FRICTION_NUMBER} present but the frontmatter carries no "
            f"{FRICTION_KEY} (new --custom-stack writes it)"
        )
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
    if report["kind"] == "observation" and custom and FRICTION_NUMBER in numbers:
        entries, none = friction_entries(sections)
        if not entries and not none:
            problems.append(
                f"section {FRICTION_NUMBER} carries no bullet: one `- <friction>` per point "
                "of friction with the stack as shipped, or one `- none` bullet"
            )
        elif str(fm.get(FRICTION_KEY)) != str(len(entries)):
            problems.append(
                f"{FRICTION_KEY} reads {fm.get(FRICTION_KEY)!r} where section "
                f"{FRICTION_NUMBER} carries {len(entries)} (persist recounts it)"
            )
    lines = body.splitlines()
    first = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), len(lines))
    if not any(ln.startswith("# ") for ln in lines[:first]):
        problems.append("title absent before section 1 (a `# ` line)")
    if not any(ln.strip() and not ln.startswith("#") for ln in lines[:first]):
        problems.append("headline absent before section 1 (one paragraph)")
    if report["kind"] == "instrumentation":
        problems.extend(check_instrumentation_body(sections))
    for value in local_paths(fm.get("repository")):
        problems.append(f"repository carries a local path, never a value: {value}")
    mode = str(fm.get("mode"))
    verifies = fm.get("verifies")
    if report["kind"] == "observation" and mode in REPLAY_MODES and verifies:
        target = baseline_path(root, str(verifies))
        if "/" not in str(verifies) and target.is_file():
            base = read_report(target, "observation")
            if "unreadable" not in base:
                problems.extend(check_rulings(sections, raw_sections(base["body"])))
    return problems


def table_with(
    tables: list[dict], patterns: tuple[str, ...]
) -> tuple[dict | None, list[str]]:
    """The first table whose header carries every pattern, and what the
    closest table lacks."""
    best: dict | None = None
    best_missing: list[str] | None = None
    for table in tables:
        missing = [p for p in patterns if column(table["header"], p) is None]
        if not missing:
            return table, []
        if best_missing is None or len(missing) < len(best_missing):
            best, best_missing = table, missing
    return None, (best_missing if best is not None else list(patterns))


def replayable_checks(current: dict) -> list[list[str]]:
    """Section 5's checks in their replayable form: the rows of a table with
    the check, query, expected-outcome and attribution columns, or the
    bullets carrying four ` — ` parts."""
    table, _ = table_with(current["tables"], CHECK_PATTERNS)
    if table is not None:
        return rows_reduced(table, [(pattern, None) for pattern in CHECK_PATTERNS])
    found = []
    for item in items(current["lines"]):
        if ITEM_RE.match(item):
            parts = ITEM_RE.sub("", item).split(GAP_SPLIT)
            if len(parts) >= 4:
                found.append([p.strip() for p in parts[:4]])
    return found


def credential_in(text: str) -> str | None:
    """A credential written as a value, or None: a key word followed by a
    literal that is neither an env var name, a secret reference nor a
    placeholder; a --query projecting a credential field; a literal key."""
    for match in CREDENTIAL_RE.finditer(text):
        literal = match.group(1)
        following = text[match.end() : match.end() + 1]
        if literal.endswith(("=", ";")) and following in WIRING_OPENERS:
            continue  # a key=value prefix cut at a placeholder or a reference
        if not WIRING_RE.match(literal):
            return match.group(0)
    for regex in (CREDENTIAL_PROJECTION_RE, SECRET_LITERAL_RE):
        match = regex.search(text)
        if match:
            return match.group(0)
    return None


def check_instrumentation_body(sections: list[dict]) -> list[str]:
    """What the instrumentation body lacks: the summary table's columns, the
    replayable checks, no credential in a check, the GenAI approach as prose."""
    problems: list[str] = []
    two = section(sections, 2)
    if two is not None:
        table, missing = table_with(two["tables"], SUMMARY_PATTERNS)
        if table is not None and (
            not table["header"] or table["header"][0].strip("*` ").lower() != "service"
        ):
            problems.append(
                "section 2's summary table opens with a column other than `Service`: "
                "the status renderer counts the services off that first column"
            )
        if table is None:
            problems.append(
                "section 2 carries no summary table with the columns "
                + ", ".join(SUMMARY_HEADER)
                + (f" (missing: {', '.join(missing)})" if missing else "")
            )
        elif not [r for r in table["rows"] if r and r[0].strip()]:
            problems.append(
                "section 2's summary table carries no row (one per service)"
            )
        if not any(
            ORDER_RE.search(line) and not line.startswith("|") for line in two["lines"]
        ):
            problems.append(
                "section 2 carries no `Implementation order:` line (show renders it)"
            )
    three = section(sections, 3)
    if three is not None:
        for table in three["tables"]:
            if any(row and GENAI_CELL_RE.search(row[0]) for row in table["rows"]):
                problems.append(
                    f"section 3 renders the {GENAI_TITLE} as a table row: it is prose "
                    f"under a `### {GENAI_TITLE}` heading (a table row there reads as a "
                    "finding to the status renderer)"
                )
                break
    five = section(sections, 5)
    if five is not None:
        if not replayable_checks(five):
            problems.append(
                "section 5 carries no replayable check: a table with the columns "
                + ", ".join(CHECK_HEADER)
                + " (one row per planned item), or bullets `- <check> — <query> — "
                "<expected outcome> — <attribution evidence>`"
            )
        for line in five["raw"]:
            found = credential_in(line)
            if found:
                problems.append(
                    f"section 5 projects a credential in a check ({cap(found, 40)[0]}): "
                    "a check names the wiring - a secret reference, an env var name, "
                    "a redacted flag - never the value"
                )
                break
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
    from the baseline, their verdicts and fates left to the run - plus the
    eighth, stack friction, when the frontmatter counts it (a custom stack)."""
    lines = [f"# Observation report — {fields['run_name']}", "", PLACEHOLDER, ""]
    titles = list(SECTION_TITLES)
    if FRICTION_KEY in fields:
        titles.append(FRICTION_TITLE)
    for number, title in enumerate(titles, start=1):
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
                        f"<fill: {' / '.join(VERDICTS)}> | <fill> |"
                    )
                lines.append("")
        if number == 5 and baseline is not None and verdict_fill:
            gaps = gap_bullets(baseline)
            if gaps:
                for gap, query in gaps:
                    fate = f"<fill: {' / '.join(f for f in FATES if f != 'new')}>"
                    lines.append(f"- {gap}{GAP_SPLIT}{fate}{GAP_SPLIT}{query}".rstrip())
                lines.append("")
                continue
        lines += [PLACEHOLDER, ""]
    return "\n".join(lines)


def instrumentation_skeleton(fields: dict, genai: list[str]) -> str:
    """The body: the title, the headline placeholder, the five sections -
    section 2 opening with the summary table's header row, section 3
    carrying a `### GenAI approach` heading per service that calls a model
    (prose, never a table), section 5 opening with the checks' header row."""
    lines = [f"# Instrumentation report — {fields['run_name']}", "", PLACEHOLDER, ""]
    for number, title in enumerate(INSTRUMENTATION_TITLES, start=1):
        lines += [f"## {number}. {title}", ""]
        if number == 2:
            lines += [
                "| " + " | ".join(SUMMARY_HEADER) + " |",
                "|" + "---|" * len(SUMMARY_HEADER),
                "| " + " | ".join([PLACEHOLDER] * len(SUMMARY_HEADER)) + " |",
                "",
                f"Implementation order: {PLACEHOLDER}",
                "",
            ]
            continue
        if number == 3 and genai:
            lines += [PLACEHOLDER, ""]
            for service in genai:
                lines += [f"### {GENAI_TITLE} — {service}", "", PLACEHOLDER, ""]
            continue
        if number == 5:
            lines += [
                PLACEHOLDER,
                "",
                "| " + " | ".join(CHECK_HEADER) + " |",
                "|" + "---|" * len(CHECK_HEADER),
                "| " + " | ".join([PLACEHOLDER] * len(CHECK_HEADER)) + " |",
                "",
            ]
            continue
        lines += [PLACEHOLDER, ""]
    return "\n".join(lines)


def new_instrumentation_report(args: argparse.Namespace) -> tuple[Path, str, list[str]]:
    notes: list[str] = []
    for flag, value in (
        ("--project", args.project),
        ("--stack", args.stack),
        ("--run-name", args.run_name),
    ):
        if not value:
            raise Refusal(f"{flag} is required on an instrumentation report")
    for flag, value in (
        ("--service", args.service),
        ("--env", args.env),
        ("--mode", args.mode),
        ("--depth", args.depth),
        ("--window", args.window),
        ("--from/--to", args.start or args.end),
        ("--verifies", args.verifies),
        ("--workload", args.workload),
        ("--instance", args.instance),
        ("--process-restarted", args.process_restarted),
        ("--custom-stack", args.custom_stack),
    ):
        if value:
            raise Refusal(
                f"{flag} is an observation report's flag, not an instrumentation report's"
            )
    run_name = args.run_name
    if not SLUG_RE.match(run_name):
        raise Refusal(
            f"the run name {run_name!r} is not a slug ([a-z0-9][a-z0-9-]*, kebab-case)"
        )
    if args.no_revision:
        root = Path(args.repo).resolve()
        repo_root = None
    else:
        repo_root = git_root(Path(args.repo))
        if repo_root is None:
            raise Refusal(
                f"not a git repository: {Path(args.repo).resolve()} (--no-revision when "
                "the investigated code is in no repository the run can reach)"
            )
        root = repo_root
    now = args.at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp, date = stamp_of(now)
    store = root / INSTRUMENTATION_DIR
    candidate = run_name
    ordinal = 1
    while (store / f"{stamp}-{candidate}.md").exists():
        ordinal += 1
        candidate = f"{run_name}-{ordinal}"
    if candidate != run_name:
        notes.append(
            f"{stamp}-{run_name}.md is taken: the next free ordinal, run_name "
            f"{candidate} (section 1 names the report it sits beside)"
        )
        run_name = candidate
    path = store / f"{stamp}-{run_name}.md"
    fields: dict[str, Any] = {
        "project": args.project,
        "stack": args.stack,
        "run_name": run_name,
        "date": date,
    }
    if repo_root is not None:
        fields["revision"] = git(repo_root, "rev-parse", "--short", "HEAD")
        fields["tree_anchor"] = ls_tree(repo_root, "HEAD")
        if args.repository:
            fields["repository"] = repository_value(args.repository)
        else:
            fields["repository"] = repo_identity(repo_root)
            if fields["repository"] is None:
                notes.append(
                    "no origin remote: repository omitted (never a local path)"
                )
    elif args.repository:
        fields["repository"] = repository_value(args.repository)
    genai = [g.strip() for value in args.genai for g in value.split(",") if g.strip()]
    store.mkdir(parents=True, exist_ok=True)
    body = instrumentation_skeleton(fields, genai)
    path.write_text(format_frontmatter(fields) + "\n" + body, encoding="utf-8")
    return path, body + "\n\n" + INSTRUMENTATION_RULES, notes


def repository_value(text: str) -> Any:
    value = parse_value(text)
    for path in local_paths(value):
        raise Refusal(
            f"--repository carries a local path, never a value: {path} (the "
            "origin remote normalized, host then path; omit it with no remote)"
        )
    return value


def new_report(args: argparse.Namespace) -> tuple[Path, str, list[str]]:
    notes: list[str] = []
    if args.kind == "instrumentation":
        return new_instrumentation_report(args)
    if args.project or args.genai:
        raise Refusal("--project and --genai belong to --kind instrumentation")
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
    if args.window and (args.start or args.end):
        raise Refusal("--window and --from/--to are two forms of one value; pass one")
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
            fields["repository"] = repository_value(args.repository)
        else:
            fields["repository"] = repo_identity(repo_root)
            if fields["repository"] is None:
                notes.append(
                    "no origin remote: repository omitted (never a local path)"
                )
    elif args.repository:
        fields["repository"] = repository_value(args.repository)
    if args.workload:
        fields["workload"] = args.workload
    if args.instance:
        fields["instance"] = parse_pairs(args.instance, "--instance")
    if args.process_restarted:
        fields["process_restarted"] = parse_pairs(
            args.process_restarted, "--process-restarted", booleans=True
        )
    if args.custom_stack:
        fields[FRICTION_KEY] = 0

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


def kind_of(fm: dict) -> str:
    """An instrumentation report carries a project and no mode."""
    return "instrumentation" if "project" in fm and "mode" not in fm else "observation"


def pinned_packages(cell: str) -> list[str]:
    """The pinned packages a summary-table cell names: the comma, semicolon
    or line separated entries carrying a version."""
    parts = re.split(r"[,;]|<br\s*/?>|\n", cell)
    return [p.strip(" `*") for p in parts if p.strip() and re.search(r"\d", p)]


def instrumentation_data(fm: dict, text: str, sections: list[dict]) -> dict:
    data: dict[str, Any] = {
        "kind": "instrumentation",
        "frontmatter": fm,
        "frontmatter_lines": [
            f"tree_anchor: <{len(fm['tree_anchor'])} entries, in the file>"
            if line.startswith("tree_anchor:")
            and isinstance(fm.get("tree_anchor"), dict)
            else line
            for line in frontmatter_lines(text)
        ],
        "baseline_lines": [],
        "baseline_name": None,
        "no_baseline": False,
        "services": [],
        "approaches": {},
        "packages": 0,
        "order": None,
        "genai": [],
        "decisions": [],
        "decisions_none": None,
        "checks": [],
    }
    one = section(sections, 1)
    if one is not None:
        listed = items(one["lines"])
        found = [i for i in listed if BASELINE_LABEL_RE.match(i)] or [
            i for i in listed if BASELINE_RE.search(i)
        ]
        data["baseline_lines"] = found[:1]
        for line in found[:1]:
            match = REPORT_FILE_RE.search(line)
            if match:
                data["baseline_name"] = match.group(0)
            elif re.search(r"no previous", line, re.IGNORECASE):
                data["no_baseline"] = True
    two = section(sections, 2)
    if two is not None:
        table, _ = table_with(two["tables"], SUMMARY_PATTERNS)
        if table is not None:
            rows = rows_reduced(
                table,
                [
                    (r"service", 0),
                    (r"approach", None),
                    (r"package", None),
                    (r"effort", None),
                    (r"risk", None),
                ],
            )
            data["services"] = rows
            for row in rows:
                key = row[1].strip().strip("*`").lower() or "unstated"
                data["approaches"][key] = data["approaches"].get(key, 0) + 1
                data["packages"] += len(pinned_packages(row[2]))
        for line in two["lines"]:
            if ORDER_RE.search(line) and not line.startswith("|"):
                data["order"] = re.sub(
                    r"^\W*implementation order\W*",
                    "",
                    line.strip(),
                    flags=re.IGNORECASE,
                ).strip()
                break
    three = section(sections, 3)
    if three is not None:
        for line in three["raw"]:
            if GENAI_HEADING_RE.match(line):
                name = re.sub(
                    r"^#{3,}\s+GenAI approach\s*[—:-]?\s*",
                    "",
                    line,
                    flags=re.IGNORECASE,
                ).strip()
                data["genai"].append(name or "a service")
    four = section(sections, 4)
    if four is not None:
        listed = [i for i in items(four["lines"]) if ITEM_RE.match(i)]
        if listed:
            data["decisions"] = [ITEM_RE.sub("", i) for i in listed]
        else:
            prose = items(four["lines"])
            if prose and NONE_RE.match(prose[0]):
                data["decisions_none"] = prose[0]
            else:
                data["decisions"] = prose
    five = section(sections, 5)
    if five is not None:
        data["checks"] = replayable_checks(five)
    return data


def synthesis_data(text: str, kind: str | None = None) -> dict:
    """The synthesis inputs; ``kind`` is the store's (``report_kind``), the
    frontmatter's shape deciding only for a file outside a store."""
    fm, body, _ = split_frontmatter(text)
    sections = raw_sections(body)
    if (kind or kind_of(fm)) == "instrumentation":
        return instrumentation_data(fm, text, sections)
    mode = str(fm.get("mode"))
    replay = mode in REPLAY_MODES
    data: dict[str, Any] = {
        "kind": "observation",
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
        "custom_stack": FRICTION_KEY in fm,
        "friction": [],
        "friction_none": None,
    }
    if FRICTION_KEY in fm:
        data["friction"], data["friction_none"] = friction_entries(sections)
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


def instrumentation_synthesis_text(data: dict) -> str:
    out: list[str] = [
        "--- frontmatter",
        *data["frontmatter_lines"],
        "--- section 1: recalled baseline",
    ]
    out += data["baseline_lines"] or ["(no recalled-baseline line found in section 1)"]
    out.append(
        "--- section 2: summary table (service | approach | key packages | effort | risk)"
    )
    out += (
        table_lines(
            ["Service", "Approach", "Key packages (pinned)", "Effort", "Risk flags"],
            data["services"],
        )
        if data["services"]
        else ["(no summary table in section 2)"]
    )
    out.append("implementation order: " + (data["order"] or "(not stated)"))
    out.append("--- section 3: GenAI approach")
    out += [f"- {g}" for g in data["genai"]] or ["(none: no service calls a model)"]
    out.append("--- section 4: open decisions")
    if data["decisions"]:
        out += [f"- {d}" for d in data["decisions"]]
    else:
        out.append(data["decisions_none"] or "(none stated)")
    out.append(
        "--- section 5: replayable checks (check | query | expected | attribution)"
    )
    out += (
        table_lines(CHECK_HEADER, data["checks"])
        if data["checks"]
        else ["(no replayable check in section 5)"]
    )
    return "\n".join(out) + "\n"


def synthesis_text(data: dict) -> str:
    if data.get("kind") == "instrumentation":
        return instrumentation_synthesis_text(data)
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
    if data["custom_stack"]:
        out.append(f"--- section {FRICTION_NUMBER}: stack friction")
        if data["friction"]:
            out += [f"- {f}" for f in data["friction"]]
        else:
            out.append(data["friction_none"] or "(no bullet in section 8)")
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


# --- a replay's preflight: the baseline, the mode, the depth, the boundary -----------


def stored_reports(root: Path) -> list[dict]:
    """Every stored report of both kinds, newest first - the filenames sort
    chronologically, and the two stores interleave on them."""
    found: list[dict] = []
    for directory, kind in (
        (OBSERVATION_DIR, "observation"),
        (INSTRUMENTATION_DIR, "instrumentation"),
    ):
        store = root / directory
        if not store.is_dir():
            continue
        for path in store.glob("*.md"):
            report = read_report(path, kind)
            report["rel"] = f"{directory}/{path.name}"
            found.append(report)
    return sorted(found, key=lambda r: r["name"], reverse=True)


def report_services(report: dict) -> list[str]:
    """An observation report's ``services``; an instrumentation report's
    summary-table services (its frontmatter carries none)."""
    if report["kind"] == "instrumentation":
        return instrumentation_services(raw_sections(report["body"]))
    return as_list(report["frontmatter"].get("services"))


def verifies_value(report: dict) -> str:
    """What a replay's ``--verifies`` takes: the bare filename of an
    observation baseline, the repo-relative path of an instrumentation one."""
    return report["rel"] if report["kind"] == "instrumentation" else report["name"]


def matches_scope(
    report: dict, services: list[str], stack: str | None, environment: str | None
) -> bool:
    fm = report["frontmatter"]
    if services:
        wanted = {s.lower() for s in services}
        if not wanted & {s.lower() for s in report_services(report)}:
            return False
    if stack and str(fm.get("stack") or "").lower() != stack.lower():
        return False
    if environment:
        if report["kind"] == "instrumentation":
            return False  # carries no environment by design
        if str(fm.get("environment") or "").lower() != environment.lower():
            return False
    return True


def stored_report(root: Path, verifies: str) -> dict | None:
    """The report a ``verifies`` value names, or None when it is not stored."""
    target = baseline_path(root, verifies)
    if not target.is_file():
        return None
    kind = "instrumentation" if "/" in verifies else "observation"
    report = read_report(target, kind)
    report["rel"] = verifies if "/" in verifies else f"{OBSERVATION_DIR}/{target.name}"
    return report


def resolve_report(
    root: Path,
    target: str | None,
    services: list[str],
    stack: str | None,
    environment: str | None,
) -> dict:
    """The report the arguments name: a path, a run name (or enough of one),
    or the newest across both stores under the constraints - asking when
    the newest reports cover several services or span both kinds."""
    reports = stored_reports(root)
    unreadable = [r["name"] for r in reports if "unreadable" in r]
    reports = [r for r in reports if "unreadable" not in r]
    if not reports:
        raise Refusal(
            "nothing to verify: no report under "
            f"{OBSERVATION_DIR}/ or {INSTRUMENTATION_DIR}/"
            + (f" (unreadable: {', '.join(unreadable)})" if unreadable else "")
        )
    if target:
        wanted = Path(target)
        exact = [
            r
            for r in reports
            if r["rel"] == re.sub(r"^\./", "", target)
            or r["name"] == wanted.name
            or (wanted.exists() and Path(r["path"]).resolve() == wanted.resolve())
        ]
        if exact:
            return exact[0]
        needle = target.lower()
        candidates = [r for r in reports if needle in r["name"].lower()]
        if not candidates:
            raise Refusal(f"no stored report is named or matches {target}")
        runs = sorted(
            {str(r["frontmatter"].get("run_name") or r["name"]) for r in candidates}
        )
        if len(runs) > 1:
            raise Ask(
                f"which report is being verified - {target} matches several runs: "
                + ", ".join(runs)
            )
        return candidates[0]
    matched = [r for r in reports if matches_scope(r, services, stack, environment)]
    if not matched:
        scope = ", ".join(
            f"{k} {v}"
            for k, v in (
                ("services", ", ".join(services)),
                ("stack", stack),
                ("environment", environment),
            )
            if v
        )
        stored = sorted({s for r in reports for s in report_services(r)})
        stacks = sorted({str(r["frontmatter"].get("stack")) for r in reports})
        raise Refusal(
            f"no stored report matches {scope}; stored: services "
            f"{', '.join(stored) or 'none'}; stacks {', '.join(stacks) or 'none'}"
        )
    # the newest reports: the ones of the newest day, and the newest of the
    # other kind when the stores hold both - several services or two kinds
    # among them is the user's call
    newest_day = matched[0]["name"][:10]
    newest = [r for r in matched if r["name"][:10] == newest_day]
    for report in matched:
        if report["kind"] != matched[0]["kind"]:
            newest.append(report)
            break
    lineages: dict[tuple, dict] = {}
    for report in newest:
        key = (
            report["kind"],
            tuple(sorted(s.lower() for s in report_services(report))),
        )
        lineages.setdefault(key, report)  # the newest of each
    if len(lineages) > 1:
        raise Ask(
            "which report is being verified - the newest reports cover several "
            "services or span both kinds: "
            + "; ".join(
                f"{r['rel']} ({r['kind']}, {', '.join(report_services(r)) or 'no service'})"
                for r in lineages.values()
            )
        )
    return matched[0]


def replay_prefix(name: str) -> str | None:
    """``verify`` or ``re-measure`` when the filename carries the replay
    prefix - a pre-convention verification says so by name alone."""
    match = REPORT_NAME_RE.match(name)
    slug = match.group(2) if match else ""
    for mode, prefix in PREFIXES.items():
        if slug.startswith(prefix):
            return mode
    return None


def hop_to_baseline(root: Path, resolved: dict, own_protocol: bool) -> tuple[dict, str]:
    """The baseline: the report itself, or - when the resolved report is a
    verification or a re-measure - the one its ``verifies`` names, exactly
    one hop; ``own_protocol`` is the carve-out that makes a verification's
    own protocol the baseline."""
    fm = resolved["frontmatter"]
    mode = str(fm.get("mode") or "").lower()
    by_name = replay_prefix(resolved["name"])
    replay = resolved["kind"] == "observation" and (mode in REPLAY_MODES or by_name)
    what = mode if mode in REPLAY_MODES else f"{by_name} by name"
    if own_protocol:
        if not replay:
            raise Refusal(
                f"--own-protocol applies to a verification or a re-measure; "
                f"{resolved['name']} is {mode or 'an instrumentation report'}"
            )
        return resolved, f"the {what}'s own protocol (the carve-out)"
    if not replay:
        return resolved, "the resolved report itself"
    verifies = fm.get("verifies")
    if not verifies:
        raise Ask(
            f"{resolved['name']} is a {what} with no verifies field (a "
            "pre-convention report): name the observation report to verify against"
        )
    baseline = stored_report(root, str(verifies))
    if baseline is None:
        raise Ask(
            f"{resolved['name']} verifies {verifies}, which is no longer stored: "
            "name the report to verify against"
        )
    if "unreadable" in baseline:
        raise Refusal(f"{verifies} cannot be read: {baseline['unreadable']}")
    return baseline, f"one hop from {resolved['name']} ({what})"


def walk_mode(root: Path, baseline: dict) -> tuple[str, str]:
    """The execution mode to replay: the baseline's when it has one, else the
    first report the ``verifies`` chain reaches whose mode is one - an
    instrumentation report at the chain's end means ``drive``."""
    current, hops, seen = baseline, 0, {baseline["name"]}
    while True:
        if current["kind"] == "instrumentation":
            return "drive", (
                "an instrumentation baseline"
                if hops == 0
                else f"the chain reaches an instrumentation report: {current['name']}"
            )
        mode = str(current["frontmatter"].get("mode") or "").lower()
        if mode in EXECUTION_MODES:
            return mode, (
                "the baseline's frontmatter"
                if hops == 0
                else f"walked {hops} hop{'s' if hops > 1 else ''} to {current['name']}"
            )
        if mode not in REPLAY_MODES:
            raise Ask(
                f"{current['name']} carries no execution mode ({mode or 'no mode'}, a "
                "pre-convention report): say which mode to replay - drive, observe "
                "or post-hoc"
            )
        verifies = current["frontmatter"].get("verifies")
        if not verifies:
            raise Ask(
                f"the verifies chain ends at {current['name']} ({mode}, no verifies): "
                "say which mode to replay - drive, observe or post-hoc"
            )
        nxt = stored_report(root, str(verifies))
        if nxt is None or "unreadable" in nxt or nxt["name"] in seen:
            raise Ask(
                f"the verifies chain ends at {current['name']}: it verifies "
                f"{verifies}, which is not stored - say which mode to replay"
            )
        seen.add(nxt["name"])
        current, hops = nxt, hops + 1


def replay_depth(baseline: dict, override: str | None) -> tuple[str, str]:
    if override:
        return override, "the argument"
    if baseline["kind"] == "instrumentation":
        return "full", "an instrumentation baseline replays every signal"
    depth = baseline["frontmatter"].get("depth")
    if depth is None:
        return "quick", (
            "the baseline predates the depth field (it ran full); say `full verify` "
            "to replay at the protocol it ran"
        )
    return str(depth), "the baseline's depth field"


def recorded_target(body: str) -> str | None:
    """The record's base URL, when it recorded one (``n/a`` is none)."""
    record = scenario_record(body) or ""
    match = BASE_URL_RE.search(record)
    if not match:
        return None
    value = match.group(1).strip("`*,;")
    return value if "://" in value else None


def is_local_target(url: str) -> bool:
    host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", url, flags=re.IGNORECASE)
    host = host.split("/", 1)[0].split("@")[-1]
    host = re.sub(r":\d+$", "", host)
    return host.lower() in LOCAL_HOSTS


def baseline_facts(root: Path, args: argparse.Namespace) -> dict:
    resolved = resolve_report(root, args.target, args.service, args.stack, args.env)
    baseline, how = hop_to_baseline(root, resolved, args.own_protocol)
    mode, mode_why = walk_mode(root, baseline)
    depth, depth_why = replay_depth(baseline, args.depth)
    fm = baseline["frontmatter"]
    sections = raw_sections(baseline["body"])
    benchmarks = [m["path"] for m in benchmark_mentions(sections, baseline["body"])]
    target = (
        recorded_target(baseline["body"]) if baseline["kind"] == "observation" else None
    )
    stack = str(fm.get("stack") or "")
    if mode != "drive":
        confirmation = f"not needed (mode {mode})"
    elif stack != "local":
        confirmation = f"required: the stack {stack} is not local"
    elif target and not is_local_target(target):
        confirmation = f"required: the recorded target {target} is not local"
    elif target:
        confirmation = "not needed (local stack, local target)"
    else:
        confirmation = "not needed (local stack, no recorded target)"
    return {
        "report": resolved["rel"],
        "baseline": baseline["rel"],
        "kind": baseline["kind"],
        "how": how,
        "verifies": verifies_value(baseline),
        "services": report_services(baseline),
        "stack": stack,
        "environment": (
            None if baseline["kind"] == "instrumentation" else fm.get("environment")
        ),
        "mode": mode,
        "mode_why": mode_why,
        "depth": depth,
        "depth_why": depth_why,
        "revision": fm.get("revision"),
        "benchmarks": benchmarks,
        "target": target,
        "confirmation": confirmation,
    }


def render_baseline(facts: dict) -> str:
    env = facts["environment"]
    lines = [
        f"report: {facts['report']}",
        f"baseline: {facts['baseline']} ({facts['kind']}, {facts['how']})",
        f"verifies: {facts['verifies']}",
        f"services: {', '.join(facts['services']) or 'none named'}",
        f"stack: {facts['stack'] or 'none'}",
        "environment: "
        + (
            "none (an instrumentation report carries no environment: the comparison "
            "is skipped, the run records the one it detects)"
            if facts["kind"] == "instrumentation"
            else str(env or "none")
        ),
        f"mode: {facts['mode']} ({facts['mode_why']})",
        f"depth: {facts['depth']} ({facts['depth_why']})",
        f"revision: {facts['revision'] or 'none'}",
        f"benchmark: {', '.join(facts['benchmarks']) or 'none named'}",
        f"target: {facts['target'] or 'not recorded'}",
        f"drive confirmation: {facts['confirmation']}",
    ]
    return "\n".join(lines) + "\n"


def porcelain_entries(root: Path) -> dict[str, list[str]]:
    """The working tree's uncommitted paths by top-level entry - ``.odd``
    included, for the benchmark a record names; the caller leaves the rest
    of the loop's own memory out."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "-z"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return {}
    if proc.returncode != 0:
        return {}
    # -z: "XY path\0", a rename adding its source as the next token; the
    # output is never stripped - the first status letter may be a space
    entries: dict[str, list[str]] = {}
    source_next = False
    for token in proc.stdout.split("\0"):
        if source_next:  # a rename's source: that entry lost a file
            source_next = False
            top = token.split("/", 1)[0]
            if top:
                entries.setdefault(top, []).append(token)
            continue
        if len(token) < 4:
            continue
        status, path = token[:2], token[3:]
        source_next = status[0] in "RC"
        top = path.split("/", 1)[0]
        if top:
            entries.setdefault(top, []).append(path)
    return entries


def classify_names(names: list[str], opts: dict) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "runtime": [],
        "non-runtime": [],
        "unclassified": [],
    }
    for name in sorted(set(names)):
        klass, _ = classify_entry(name, opts)
        groups[klass].append(name)
    return groups


def boundary_facts(root: Path, path: Path, args: argparse.Namespace) -> dict:
    """Verification, re-measure or undecidable: the baseline's tree anchor
    against HEAD entry by entry, the working tree, and the benchmark the
    record names - the git walk only when the anchor is absent."""
    kind = report_kind(path)
    if kind is None:
        raise Refusal(f"{path} is not a stored report")
    store_root, rel = locate(path)
    if store_root is None:
        raise Refusal(f"{path} is in no git repository")
    report = read_report(path, kind)
    if "unreadable" in report:
        raise Refusal(f"{path.name} cannot be read: {report['unreadable']}")
    fm = report["frontmatter"]
    head_tree = ls_tree(root, "HEAD")
    if head_tree is None:
        raise Refusal(f"{root} has no HEAD to compare the baseline against")
    notes: list[str] = []
    identities = sorted(
        {i for i in (normalize_remote(str(v)) for v in _repository_values(fm)) if i}
    )
    own = repo_identity(root)
    if identities and own and any(i != own for i in identities):
        raise Refusal(
            f"the baseline names the repository {', '.join(identities)}; --repo is "
            f"{own} - run this in that repository's clone"
        )
    if identities and own is None:
        notes.append(
            f"the baseline names the repository {', '.join(identities)}; --repo has no "
            "origin to prove it is the same one"
        )
    opts = {
        "runtime": {n.lower() for n in args.runtime},
        "non_runtime": {n.lower() for n in args.non_runtime},
        "classifications": load_classifications(store_root, head_tree)["effective"],
    }
    revision = resolve_revision(root, fm.get("revision"))
    anchor = fm.get("tree_anchor")
    head_short = git(root, "rev-parse", "--short", "HEAD") or "HEAD"
    differing: dict[str, list[str]] = {}
    one_sided: list[str] = []
    differing_unit = "paths"
    if isinstance(anchor, dict):
        diff = tree_anchor_diff(root, anchor, head_tree, revision, opts)
        method = f"tree anchor ({len(anchor)} entries) against HEAD {head_short}"
        groups = classify_names(
            diff["runtime"] + diff["non_runtime"] + diff["unclassified"], opts
        )
        # an entry on one side only - added or removed since the anchor -
        # stays uncertain whatever its ruling (the ledger's rule)
        one_sided = sorted(set(diff["only_in_anchor"]) | set(diff["only_at_candidate"]))
        if diff["changed_paths"]:
            differing = {k: v["paths"] for k, v in diff["changed_paths"].items()}
    elif revision and revision["resolves"]:
        out = git(root, "diff", "--name-only", revision["sha"], "HEAD") or ""
        for p in out.splitlines():
            if p.strip() and p.split("/", 1)[0] != ".odd":
                differing.setdefault(p.split("/", 1)[0], []).append(p)
        groups = classify_names(list(differing), opts)
        method = (
            f"no tree anchor: the tree at {revision['value']} against HEAD {head_short}"
        )
    else:
        commit = added_commit(store_root, rel)
        if commit is None:
            raise Ask(
                f"{path.name} carries no tree anchor, "
                + (
                    f"its revision {fm.get('revision')} does not resolve"
                    if fm.get("revision")
                    else "no revision"
                )
                + " and the file is not committed: nothing fixes the boundary - say "
                "whether the code changed since the baseline"
            )
        boundary = report_boundary(None, commit)
        commits = (
            commits_after(
                root,
                boundary,
                ["."] + [f":(exclude){m}" for m in MEMORY_PATHS],
                commit["sha"],
            )
            or []
        )
        for c in commits:
            for entry in c["entries"]:
                if entry != ".odd":
                    differing.setdefault(entry, []).append(c["sha"][:7])
        differing_unit = "commits"
        groups = classify_names(list(differing), opts)
        method = (
            f"no tree anchor, revision {fm.get('revision') or 'absent'} unresolvable: "
            f"the {len(commits)} commit(s) since the report's own commit date "
            f"{commit['date']}"
        )
    uncommitted = porcelain_entries(root)
    memory_paths = uncommitted.pop(".odd", [])  # a report being written, a ledger
    dirty = uncommitted
    dirty_groups = classify_names(list(dirty), opts)
    sections = raw_sections(report["body"])
    benchmarks = []
    own_commit = added_commit(store_root, rel)
    bench_boundary = report_boundary(revision, own_commit)
    for mention in benchmark_mentions(sections, report["body"]):
        bpath = mention["path"]
        # commits since the revision, else since the report's own commit
        # date (its own commit ignored) - the same boundary as the code's
        since = commits_after(
            store_root,
            bench_boundary,
            [bpath],
            own_commit["sha"] if own_commit else None,
        )
        touched = [p for p in memory_paths if p == bpath or p.startswith(bpath + "/")]
        benchmarks.append({"path": bpath, "commits": since, "dirty": touched})
    benchmark_changed = any(b["commits"] or b["dirty"] for b in benchmarks)
    if groups["runtime"] or dirty_groups["runtime"] or benchmark_changed:
        verdict = "verification"
    elif groups["unclassified"] or dirty_groups["unclassified"] or one_sided:
        verdict = "undecidable"
    else:
        verdict = "re-measure"
    return {
        "verdict": verdict,
        "baseline": rel,
        "revision": revision,
        "method": method,
        "groups": groups,
        "differing": differing,
        "differing_unit": differing_unit,
        "one_sided": one_sided,
        "dirty": dirty,
        "dirty_groups": dirty_groups,
        "benchmarks": benchmarks,
        "notes": notes,
    }


def _repository_values(fm: dict) -> list[str]:
    value = fm.get("repository")
    if isinstance(value, dict):
        return [str(v) for v in value.values() if v]
    return [str(value)] if value else []


def render_boundary(facts: dict) -> str:
    groups, differing = facts["groups"], facts["differing"]

    unit = facts["differing_unit"]

    def entries(names: list[str]) -> str:
        if not names:
            return "none"
        parts = []
        for name in names:
            paths = differing.get(name) or []
            parts.append(
                f"{name} ({plural(len(paths), unit[:-1])}: {', '.join(paths[:3])})"
                if paths
                else name
            )
        return ", ".join(parts)

    dirty = facts["dirty"]
    dirty_text = "clean"
    if dirty:
        dirty_text = "dirty: " + ", ".join(
            f"{name} ({klass}: {', '.join(dirty[name][:3])})"
            for klass in ("runtime", "unclassified", "non-runtime")
            for name in facts["dirty_groups"][klass]
        )
    bench_lines = []
    for b in facts["benchmarks"]:
        if b["commits"] is None and not b["dirty"]:
            state = "no boundary to count commits from"
        elif b["commits"] or b["dirty"]:
            state = (
                f"changed: {len(b['commits'] or [])} commit(s) since the baseline"
                + (f", {len(b['dirty'])} uncommitted path(s)" if b["dirty"] else "")
            )
        else:
            state = "unchanged since the baseline"
        bench_lines.append(f"{b['path']}: {state}")
    revision = facts["revision"]
    rev_text = "none"
    if revision:
        rev_text = revision["value"] + (
            "" if revision["resolves"] else " (does not resolve here)"
        )
    persist = {
        "verification": "--mode verify",
        "re-measure": "--mode re-measure",
        "undecidable": "undecided",
    }[facts["verdict"]]
    if facts["verdict"] == "undecidable":
        reasons = []
        if groups["unclassified"] or facts["dirty_groups"]["unclassified"]:
            reasons.append(
                "until the unclassified entries are ruled - "
                '/odd-status "<entry> is runtime | non-runtime" records the ruling, '
                "--runtime/--non-runtime holds for this run"
            )
        if facts["one_sided"]:
            reasons.append(
                "no ruling settles an entry present on one side only - ask the "
                "user which of the two the mission is"
            )
        persist += ": " + "; ".join(reasons)
    lines = [
        f"boundary: {facts['verdict']}",
        f"baseline: {facts['baseline']}",
        f"revision: {rev_text}",
        f"method: {facts['method']}",
        f"runtime entries differing: {entries(groups['runtime'])}",
        "non-runtime entries differing (ignored): "
        + (", ".join(groups["non-runtime"]) or "none"),
        f"unclassified entries differing: {entries(groups['unclassified'])}",
        "entries present on one side only (uncertain): "
        + (", ".join(facts["one_sided"]) or "none"),
        f"working tree: {dirty_text}",
        "benchmark: " + ("; ".join(bench_lines) if bench_lines else "none named"),
        f"persist: {persist}",
    ]
    lines.extend(f"note: {n}" for n in facts["notes"])
    return "\n".join(lines) + "\n"


# --- show ------------------------------------------------------------------------


def plural(count: int, noun: str, nouns: str | None = None) -> str:
    return f"{count} {noun if count == 1 else (nouns or noun + 's')}"


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


def dominant_approach(approaches: dict) -> str:
    if not approaches:
        return "no"
    name, count = max(approaches.items(), key=lambda kv: (kv[1], kv[0]))
    return (
        name
        if count * 2 > sum(approaches.values()) or len(approaches) == 1
        else "mixed"
    )


def render_instrumentation_headline(data: dict) -> str:
    text = (
        f"{plural(len(data['services']), 'service')}, "
        f"{dominant_approach(data['approaches'])} approach, "
        f"{plural(data['packages'], 'pinned package')}, "
        f"{plural(len(data['decisions']), 'decision')} open"
    )
    if data["genai"]:
        text += f", GenAI approach for {plural(len(data['genai']), 'service')}"
    if data["baseline_name"]:
        text += f", vs baseline {data['baseline_name']}"
    elif data["no_baseline"]:
        text += ", no previous report"
    return f"**{text}**"


def render_instrumentation_show(data: dict, rel: str, commit: str | None) -> str:
    fm = data["frontmatter"]
    out = [render_instrumentation_headline(data), ""]
    out.append(
        f"Stored at `{rel}` — " + (f"commit {commit}" if commit else "not committed")
    )
    out.append("")
    run = [("project", fm.get("project")), ("stack", fm.get("stack"))]
    if fm.get("revision"):
        run.append(("revision", fm.get("revision")))
    if fm.get("repository"):
        run.append(("repository", format_value(fm.get("repository"))))
    run.append(("baseline", data["baseline_name"] or "none"))
    out += [f"{key}: {value}" for key, value in run]
    out.append("")
    rows = [
        [
            cap(r[0], MAX_CELL)[0],
            cap(r[1], MAX_CELL)[0],
            cap(r[2], MAX_TITLE_CELL)[0],
            cap(r[3], MAX_CELL)[0],
            cap(r[4], MAX_CELL)[0],
        ]
        for r in data["services"]
    ]
    out += table_lines(
        ["Service", "Approach", "Key packages (pinned)", "Effort", "Risk flags"],
        rows,
        MAX_ROWS,
    )
    if data["order"]:
        out.append(f"Implementation order: {cap(data['order'], MAX_LINE)[0]}")
    out.append("")
    if data["genai"]:
        out.append(
            f"GenAI approach (section 3, prose): {', '.join(data['genai'][:MAX_ROWS])}"
        )
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
    out.append(
        f"Verification protocol: {plural(len(data['checks']), 'replayable check')} in "
        "section 5 — /odd-verify replays them once the instrumentation lands"
    )
    out.append("")
    if count:
        out.append(
            f"Next: settle the {plural(count, 'open decision')}, then build the "
            "spec-driven instrumentation plan from the report."
        )
    else:
        out.append(
            "Next: build the spec-driven instrumentation plan from the report; "
            "replay its protocol with /odd-verify once the instrumentation lands."
        )
    return "\n".join(out) + "\n"


def render_headline(data: dict) -> str:
    if data.get("kind") == "instrumentation":
        return render_instrumentation_headline(data)
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
            text = (
                f"verify — {plural(len(data['rulings']), 'baseline finding')} ruled, "
                "no check table"
            )
    elif mode == "re-measure":
        passed, failed, unruled = verdict_counts(data["checks"])
        total = len(data["checks"])
        text = (
            f"{'drift' if failed else 'no drift'} — {passed}/{total} checks within range"
            if total
            else f"re-measure — {plural(len(data['findings']), 'finding')} re-measured"
        )
    else:
        text = (
            f"{plural(len(findings), 'anomaly', 'anomalies')} ({high} high, "
            f"{confirmed} confirmed), {plural(gaps, 'telemetry gap')}"
        )
        if data["baseline_name"]:
            text += f", vs baseline {data['baseline_name']}"
        elif data["no_baseline"]:
            text += ", no previous report"
    if data["quick"]:
        summary = not_queried_summary(data["not_queried"])
        text = f"quick — {text}" + (f", {summary}" if summary else "")
    return f"**{text}**"


def render_show(data: dict, rel: str, commit: str | None) -> str:
    if data.get("kind") == "instrumentation":
        return render_instrumentation_show(data, rel, commit)
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
        if data["mode"] == "re-measure" or not (data["checks"] or data["rulings"]):
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
    if data["custom_stack"]:
        out.append("")
        friction = len(data["friction"])
        out.append(
            f"Stack friction: {friction}"
            + (
                " — /odd-instrument-stack from report fixes the stack from them"
                if friction
                else (
                    " — every backend call went through a shipped invocation, "
                    "and each answered as its guide states"
                )
            )
        )
        for entry in data["friction"][:MAX_ROWS]:
            out.append(f"- {cap(entry, MAX_LINE)[0]}")
        if friction > MAX_ROWS:
            out.append(f"+{friction - MAX_ROWS} more in the report")
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
        return (
            f"settle the {plural(len(data['decisions']), 'open decision')}, then "
            "build the fix plan from the report; replay its protocol with "
            "/odd-verify once the fix lands."
        )
    return "build the fix plan from the report; replay its protocol with /odd-verify once the fix lands."


# --- persist ---------------------------------------------------------------------


def splice_body(path: Path, draft: Path) -> list[str]:
    """The draft's text under the report's frontmatter, replacing the body.

    The run writes its sections to a draft with its file tool and
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
    before = path.read_text(encoding="utf-8")
    head = frontmatter_lines(before)
    if not head:
        raise Refusal(f"{path.name} carries no frontmatter to keep; run new first")
    path.write_text("\n".join(head) + "\n\n" + text.strip() + "\n", encoding="utf-8")
    counted = recount_friction(path)
    if counted is not None:
        notes.append(f"{FRICTION_KEY}: {counted} (section {FRICTION_NUMBER} recounted)")
    frontmatter_problems = check_file(path, written_now=True)
    problems = check_file(path, written_now=True, body=True)
    if problems:
        # the file keeps what new wrote - a replay's pre-filled rulings and
        # gaps included - and the draft is what the run fixes; a problem of
        # the frontmatter is the file's, never the draft's
        path.write_text(before, encoding="utf-8")
        raise Refusal(
            f"the report could not be persisted - {path.name} kept as new wrote "
            "it, fix what each line names and persist again:\n"
            + "\n".join(
                f"  {path.name if p in frontmatter_problems or p.startswith('repository ') else draft.name}: {p}"
                for p in problems
            )
        )
    return notes


def persist(
    path: Path, no_commit: bool, body: Path | None = None
) -> tuple[list[str], list[str]]:
    """The return value's lines (stdout) and the notes (stderr)."""
    spliced = splice_body(path, body) if body is not None else []
    # a spliced draft was checked as it landed; a file persisted as it is is checked here
    problems = [] if body is not None else check_file(path, written_now=True, body=True)
    if problems:
        raise Refusal(
            "the report does not follow the memory contract - fix it before "
            "persisting:\n" + "\n".join(f"  {path.name}: {p}" for p in problems)
        )
    text = path.read_text(encoding="utf-8")
    fm, _, _ = split_frontmatter(text)
    run_name = str(fm.get("run_name"))
    mode = str(fm.get("mode"))
    kind = report_kind(path) or "observation"
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
        target = (
            f"docs/odd-instrumentation-report-{run_name}"
            if kind == "instrumentation"
            else f"docs/odd-observe-run-report-{run_name}"
        )
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
                f"docs(odd): instrumentation investigation {run_name}"
                if kind == "instrumentation"
                else f"docs(odd): {SUBJECTS.get(mode, 'observation report')} {run_name}"
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
    # the headline alone: the caller's show renders the synthesis from the
    # file once, so the block never travels through two more contexts
    lines.append(f"headline: {render_headline(synthesis_data(text, kind))}")
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
        help="the report kind (default observation)",
    )
    p.add_argument("--repo", default=".", help="a path inside the observed repository")
    p.add_argument(
        "--project",
        help="instrumentation: what was investigated (the repository, or a path in it)",
    )
    p.add_argument(
        "--genai",
        action="append",
        default=[],
        help="instrumentation: a service that calls a model (repeatable) - section 3 "
        "opens a `### GenAI approach` heading for it",
    )
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
    p.add_argument(
        "--custom-stack",
        action="store_true",
        help="the stack is a custom one: the report carries section 8, stack friction, "
        "and the frontmatter counts its entries",
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
        "--sections",
        default=None,
        help="comma-separated section numbers (default 1,2,3,7 on an observation "
        "report, 1,2,4,5 on an instrumentation one)",
    )
    p.add_argument(
        "--record",
        action="store_true",
        help="section 1 reduced to its scenario record and replay notes",
    )

    p = sub.add_parser(
        "baseline",
        help="a replay's baseline, verifies value, mode and depth (exit 3: ask)",
    )
    p.add_argument("target", nargs="?", help="a report path, or enough of a run name")
    p.add_argument("--repo", default=".", help="a path inside the repository")
    p.add_argument("--service", action="append", default=[], help="repeatable")
    p.add_argument("--stack")
    p.add_argument("--env", help="the deployment environment the baseline ran on")
    p.add_argument("--depth", choices=DEPTHS, help="the argument's depth, which wins")
    p.add_argument(
        "--own-protocol",
        action="store_true",
        help="the carve-out: a verification's own protocol is the baseline",
    )

    p = sub.add_parser(
        "boundary",
        help="verification, re-measure or undecidable, from the baseline's tree "
        "anchor (exit 3: undecidable)",
    )
    p.add_argument("path", help="the baseline report")
    p.add_argument("--repo", default=".", help="a path inside the observed repository")
    p.add_argument(
        "--runtime",
        action="append",
        default=[],
        help="an entry ruled runtime, this run",
    )
    p.add_argument(
        "--non-runtime",
        action="append",
        default=[],
        help="an entry ruled non-runtime, this run",
    )

    p = sub.add_parser(
        "persist", help="the work branch, the lone commit, the return value"
    )
    p.add_argument("path")
    p.add_argument(
        "--body",
        help="a draft holding the report's body (the title, the headline and the "
        "sections - seven, eight on a custom stack; five on an instrumentation "
        "report): written under the frontmatter in place of the file's body",
    )
    p.add_argument(
        "--no-commit", action="store_true", help="write nothing to git; say so"
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            path, body, notes = new_report(args)
            # the path first, then the body as written (plus, for the
            # instrumentation kind, the rules footer that never reaches the
            # file): the run replaces every <fill> from this text and never
            # reads the file back
            print(path)
            print(
                "--- the file below its frontmatter: write it filled (every <fill> "
                "replaced, the headings kept) to a draft, then persist --body it:"
            )
            print(body.rstrip())
            for note in notes:
                print(note, file=sys.stderr)
            return 0
        if args.command in ("baseline", "boundary"):
            root = git_root(Path(args.repo))
            if root is None:
                raise Refusal(f"not a git repository: {Path(args.repo).resolve()}")
            if args.command == "baseline":
                sys.stdout.write(render_baseline(baseline_facts(root, args)))
                return 0
            path = Path(args.path)
            if not path.is_file():
                raise Refusal(f"no such file: {path}")
            facts = boundary_facts(root, path, args)
            sys.stdout.write(render_boundary(facts))
            return 3 if facts["verdict"] == "undecidable" else 0
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
            numbers = args.sections or (
                "1,2,4,5" if report_kind(path) == "instrumentation" else "1,2,3,7"
            )
            out, missing = read_sections(text, parse_numbers(numbers), args.record)
            sys.stdout.write(out)
            for line in missing:
                print(line, file=sys.stderr)
            return 0
        if args.command in ("synthesis", "show"):
            root, rel = locate(path)
            commit = file_commit(root, rel)
            data = synthesis_data(text, report_kind(path))
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
    except Ask as exc:
        print(f"ask: {exc}")
        return 3
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
