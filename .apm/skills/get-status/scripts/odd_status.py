#!/usr/bin/env python3
"""Compute the deterministic facts behind an ODD loop status.

The get-status skill reasons on the fact sheet this script prints
instead of parsing every stored report and running git turn by turn.
The script computes facts only - frontmatters, commit boundaries,
tree-anchor diffs, the lifted tables, the ruling ledgers - and never
rules on their meaning: the chain, the trends, and the recommendation
stay with the skill.

Standard library only, read-only: it never writes, never queries a
backend, never starts the stack. JSON on stdout, diagnostics on stderr.

    python3 odd_status.py [--repo PATH] [--service NAME ...] [--stack S]
                          [--env E] [--non-runtime NAME ...]
                          [--runtime NAME ...] [--section-texts 3,5]
                          [--table-sections 2,3,5] [--max-cell N]
                          [--max-text N] [--max-commits N]
    python3 odd_status.py --render [--full] [--ruled REPORT/ID=STATE ...] ...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# The report format is written and read by one module, odd-memory's
# odd_report.py. The skills deploy side by side under one skills root on
# every host (package-layout), so the sibling resolves from this file's
# own location - and an install that dropped it is refused in one line.
sys.dont_write_bytecode = True  # never leave bytecode in the package
_ODD_MEMORY_SCRIPTS = Path(__file__).resolve().parents[2] / "odd-memory" / "scripts"
if not (_ODD_MEMORY_SCRIPTS / "odd_report.py").is_file():
    print(
        "odd_status.py: the odd-memory skill is not installed beside get-status "
        f"(no {_ODD_MEMORY_SCRIPTS / 'odd_report.py'}) - the two skills deploy side by "
        "side; install the package whole",
        file=sys.stderr,
    )
    sys.exit(2)
sys.path.insert(0, str(_ODD_MEMORY_SCRIPTS))
import odd_report
from odd_report import (
    LEGACY_PREFIX,
    MAX_FINDING_TITLE,
    OBSERVATION_MODES,
    REPLAY_MODES,
    as_list,
    cap,
    check_report,
    finding_ids,
    findings_at_a_glance,
    git,
    git_root,
    headline,
    is_separator_row,
    ls_tree,
    normalize_remote,
    paragraphs_starting_with,
    raw_sections,
    repo_identity,
    scenario_record,
    split_cells,
    split_frontmatter,
)

OBSERVATION_MODES_ALL = OBSERVATION_MODES
ELLIPSIS = odd_report.ELLIPSIS  # the cap marker, read by the tests here

SCHEMA = "odd-status-facts/1"

OBSERVATION_DIR = ".odd/observe-run-reports"
INSTRUMENTATION_DIR = ".odd/otel-instrumentation-reports"
LEDGER_PATH = ".odd/decisions.md"
CLASSIFICATIONS_PATH = ".odd/entry-classifications.md"
CLASSES = ("runtime", "non-runtime")
BENCHMARKS_DIR = ".odd/benchmarks"

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

DEFAULT_SECTION_TEXTS = (3, 5)
DEFAULT_TABLE_SECTIONS = (2, 3, 5)
# A replay (verify, re-measure) rules in its protocol section too.
REPLAY_TABLE_SECTIONS = (2, 3, 5, 7)
DEFAULT_MAX_CELL = 120
DEFAULT_MAX_TEXT = 1500  # per bullet of a bulleted section, else per section
# bullets lifted from a section, the rest counted: a section's prose can
# reach this many times --max-text, the price of never cutting a compliant
# section mid-bullet - real sections carry under ten bullets
MAX_TEXT_BULLETS = 40
NOTHING_CUT = {
    "truncated": False,
    "bullets_dropped": 0,
    "bullets_cut": 0,
    "prose_cut": False,
}
DEFAULT_RECENT = 3
MAX_COMPACT_PARAGRAPH = 300
DEFAULT_MAX_RECORD = 800
DEFAULT_MAX_COMMITS = 10
MAX_CHANGED_PATHS = 10
BENCHMARK_RE = re.compile(r"\.odd/benchmarks/([A-Za-z0-9_.-]+)")
# --- git ------------------------------------------------------------------


def report_repositories(frontmatter: dict) -> tuple[list[str], list[str]]:
    """The identities a report's ``repository`` field names, normalized -
    one, several (a per-service map spanning repositories), or none - and
    the raw values the normalization could not read."""
    value = frontmatter.get("repository")
    values = [v for v in (value.values() if isinstance(value, dict) else [value]) if v]
    found: set[str] = set()
    unrecognized: list[str] = []
    for raw in values:
        identity = normalize_remote(str(raw))
        if identity:
            found.add(identity)
        else:
            unrecognized.append(str(raw))
    return sorted(found), unrecognized


def resolve_root(root: Path, frontmatter: dict, opts: dict) -> dict:
    """Where a report's revision and tree anchor resolve: the store's own
    repository when the report names none or the store's identity, a clone
    the caller named, or nowhere - unreachable, unrecognized, or spanning
    several. A value present but unreadable is never read as the store's."""
    identities, unrecognized = report_repositories(frontmatter)
    where: dict = {"identities": identities, "identity": None, "root": None}
    if unrecognized:
        # a value the rules cannot read: unknown alone, and still spanning
        # when readable ones sit beside it - one anchor covers neither
        source = "spans" if identities else "unrecognized"
        return {**where, "source": source, "raw": unrecognized}
    if not identities:
        return {**where, "source": "store", "root": root}
    if len(identities) > 1:
        return {**where, "source": "spans"}
    [identity] = identities
    where["identity"] = identity
    if opts.get("identity") and identity == opts["identity"]:
        return {**where, "source": "store", "root": root}
    clone = opts.get("clones", {}).get(identity)
    if clone is not None:
        return {**where, "source": "clone", "root": clone}
    return {
        **where,
        "source": "unreachable",
        "store_identity_unknown": opts.get("identity") is None,
    }


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


