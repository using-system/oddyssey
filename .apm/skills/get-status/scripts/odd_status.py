#!/usr/bin/env python3
"""Compute the deterministic facts behind an ODD loop status.

The get-status skill reasons on the fact sheet this script prints
instead of parsing every stored report and running git turn by turn.
The script computes facts only - frontmatters, commit boundaries,
tree-anchor diffs, the lifted tables, the decisions ledger - and never
rules on their meaning: the chain, the trends, and the recommendation
stay with the skill.

Standard library only, read-only: it never writes, never queries a
backend, never starts the stack. JSON on stdout, diagnostics on stderr.

    python3 odd_status.py [--repo PATH] [--service NAME ...] [--stack S]
                          [--env E] [--non-runtime NAME ...]
                          [--runtime NAME ...] [--section-texts 3,5]
                          [--table-sections 2,3,5] [--max-cell N]
                          [--max-text N] [--max-commits N]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA = "odd-status-facts/1"

OBSERVATION_DIR = ".odd/observe-run-reports"
INSTRUMENTATION_DIR = ".odd/otel-instrumentation-reports"
LEDGER_PATH = ".odd/decisions.md"
BENCHMARKS_DIR = ".odd/benchmarks"

# The loop's own memory: a commit touching nothing else is never a fix.
MEMORY_PATHS = (OBSERVATION_DIR, INSTRUMENTATION_DIR, LEDGER_PATH)

# Top-level tree entries that cannot change a service's runtime behavior
# in any repository: editor and CI configuration, and the documentation
# files every project carries. Conservative on purpose - a directory a
# service could live in (agents/, assets/, marketplace/, ...) is never
# listed, and anything not listed is reported as unclassified for the
# skill to decide. Matched on the lower-cased name.
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

DEFAULT_SECTION_TEXTS = (3, 5)
DEFAULT_TABLE_SECTIONS = (2, 3, 5)
# A replay (verify, re-measure) rules in its protocol section too.
REPLAY_MODES = ("verify", "re-measure")
REPLAY_TABLE_SECTIONS = (2, 3, 5, 7)
DEFAULT_MAX_CELL = 120
DEFAULT_MAX_TEXT = 1500
DEFAULT_RECENT = 3
MAX_FINDING_TITLE = 80
MAX_COMPACT_PARAGRAPH = 300
DEFAULT_MAX_RECORD = 800
DEFAULT_MAX_COMMITS = 10
MAX_CHANGED_PATHS = 10
ELLIPSIS = "…"

SECTION_RE = re.compile(r"^##\s+(\d+)\.\s*(.*?)\s*$")
FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z_][\w.-]*):(.*)$")
BENCHMARK_RE = re.compile(r"\.odd/benchmarks/([A-Za-z0-9_.-]+)")
TABLE_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")
SCENARIO_HEADING_RE = re.compile(r"^#{3,}\s+scenario record\b", re.IGNORECASE)
SCENARIO_LABEL_RE = re.compile(r"^\s*(?:-\s*)?\*\*scenario record", re.IGNORECASE)
BOLD_LABEL_RE = re.compile(r"^\s*(?:-\s*)?\*\*[A-Z]")


# --- git ------------------------------------------------------------------


def git(root: Path, *args: str) -> str | None:
    """Run git in ``root``; the stripped stdout, or None when git fails."""
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def git_root(path: Path) -> Path | None:
    top = git(path, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def head_facts(root: Path) -> dict | None:
    line = git(root, "log", "-1", "--format=%H%x1f%cI")
    if not line:
        return None
    sha, date = line.split("\x1f")
    return {"sha": sha, "date": date}


def file_commit(root: Path, rel: str) -> dict | None:
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


def ls_tree(root: Path, ref: str) -> dict[str, str] | None:
    out = git(root, "ls-tree", ref)
    if out is None:
        return None
    entries = {}
    for line in out.splitlines():
        meta, name = line.split("\t", 1)
        entries[name] = meta.split()[2]
    return entries


def changed_paths(root: Path, revision_sha: str, entry: str) -> dict:
    out = git(root, "diff", "--name-only", revision_sha, "HEAD", "--", entry) or ""
    paths = [p for p in out.splitlines() if p.strip()]
    return {"count": len(paths), "paths": paths[:MAX_CHANGED_PATHS]}


# --- frontmatter ------------------------------------------------------------


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


# --- body --------------------------------------------------------------------


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


def cap(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + ELLIPSIS, True


def cap_table(table: dict, max_cell: int) -> dict:
    truncated = 0
    rows = []
    for row in table["rows"]:
        cells = []
        for cell in row:
            cell, cut = cap(cell, max_cell)
            truncated += cut
            cells.append(cell)
        rows.append(cells)
    return {"header": table["header"], "rows": rows, "truncated_cells": truncated}


def raw_sections(body: str) -> list[dict]:
    """The numbered ``## N.`` sections, uncapped: tables and prose lines."""
    sections: list[dict] = []
    current: dict | None = None
    buffer: list[str] = []

    def close() -> None:
        if current is not None:
            current["tables"], current["lines"] = extract_tables(buffer)
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


