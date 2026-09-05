"""Tests for the odd-memory skill's recall script.

The script lists the stored reports matching a mission's scope, newest
first, one line each, so a recall reads one frontmatter - the baseline's -
instead of every one. Loaded from its packaged location; every test
builds a throwaway git repository.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[3] / ".apm" / "skills"
SCRIPT = SKILLS / "odd-memory" / "scripts" / "odd_recall.py"
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
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recall():
    return _load("odd_recall", SCRIPT)


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

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "--short", "HEAD")


def observation(
    *,
    services="[checkout]",
    stack="local",
    environment="local",
    mode="drive",
    depth="full",
    run_name="a",
    date="2026-08-10",
    extra="",
) -> str:
    lines = [
        "---",
        f"services: {services}",
        f"stack: {stack}",
        f"environment: {environment}",
        f"mode: {mode}",
        *([f"depth: {depth}"] if depth else []),
        f"window: {date}T10:00:00Z/{date}T10:05:00Z",
        f"run_name: {run_name}",
        f"date: {date}",
        *([extra] if extra else []),
        "---",
        "",
        "## 1. Mission and run record",
        "",
        "- **Service:** checkout.",
        "",
    ]
    return "\n".join(lines)


def plan(
    *, project="myrepo/src", stack="local", run_name="app-python", date="2026-08-09"
):
    return (
        f"---\nproject: {project}\nstack: {stack}\nrun_name: {run_name}\n"
        f"date: {date}\n---\n\n## 1. Summary\n"
    )


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    r.write("src/app.py", "print('v1')\n")
    r.commit("feat: initial")
    return r


def run(repo: Repo, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo.root), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
        check=False,
    )


def lines(proc: subprocess.CompletedProcess) -> list[list[str]]:
    return [line.split("\t") for line in proc.stdout.splitlines()]


OBS = ".odd/observe-run-reports"
INS = ".odd/otel-instrumentation-reports"


def store(repo: Repo) -> None:
    repo.write(f"{OBS}/2026-08-10-1000-a.md", observation(run_name="a"))
    repo.write(
        f"{OBS}/2026-08-11-1000-b.md",
        observation(
            services="[checkout, payment]",
            environment="prod",
            run_name="b",
            date="2026-08-11",
            extra="workload: peak-hour\nrepository: github.com/example-org/checkout",
        ),
    )
    repo.write(
        f"{OBS}/2026-08-12-1000-verify-a.md",
        observation(
            mode="verify",
            run_name="a",
            date="2026-08-12",
            extra="verifies: 2026-08-10-1000-a.md",
        ),
    )
    repo.write(
        f"{OBS}/2026-08-13-1000-c.md",
        observation(
            services="[payment]", stack="grafana", run_name="c", date="2026-08-13"
        ),
    )
    repo.write(f"{INS}/2026-08-09-1000-app-python.md", plan())
    repo.commit("docs(odd): reports")


# --- listing -------------------------------------------------------------------


def test_recall_lists_the_matches_newest_first_with_the_frontmatter_columns(repo):
    store(repo)
    proc = run(repo, "--service", "checkout")
    assert proc.returncode == 0, proc.stderr
    assert lines(proc) == [
        [
            "2026-08-12-1000-verify-a.md",
            "observation",
            "checkout",
            "local",
            "local",
            "verify",
            "full",
            "2026-08-10-1000-a.md",
            "-",
            "-",
        ],
        [
            "2026-08-11-1000-b.md",
            "observation",
            "checkout,payment",
            "local",
            "prod",
            "drive",
            "full",
            "-",
            "peak-hour",
            "github.com/example-org/checkout",
        ],
        [
            "2026-08-10-1000-a.md",
            "observation",
            "checkout",
            "local",
            "local",
            "drive",
            "full",
            "-",
            "-",
            "-",
        ],
    ]
    assert proc.stderr == ""


def test_a_per_service_repository_map_prints_as_service_equals_repository(repo):
    repo.write(
        f"{OBS}/2026-08-10-1000-a.md",
        observation(
            services="[checkout, payment]",
            extra="repository: {checkout: github.com/example-org/checkout, payment: gitlab.com/example-group/payment, cart: }",
        ),
    )
    repo.commit("docs(odd): report")
    assert lines(run(repo))[0][9] == (
        "checkout=github.com/example-org/checkout,payment=gitlab.com/example-group/payment,cart=-"
    )


def test_services_intersect_and_stack_and_environment_filter(repo):
    store(repo)
    assert [l[0] for l in lines(run(repo, "--service", "payment"))] == [
        "2026-08-13-1000-c.md",
        "2026-08-11-1000-b.md",
    ]
    assert [
        l[0] for l in lines(run(repo, "--service", "payment", "--stack", "local"))
    ] == ["2026-08-11-1000-b.md"]
    assert [
        l[0] for l in lines(run(repo, "--service", "checkout", "--env", "prod"))
    ] == ["2026-08-11-1000-b.md"]
    # two services: a report matches when it carries any of them
    assert len(lines(run(repo, "--service", "checkout", "--service", "payment"))) == 4
    # no scope at all: the whole observation store
    assert len(lines(run(repo))) == 4


def test_an_unknown_environment_matches_only_another_unknown(repo):
    repo.write(f"{OBS}/2026-08-10-1000-a.md", observation(environment="unknown"))
    repo.write(
        f"{OBS}/2026-08-11-1000-b.md", observation(run_name="b", date="2026-08-11")
    )
    repo.commit("docs(odd): reports")
    assert [l[0] for l in lines(run(repo, "--env", "unknown"))] == [
        "2026-08-10-1000-a.md"
    ]
    assert [l[0] for l in lines(run(repo, "--env", "local"))] == [
        "2026-08-11-1000-b.md"
    ]
    # provisional environment (none given): both match, environment pending
    assert len(lines(run(repo))) == 2


def test_a_full_mission_skips_a_newer_quick_report_and_names_it(repo):
    repo.write(f"{OBS}/2026-08-10-1000-a.md", observation(run_name="a"))
    repo.write(
        f"{OBS}/2026-08-11-1000-q.md",
        observation(run_name="q", date="2026-08-11", depth="quick"),
    )
    repo.write(
        f"{OBS}/2026-08-09-1000-old.md",
        observation(run_name="old", date="2026-08-09", depth=""),
    )
    repo.commit("docs(odd): reports")
    proc = run(repo, "--depth", "full")
    assert [l[0] for l in lines(proc)] == [
        "2026-08-10-1000-a.md",
        "2026-08-09-1000-old.md",
    ]
    assert proc.stderr.strip() == "newer quick report skipped: 2026-08-11-1000-q.md"
    assert [l[6] for l in lines(proc)] == ["full", "-"]  # depth absent reads as full
    proc = run(repo, "--depth", "quick")
    assert next(l[0] for l in lines(proc)) == "2026-08-11-1000-q.md"
    assert proc.stderr == ""


def test_mode_filters_the_matches(repo):
    store(repo)
    assert [l[0] for l in lines(run(repo, "--mode", "verify"))] == [
        "2026-08-12-1000-verify-a.md"
    ]
    assert len(lines(run(repo, "--mode", "verify", "--mode", "drive"))) == 4


def test_instrumentation_reports_match_when_the_project_covers_the_scope(repo):
    store(repo)
    proc = run(repo, "--kind", "instrumentation", "--project", "myrepo/src/app")
    assert lines(proc) == [
        [
            "2026-08-09-1000-app-python.md",
            "instrumentation",
            "myrepo/src",
            "local",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
        ]
    ]
    assert (
        lines(run(repo, "--kind", "instrumentation", "--project", "myrepo/src")) != []
    )
    assert (
        lines(run(repo, "--kind", "instrumentation", "--project", "myrepo/srcx")) == []
    )
    assert (
        lines(
            run(
                repo,
                "--kind",
                "instrumentation",
                "--project",
                "myrepo/src",
                "--stack",
                "grafana",
            )
        )
        == []
    )
    assert lines(run(repo, "--kind", "instrumentation")) != []


# --- nothing matches, nothing stored -------------------------------------------------


def test_a_scope_matching_nothing_prints_nothing_and_says_what_exists(repo):
    store(repo)
    proc = run(repo, "--service", "orders", "--env", "uat")
    assert proc.returncode == 0 and proc.stdout == ""
    assert "no stored report matches service orders, environment uat" in proc.stderr
    assert "services: checkout, payment" in proc.stderr
    assert "stacks: grafana, local" in proc.stderr
    assert "environments: local, prod" in proc.stderr


def test_an_absent_or_empty_store_is_a_first_run(repo):
    proc = run(repo, "--service", "checkout")
    assert proc.returncode == 0 and proc.stdout == ""
    assert "no report under .odd/observe-run-reports/ - a first run" in proc.stderr
    (repo.root / OBS).mkdir(parents=True)
    proc = run(repo)
    assert proc.returncode == 0 and proc.stdout == "" and "first run" in proc.stderr


# --- a malformed report is listed and reported, never skipped silently ---------------


def test_a_malformed_report_is_listed_and_reported(repo):
    repo.write(
        f"{OBS}/2026-08-10-1000-a.md",
        observation()
        .replace("mode: drive", "mode: drove")
        .replace("window: ", "when: "),
    )
    repo.commit("docs(odd): report")
    proc = run(repo)
    assert proc.returncode == 0
    assert lines(proc)[0][0] == "2026-08-10-1000-a.md"
    assert "2026-08-10-1000-a.md: window absent" in proc.stderr
    assert "2026-08-10-1000-a.md: mode 'drove' is not one of" in proc.stderr


def test_a_flagged_report_outside_the_scope_is_still_reported(repo):
    # the flaw sits in the very field the scope matches on: no stack at all
    repo.write(
        f"{OBS}/2026-08-10-1000-a.md", observation().replace("stack: local\n", "")
    )
    repo.write(
        f"{OBS}/2026-08-11-1000-b.md", observation(run_name="b", date="2026-08-11")
    )
    repo.commit("docs(odd): reports")
    proc = run(repo, "--service", "checkout", "--stack", "local")
    assert [l[0] for l in lines(proc)] == ["2026-08-11-1000-b.md"]
    assert "not matched, flagged: 2026-08-10-1000-a.md: stack absent" in proc.stderr


def test_no_full_match_says_so_instead_of_a_misleading_skip(repo):
    repo.write(f"{OBS}/2026-08-10-1000-a.md", observation(depth="quick"))
    repo.write(
        f"{OBS}/2026-08-11-1000-b.md",
        observation(run_name="b", date="2026-08-11", depth="quick"),
    )
    repo.commit("docs(odd): reports")
    proc = run(repo, "--depth", "full")
    assert proc.stdout == ""
    assert (
        "no full match; 2 quick report(s) skipped: 2026-08-11-1000-b.md, 2026-08-10-1000-a.md"
        in proc.stderr
    )
    assert "newer quick" not in proc.stderr


def test_an_empty_or_null_depth_reads_as_full(repo):
    repo.write(
        f"{OBS}/2026-08-10-1000-a.md",
        observation(depth="").replace("mode: drive", "mode: drive\ndepth:"),
    )
    repo.write(
        f"{OBS}/2026-08-11-1000-b.md",
        observation(run_name="b", date="2026-08-11", depth="null"),
    )
    repo.commit("docs(odd): reports")
    proc = run(repo, "--depth", "full")
    assert [l[0] for l in lines(proc)] == [
        "2026-08-11-1000-b.md",
        "2026-08-10-1000-a.md",
    ]
    assert proc.stderr == ""


def test_flags_of_the_other_kind_are_refused(repo):
    store(repo)
    for args in (("--kind", "instrumentation", "--service", "x"), ("--project", "x")):
        proc = run(repo, *args)
        assert proc.returncode == 2 and proc.stdout == "", args
        assert len(proc.stderr.strip().splitlines()) == 1


def test_an_unreadable_report_is_reported_and_the_rest_listed(repo):
    store(repo)
    (repo.root / OBS / "2026-08-14-1000-bad.md").write_bytes(b"---\n\xff\xfe\n---\n")
    proc = run(repo)
    assert proc.returncode == 0
    assert "2026-08-14-1000-bad.md: unreadable" in proc.stderr
    assert len(lines(proc)) == 4


# --- one check, two callers: the recall agrees with the memory invariant -------------


VARIANTS = {
    "well-formed": observation(),
    "no depth (legacy, not a violation)": observation(depth=""),
    "bad mode": observation(mode="drove"),
    "no window": observation().replace("window: ", "when: "),
    "bad window": observation().replace("T10:05:00Z", "T09:00:00Z"),
    "date differs from filename": observation(date="2026-08-11").replace(
        "window: 2026-08-11", "window: 2026-08-10"
    ),
    "verify without verifies": observation(mode="verify"),
    "verifies names nothing": observation(mode="verify", extra="verifies: nope.md"),
    "block-style services": observation().replace(
        "services: [checkout]", "services:\n  - checkout"
    ),
    "empty services": observation(services="[]"),
    "no frontmatter": "## 1. Mission\n",
    "bad depth": observation(depth="deep"),
    "empty depth value": observation(depth="").replace(
        "mode: drive", "mode: drive\ndepth:"
    ),
    "null depth": observation(depth="null"),
    "null verifies on a drive report": observation(extra="verifies: null"),
    "scalar services": observation(services="checkout"),
    "quoted services with a comma": observation(services='["a, b", checkout]'),
    "no stack": observation().replace("stack: local\n", ""),
    "no environment": observation().replace("environment: local\n", ""),
    "bad date": observation(date="10/08/2026").replace(
        "window: 10/08/2026", "window: 2026-08-10"
    ),
}


@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_the_recall_check_agrees_with_get_status_invariant(
    repo, recall, odd_status, variant
):
    rel = f"{OBS}/2026-08-10-1000-a.md"
    repo.write(rel, VARIANTS[variant])
    repo.commit("docs(odd): report")
    parsed = odd_status.parse_report(repo.root, rel, "observation")
    expected = [
        p
        for p in odd_status.check_report(parsed, {"2026-08-10-1000-a.md"}, repo.root)
        if not p.startswith(odd_status.LEGACY_PREFIX)
    ]
    report = recall.read_report(repo.root / rel, "observation")
    problems = recall.check(report, {"2026-08-10-1000-a.md"}, repo.root)
    assert sorted(problems) == sorted(expected), variant
    # the values read agree too, so a match is a match for both readers
    assert report["frontmatter"] == parsed["frontmatter"], variant


@pytest.mark.parametrize(
    "name",
    [
        "2026-08-10-1000-a.md",
        "2026-08-10-1000-verify-a.md",
        "2026-08-10-a.md",
        "notes.md",
    ],
)
def test_the_filename_check_agrees_with_get_status(repo, recall, odd_status, name):
    mode = "verify" if "verify-" in name else "drive"
    extra = "verifies: 2026-08-10-1000-a.md" if mode == "verify" else ""
    rel = f"{OBS}/{name}"
    repo.write(rel, observation(mode=mode, extra=extra))
    repo.commit("docs(odd): report")
    parsed = odd_status.parse_report(repo.root, rel, "observation")
    stored = {name, "2026-08-10-1000-a.md"}
    expected = [
        p
        for p in odd_status.check_report(parsed, stored, repo.root)
        if not p.startswith(odd_status.LEGACY_PREFIX)
    ]
    problems = recall.check(
        recall.read_report(repo.root / rel, "observation"), stored, repo.root
    )
    assert sorted(problems) == sorted(expected), name


# --- cli ---------------------------------------------------------------------------


def test_usage_errors_and_a_missing_repository_are_one_stderr_line(repo, tmp_path):
    for args in (("--depth", "deep"), ("--kind", "plan")):
        proc = run(repo, *args)
        assert proc.returncode == 2 and proc.stdout == ""
        assert len(proc.stderr.strip().splitlines()) == 1, args
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(tmp_path / "nowhere")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2 and "not a git repository" in proc.stderr
    assert not (SCRIPT.parent / "__pycache__").exists()