def changed_paths(root: Path, revision_sha: str, entry: str) -> dict:
    out = git(root, "diff", "--name-only", revision_sha, "HEAD", "--", entry) or ""
    paths = [p for p in out.splitlines() if p.strip()]
    return {"count": len(paths), "paths": paths[:MAX_CHANGED_PATHS]}


# --- frontmatter ------------------------------------------------------------


# --- body --------------------------------------------------------------------


def bullet_blocks(lines: list[str]) -> list[list[str]]:
    """A section's prose in blocks: the lines before its first bullet, then
    one block per bullet - a bullet carrying the lines wrapped under it and
    the blank lines that follow it. The blocks rejoin into the prose as
    written, so the lift changes a section's spacing only where it cuts."""
    blocks: list[list[str]] = [[]]
    for line in lines:
        if line.startswith("- "):
            blocks.append([])
        blocks[-1].append(line)
    return blocks


def cap_block(block: list[str], limit: int | None) -> tuple[list[str], bool]:
    """One block capped on its own, the blank lines around it kept."""
    head, tail = 0, len(block)
    while head < tail and not block[head].strip():
        head += 1
    while tail > head and not block[tail - 1].strip():
        tail -= 1
    body, cut = cap("\n".join(block[head:tail]), limit)
    return [*block[:head], *(body.split("\n") if body else []), *block[tail:]], cut


def cap_text(lines: list[str], limit: int | None) -> tuple[str, dict]:
    """A section's prose as emitted, and what the cap took from it.

    A bulleted section - the one-bullet-per-gap shape a gaps section is
    written in - is lifted bullet by bullet: the prose before the first
    bullet and every bullet capped on its own, at most ``MAX_TEXT_BULLETS``
    of them. A compliant section is never cut mid-bullet because its total
    crossed the cap. A section carrying no bullet is capped as one text.

    What the cap took is stated piece by piece - ``bullets_dropped`` whole,
    ``bullets_cut`` at their tail, ``prose_cut`` for the prose before the
    bullets or, in a bulletless section, the text itself - so a reader
    never has to infer which piece is short.
    """
    blocks = bullet_blocks(lines)
    if len(blocks) == 1:
        text, cut = cap("\n".join(lines).strip(), limit)
        return text, {**NOTHING_CUT, "truncated": cut, "prose_cut": cut}
    dropped = max(0, len(blocks) - 1 - MAX_TEXT_BULLETS)
    out: list[str] = []
    prose_cut, bullets_cut = False, 0
    for index, block in enumerate(blocks[: MAX_TEXT_BULLETS + 1]):
        capped, cut = cap_block(block, limit)
        out += capped
        if index:
            bullets_cut += cut
        else:
            prose_cut = cut
    return "\n".join(out).strip(), {
        "truncated": bool(dropped or bullets_cut or prose_cut),
        "bullets_dropped": dropped,
        "bullets_cut": bullets_cut,
        "prose_cut": prose_cut,
    }


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
            emitted["text"], taken = cap_text(section["lines"], opts["max_text"])
        else:
            emitted["text"], taken = None, NOTHING_CUT
        emitted["text_truncated"] = taken["truncated"]
        emitted["text_bullets_dropped"] = taken["bullets_dropped"]
        emitted["text_bullets_cut"] = taken["bullets_cut"]
        emitted["text_prose_cut"] = taken["prose_cut"]
        out.append(emitted)
    return out


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