def capped_sections(
    sections: list[dict], opts: dict, table_sections: tuple
) -> list[dict]:
    """The sections as emitted: tables and prose under the lift options."""
    out = []
    for section in sections:
        number = section["number"]
        emitted: dict[str, Any] = {"number": number, "title": section["title"]}
        if number in table_sections:
            emitted["tables"] = [
                cap_table(t, opts["max_cell"]) for t in section["tables"]
            ]
            emitted["tables_skipped"] = 0
        else:
            emitted["tables"] = []
            emitted["tables_skipped"] = len(section["tables"])
        if number in opts["section_texts"]:
            emitted["text"], emitted["text_truncated"] = cap(
                "\n".join(section["lines"]).strip(), opts["max_text"]
            )
        else:
            emitted["text"], emitted["text_truncated"] = None, False
        out.append(emitted)
    return out


def finding_ids(sections: list[dict]) -> tuple[list[str], str]:
    """The IDs section 3's tables name in their first column, and its prose.

    Computed on the uncapped section, whatever the lift options: a
    ledger row is validated against the report, not against what the
    sheet chose to show.
    """
    ids: list[str] = []
    prose = ""
    for section in sections:
        if section["number"] != 3:
            continue
        for table in section["tables"]:
            for row in table["rows"]:
                if row and row[0].strip():
                    candidate = row[0].split()[0].strip("*`")
                    if candidate and candidate not in ids:
                        ids.append(candidate)
        prose = "\n".join(section["lines"])
    return ids, prose


def column(header: list[str], pattern: str) -> int | None:
    for index, cell in enumerate(header):
        if re.search(pattern, cell, re.IGNORECASE):
            return index
    return None


def cell_at(row: list[str], index: int | None) -> str | None:
    if index is None or index >= len(row):
        return None
    return row[index].strip() or None


def findings_at_a_glance(sections: list[dict], replay: bool) -> list[dict]:
    """The findings a report names, reduced to id, title, severity, ruling.

    Section 3's rows always; on a replay, the rows of every other table
    carrying a ruling column (a verification may rule in its protocol
    table). What every report keeps whatever its detail level, so the
    ledger and the burn-down read from the compact entries too.
    """
    out: list[dict] = []
    for section in sections:
        number = section["number"]
        for table in section["tables"]:
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
                        "title": cap(title, MAX_FINDING_TITLE)[0] if title else None,
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


# --- tree anchor --------------------------------------------------------------


def is_non_runtime(name: str, extra: set[str], runtime: set[str]) -> bool:
    if name.lower() in runtime:
        return False
    return name.lower() in extra or name.lower() in NON_RUNTIME_NAMES


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
        "ignored": [],
        "unchanged": 0,
        "runtime": [],
        "non_runtime": [],
        "unclassified": [],
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
            if name.lower() in opts["runtime"]:
                diff["runtime"].append(name)
            elif is_non_runtime(name, opts["non_runtime"], opts["runtime"]):
                diff["non_runtime"].append(name)
            else:
                diff["unclassified"].append(name)
    if revision and revision["resolves"]:
        diff["changed_paths"] = {
            name: changed_paths(root, revision["sha"], name) for name in differing
        }
    return diff


# --- reports ----------------------------------------------------------------


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


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


def project_scope(root: Path, project: Any) -> str | None:
    """The repo-relative path an instrumentation ``project`` names, if any."""
    if not project:
        return None
    text = str(project).strip("/")
    for candidate in (text, text.partition("/")[2]):
        if candidate and (root / candidate).exists():
            return candidate
    return None


