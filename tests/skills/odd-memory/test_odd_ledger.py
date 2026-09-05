"""Tests for the odd-memory skill's ledger script.

The script is the only writer of the maintainer-ruling ledgers. It is
loaded from its packaged location so the tests exercise the very file
the skill ships; every test builds a throwaway git repository.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[3] / ".apm" / "skills"
SCRIPT = SKILLS / "odd-memory" / "scripts" / "odd_ledger.py"
STATUS_SCRIPT = SKILLS / "get-status" / "scripts" / "odd_status.py"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "example-user",
    "GIT_AUTHOR_EMAIL": "example-user@example.com",
    "GIT_COMMITTER_NAME": "example-user",
    "GIT_COMMITTER_EMAIL": "example-user@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _load(name: str, path: Path):
    sys.dont_write_bytecode = True  # never leave a __pycache__ in the packaged skill
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ledger():
    return _load("odd_ledger", SCRIPT)


@pytest.fixture(scope="module")
def odd_status():
    return _load("odd_status", STATUS_SCRIPT)


class Repo:
    def __init__(self, root: Path):
        self.root = root
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            cwd=self.root,
            env={**os.environ, **GIT_ENV},
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def write(self, rel: str, content: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding="utf-8")

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "--short", "HEAD")


REPORT = """\
---
services: [checkout]
stack: local
environment: local
mode: drive
depth: full
window: 2026-08-10T10:00:00Z/2026-08-10T10:01:00Z
run_name: a
date: 2026-08-10
---
**Answer to the question:** one finding worth a fix.

## 1. Mission and run record

- **Service:** `checkout`.

## 2. Observed behavior

| Operation | Requests | p95 |
|---|---|---|
| POST /checkout | 30 | 120 ms |

## 3. Anomalies and probable causes

| # | Finding | Severity | Confidence | Evidence | Expected gain |
|---|---|---|---|---|---|
| F1 | N+1 on cart lines | high | confirmed | 30 spans per call | p95 -60 ms |
| **F2** | Cold start | low | suspected | first call 400 ms | none |

The retry storm P7 is discussed in prose only, below the table.

## 4. Improvement opportunities

