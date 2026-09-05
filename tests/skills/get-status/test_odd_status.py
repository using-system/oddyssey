"""Tests for the get-status skill's fact-sheet script.

The script is loaded from its packaged location so the tests exercise
the very file the skill ships. Every test builds a throwaway git
repository: the script reads the loop's memory and git, nothing else.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".apm"
    / "skills"
    / "get-status"
    / "scripts"
    / "odd_status.py"
)


def _load_module():
    sys.dont_write_bytecode = True  # never leave a __pycache__ in the packaged skill
    spec = importlib.util.spec_from_file_location("odd_status", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def odd_status():
    return _load_module()


GIT_ENV = {
    "GIT_AUTHOR_NAME": "example-user",
    "GIT_AUTHOR_EMAIL": "example-user@example.com",
    "GIT_COMMITTER_NAME": "example-user",
    "GIT_COMMITTER_EMAIL": "example-user@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


class Repo:
    """A throwaway git repository the tests drive by hand."""

    def __init__(self, root: Path):
        self.root = root
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str, date: str | None = None) -> str:
        env = {**os.environ, **GIT_ENV}
        if date:
            env["GIT_AUTHOR_DATE"] = date
            env["GIT_COMMITTER_DATE"] = date
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            cwd=self.root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def write(self, rel: str, content: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def commit(self, message: str, *rels: str, date: str | None = None) -> str:
        self.git("add", "-A", "--", *rels) if rels else self.git("add", "-A")
        self.git("commit", "-q", "-m", message, date=date)
        return self.git("rev-parse", "--short", "HEAD")

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def tree_anchor(self) -> str:
        entries = []
        for line in self.git("ls-tree", "HEAD").splitlines():
            meta, name = line.split("\t", 1)
            entries.append(f'{name}: "{meta.split()[2]}"')
        return "{" + ", ".join(entries) + "}"


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    r.write("src/app.py", "print('v1')\n")
    r.write("docs/guide.md", "# guide\n")
    r.write("README.md", "# readme\n")
    r.commit("feat: initial", date="2026-08-01T10:00:00Z")
    return r


def observation(
    *,
    services: str = "[checkout]",
    stack: str = "local",
    environment: str = "local",
    mode: str = "drive",
    run_name: str = "checkout-sweep",
    date: str = "2026-08-10",
    revision: str | None = None,
    extra_frontmatter: str = "",
    body: str = "",
) -> str:
    lines = [
        "---",
        f"services: {services}",
        f"stack: {stack}",
        f"environment: {environment}",
        f"mode: {mode}",
        "depth: full",
        f"window: {date}T10:00:00Z/{date}T10:05:00Z",
        f"run_name: {run_name}",
        f"date: {date}",
    ]
    if revision:
        lines.append(f"revision: {revision}")
    if extra_frontmatter:
        lines.append(extra_frontmatter)
    lines.append("---")
    lines.append("")
    lines.append(f"# Observation report: {run_name}")
    lines.append("")
    lines.append(body or DEFAULT_BODY)
    return "\n".join(lines) + "\n"


DEFAULT_BODY = """\
**Answer to the question:** checkout answers in p95 120 ms, one
finding worth a fix.

## 1. Mission and run record

- **Service:** `checkout`.

### Scenario record (verbatim)

Ad-hoc: 30 calls.

## 2. Observed behavior

| Operation | Requests | Rate | p50 | p95 | p99 | Error % | Notable |
|---|---|---|---|---|---|---|---|
| POST /checkout | 30 | 1/s | 80 ms | 120 ms | 130 ms | 0 % | one slow, a \\| pipe |
| GET /cart | 30 | 1/s | 10 ms | 12 ms | 14 ms | 0 % | - |

## 3. Anomalies and probable causes

| # | Finding | Severity | Confidence | Evidence | Expected gain |
|---|---|---|---|---|---|
| F1 | N+1 on cart lines | high | confirmed | 30 spans per call | p95 -60 ms |
| F2 | Cold start | low | suspected | first call 400 ms | none |

Prose after the table stays in the section text.

## 4. Improvement opportunities

- Batch the cart lines query.

## 5. Telemetry gaps

- **Logs: absent for checkout** - no log stream carries the service.

## 6. Decisions the spec must settle

- Nothing.

## 7. Measurement protocol for the fix