def parse_report(root: Path, rel: str, kind: str) -> dict:
    """Everything a report says by itself - no git yet."""
    path = root / rel
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"path": rel, "kind": kind, "unreadable": str(exc)}
    frontmatter, body, errors = split_frontmatter(text)
    sections = raw_sections(body)
    ids, section3_prose = finding_ids(sections)
    if kind == "instrumentation":
        services = instrumentation_services(sections)
    else:
        services = as_list(frontmatter.get("services"))
    return {
        "path": rel,
        "kind": kind,
        "frontmatter": frontmatter,
        "frontmatter_errors": errors,
        "services": services,
        "_body": body,
        "_sections": sections,
        "_ids": ids,
        "_section3_prose": section3_prose,
    }


def lineage_key(report: dict) -> tuple:
    """The line a report belongs to: one service set on one stack and environment."""
    fm = report["frontmatter"]
    if report["kind"] == "instrumentation":
        return ("instrumentation", str(fm.get("project")), str(fm.get("stack")))
    return (
        tuple(sorted(report["services"])),
        str(fm.get("stack")),
        str(fm.get("environment")),
    )


def assign_detail(reports: list[dict], recent: int | None) -> None:
    """The newest ``recent`` reports of each lineage are full, the rest compact."""
    by_lineage: dict[tuple, list[dict]] = {}
    for report in reports:
        if "unreadable" in report:
            continue
        by_lineage.setdefault(lineage_key(report), []).append(report)
    for line in by_lineage.values():
        cutoff = 0 if recent is None else max(len(line) - recent, 0)
        for index, report in enumerate(line):
            report["detail"] = "full" if index >= cutoff else "compact"


def compact_paragraph(text: str | None, full: bool) -> str | None:
    """A paragraph as a compact entry keeps it: cut, the cut marked."""
    if text is None or full:
        return text
    return cap(text, MAX_COMPACT_PARAGRAPH)[0]


def enrich_report(root: Path, report: dict, opts: dict) -> dict:
    """Add the git facts and the lifted body, under the report's detail level."""
    frontmatter = report["frontmatter"]
    body, sections = report.pop("_body"), report.pop("_sections")
    full = report["detail"] == "full"
    kind = report["kind"]
    commit = file_commit(root, report["path"])
    revision = resolve_revision(root, frontmatter.get("revision"))
    boundary = report_boundary(revision, commit)
    own_sha = commit["sha"] if commit else None

    anchor = frontmatter.get("tree_anchor")
    if isinstance(anchor, dict):
        frontmatter["tree_anchor"] = f"{len(anchor)} entries, see tree_anchor_diff"

    scope = (
        project_scope(root, frontmatter.get("project"))
        if kind == "instrumentation"
        else None
    )
    pathspec = [scope or "."] + [f":(exclude){p}" for p in MEMORY_PATHS]
    commits = commits_after(root, boundary, pathspec, own_sha)

    benchmarks = []
    for mention in benchmark_mentions(sections, body):
        benchmarks.append(
            {
                **mention,
                "commits_since": commits_after(
                    root, boundary, [mention["path"]], own_sha
                ),
            }
        )

    replay = str(frontmatter.get("mode")).lower() in REPLAY_MODES
    table_sections = opts["table_sections"]
    if table_sections is None:
        table_sections = REPLAY_TABLE_SECTIONS if replay else DEFAULT_TABLE_SECTIONS

    record = scenario_record(body) if full else None
    record_text, record_truncated = (
        cap(record, opts["max_record"]) if record else (None, False)
    )

    report.update(
        {
            "commit": commit,
            "revision": revision,
            "tree_anchor_diff": tree_anchor_diff(
                root, anchor, opts["head_tree"], revision if full else None, opts
            ),
            "commits_since": {
                "boundary": boundary["kind"],
                "scope": scope or "repo-wide",
                "count": None if commits is None else len(commits),
                "commits": (commits or [])[: opts["max_commits"]] if full else None,
                "truncated": full
                and bool(commits)
                and len(commits) > opts["max_commits"],
            },
            "benchmarks": benchmarks,
            "headline": compact_paragraph(headline(body), full),
            "verdict_lines": [
                compact_paragraph(p, full)
                for p in paragraphs_starting_with(body, "**Verdict")
            ],
            "scenario_record": record_text,
            "scenario_record_truncated": record_truncated,
            "finding_ids": report.pop("_ids"),
            "findings": findings_at_a_glance(sections, replay),
            "sections": capped_sections(sections, opts, table_sections) if full else [],
        }
    )
    return report