# --- reports ----------------------------------------------------------------


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
    where = resolve_root(root, frontmatter, opts)
    target = where["root"]
    if target is None:
        # no repository to resolve in: the revision is a fact the report
        # states, the boundary is unknown - never the store's commit date,
        # which is a fact about the store, not about the service
        text = frontmatter.get("revision")
        revision = (
            None
            if text is None
            else {"value": str(text), "resolves": False, "sha": None}
        )
        boundary = {"kind": "unreachable"}
    else:
        revision = resolve_revision(target, frontmatter.get("revision"))
        boundary = report_boundary(revision, commit)
    own_sha = commit["sha"] if commit else None
    report["repository"] = {
        "identities": where["identities"],
        "identity": where["identity"],
        "source": where["source"],
        "root": None if target is None else str(target),
        "foreign": where["source"] != "store",
        **({"raw": where["raw"]} if "raw" in where else {}),
        **(
            {"store_identity_unknown": True}
            if where.get("store_identity_unknown")
            else {}
        ),
    }
    trees = opts.setdefault("head_trees", {str(root): opts["head_tree"]})
    candidate = None
    if target is not None:
        if str(target) not in trees:
            trees[str(target)] = ls_tree(target, "HEAD")
        candidate = trees[str(target)]
    # a benchmark lives in the store: its leg counts store commits from a
    # store-local boundary, never from a revision that only the clone knows
    bench_boundary = (
        boundary if where["source"] == "store" else report_boundary(None, commit)
    )

    anchor = frontmatter.get("tree_anchor")
    if isinstance(anchor, dict):
        frontmatter["tree_anchor"] = f"{len(anchor)} entries, see tree_anchor_diff"

    scope = (
        project_scope(target or root, frontmatter.get("project"))
        if kind == "instrumentation"
        else None
    )
    pathspec = [scope or "."] + [f":(exclude){p}" for p in MEMORY_PATHS]
    commits = commits_after(target or root, boundary, pathspec, own_sha)

    benchmarks = []
    for mention in benchmark_mentions(sections, body):
        benchmarks.append(
            {
                **mention,
                "commits_since": commits_after(
                    root, bench_boundary, [mention["path"]], own_sha
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
            "tree_anchor_diff": (
                None
                if target is None
                else tree_anchor_diff(
                    target, anchor, candidate, revision if full else None, opts
                )
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
            "findings": findings_at_a_glance(sections, replay, opts["max_title"]),
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


# --- the memory invariant (issue #307) ---------------------------------------


def check_invariant(root: Path, reports: list[dict]) -> dict:
    """Every stored report checked; a report whose only problem is a field
    it predates is listed as legacy, not as a violation - the contract reads
    it as full, and nothing can ever change an append-only file."""
    stored = {Path(r["path"]).name for r in reports if r["kind"] == "observation"}
    violations = []
    legacy = []
    for report in reports:
        problems = check_report(report, stored, root)
        if not problems:
            continue
        if all(p.startswith(LEGACY_PREFIX) for p in problems):
            legacy.append(report["path"])
            continue
        violations.append(
            {"path": report["path"], "kind": report["kind"], "problems": problems}
        )
    return {"checked": len(reports), "violations": violations, "legacy": legacy}


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
    max_title: int | None = MAX_FINDING_TITLE,
    clones: dict[str, Path] | None = None,
) -> dict:
    root = Path(root)
    services = list(services or [])
    opts = {
        "identity": repo_identity(root),
        "clones": {k: Path(v) for k, v in (clones or {}).items()},
        "section_texts": tuple(section_texts),
        "table_sections": None if table_sections is None else tuple(table_sections),
        "max_cell": max_cell,
        "max_text": max_text,
        "max_record": max_record,
        "max_commits": max_commits,
        "max_title": max_title,
        "non_runtime": {n.lower() for n in non_runtime},
        "runtime": {n.lower() for n in runtime},
        "head_tree": ls_tree(root, "HEAD"),
    }
    known_tree: dict[str, str] = dict(opts["head_tree"] or {})
    for clone in opts["clones"].values():
        known_tree.update(ls_tree(clone, "HEAD") or {})
    classifications = load_classifications(root, known_tree)
    opts["classifications"] = classifications["effective"]
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
        "repositories": sorted(repositories_named(readable)),
    }
    matched = [r for r in reports if matches(r, services, stack, environment)]
    ledger = load_ledger(root, reports)
    invariant = check_invariant(root, reports)
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
        "classifications": classifications,
        "repository": {
            "identity": opts["identity"],
            "clones": {k: str(v) for k, v in opts["clones"].items()},
        },
        "invariant": invariant,
    }


def repositories_named(reports: list[dict]) -> set[str]:
    """The distinct ``repository`` values the reports carry - a scalar, or
    the values of a per-service map."""
    found: set[str] = set()
    for report in reports:
        value = report["frontmatter"].get("repository")
        values = value.values() if isinstance(value, dict) else [value]
        found.update(normalize_remote(str(v)) or str(v) for v in values if v)
    return found


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
    parser.add_argument(
        "--full",
        action="store_true",
        help="render the working tables whole instead of the one-screen synthesis "
        "(implied by a scope: --service, --stack or --env; with --render)",
    )
    parser.add_argument(
        "--ruled",
        action="append",
        default=[],
        metavar="REPORT/ID=STATE",
        help="a ruling on a finding applied before rendering, STATE one of open, "
        "fixed, regressed (repeatable; with --render; never persisted)",
    )
    parser.add_argument("--env", help="restrict to this deployment environment")
    parser.add_argument(
        "--non-runtime",
        action="append",
        default=[],
        help="a top-level tree entry that cannot change the service's runtime, for "
        "this run only - the repository's own rulings live in "
        ".odd/entry-classifications.md (repeatable)",
    )
    parser.add_argument(
        "--runtime",
        action="append",
        default=[],
        help="a top-level tree entry to keep out of non_runtime whatever its name or "
        "ruling, for this run only (repeatable)",
    )
    parser.add_argument(
        "--repository",
        action="append",
        default=[],
        metavar="IDENTITY=PATH",
        help="where a repository a report names is cloned (its identity as the "
        "report's repository field writes it, a path inside the clone; repeatable) - "
        "a report naming another repository resolves its revision and tree anchor "
        "there, or has an unknown boundary",
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
        help="characters kept before truncation, per bullet of a bulleted "
        "section prose, else per section",
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
    if args.full and not args.render:
        parser.error("--full only applies with --render")
    if args.ruled and not args.render:
        parser.error("--ruled only applies with --render")
    if args.recent is None:
        recent = DEFAULT_RECENT
    else:
        recent = None if args.recent.lower() == "all" else int(args.recent)
    root = git_root(Path(args.repo))
    if root is None:
        print(f"not a git repository: {Path(args.repo).resolve()}", file=sys.stderr)
        return 2
    clones: dict[str, Path] = {}
    for pair in args.repository:
        identity, sep, path = pair.partition("=")
        normalized = normalize_remote(identity)
        if not sep or not normalized:
            parser.error(f"--repository takes IDENTITY=PATH, got {pair!r}")
        clone = git_root(Path(path))
        if clone is None:
            parser.error(
                f"--repository {pair!r}: {path} is not inside a git repository"
            )
        clones[normalized] = clone
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
        # the rendering references a finding by its key and its whole title
        max_title=None if args.render else MAX_FINDING_TITLE,
        clones=clones,
    )
    if args.render:
        # the renderer lives next to this file; never leave bytecode in the skill
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import odd_render

        full = args.full or bool(args.service or args.stack or args.env)
        sys.stdout.write(
            odd_render.render(facts, today=args.today, full=full, ruled=args.ruled)
        )
        return 0
    json.dump(facts, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