- Batch the cart lines query (see C9 in the protocol, not a finding).
"""


def report(services="[checkout]", stack="local", environment="local", body=REPORT):
    return (
        body.replace("services: [checkout]", f"services: {services}")
        .replace("stack: local", f"stack: {stack}")
        .replace("environment: local", f"environment: {environment}")
    )


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    r.write("src/app.py", "print('v1')\n")
    r.write(".odd/observe-run-reports/2026-08-10-1000-a.md", REPORT)
    r.commit("docs(odd): observation report a")
    return r


def run(repo: Repo, *args: str) -> subprocess.CompletedProcess:
    # no global configuration: the suite never depends on the developer's own
    config = () if "--config" in args else ("--config", os.devnull)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo.root), *config, *args],
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
        check=False,
    )


DECIDE = ("decide", "2026-08-10-1000-a.md/F1", "wontfix", "--rationale")


# --- decide ------------------------------------------------------------------------


def test_decide_creates_the_ledger_with_the_skeleton_and_one_row(repo, ledger):
    proc = run(repo, *DECIDE, "Batching is not worth the risk", "--today", "2026-08-13")
    assert proc.returncode == 0, proc.stderr
    text = repo.read(".odd/decisions.md")
    assert text.startswith(ledger.SKELETON)
    assert text.endswith(
        "| 2026-08-13 | 2026-08-10-1000-a.md / F1 | wontfix "
        "| Batching is not worth the risk |\n"
    )
    lines = dict(line.split(": ", 1) for line in proc.stdout.splitlines())
    assert lines["path"] == ".odd/decisions.md"
    assert lines["row"] == (
        "| 2026-08-13 | 2026-08-10-1000-a.md / F1 | wontfix "
        "| Batching is not worth the risk |"
    )
    assert lines["branch"] == "docs/odd-finding-decision-f1-wontfix"
    assert lines["subject"] == "docs(odd): finding decision F1 wontfix"
    assert not (SCRIPT.parent / "__pycache__").exists()


def test_decide_appends_and_leaves_the_rows_above_untouched(repo, ledger):
    run(repo, *DECIDE, "first", "--today", "2026-08-13")
    before = repo.read(".odd/decisions.md")
    proc = run(
        repo,
        "decide",
        "2026-08-10-1000-a.md / F2",
        "accepted-by-design",
        "--rationale",
        "Cold start is the design",
        "--today",
        "2026-08-14",
    )
    assert proc.returncode == 0, proc.stderr
    after = repo.read(".odd/decisions.md")
    assert after.startswith(before)
    assert after[len(before) :] == (
        "| 2026-08-14 | 2026-08-10-1000-a.md / F2 | accepted-by-design "
        "| Cold start is the design |\n"
    )


def test_decide_accepts_a_report_path_and_a_bold_id_in_the_table(repo):
    proc = run(
        repo,
        "decide",
        ".odd/observe-run-reports/2026-08-10-1000-a.md/F2",
        "wontfix",
        "--rationale",
        "fine",
        "--today",
        "2026-08-13",
    )
    assert proc.returncode == 0, proc.stderr
    assert "| 2026-08-10-1000-a.md / F2 | wontfix |" in repo.read(".odd/decisions.md")


def test_decide_finds_an_id_named_only_in_section_3_prose(repo):
    proc = run(
        repo,
        "decide",
        "2026-08-10-1000-a.md/P7",
        "wontfix",
        "--rationale",
        "retries are bounded",
        "--today",
        "2026-08-13",
    )
    assert proc.returncode == 0, proc.stderr


def test_decide_appends_after_a_ledger_without_a_final_newline(repo, ledger):
    repo.write(".odd/decisions.md", ledger.SKELETON.rstrip("\n"))
    proc = run(repo, *DECIDE, "fine", "--today", "2026-08-13")
    assert proc.returncode == 0, proc.stderr
    text = repo.read(".odd/decisions.md")
    assert text.startswith(ledger.SKELETON)
    assert text.count("\n| 2026-08-13 |") == 1


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (("decide", "F1", "wontfix", "--rationale", "x"), "not <report>/<ID>"),
        (
            ("decide", "2026-08-10-1000-a.md/F1", "wontfix", "--rationale", ""),
            "rationale is required",
        ),
        (
            ("decide", "2026-08-10-1000-a.md/F1", "wontfix", "--rationale", "  "),
            "rationale is required",
        ),
        (
            ("decide", "2026-08-10-1000-a.md/F1", "wontfix", "--rationale", "a\nb"),
            "one line",
        ),
        (
            ("decide", "2026-08-10-1000-a.md/F1", "wontfix", "--rationale", "a | b"),
            "no '|'",
        ),
        (
            ("decide", "2026-08-10-1000-a.md/F1", "wontfix", "--rationale", "x"),
            None,
        ),
        (
            ("decide", "2026-08-11-1000-b.md/F1", "wontfix", "--rationale", "x"),
            "no stored report named 2026-08-11-1000-b.md",
        ),
        (
            ("decide", "2026-08-10-1000-a.md/F9", "wontfix", "--rationale", "x"),
            "2026-08-10-1000-a.md carries no finding F9",
        ),
        (
            ("decide", "2026-08-10-1000-a.md/C9", "wontfix", "--rationale", "x"),
            "carries no finding C9",
        ),
        (
            ("decide", "2026-08-10-1000-a.md/F1", "open", "--rationale", "x"),
            "use reopen",
        ),
        (
            ("decide", "2026-08-10-1000-a.md/F1", "won't fix", "--rationale", "x"),
            "verdict is one word",
        ),
        (
            (
                "decide",
                "2026-08-10-1000-a.md/F1",
                "wontfix",
                "--rationale",
                "seen on 3f2a9c1e-7b4d-4e8a-9c21-5d6e7f8a9b0c",
            ),
            "identifier",
        ),
        (
            (
                "decide",
                "2026-08-10-1000-a.md/F1",
                "wontfix",
                "--rationale",
                "logged under /Users/example-user/work",
            ),
            "home-directory path",
        ),
        (
            (
                "decide",
                "2026-08-10-1000-a.md/F1",
                "wontfix",
                "--rationale",
                "x",
                "--today",
                "13/08/2026",
            ),
            "YYYY-MM-DD",
        ),
    ],
)
def test_decide_refuses_with_one_reason_and_writes_nothing(repo, args, reason):
    proc = run(repo, *args)
    if reason is None:
        assert proc.returncode == 0, proc.stderr
        return
    assert proc.returncode == 2, proc.stdout
    assert reason in proc.stderr
    assert len(proc.stderr.strip().splitlines()) == 1
    assert proc.stdout == ""
    assert not (repo.root / ".odd" / "decisions.md").exists()


def test_a_refusal_never_touches_an_existing_ledger(repo):
    run(repo, *DECIDE, "first", "--today", "2026-08-13")
    before = repo.read(".odd/decisions.md")
    proc = run(repo, "decide", "2026-08-10-1000-a.md/F9", "wontfix", "--rationale", "x")
    assert proc.returncode == 2
    assert repo.read(".odd/decisions.md") == before


def test_decide_writes_the_ledger_and_nothing_else(repo):
    proc = run(repo, *DECIDE, "fine", "--today", "2026-08-13")
    assert proc.returncode == 0, proc.stderr
    assert repo.git("status", "--porcelain") == "?? .odd/decisions.md"
    assert [p.name for p in (repo.root / ".odd").iterdir() if p.is_file()] == [
        "decisions.md"
    ]


def test_an_empty_ledger_file_gets_the_skeleton(repo, ledger):
    repo.write(".odd/decisions.md", "")
    proc = run(repo, *DECIDE, "fine", "--today", "2026-08-13")
    assert proc.returncode == 0, proc.stderr
    text = repo.read(".odd/decisions.md")
    assert text.startswith(ledger.SKELETON) and text.count("| 2026-08-13 |") == 1


@pytest.mark.parametrize(
    "rationale",
    [
        "the zeroed 00000000-0000-0000-0000-000000000000 id is a placeholder",
        "the runner clone under /home/runner/work is generic",
        "a <user> placeholder path /Users/<user>/work is fine",
        "the Contoso tenant is the documented placeholder",
    ],
)
def test_the_scan_exemptions_hold_for_a_rationale(repo, rationale):
    proc = run(repo, *DECIDE, rationale, "--today", "2026-08-13")
    assert proc.returncode == 0, proc.stderr


def test_a_stack_config_value_of_the_global_configuration_is_refused(repo, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        '{"stack": "azure-monitor", "stack_config": {"azure-monitor": '
        '{"workspace": "acme-prod-eu", "region": "westeurope"}, '
        '"local": {"grafana_port": "3000"}}}'
    )
    refused = run(
        repo,
        "--config",
        str(config),
        *DECIDE,
        "only the acme-prod-eu workspace sees it",
        "--today",
        "2026-08-13",
    )
    assert refused.returncode == 2 and "stack_config" in refused.stderr
    assert not (repo.root / ".odd" / "decisions.md").exists()
    # a neutral key's value and the local stack's values are not identifiers
    ok = run(
        repo,
        "--config",
        str(config),
        *DECIDE,
        "westeurope on port 3000 is fine",
        "--today",
        "2026-08-13",
    )
    assert ok.returncode == 0, ok.stderr
    # no configuration at all: nothing to protect, never a refusal
    ok = run(repo, "--config", str(tmp_path / "missing.json"), *DECIDE, "acme-prod-eu")
    assert ok.returncode == 0, ok.stderr


def test_every_failure_is_one_stderr_line_and_exit_2(repo):
    for args in ((), ("decide",), ("decide", "a.md/F1"), ("nope",)):
        proc = run(repo, *args)
        assert proc.returncode == 2, args
        assert proc.stdout == "" and len(proc.stderr.strip().splitlines()) == 1, args
    (repo.root / ".odd/observe-run-reports/2026-08-11-1000-bad.md").write_bytes(
        b"---\nservices: [x]\n---\n\xff\xfe not utf-8"
    )
    proc = run(
        repo, "decide", "2026-08-11-1000-bad.md/F1", "wontfix", "--rationale", "x"
    )
    assert proc.returncode == 2 and "cannot read 2026-08-11-1000-bad.md" in proc.stderr
    proc = run(repo, "resolve", "F1")
    assert proc.returncode == 2 and "cannot read" in proc.stderr


def test_decide_uses_the_utc_date_by_default(repo, ledger, monkeypatch):
    proc = run(repo, *DECIDE, "fine")
    assert proc.returncode == 0, proc.stderr
    row = next(line for line in proc.stdout.splitlines() if line.startswith("row: "))
    date = row.split("|")[1].strip()
    assert date == ledger.utc_today()


# --- reopen ------------------------------------------------------------------------


def test_reopen_appends_an_open_row_with_its_own_branch_and_subject(repo):
    run(repo, *DECIDE, "first", "--today", "2026-08-13")
    proc = run(
        repo,
        "reopen",
        "2026-08-10-1000-a.md/F1",
        "--rationale",
        "the fix shipped after all",
        "--today",
        "2026-08-20",
    )
    assert proc.returncode == 0, proc.stderr
    assert repo.read(".odd/decisions.md").endswith(
        "| 2026-08-20 | 2026-08-10-1000-a.md / F1 | open | the fix shipped after all |\n"
    )
    lines = dict(line.split(": ", 1) for line in proc.stdout.splitlines())
    assert lines["branch"] == "docs/odd-finding-decision-f1-open"
    assert lines["subject"] == "docs(odd): finding decision F1 open"


# --- resolve -----------------------------------------------------------------------


def test_resolve_lists_the_reports_carrying_the_id_newest_first(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-12-1000-b.md",
        report(services="[payment]", environment="prod").replace(
            "run_name: a", "run_name: b"
        ),
    )
    repo.commit("docs(odd): report b")
    proc = run(repo, "resolve", "F1")
    assert proc.returncode == 3, proc.stderr  # several candidates: ask, never guess
    assert proc.stdout.splitlines() == [
        "2026-08-12-1000-b.md / F1\tN+1 on cart lines",
        "2026-08-10-1000-a.md / F1\tN+1 on cart lines",
    ]
    proc = run(repo, "resolve", "F1", "--service", "payment")
    assert proc.returncode == 0
    assert proc.stdout == "2026-08-12-1000-b.md / F1\tN+1 on cart lines\n"
    proc = run(repo, "resolve", "F1", "--env", "local", "--stack", "local")
    assert proc.returncode == 0
    assert proc.stdout.startswith("2026-08-10-1000-a.md / F1\t")
    proc = run(repo, "resolve", "F9")
    assert proc.returncode == 2 and "no stored report carries F9" in proc.stderr
    proc = run(repo, "resolve", "P7")
    assert proc.returncode == 3
    assert "2026-08-10-1000-a.md / P7\t(named in section 3 prose)" in proc.stdout


# --- the branch name rule, as code -------------------------------------------------


@pytest.mark.parametrize(
    ("finding_id", "verdict", "branch"),
    [
        ("F4", "wontfix", "docs/odd-finding-decision-f4-wontfix"),
        (
            "A5 (2026-08-22-2227)",
            "wontfix",
            "docs/odd-finding-decision-a5-2026-08-22-2227-wontfix",
        ),
        ("N2", "accepted-by-design", "docs/odd-finding-decision-n2-accepted-by-design"),
    ],
)
def test_branch_name_normalizes_both_values(ledger, finding_id, verdict, branch):
    assert ledger.branch_name(finding_id, verdict) == branch


# --- one check, two callers: the ledger agrees with get-status -----------------------


SHAPES = {
    "well-formed": REPORT,
    # a section 3 heading without the dot is not section 3 for get-status
    "no-dot heading": REPORT.replace("## 3. Anomalies", "## 3 Anomalies"),
    # an ID as the first cell of a table header is not a finding
    "id in a header": REPORT.replace("| # | Finding |", "| H1 | Finding |"),
    # a pipe block without a separator line is prose, and its words count
    "pipe block without separator": REPORT.replace(
        "The retry storm P7 is discussed in prose only, below the table.",
        "| note | see Q3 | and R4 |\n| more | Q3 again | - |",
    ),
    # two section 3 headings: both contribute rows, the prose is the last one's
    "second section 3": REPORT
    + "\n## 3. Again\n\n| # | Finding |\n|---|---|\n| Z9 | dup |\n",
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize(
    "finding_id",
    ["F1", "F2", "P7", "F9", "C9", "H1", "Q3", "R4", "Z9", "POST", "Finding", "cart"],
)
def test_finding_check_agrees_with_get_status(
    repo, ledger, odd_status, shape, finding_id
):
    # the invariant's verdict on a ledger row naming the ID is the reference
    body = SHAPES[shape]
    repo.write(".odd/observe-run-reports/2026-08-10-1000-a.md", body)
    repo.write(
        ".odd/decisions.md",
        ledger.SKELETON
        + f"| 2026-08-13 | 2026-08-10-1000-a.md / {finding_id} | wontfix | x |\n",
    )
    facts = odd_status.build_facts(repo.root, recent=None)
    [row] = facts["ledger"]["rows"]
    expected = row["status"] == "ok"
    assert ledger.finding_in_report(body, finding_id) == expected, (shape, finding_id)


# --- degrade -----------------------------------------------------------------------


def test_outside_a_git_repository_or_without_the_store_the_script_says_so(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(tmp_path), *DECIDE, "x"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2 and "not a git repository" in proc.stderr
    r = Repo(tmp_path)
    r.write("README.md", "# x\n")
    r.commit("init")
    proc = run(r, *DECIDE, "x")
    assert proc.returncode == 2 and "no stored report named" in proc.stderr


# --- classify --------------------------------------------------------------------


CLASSIFY = ("classify", "src", "runtime", "--rationale")


def test_classify_creates_the_ledger_with_its_skeleton_and_one_row(repo, ledger):
    proc = run(repo, *CLASSIFY, "the service's code", "--today", "2026-08-13")
    assert proc.returncode == 0, proc.stderr
    text = repo.read(".odd/entry-classifications.md")
    assert text.startswith(ledger.CLASSIFICATIONS_SKELETON)
    assert text.endswith("| 2026-08-13 | src | runtime | the service's code |\n")
    lines = dict(line.split(": ", 1) for line in proc.stdout.splitlines())
    assert lines["path"] == ".odd/entry-classifications.md"
    assert lines["row"] == "| 2026-08-13 | src | runtime | the service's code |"
    assert lines["branch"] == "docs/odd-entry-classification-src-runtime"
    assert lines["subject"] == "docs(odd): entry classification src runtime"
    assert repo.git("status", "--porcelain") == "?? .odd/entry-classifications.md"
    assert not (repo.root / ".odd" / "decisions.md").exists()


def test_classify_leaves_an_existing_decisions_ledger_byte_identical(repo):
    run(repo, *DECIDE, "first", "--today", "2026-08-13")
    before = repo.read(".odd/decisions.md")
    proc = run(repo, *CLASSIFY, "the service's code", "--today", "2026-08-13")
    assert proc.returncode == 0, proc.stderr
    assert repo.read(".odd/decisions.md") == before


def test_classify_appends_a_later_row_and_normalizes_the_class(repo):
    run(repo, *CLASSIFY, "first", "--today", "2026-08-13")
    before = repo.read(".odd/entry-classifications.md")
    proc = run(
        repo,
        "classify",
        "src/",
        "Non-Runtime",
        "--rationale",
        "moved",
        "--today",
        "2026-08-14",
    )
    assert proc.returncode == 0, proc.stderr
    after = repo.read(".odd/entry-classifications.md")
    assert after.startswith(before)
    assert after[len(before) :] == "| 2026-08-14 | src | non-runtime | moved |\n"


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (("classify", "nope", "runtime", "--rationale", "x"), "not a top-level entry"),
        (
            ("classify", ".odd", "non-runtime", "--rationale", "x"),
            "always ignores .odd",
        ),
        (
            ("classify", "src/app.py", "runtime", "--rationale", "x"),
            "not a top-level entry",
        ),
        (("classify", "src", "maybe", "--rationale", "x"), "runtime or non-runtime"),
        (("classify", "src", "runtime", "--rationale", ""), "rationale is required"),
        (
            (
                "classify",
                "src",
                "runtime",
                "--rationale",
                "under /Users/example-user/x",
            ),
            "home-directory path",
        ),
        (
            ("classify", "src", "runtime", "--rationale", "x", "--today", "yesterday"),
            "YYYY-MM-DD",
        ),
    ],
)
def test_classify_refuses_with_one_reason_and_writes_nothing(repo, args, reason):
    proc = run(repo, *args)
    assert proc.returncode == 2, proc.stdout
    assert reason in proc.stderr and len(proc.stderr.strip().splitlines()) == 1
    assert proc.stdout == ""
    assert not (repo.root / ".odd" / "entry-classifications.md").exists()


def test_classify_refuses_without_a_head_commit(tmp_path):
    r = Repo(tmp_path)
    proc = run(r, *CLASSIFY, "x")
    assert proc.returncode == 2 and "no HEAD commit" in proc.stderr


def test_classification_branch_name_normalizes_the_entry(ledger):
    assert (
        ledger.classification_branch_name(".apm", "non-runtime")
        == "docs/odd-entry-classification-apm-non-runtime"
    )
    assert (
        ledger.classification_branch_name("apm.yml", "runtime")
        == "docs/odd-entry-classification-apm-yml-runtime"
    )