def list_reports(root: Path) -> list[tuple[str, str]]:
    found = []
    for rel_dir, kind in (
        (OBSERVATION_DIR, "observation"),
        (INSTRUMENTATION_DIR, "instrumentation"),
    ):
        directory = root / rel_dir
        if directory.is_dir():
            for path in directory.glob("*.md"):
                found.append((f"{rel_dir}/{path.name}", kind))
    return sorted(found, key=lambda item: (Path(item[0]).name, item[0]))


def matches(
    report: dict, services: list[str], stack: str | None, environment: str | None
) -> bool:
    if "unreadable" in report:
        return not services and stack is None and environment is None
    fm = report["frontmatter"]
    if services and not set(services) & set(report["services"]):
        return False
    if stack is not None and str(fm.get("stack")) != stack:
        return False
    return environment is None or (
        report["kind"] == "observation" and str(fm.get("environment")) == environment
    )


# --- ledger -----------------------------------------------------------------


def finding_known(report: dict, finding_id: str) -> bool:
    if finding_id in report["finding_ids"]:
        return True
    return bool(re.search(rf"\b{re.escape(finding_id)}\b", report["_section3_prose"]))


def load_ledger(root: Path, reports: list[dict]) -> dict:
    path = root / LEDGER_PATH
    if not path.is_file():
        return {"present": False, "rows": [], "effective": {}}
    by_name = {Path(r["path"]).name: r for r in reports if "unreadable" not in r}
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
        date, finding, verdict, rationale = cells
        row.update(date=date, finding=finding, verdict=verdict, rationale=rationale)
        report_name, sep, finding_id = finding.partition(" / ")
        report_name, finding_id = report_name.strip(), finding_id.strip()
        if not sep or not report_name or not finding_id:
            row.update(
                status="skipped",
                reason="finding is not '<report filename> / <finding ID>'",
            )
        elif report_name not in by_name:
            row.update(status="skipped", reason=f"no stored report named {report_name}")
        elif not finding_known(by_name[report_name], finding_id):
            row.update(
                status="skipped",
                reason=f"{report_name} carries no finding {finding_id}",
            )
        else:
            row["status"] = "ok"
            effective[f"{report_name} / {finding_id}"] = {
                "line": number,
                "date": date,
                "verdict": verdict,
                "rationale": rationale,
            }
        rows.append(row)
    return {"present": True, "rows": rows, "effective": effective}


# --- the fact sheet -----------------------------------------------------------


def build_facts(
    root: Path,
    services: list[str] | None = None,
    stack: str | None = None,
    environment: str | None = None,
    section_texts: tuple[int, ...] = DEFAULT_SECTION_TEXTS,
    table_sections: tuple[int, ...] | None = None,
    max_cell: int = DEFAULT_MAX_CELL,
    max_text: int = DEFAULT_MAX_TEXT,
    max_record: int = DEFAULT_MAX_RECORD,
    max_commits: int = DEFAULT_MAX_COMMITS,
    non_runtime: tuple[str, ...] = (),
    runtime: tuple[str, ...] = (),
    recent: int | None = DEFAULT_RECENT,
) -> dict:
    root = Path(root)
    services = list(services or [])
    opts = {
        "section_texts": tuple(section_texts),
        "table_sections": None if table_sections is None else tuple(table_sections),
        "max_cell": max_cell,
        "max_text": max_text,
        "max_record": max_record,
        "max_commits": max_commits,
        "non_runtime": {n.lower() for n in non_runtime},
        "runtime": {n.lower() for n in runtime},
        "head_tree": ls_tree(root, "HEAD"),
    }
    reports = [parse_report(root, rel, kind) for rel, kind in list_reports(root)]
    assign_detail(reports, recent)
    readable = [r for r in reports if "unreadable" not in r]
    for report in readable:
        enrich_report(root, report, opts)

    inventory = {
        "report_count": len(reports),
        "services": sorted({s for r in readable for s in r["services"]}),
        "stacks": sorted(
            {
                str(r["frontmatter"]["stack"])
                for r in readable
                if r["frontmatter"].get("stack")
            }
        ),
        "environments": sorted(
            {
                str(r["frontmatter"]["environment"])
                for r in readable
                if r["kind"] == "observation" and r["frontmatter"].get("environment")
            }
        ),
    }
    matched = [r for r in reports if matches(r, services, stack, environment)]
    ledger = load_ledger(root, reports)
    for report in readable:
        report.pop("_section3_prose", None)
    return {
        "schema": SCHEMA,
        "repo": str(root),
        "head": head_facts(root),
        "loop_started": bool(reports),
        "filters": {"services": services, "stack": stack, "environment": environment},
        "inventory": inventory,
        "matched": len(matched),
        "reports": matched,
        "ledger": ledger,
    }