| Check | Before | Pass criterion |
|---|---|---|
| p95 POST /checkout | 120 ms | < 80 ms |
"""


LEDGER_HEAD = (
    "# ODD finding decisions\n\nRows are appended, never rewritten.\n\n"
    "| Date | Finding | Verdict | Rationale |\n|---|---|---|---|\n"
)


def run_script(repo: Repo, *args: str, cwd: Path | None = None) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd or repo.root,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == "", proc.stderr
    return json.loads(proc.stdout)


def facts(repo: Repo, **kwargs) -> dict:
    module = _load_module()
    return module.build_facts(repo.root, **kwargs)


# --- frontmatter -----------------------------------------------------------


def test_frontmatter_parses_scalars_lists_and_flow_mappings(odd_status):
    text = (
        "---\n"
        "services: [checkout, payment]\n"
        "stack: local\n"
        'window: "2026-08-22T10:04:12Z/2026-08-22T10:05:03Z"\n'
        "process_restarted: true\n"
        'instance: {checkout: "id=a, with comma", payment: af6070c1}\n'
        'tree_anchor: {.odd: "1dc9", src: "2497"}\n'
        "---\n"
        "# body\n"
    )
    fm, body, errors = odd_status.split_frontmatter(text)
    assert errors == []
    assert fm["services"] == ["checkout", "payment"]
    assert fm["stack"] == "local"
    assert fm["window"] == "2026-08-22T10:04:12Z/2026-08-22T10:05:03Z"
    assert fm["process_restarted"] is True
    assert fm["instance"] == {"checkout": "id=a, with comma", "payment": "af6070c1"}
    assert fm["tree_anchor"] == {".odd": "1dc9", "src": "2497"}
    assert body.startswith("# body")


def test_frontmatter_keeps_an_unparseable_line_as_an_error_not_a_failure(odd_status):
    text = (
        "---\nservices: [checkout]\nthis line has no colon\nstack: local\n---\nbody\n"
    )
    fm, _, errors = odd_status.split_frontmatter(text)
    assert fm["services"] == ["checkout"]
    assert fm["stack"] == "local"
    assert len(errors) == 1
    assert "no colon" in errors[0]


def test_unquoted_apostrophe_does_not_open_a_quote(odd_status):
    fm, _, errors = odd_status.split_frontmatter(
        "---\ninstance: {a: it's fine, b: other}\nnote: don't\n---\n"
    )
    assert errors == []
    assert fm["instance"] == {"a": "it's fine", "b": "other"}
    assert fm["note"] == "don't"


def test_block_style_value_is_reported_not_mangled(odd_status):
    text = "---\nservices:\n  - checkout\n  - payment\nstack: local\n---\n"
    fm, _, errors = odd_status.split_frontmatter(text)
    assert fm["services"] is None
    assert fm["stack"] == "local"
    assert len(errors) == 1
    assert "services" in errors[0] and "block" in errors[0]


def test_wrapped_flow_values_are_joined_even_when_a_line_carries_a_colon(odd_status):
    text = (
        "---\n"
        'tree_anchor: {src: "aaa",\n'
        '  docs: "bbb"}\n'
        'instance: {mcp: "id=odd-262 on every process,\n'
        '  opt-in via OTEL_RESOURCE_ATTRIBUTES: the -e flag"}\n'
        "---\n"
    )
    fm, _, errors = odd_status.split_frontmatter(text)
    assert errors == []
    assert fm["tree_anchor"] == {"src": "aaa", "docs": "bbb"}
    assert fm["instance"] == {
        "mcp": "id=odd-262 on every process, opt-in via OTEL_RESOURCE_ATTRIBUTES: the -e flag"
    }


def test_block_style_mapping_is_reported_not_mangled(odd_status):
    text = "---\ntree_anchor:\n  src: aaa\n  docs: bbb\n---\n"
    fm, _, errors = odd_status.split_frontmatter(text)
    assert fm["tree_anchor"] is None
    assert len(errors) == 1 and "tree_anchor" in errors[0]


def test_missing_frontmatter_is_reported_not_fatal(odd_status):
    fm, body, errors = odd_status.split_frontmatter("# no frontmatter here\n")
    assert fm == {}
    assert body.startswith("# no frontmatter")
    assert errors == ["no frontmatter block"]


# --- inventory and filters ------------------------------------------------


def test_no_odd_directory_means_the_loop_has_not_started(repo):
    out = facts(repo)
    assert out["loop_started"] is False
    assert out["reports"] == []
    assert out["inventory"] == {
        "report_count": 0,
        "services": [],
        "stacks": [],
        "environments": [],
        "repositories": [],
    }


def test_inventory_lists_distinct_services_stacks_and_environments(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md",
        observation(services="[checkout, payment]"),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-prod-sweep.md",
        observation(
            services="[checkout]",
            stack="grafana",
            environment="prod",
            run_name="prod-sweep",
            date="2026-08-11",
        ),
    )
    repo.commit("docs(odd): reports")
    out = facts(repo)
    assert out["loop_started"] is True
    assert out["inventory"] == {
        "report_count": 2,
        "services": ["checkout", "payment"],
        "stacks": ["grafana", "local"],
        "environments": ["local", "prod"],
        "repositories": [],
    }
    assert [r["kind"] for r in out["reports"]] == ["observation", "observation"]


def test_service_filter_matches_exactly_and_a_partial_name_misses(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md",
        observation(services="[checkout-api]"),
    )
    repo.commit("docs(odd): report")
    exact = facts(repo, services=["checkout-api"])
    assert exact["matched"] == 1
    partial = facts(repo, services=["checkout"])
    assert partial["matched"] == 0
    assert partial["reports"] == []
    assert partial["filters"] == {
        "services": ["checkout"],
        "stack": None,
        "environment": None,
    }
    # the inventory survives an empty match, so the caller can correct the scope
    assert partial["inventory"]["services"] == ["checkout-api"]


def test_stack_and_environment_filters_are_distinct_scopes(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md",
        observation(stack="grafana", environment="local"),
    )
    repo.commit("docs(odd): report")
    assert facts(repo, stack="grafana")["matched"] == 1
    assert facts(repo, environment="grafana")["matched"] == 0
    assert facts(repo, stack="grafana", environment="prod")["matched"] == 0


# --- git boundaries ---------------------------------------------------------


def test_report_commit_is_the_commit_that_added_the_file(repo):
    rel = ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md"
    repo.write(rel, observation())
    added = repo.commit("docs(odd): report", date="2026-08-10T12:00:00Z")
    repo.write("src/app.py", "print('v2')\n")
    repo.commit("fix: later", date="2026-08-12T12:00:00Z")
    out = facts(repo)
    report = out["reports"][0]
    assert report["path"] == rel
    assert report["commit"]["sha"].startswith(added)
    assert report["commit"]["date"].startswith("2026-08-10")


def test_uncommitted_report_has_no_commit(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md", observation()
    )
    out = facts(repo)
    assert out["reports"][0]["commit"] is None
    since = out["reports"][0]["commits_since"]
    assert since["boundary"] == "none"
    assert since["count"] is None
    assert since["commits"] == []


def test_benchmark_commits_are_null_without_a_boundary(repo):
    body = DEFAULT_BODY.replace("Ad-hoc: 30 calls.", "Benchmark: .odd/benchmarks/x/")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body=body),
    )
    assert facts(repo)["reports"][0]["benchmarks"][0]["commits_since"] is None


def test_revision_resolution_is_stated_either_way(repo):
    resolvable = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=resolvable),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-b.md",
        observation(run_name="b", date="2026-08-11", revision="0000000"),
    )
    repo.commit("docs(odd): reports")
    a, b = facts(repo)["reports"]
    assert a["revision"] == {
        "value": resolvable,
        "resolves": True,
        "sha": repo.git("rev-parse", resolvable),
    }
    assert b["revision"] == {"value": "0000000", "resolves": False, "sha": None}


def test_report_without_revision_says_so(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    assert facts(repo)["reports"][0]["revision"] is None


def test_tree_anchor_diff_classifies_entries_against_head(repo):
    # a real anchor always carries .odd: the ledger or an earlier report
    repo.write(".odd/decisions.md", LEDGER_HEAD)
    repo.commit("docs(odd): ledger")
    anchor = repo.tree_anchor()
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", extra_frontmatter=f"tree_anchor: {anchor}"),
    )
    repo.commit("docs(odd): report")
    # docs change: non-runtime; src change: unclassified; a new entry appears
    repo.write("docs/guide.md", "# guide v2\n")
    repo.write("src/app.py", "print('v2')\n")
    repo.write("CHANGELOG.md", "# changes\n")
    repo.commit("feat: change")
    diff = facts(repo)["reports"][0]["tree_anchor_diff"]
    assert diff["candidate"] == "HEAD"
    assert diff["ignored"] == [".odd"]
    assert diff["unchanged"] == 1
    assert diff["non_runtime"] == ["docs"]
    assert diff["unclassified"] == ["src"]
    assert diff["only_at_candidate"] == ["CHANGELOG.md"]
    assert diff["only_in_anchor"] == []
    # without a resolvable revision the paths behind a differing entry are unknown
    assert diff["changed_paths"] is None


def test_tree_anchor_diff_lists_the_paths_behind_each_differing_entry(repo):
    repo.write(".odd/decisions.md", LEDGER_HEAD)
    repo.commit("docs(odd): ledger")
    rev = repo.git("rev-parse", "--short", "HEAD")
    anchor = repo.tree_anchor()
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(
            run_name="a", revision=rev, extra_frontmatter=f"tree_anchor: {anchor}"
        ),
    )
    repo.commit("docs(odd): report")
    repo.write("src/app.py", "print('v2')\n")
    repo.write("src/pyproject.toml", "version = '2'\n")
    repo.write("docs/guide.md", "# v2\n")
    repo.commit("chore(release): 2")
    diff = facts(repo)["reports"][0]["tree_anchor_diff"]
    assert diff["changed_paths"] == {
        "docs": {"count": 1, "paths": ["docs/guide.md"]},
        "src": {"count": 2, "paths": ["src/app.py", "src/pyproject.toml"]},
    }


def test_odd_missing_from_the_anchor_is_ignored_not_reported_as_new(repo):
    # the first report of a repo: its revision predates any .odd/ entry
    anchor = repo.tree_anchor()
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", extra_frontmatter=f"tree_anchor: {anchor}"),
    )
    repo.commit("docs(odd): report")
    diff = facts(repo)["reports"][0]["tree_anchor_diff"]
    assert diff["ignored"] == [".odd"]
    assert diff["only_at_candidate"] == []
    assert diff["unchanged"] == 3


def test_non_runtime_classification_is_generic_and_correctable(repo):
    for rel in (
        "agents/main.py",
        "assets/app.css",
        "marketplace/index.js",
        ".github/ci.yml",
    ):
        repo.write(rel, "v1\n")
    repo.write(".odd/decisions.md", LEDGER_HEAD)
    repo.commit("feat: layout")
    anchor = repo.tree_anchor()
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", extra_frontmatter=f"tree_anchor: {anchor}"),
    )
    repo.commit("docs(odd): report")
    for rel in (
        "agents/main.py",
        "assets/app.css",
        "marketplace/index.js",
        ".github/ci.yml",
        "docs/guide.md",
        "README.md",
    ):
        repo.write(rel, "v2\n")
    repo.commit("feat: touch everything")
    diff = facts(repo)["reports"][0]["tree_anchor_diff"]
    # a service can live in agents/, assets/ or marketplace/: never ruled non-runtime
    assert diff["unclassified"] == ["agents", "assets", "marketplace"]
    assert diff["non_runtime"] == [".github", "README.md", "docs"]
    loose = facts(repo, non_runtime=["ASSETS"])["reports"][0]["tree_anchor_diff"]
    assert "assets" in loose["non_runtime"]
    corrected = facts(repo, runtime=["DOCS"])["reports"][0]["tree_anchor_diff"]
    assert corrected["non_runtime"] == [".github", "README.md"]
    assert corrected["runtime"] == ["docs"]
    assert "docs" not in corrected["unclassified"]


def test_tree_anchor_diff_honours_extra_non_runtime_names(repo):
    anchor = repo.tree_anchor()
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", extra_frontmatter=f"tree_anchor: {anchor}"),
    )
    repo.commit("docs(odd): report")
    repo.write("src/app.py", "print('v2')\n")
    repo.commit("feat: change")
    diff = facts(repo, non_runtime=["src"])["reports"][0]["tree_anchor_diff"]
    assert diff["non_runtime"] == ["src"]
    assert diff["unclassified"] == []


def test_wrapped_tree_anchor_still_yields_a_diff(repo):
    repo.write(".odd/decisions.md", LEDGER_HEAD)
    repo.commit("docs(odd): ledger")
    anchor = repo.tree_anchor().replace(", ", ",\n  ")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", extra_frontmatter=f"tree_anchor: {anchor}"),
    )
    repo.commit("docs(odd): report")
    report = facts(repo)["reports"][0]
    assert report["frontmatter_errors"] == []
    assert report["tree_anchor_diff"] is not None


def test_report_without_tree_anchor_has_no_diff(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    assert facts(repo)["reports"][0]["tree_anchor_diff"] is None


def test_commits_since_revision_exclude_memory_only_commits(repo):
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev),
    )
    repo.commit("docs(odd): observation report a")
    repo.write(
        ".odd/decisions.md",
        "# ODD finding decisions\n\n| Date | Finding | Verdict | Rationale |\n|---|---|---|---|\n",
    )
    repo.commit("docs(odd): decision")
    repo.write("src/app.py", "print('v2')\n")
    fix = repo.commit("fix: the finding")
    repo.write("docs/guide.md", "# guide v2\n")
    doc = repo.commit("docs(guide): wording")
    since = facts(repo)["reports"][0]["commits_since"]
    assert since["boundary"] == "revision"
    assert since["scope"] == "repo-wide"
    assert since["count"] == 2
    assert [c["sha"][:7] for c in since["commits"]] == [doc, fix]
    assert since["commits"][1]["subject"] == "fix: the finding"
    # each commit names the top-level entries it touched, so the skill can
    # tell a documentation-only commit from a fix without another git call
    assert since["commits"][0]["entries"] == ["docs"]
    assert since["commits"][1]["entries"] == ["src"]
    assert since["truncated"] is False


def test_commits_since_fall_back_to_the_report_commit_date_when_revision_is_unresolvable(
    repo,
):
    rel = ".odd/observe-run-reports/2026-08-10-1000-a.md"
    repo.write(rel, observation(run_name="a", revision="0000000"))
    repo.write("src/app.py", "print('squashed with the report')\n")
    own = repo.commit("feat: squash carrying the report", date="2026-08-10T12:00:00Z")
    repo.write("src/app.py", "print('v3')\n")
    later = repo.commit("fix: after", date="2026-08-12T12:00:00Z")
    since = facts(repo)["reports"][0]["commits_since"]
    assert since["boundary"] == "commit-date"
    assert [c["sha"][:7] for c in since["commits"]] == [later]
    assert own not in [c["sha"][:7] for c in since["commits"]]


def test_a_squash_carrying_code_and_the_report_counts_when_the_revision_resolves(repo):
    # squash-merge: the report's own commit also lands the fix it describes
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev),
    )
    repo.write("src/app.py", "print('fixed in the same squash')\n")
    own = repo.commit("fix: the finding, with its report")
    since = facts(repo)["reports"][0]["commits_since"]
    assert since["boundary"] == "revision"
    assert [c["sha"][:7] for c in since["commits"]] == [own]


def test_commits_since_are_capped_and_flagged_as_truncated(repo):
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev),
    )
    repo.commit("docs(odd): report")
    for i in range(4):
        repo.write("src/app.py", f"print({i})\n")
        repo.commit(f"fix: {i}")
    since = facts(repo, max_commits=2)["reports"][0]["commits_since"]
    assert since["count"] == 4
    assert len(since["commits"]) == 2
    assert since["truncated"] is True


def test_every_benchmark_the_body_names_is_listed_with_its_section(repo):
    repo.write(
        ".odd/benchmarks/checkout-load/script.js", "export default function () {}\n"
    )
    repo.commit("feat(bench): checkout-load")
    rev = repo.git("rev-parse", "--short", "HEAD")
    body = DEFAULT_BODY.replace(
        "Ad-hoc: 30 calls.",
        "Benchmark: `.odd/benchmarks/checkout-load/` (manifest v1).",
    ).replace(
        "- Batch the cart lines query.",
        "- Batch the cart lines query; consider authoring .odd/benchmarks/future-idea/ later.",
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev, body=body),
    )
    repo.commit("docs(odd): report")
    repo.write("src/app.py", "print('v2')\n")
    repo.commit("fix: code")
    repo.write(
        ".odd/benchmarks/checkout-load/script.js",
        "export default function () { /* v2 */ }\n",
    )
    bump = repo.commit("feat(bench): checkout-load v2")
    report = facts(repo)["reports"][0]
    assert [(b["path"], b["section"]) for b in report["benchmarks"]] == [
        (".odd/benchmarks/checkout-load", 1),
        (".odd/benchmarks/future-idea", 4),
    ]
    assert [c["sha"][:7] for c in report["benchmarks"][0]["commits_since"]] == [bump]
    assert report["benchmarks"][1]["commits_since"] == []
    # a benchmark is living source, never memory: its commit counts as a change
    assert bump in [c["sha"][:7] for c in report["commits_since"]["commits"]]


def test_report_naming_no_benchmark_lists_none(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    assert facts(repo)["reports"][0]["benchmarks"] == []


# --- body extraction --------------------------------------------------------


def test_body_yields_headline_sections_tables_and_selected_texts(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    report = facts(repo)["reports"][0]
    assert report["headline"].startswith(
        "**Answer to the question:** checkout answers in p95 120 ms"
    )
    sections = {s["number"]: s for s in report["sections"]}
    assert [s["number"] for s in report["sections"]] == [1, 2, 3, 4, 5, 6, 7]
    assert sections[2]["title"] == "Observed behavior"
    ops = sections[2]["tables"][0]
    assert ops["header"] == [
        "Operation",
        "Requests",
        "Rate",
        "p50",
        "p95",
        "p99",
        "Error %",
        "Notable",
    ]
    assert ops["rows"][0] == [
        "POST /checkout",
        "30",
        "1/s",
        "80 ms",
        "120 ms",
        "130 ms",
        "0 %",
        "one slow, a | pipe",
    ]
    findings = sections[3]["tables"][0]
    assert [row[0] for row in findings["rows"]] == ["F1", "F2"]
    # texts: only the requested sections carry their prose, tables removed
    assert "Prose after the table" in sections[3]["text"]
    assert "| F1 |" not in sections[3]["text"]
    assert "Logs: absent for checkout" in sections[5]["text"]
    assert sections[2]["text"] is None
    assert sections[1]["text"] is None
    # the scenario record is what step 4's comparability rests on: always lifted
    assert report["scenario_record"] == "Ad-hoc: 30 calls."
    assert report["scenario_record_truncated"] is False
    assert report["finding_ids"] == ["F1", "F2"]


def test_scenario_record_is_capped_and_absent_when_the_body_has_none(repo):
    body = DEFAULT_BODY.replace("Ad-hoc: 30 calls.", "z" * 5000)
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body=body),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-b.md",
        observation(
            run_name="b", date="2026-08-11", body="## 1. Mission\n\nNo record here.\n"
        ),
    )
    repo.commit("docs(odd): reports")
    a, b = facts(repo)["reports"]
    assert len(a["scenario_record"]) == 800 + 1
    assert a["scenario_record_truncated"] is True
    a = facts(repo, max_record=6000)["reports"][0]
    assert a["scenario_record_truncated"] is False
    assert b["scenario_record"] is None


def test_finding_ids_do_not_depend_on_which_tables_are_lifted(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.write(
        ".odd/decisions.md",
        LEDGER_HEAD
        + "| 2026-08-12 | 2026-08-10-1000-a.md / F1 | wontfix | Rare path |\n",
    )
    repo.commit("docs(odd): report and ledger")
    out = facts(repo, table_sections=[2])
    assert out["reports"][0]["finding_ids"] == ["F1", "F2"]
    assert out["ledger"]["rows"][0]["status"] == "ok"


def test_unreadable_report_is_reported_and_the_rest_renders(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    (repo.root / ".odd/observe-run-reports/2026-08-11-1000-b.md").write_bytes(
        b"---\nservices: [x]\n---\n\xff\xfe"
    )
    repo.commit("docs(odd): reports")
    out = facts(repo)
    assert out["inventory"]["report_count"] == 2
    a, b = out["reports"]
    assert a["services"] == ["checkout"]
    assert b["path"].endswith("b.md")
    assert "unreadable" in b and "decode" in b["unreadable"].lower()


def test_section_texts_follow_the_requested_numbers(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    sections = {
        s["number"]: s
        for s in facts(repo, section_texts=[1, 7])["reports"][0]["sections"]
    }
    assert sections[1]["text"] is not None
    assert sections[7]["text"] is not None
    assert sections[3]["text"] is None


def test_verdict_paragraphs_are_lifted_from_a_verification(repo):
    body = DEFAULT_BODY.replace(
        "## 3. Anomalies and probable causes",
        "**Verdict: 2/2 passed** on unchanged\ncriteria.\n\n## 3. Anomalies and probable causes",
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-verify-a.md",
        observation(
            run_name="a",
            mode="verify",
            date="2026-08-11",
            extra_frontmatter="verifies: 2026-08-10-1000-a.md",
            body=body,
        ),
    )
    repo.commit("docs(odd): verification")
    report = facts(repo)["reports"][0]
    assert report["frontmatter"]["verifies"] == "2026-08-10-1000-a.md"
    assert report["verdict_lines"] == ["**Verdict: 2/2 passed** on unchanged criteria."]


def test_a_body_with_no_numbered_sections_degrades_to_an_empty_list(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body="Just prose, no headings.\n"),
    )
    repo.commit("docs(odd): report")
    report = facts(repo)["reports"][0]
    assert report["sections"] == []
    assert report["headline"] == "Just prose, no headings."
    assert report["verdict_lines"] == []


def test_headline_is_absent_when_a_section_heading_opens_the_body(repo):
    body = DEFAULT_BODY.split("## 1.", 1)[1]
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body="## 1." + body),
    )
    repo.commit("docs(odd): report")
    assert facts(repo)["reports"][0]["headline"] is None


# --- size caps ---------------------------------------------------------------


def test_tables_are_lifted_only_from_the_requested_sections(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    sections = {s["number"]: s for s in facts(repo)["reports"][0]["sections"]}
    assert len(sections[2]["tables"]) == 1
    assert len(sections[3]["tables"]) == 1
    assert sections[7]["tables"] == []
    assert sections[7]["tables_skipped"] == 1
    assert sections[2]["tables_skipped"] == 0
    # and section 7's table lines do not leak into its text either
    sections = {
        s["number"]: s
        for s in facts(repo, table_sections=[7], section_texts=[7])["reports"][0][
            "sections"
        ]
    }
    assert sections[7]["tables"][0]["header"] == ["Check", "Before", "Pass criterion"]
    assert "| p95 POST" not in sections[7]["text"]
    assert sections[2]["tables"] == []


@pytest.mark.parametrize("mode", ["verify", "re-measure", "Verify"])
def test_a_replay_report_also_lifts_its_section_7_tables(repo, mode):
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-verify-a.md",
        observation(
            run_name="a",
            mode=mode,
            date="2026-08-11",
            extra_frontmatter="verifies: 2026-08-10-1000-a.md",
        ),
    )
    repo.commit("docs(odd): replay")
    sections = {s["number"]: s for s in facts(repo)["reports"][0]["sections"]}
    assert sections[7]["tables"][0]["header"] == ["Check", "Before", "Pass criterion"]
    assert sections[7]["tables_skipped"] == 0
    # the explicit option still wins over the mode
    sections = {
        s["number"]: s
        for s in facts(repo, table_sections=[2])["reports"][0]["sections"]
    }
    assert sections[7]["tables"] == []


def test_long_cells_are_truncated_with_a_marker_and_counted(repo):
    long_evidence = "x" * 500
    body = DEFAULT_BODY.replace("30 spans per call", long_evidence)
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body=body),
    )
    repo.commit("docs(odd): report")
    findings = {s["number"]: s for s in facts(repo)["reports"][0]["sections"]}[3][
        "tables"
    ][0]
    cell = findings["rows"][0][4]
    assert cell == "x" * 120 + "…"
    assert findings["truncated_cells"] == 1
    untruncated = {
        s["number"]: s for s in facts(repo, max_cell=1000)["reports"][0]["sections"]
    }[3]["tables"][0]
    assert untruncated["rows"][0][4] == long_evidence
    assert untruncated["truncated_cells"] == 0


def test_section_text_is_capped_and_flagged(repo):
    body = DEFAULT_BODY.replace(
        "Prose after the table", "y" * 5000 + " prose after the table"
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body=body),
    )
    repo.commit("docs(odd): report")
    section = {s["number"]: s for s in facts(repo)["reports"][0]["sections"]}[3]
    assert len(section["text"]) == 1500 + 1
    assert section["text"].endswith("…")
    assert section["text_truncated"] is True
    section = {
        s["number"]: s for s in facts(repo, max_text=10000)["reports"][0]["sections"]
    }[3]
    assert section["text_truncated"] is False
    assert "prose after the table" in section["text"]


def test_tree_anchor_is_summarized_in_the_emitted_frontmatter(repo):
    repo.write(".odd/decisions.md", LEDGER_HEAD)
    repo.commit("docs(odd): ledger")
    anchor = repo.tree_anchor()
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", extra_frontmatter=f"tree_anchor: {anchor}"),
    )
    repo.commit("docs(odd): report")
    report = facts(repo)["reports"][0]
    assert report["frontmatter"]["tree_anchor"] == "4 entries, see tree_anchor_diff"
    assert report["tree_anchor_diff"] is not None


# --- the recent window ----------------------------------------------------------


def lineage(repo: Repo, days: list[int], **kwargs) -> None:
    for day in days:
        date = f"2026-08-{day:02d}"
        repo.write(
            f".odd/observe-run-reports/{date}-1000-run{day}.md",
            observation(run_name=f"run{day}", date=date, **kwargs),
        )
    repo.commit("docs(odd): reports")


def test_older_reports_of_a_lineage_are_compact_beyond_the_recent_window(repo):
    lineage(repo, [10, 11, 12, 13, 14])
    reports = facts(repo, recent=2)["reports"]
    assert [r["detail"] for r in reports] == ["compact"] * 3 + ["full"] * 2
    old, new = reports[0], reports[-1]
    assert new["sections"][1]["tables"]
    assert old["sections"] == []
    assert old["scenario_record"] is None
    assert old["commits_since"]["count"] == 0
    assert old["commits_since"]["commits"] is None
    # what every report keeps, whatever its detail: the findings at a glance
    assert old["findings"] == new["findings"]
    assert new["findings"] == [
        {
            "id": "F1",
            "title": "N+1 on cart lines",
            "severity": "high",
            "ruling": None,
            "section": 3,
        },
        {
            "id": "F2",
            "title": "Cold start",
            "severity": "low",
            "ruling": None,
            "section": 3,
        },
    ]
    assert new["finding_ids"] == ["F1", "F2"]


def test_a_compact_report_caps_its_headline_and_verdict_paragraphs(repo):
    body = DEFAULT_BODY.replace(
        "**Answer to the question:** checkout answers in p95 120 ms, one\nfinding worth a fix.",
        "**Answer to the question:** "
        + "h" * 500
        + "\n\n**Verdict: "
        + "v" * 500
        + "**",
    )
    for day in (10, 11):
        repo.write(
            f".odd/observe-run-reports/2026-08-{day}-1000-run{day}.md",
            observation(run_name=f"run{day}", date=f"2026-08-{day}", body=body),
        )
    repo.commit("docs(odd): reports")
    old, new = facts(repo, recent=1)["reports"]
    assert old["detail"] == "compact" and new["detail"] == "full"
    assert len(new["headline"]) == len("**Answer to the question:** ") + 500
    assert len(old["headline"]) == 300 + 1 and old["headline"].endswith("…")
    assert len(old["verdict_lines"][0]) == 300 + 1
    assert len(new["verdict_lines"][0]) == len("**Verdict: ") + 500 + 2


def test_the_window_is_per_lineage_and_the_default_is_three(repo):
    lineage(repo, [10, 11, 12, 13])
    lineage(repo, [20, 21], services="[payment]")
    lineage(repo, [22], stack="grafana")
    details = {
        Path(r["path"]).stem.split("-")[-1]: r["detail"] for r in facts(repo)["reports"]
    }
    assert details == {
        "run10": "compact",
        "run11": "full",
        "run12": "full",
        "run13": "full",
        "run20": "full",
        "run21": "full",
        "run22": "full",
    }


def test_recent_all_lifts_everything(repo):
    lineage(repo, [10, 11, 12, 13, 14])
    assert {r["detail"] for r in facts(repo, recent=None)["reports"]} == {"full"}
    out = run_script(repo, "--recent", "all")
    assert {r["detail"] for r in out["reports"]} == {"full"}
    out = run_script(repo, "--recent", "1")
    assert [r["detail"] for r in out["reports"]] == ["compact"] * 4 + ["full"]


def test_findings_at_a_glance_carry_the_ruling_of_a_verification(repo):
    body = DEFAULT_BODY.replace(
        "| # | Finding | Severity | Confidence | Evidence | Expected gain |\n"
        "|---|---|---|---|---|---|\n"
        "| F1 | N+1 on cart lines | high | confirmed | 30 spans per call | p95 -60 ms |\n"
        "| F2 | Cold start | low | suspected | first call 400 ms | none |",
        "| # | Baseline finding | Fate | Evidence |\n"
        "|---|---|---|---|\n"
        "| F1 | N+1 on cart lines | FIXED | 1 span per call |\n"
        "| F2 | Cold start | still present | 390 ms |",
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-verify-a.md",
        observation(
            run_name="a",
            mode="verify",
            date="2026-08-11",
            extra_frontmatter="verifies: 2026-08-10-1000-a.md",
            body=body,
        ),
    )
    repo.commit("docs(odd): verification")
    assert facts(repo)["reports"][0]["findings"] == [
        {
            "id": "F1",
            "title": "N+1 on cart lines",
            "severity": None,
            "ruling": "FIXED",
            "section": 3,
        },
        {
            "id": "F2",
            "title": "Cold start",
            "severity": None,
            "ruling": "still present",
            "section": 3,
        },
    ]


def test_findings_at_a_glance_keep_the_rulings_a_replay_puts_in_its_protocol_table(
    repo,
):
    body = DEFAULT_BODY.replace(
        "| Check | Before | Pass criterion |\n|---|---|---|\n| p95 POST /checkout | 120 ms | < 80 ms |",
        "| Check | Before | This run | Verdict |\n|---|---|---|---|\n"
        "| C4 healthz noise | 400 ms | 0 | **FIXED** |\n| C5 profiles tagged | absent | tagged | closed |",
    )
    for day in (11, 12):
        repo.write(
            f".odd/observe-run-reports/2026-08-{day}-1000-verify-a.md",
            observation(
                run_name="a",
                mode="verify",
                date=f"2026-08-{day}",
                extra_frontmatter="verifies: 2026-08-10-1000-a.md",
                body=body,
            ),
        )
    repo.commit("docs(odd): verifications")
    old, new = facts(repo, recent=1)["reports"]
    assert old["detail"] == "compact" and new["detail"] == "full"
    expected = [
        {
            "id": "F1",
            "title": "N+1 on cart lines",
            "severity": "high",
            "ruling": None,
            "section": 3,
        },
        {
            "id": "F2",
            "title": "Cold start",
            "severity": "low",
            "ruling": None,
            "section": 3,
        },
        {
            "id": "C4",
            "title": None,
            "severity": None,
            "ruling": "**FIXED**",
            "section": 7,
        },
        {"id": "C5", "title": None, "severity": None, "ruling": "closed", "section": 7},
    ]
    assert old["findings"] == expected
    assert new["findings"] == expected
    # a drive report's protocol table carries no ruling column: nothing lifted from it
    repo.write(
        ".odd/observe-run-reports/2026-08-13-1000-b.md",
        observation(run_name="b", date="2026-08-13", body=body),
    )
    repo.commit("docs(odd): drive")
    drive = facts(repo)["reports"][-1]
    assert [f["section"] for f in drive["findings"]] == [3, 3]


def test_recent_rejects_a_value_that_is_neither_a_number_nor_all(repo):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo.root), "--recent", "five"],
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
        check=False,
    )
    assert proc.returncode == 2
    assert "--recent" in proc.stderr


# --- ledger ----------------------------------------------------------------


def test_ledger_absent_is_a_fact(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    ledger = facts(repo)["ledger"]
    assert ledger == {"present": False, "rows": [], "effective": {}}


def test_ledger_latest_row_wins_and_bad_rows_are_reported_not_dropped(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.write(
        ".odd/decisions.md",
        LEDGER_HEAD
        + "| 2026-08-12 | 2026-08-10-1000-a.md / F1 | wontfix | Rare path |\n"
        + "| 2026-08-13 | 2026-08-10-1000-a.md / F1 | open | Reconsidered |\n"
        + "| 2026-08-13 | 2026-08-10-1000-a.md / F9 | wontfix | No such finding |\n"
        + "| 2026-08-13 | 2026-01-01-0000-missing.md / F1 | wontfix | No such report |\n"
        + "| 2026-08-13 | garbage without separator | wontfix |\n"
        + "| 2026-08-14 | 2026-08-10-1000-a.md / F2 | accepted-by-design | Cold start is the design |\n",
    )
    repo.commit("docs(odd): report and ledger")
    ledger = facts(repo)["ledger"]
    assert ledger["present"] is True
    statuses = [(r["line"], r["status"]) for r in ledger["rows"]]
    assert statuses == [
        (7, "ok"),
        (8, "ok"),
        (9, "skipped"),
        (10, "skipped"),
        (11, "skipped"),
        (12, "ok"),
    ]
    reasons = {
        r["line"]: r.get("reason") for r in ledger["rows"] if r["status"] == "skipped"
    }
    assert "F9" in reasons[9]
    assert "2026-01-01-0000-missing.md" in reasons[10]
    assert "column" in reasons[11]
    assert ledger["effective"] == {
        "2026-08-10-1000-a.md / F1": {
            "line": 8,
            "date": "2026-08-13",
            "verdict": "open",
            "rationale": "Reconsidered",
        },
        "2026-08-10-1000-a.md / F2": {
            "line": 12,
            "date": "2026-08-14",
            "verdict": "accepted-by-design",
            "rationale": "Cold start is the design",
        },
    }


@pytest.mark.parametrize("padding", [0, 4500])
def test_ledger_finds_a_finding_named_only_in_prose_even_past_the_text_cap(
    repo, padding
):
    prose = (
        "y" * padding + " Finding **F7** is real, the table was collapsed (quick).\n"
    )
    body = (
        DEFAULT_BODY.split("## 3.")[0]
        + "## 3. Anomalies and probable causes\n\n"
        + prose
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body=body),
    )
    repo.write(
        ".odd/decisions.md",
        LEDGER_HEAD
        + "| 2026-08-12 | 2026-08-10-1000-a.md / F7 | wontfix | Quick report |\n",
    )
    repo.commit("docs(odd): report and ledger")
    out = facts(repo)
    row = out["ledger"]["rows"][0]
    assert row["status"] == "ok", row
    assert out["reports"][0]["finding_ids"] == []
    section = {s["number"]: s for s in out["reports"][0]["sections"]}[3]
    assert section["text_truncated"] is (padding > 0)


def test_ledger_is_read_whole_even_when_the_status_is_filtered(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.write(
        ".odd/decisions.md",
        LEDGER_HEAD
        + "| 2026-08-12 | 2026-08-10-1000-a.md / F1 | wontfix | Rare path |\n",
    )
    repo.commit("docs(odd): report and ledger")
    out = facts(repo, services=["nobody"])
    assert out["matched"] == 0
    assert list(out["ledger"]["effective"]) == ["2026-08-10-1000-a.md / F1"]


# --- instrumentation reports -------------------------------------------------


INSTRUMENTATION_BODY = """\
## 1. Stack inventory

- `src/app.py`: Python, no telemetry.

## 2. Summary table

| Service | Language | Approach | Order |
|---|---|---|---|
| checkout | Python | SDK | 1 |
| payment | Python | SDK | 2 |

## 3. Decisions made, with rationale

- SDK over agent.

## 4. Decisions the spec must settle

- Sampling.

## 5. Verification protocol

| Signal | Check |
|---|---|
| traces | one span per request |
"""


def instrumentation(project: str, revision: str | None = None) -> str:
    fm = [
        "---",
        f"project: {project}",
        "stack: local",
        "run_name: app-python",
        "date: 2026-08-09",
    ]
    if revision:
        fm.append(f"revision: {revision}")
    fm.append("---")
    return "\n".join(fm) + "\n\n# Instrumentation report\n\n" + INSTRUMENTATION_BODY


def test_instrumentation_report_is_scoped_to_its_project_path_when_it_exists(repo):
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app-python.md",
        instrumentation("myrepo/src", rev),
    )
    repo.commit("docs(odd): instrumentation report")
    repo.write("src/app.py", "print('instrumented')\n")
    code = repo.commit("feat: instrument")
    repo.write("docs/guide.md", "# v2\n")
    repo.commit("docs: guide")
    report = facts(repo)["reports"][0]
    assert report["kind"] == "instrumentation"
    assert report["frontmatter"]["project"] == "myrepo/src"
    since = report["commits_since"]
    assert since["scope"] == "src"
    assert [c["sha"][:7] for c in since["commits"]] == [code]


def test_instrumentation_report_whose_project_is_the_whole_repo_counts_repo_wide(repo):
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app-python.md",
        instrumentation("myrepo", rev),
    )
    repo.commit("docs(odd): instrumentation report")
    assert facts(repo)["reports"][0]["commits_since"]["scope"] == "repo-wide"


def test_instrumentation_summary_table_counts_only_when_its_first_column_is_service(
    repo,
):
    body = INSTRUMENTATION_BODY.replace(
        "| Service | Language | Approach | Order |",
        "| Destination | Mechanism | Approach | Order |",
    )
    text = instrumentation("myrepo").replace(INSTRUMENTATION_BODY, body)
    repo.write(".odd/otel-instrumentation-reports/2026-08-09-1000-app-python.md", text)
    repo.commit("docs(odd): instrumentation report")
    out = facts(repo)
    assert out["reports"][0]["services"] == []
    assert out["inventory"]["services"] == []


def test_instrumentation_summary_table_header_tolerates_emphasis(repo):
    body = INSTRUMENTATION_BODY.replace(
        "| Service | Language | Approach | Order |",
        "| **Service** | Language | Approach | Order |",
    )
    text = instrumentation("myrepo").replace(INSTRUMENTATION_BODY, body)
    repo.write(".odd/otel-instrumentation-reports/2026-08-09-1000-app-python.md", text)
    repo.commit("docs(odd): instrumentation report")
    assert facts(repo)["reports"][0]["services"] == ["checkout", "payment"]


def test_instrumentation_report_matches_a_service_named_in_its_summary_table(repo):
    repo.write(
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app-python.md",
        instrumentation("myrepo"),
    )
    repo.commit("docs(odd): instrumentation report")
    assert facts(repo, services=["payment"])["matched"] == 1
    assert facts(repo, services=["pay"])["matched"] == 0
    assert facts(repo, environment="prod")["matched"] == 0
    assert facts(repo)["inventory"]["services"] == ["checkout", "payment"]


# --- the command line ---------------------------------------------------------


def test_cli_prints_json_and_finds_the_repo_root_from_a_subdirectory(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    out = run_script(repo, cwd=repo.root / "src")
    assert out["schema"] == "odd-status-facts/1"
    assert out["repo"] == str(repo.root.resolve())
    assert out["head"]["sha"] == repo.head()
    assert out["matched"] == 1


def test_cli_filters_and_options(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", services="[checkout, payment]"),
    )
    repo.commit("docs(odd): report")
    out = run_script(
        repo,
        "--repo",
        str(repo.root),
        "--service",
        "payment",
        "--stack",
        "local",
        "--env",
        "local",
        "--section-texts",
        "1,5",
        "--non-runtime",
        "src",
        "--runtime",
        "docs",
        "--table-sections",
        "7",
        "--max-cell",
        "5",
        "--max-text",
        "12",
        "--max-record",
        "3",
        "--max-commits",
        "1",
    )
    assert out["filters"] == {
        "services": ["payment"],
        "stack": "local",
        "environment": "local",
    }
    assert out["matched"] == 1
    sections = {s["number"]: s for s in out["reports"][0]["sections"]}
    assert sections[1]["text"] is not None
    assert sections[3]["text"] is None
    assert sections[5]["text"] == "- **Logs: ab…"
    assert sections[5]["text_truncated"] is True
    assert sections[7]["tables"][0]["rows"][0] == ["p95 P…", "120 m…", "< 80 …"]
    assert out["reports"][0]["scenario_record"] == "Ad-…"
    assert sections[2]["tables"] == []


def test_cli_outside_a_git_repository_exits_2(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(tmp_path)],
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
        check=False,
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "git repository" in proc.stderr


def test_scenario_record_is_also_found_as_a_bold_label(repo):
    body = DEFAULT_BODY.replace(
        "### Scenario record (verbatim)\n\nAd-hoc: 30 calls.",
        "- **Scenario record** (`run-scenario` section 6): Ad-hoc,\n"
        "  30 calls in a row.\n- **Timeline (UTC):** 10:00 start.",
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body=body),
    )
    repo.commit("docs(odd): report")
    record = facts(repo)["reports"][0]["scenario_record"]
    assert record.startswith(
        "- **Scenario record** (`run-scenario` section 6): Ad-hoc,"
    )
    assert "30 calls in a row." in record
    assert "Timeline" not in record


# --- the memory invariant (issue #307) ---------------------------------------


def _violations(facts_: dict) -> dict[str, list[str]]:
    return {
        Path(v["path"]).name: v["problems"] for v in facts_["invariant"]["violations"]
    }


def test_invariant_is_clean_for_a_conforming_store(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md", observation()
    )
    repo.commit("docs(odd): report")
    result = facts(repo)
    assert result["invariant"] == {"checked": 1, "violations": [], "legacy": []}


def test_invariant_flags_missing_and_malformed_frontmatter_fields(repo):
    text = (
        observation()
        .replace("depth: full\n", "")
        .replace(
            "window: 2026-08-10T10:00:00Z/2026-08-10T10:05:00Z",
            "window: 10:00 to 10:05",
        )
        .replace("mode: drive", "mode: drove")
    )
    repo.write(".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md", text)
    repo.commit("docs(odd): report")
    problems = _violations(facts(repo))["2026-08-10-1000-checkout-sweep.md"]
    assert any(p.startswith("depth absent") for p in problems)
    assert any(p.startswith("window") for p in problems)
    assert any(p.startswith("mode") for p in problems)
    assert facts(repo)["invariant"]["checked"] == 1


def test_invariant_lists_a_report_predating_depth_as_legacy_not_violation(repo):
    # The contract reads a report without depth as full: nothing can ever
    # change an append-only file, so it is a note, not a violation.
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md",
        observation().replace("depth: full\n", ""),
    )
    repo.commit("docs(odd): report")
    result = facts(repo)["invariant"]
    assert result["violations"] == []
    assert result["legacy"] == [
        ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md"
    ]


def test_invariant_resolves_a_bare_verifies_against_observation_reports_only(repo):
    # A bare filename names a sibling observation report; an instrumentation
    # baseline is named by its repo-relative path (the report reference).
    repo.write(
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app.md",
        "---\nproject: app\nstack: local\nrun_name: app\ndate: 2026-08-09\n---\n\n# plan\n",
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-12-1000-verify-app.md",
        observation(
            mode="verify",
            run_name="app",
            date="2026-08-12",
            extra_frontmatter="verifies: 2026-08-09-1000-app.md",
        ),
    )
    repo.commit("docs(odd): reports")
    problems = _violations(facts(repo))["2026-08-12-1000-verify-app.md"]
    assert any("verifies names no stored report" in p for p in problems)


def test_invariant_flags_a_window_whose_end_precedes_its_start(repo):
    text = observation().replace(
        "window: 2026-08-10T10:00:00Z/2026-08-10T10:05:00Z",
        "window: 2026-08-10T10:05:00Z/2026-08-10T10:00:00Z",
    )
    repo.write(".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md", text)
    repo.commit("docs(odd): report")
    problems = _violations(facts(repo))["2026-08-10-1000-checkout-sweep.md"]
    assert any("end precedes" in p for p in problems)


def test_invariant_flags_a_verifies_naming_no_stored_report(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md", observation()
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-12-1000-verify-checkout.md",
        observation(
            mode="verify",
            run_name="checkout",
            date="2026-08-12",
            extra_frontmatter="verifies: 2026-08-01-1000-ghost.md",
        ),
    )
    repo.commit("docs(odd): reports")
    violations = _violations(facts(repo))
    assert "2026-08-10-1000-checkout-sweep.md" not in violations
    assert any(
        "verifies" in p and "ghost" in p
        for p in violations["2026-08-12-1000-verify-checkout.md"]
    )


def test_invariant_requires_verifies_on_a_replay_and_accepts_an_instrumentation_path(
    repo,
):
    repo.write(
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app.md",
        "---\nproject: app\nstack: local\nrun_name: app\ndate: 2026-08-09\n---\n\n# plan\n",
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-12-1000-verify-app.md",
        observation(
            mode="verify",
            run_name="app",
            date="2026-08-12",
            extra_frontmatter="verifies: .odd/otel-instrumentation-reports/2026-08-09-1000-app.md",
        ),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-13-1000-remeasure-app.md",
        observation(mode="re-measure", run_name="app", date="2026-08-13"),
    )
    repo.commit("docs(odd): reports")
    violations = _violations(facts(repo))
    assert "2026-08-12-1000-verify-app.md" not in violations
    assert any(
        "verifies absent" in p for p in violations["2026-08-13-1000-remeasure-app.md"]
    )


def test_invariant_flags_a_filename_off_the_convention_and_a_mismatched_slug(repo):
    repo.write(".odd/observe-run-reports/notes.md", observation())
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-other-slug.md",
        observation(date="2026-08-10"),
    )
    repo.commit("docs(odd): reports")
    violations = _violations(facts(repo))
    assert any("filename" in p for p in violations["notes.md"])
    problems = violations["2026-08-11-1000-other-slug.md"]
    assert any("slug" in p and "run_name" in p for p in problems)
    assert any("date" in p for p in problems)


def test_invariant_expects_the_replay_prefix_on_a_verification_filename(repo):
    # A verification keeps the replayed run_name and prefixes its filename
    # with verify-: a file named without the prefix is a violation, and a
    # file named with it but carrying the prefixed run_name is one too.
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md", observation()
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-12-1000-checkout-sweep.md",
        observation(
            mode="verify",
            date="2026-08-12",
            extra_frontmatter="verifies: 2026-08-10-1000-checkout-sweep.md",
        ),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-13-1000-verify-checkout-sweep.md",
        observation(
            mode="verify",
            run_name="verify-checkout-sweep",
            date="2026-08-13",
            extra_frontmatter="verifies: 2026-08-10-1000-checkout-sweep.md",
        ),
    )
    repo.commit("docs(odd): reports")
    violations = _violations(facts(repo))
    assert any(
        "'verify-checkout-sweep'" in p
        for p in violations["2026-08-12-1000-checkout-sweep.md"]
    )
    assert any(
        "with the verify- prefix" in p
        for p in violations["2026-08-13-1000-verify-checkout-sweep.md"]
    )


def test_invariant_checks_an_instrumentation_report_and_an_unreadable_file(repo):
    repo.write(
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app.md",
        "---\nstack: local\nrun_name: app\ndate: 2026-08-09\n---\n\n# plan\n",
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-broken.md", "no frontmatter at all\n"
    )
    repo.commit("docs(odd): reports")
    violations = _violations(facts(repo))
    assert any("project absent" in p for p in violations["2026-08-09-1000-app.md"])
    assert any("frontmatter" in p for p in violations["2026-08-10-1000-broken.md"])


def test_invariant_covers_every_stored_report_even_when_the_status_is_filtered(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-checkout-sweep.md",
        observation().replace("mode: drive", "mode: drove"),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-cart-sweep.md",
        observation(services="[cart]", run_name="cart-sweep", date="2026-08-11"),
    )
    repo.commit("docs(odd): reports")
    result = facts(repo, services=["cart"])
    assert result["matched"] == 1
    assert result["invariant"]["checked"] == 2
    assert "2026-08-10-1000-checkout-sweep.md" in _violations(result)


# --- the entry-classification ledger ------------------------------------------------


CLASSIFICATIONS_HEAD = (
    "# ODD entry classifications\n\nRows are appended, never rewritten.\n\n"
    "| Date | Entry | Class | Rationale |\n|---|---|---|---|\n"
)


def _anchored_report(repo: Repo) -> None:
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(
            run_name="a", extra_frontmatter=f"tree_anchor: {repo.tree_anchor()}"
        ),
    )
    repo.commit("docs(odd): report")


def test_classifications_absent_is_a_fact(repo):
    _anchored_report(repo)
    assert facts(repo)["classifications"] == {
        "present": False,
        "rows": [],
        "effective": {},
    }


def test_classification_rows_are_read_latest_wins_and_bad_rows_are_reported(repo):
    _anchored_report(repo)
    repo.write(
        ".odd/entry-classifications.md",
        CLASSIFICATIONS_HEAD
        + "| 2026-08-11 | src | non-runtime | first thought |\n"
        + "| 2026-08-12 | src | runtime | the service |\n"
        + "| 2026-08-12 | Docs | runtime | served by the service |\n"
        + "| 2026-08-12 | nope | runtime | no such entry |\n"
        + "| 2026-08-12 | src | maybe | no such class |\n"
        + "| 2026-08-12 | src | runtime |\n",
    )
    repo.commit("docs(odd): classifications")
    ledger = facts(repo)["classifications"]
    assert ledger["present"] is True
    assert [(r["line"], r["status"]) for r in ledger["rows"]] == [
        (7, "ok"),
        (8, "ok"),
        (9, "ok"),
        (10, "skipped"),
        (11, "skipped"),
        (12, "skipped"),
    ]
    reasons = {
        r["line"]: r["reason"] for r in ledger["rows"] if r["status"] == "skipped"
    }
    assert reasons[10] == "no top-level entry named nope at HEAD"
    assert reasons[11] == "class is neither runtime nor non-runtime: maybe"
    assert reasons[12] == "expected 4 columns, got 3"
    assert ledger["effective"]["src"]["class"] == "runtime"
    assert ledger["effective"]["src"]["line"] == 8
    assert ledger["effective"]["docs"]["class"] == "runtime"


def test_classification_precedence_is_flag_then_file_then_built_in(repo):
    _anchored_report(repo)
    repo.write(
        ".odd/entry-classifications.md",
        CLASSIFICATIONS_HEAD
        + "| 2026-08-12 | src | non-runtime | a vendored mirror, never run |\n"
        + "| 2026-08-12 | docs | runtime | served by the service |\n",
    )
    repo.commit("docs(odd): classifications")
    repo.write("src/app.py", "print('v2')\n")
    repo.write("docs/guide.md", "# v2\n")
    repo.write("README.md", "# v2\n")
    repo.commit("feat: change everything")
    # the file settles src and docs, the built-in list settles README.md
    diff = facts(repo)["reports"][0]["tree_anchor_diff"]
    assert diff["non_runtime"] == ["README.md", "src"]
    assert diff["runtime"] == ["docs"]
    assert diff["unclassified"] == []
    assert diff["classified_by"] == {
        "README.md": "built-in",
        "src": "file",
        "docs": "file",
    }
    # a flag overrides the file for one run, in both directions
    diff = facts(repo, runtime=["src"], non_runtime=["docs"])["reports"][0][
        "tree_anchor_diff"
    ]
    assert diff["runtime"] == ["src"] and "docs" in diff["non_runtime"]
    assert diff["classified_by"]["src"] == "flag"
    assert diff["classified_by"]["docs"] == "flag"


def test_a_classifications_only_commit_is_memory_not_code(repo):
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev),
    )
    repo.commit("docs(odd): report")
    repo.write(".odd/entry-classifications.md", CLASSIFICATIONS_HEAD)
    repo.commit("docs(odd): entry classification src runtime")
    assert facts(repo)["reports"][0]["commits_since"]["count"] == 0