def parse_section_texts(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in text.split(",") if n.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="a path inside the repository (default: the working directory)",
    )
    parser.add_argument(
        "--service",
        action="append",
        default=[],
        help="restrict to this service (exact name; repeatable)",
    )
    parser.add_argument("--stack", help="restrict to this stack")
    parser.add_argument(
        "--render",
        action="store_true",
        help="print the status as markdown by the skill's rules instead of the JSON facts",
    )
    parser.add_argument(
        "--today",
        help="the date the cadence rules count from, YYYY-MM-DD (default: today; with --render)",
    )
    parser.add_argument("--env", help="restrict to this deployment environment")
    parser.add_argument(
        "--non-runtime",
        action="append",
        default=[],
        help="a top-level tree entry that cannot change the service's runtime (repeatable)",
    )
    parser.add_argument(
        "--runtime",
        action="append",
        default=[],
        help="a top-level tree entry to keep out of non_runtime whatever its name (repeatable)",
    )
    parser.add_argument(
        "--section-texts",
        default=",".join(str(n) for n in DEFAULT_SECTION_TEXTS),
        help="report sections whose prose is included, comma-separated (default: 3,5)",
    )
    parser.add_argument(
        "--table-sections",
        default=None,
        help="report sections whose tables are lifted, comma-separated "
        "(default: 2,3,5, plus 7 on a verify or re-measure report)",
    )
    parser.add_argument(
        "--max-cell",
        type=int,
        default=DEFAULT_MAX_CELL,
        help="characters kept per table cell before truncation",
    )
    parser.add_argument(
        "--max-text",
        type=int,
        default=DEFAULT_MAX_TEXT,
        help="characters kept per section prose before truncation",
    )
    parser.add_argument(
        "--max-record",
        type=int,
        default=DEFAULT_MAX_RECORD,
        help="characters kept of the scenario record before truncation",
    )
    parser.add_argument(
        "--recent",
        default=None,
        help="reports lifted in full per lineage (service set, stack, environment), "
        "newest first; the rest are compact. A number, or 'all' (default: 3; "
        "not with --render)",
    )
    parser.add_argument(
        "--max-commits",
        type=int,
        default=DEFAULT_MAX_COMMITS,
        help="commits listed per report; the count is always complete",
    )
    args = parser.parse_args(argv)

    if (
        args.recent is not None
        and args.recent.lower() != "all"
        and not args.recent.isdigit()
    ):
        parser.error("--recent takes a number or 'all'")
    if args.render and args.recent is not None:
        parser.error(
            "--recent does not apply with --render: the rules read every report"
        )
    if args.today and not args.render:
        parser.error("--today only applies with --render")
    if args.recent is None:
        recent = DEFAULT_RECENT
    else:
        recent = None if args.recent.lower() == "all" else int(args.recent)
    root = git_root(Path(args.repo))
    if root is None:
        print(f"not a git repository: {Path(args.repo).resolve()}", file=sys.stderr)
        return 2
    facts = build_facts(
        root,
        services=args.service,
        stack=args.stack,
        environment=args.env,
        section_texts=parse_section_texts(args.section_texts),
        table_sections=(
            None
            if args.table_sections is None
            else parse_section_texts(args.table_sections)
        ),
        max_cell=args.max_cell,
        max_text=args.max_text,
        max_record=args.max_record,
        max_commits=args.max_commits,
        non_runtime=tuple(args.non_runtime),
        runtime=tuple(args.runtime),
        # the renderer applies the rules to every report: no window
        recent=None if args.render else recent,
    )
    if args.render:
        # the renderer lives next to this file; never leave bytecode in the skill
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import odd_render

        sys.stdout.write(odd_render.render(facts, today=args.today))
        return 0
    json.dump(facts, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
