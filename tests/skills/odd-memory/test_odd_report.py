"""Tests for the odd-memory skill's report script.

``odd_report.py`` owns the observation report's file format: it names
the file, fills the frontmatter from the repository, writes the section
skeleton, checks a written report against the memory contract, persists
it on the work branch in a lone commit, and extracts the synthesis a
mission closes with. The script is loaded from its packaged location so
the tests exercise the very file the skill ships; every test that
touches git builds a throwaway repository.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SKILLS = ROOT / ".apm" / "skills"
SCRIPT = SKILLS / "odd-memory" / "scripts" / "odd_report.py"
HOOK = ROOT / ".apm" / "hooks" / "scripts" / "check_report_frontmatter.py"
STORED = ROOT / ".odd" / "observe-run-reports"
OBS = ".odd/observe-run-reports"
INS = ".odd/otel-instrumentation-reports"
WINDOW = "2026-08-10T10:04:12Z/2026-08-10T10:05:03Z"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "example-user",
    "GIT_AUTHOR_EMAIL": "example-user@example.com",
    "GIT_COMMITTER_NAME": "example-user",
    "GIT_COMMITTER_EMAIL": "example-user@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _load(name: str, path: Path):
    sys.dont_write_bytecode = True  # never leave a __pycache__ in the package
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def report():
    return _load("odd_report", SCRIPT)


@pytest.fixture(scope="module")
def hook():
    return _load("check_report_frontmatter", HOOK)


class Repo:
    def __init__(
        self, root: Path, remote: str | None = "git@github.com:example-org/checkout.git"
    ):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        if remote:
            self.git("remote", "add", "origin", remote)

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


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path / "repo")
    r.write("src/app.py", "print('v1')\n")
    r.write("README.md", "# checkout\n")
    r.commit("feat: initial")
    return r


def run(repo: Repo | Path, *args: str) -> subprocess.CompletedProcess:
    root = repo.root if isinstance(repo, Repo) else repo
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=root,
        env={**os.environ, **GIT_ENV},
        check=False,
    )


NEW = (
    "new",
    "--service",
    "checkout",
    "--stack",
    "local",
    "--env",
    "local",
    "--mode",
    "drive",
    "--depth",
    "full",
    "--window",
    WINDOW,
)


def new(repo: Repo, *extra: str, run_name: str | None = "checkout-sweep") -> Path:
    args = [*NEW, "--repo", str(repo.root), *extra]
    if run_name:
        args += ["--run-name", run_name]
    proc = run(repo, *args)
    assert proc.returncode == 0, proc.stderr
    path = Path(proc.stdout.splitlines()[0])
    assert path.is_file(), proc.stdout
    return path


def frontmatter(report, path: Path) -> dict:
    fm, _, errors = report.split_frontmatter(path.read_text(encoding="utf-8"))
    assert errors == []
    return fm


def fill(path: Path, text: str = "filled") -> None:
    """Replace every placeholder the skeleton left, so the check passes."""
    content = path.read_text(encoding="utf-8")
    import re

    content = re.sub(r"<fill[^>]*>", text, content)
    path.write_text(content, encoding="utf-8")


# --- naming -------------------------------------------------------------------


def test_new_names_the_file_from_the_window_start_and_the_slug(repo, report):
    path = new(repo)
    assert path == repo.root / OBS / "2026-08-10-1004-checkout-sweep.md"
    fm = frontmatter(report, path)
    assert fm["run_name"] == "checkout-sweep"
    assert fm["date"] == "2026-08-10"
    assert fm["window"] == WINDOW


def test_new_prints_the_skeleton_after_the_path(repo):
    proc = run(repo, *NEW, "--repo", str(repo.root), "--run-name", "a")
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0].endswith("2026-08-10-1004-a.md")
    assert lines[1].startswith("--- the file below its frontmatter")
    assert "persist --body" in lines[1]
    body = "\n".join(lines[2:])
    written = Path(lines[0]).read_text(encoding="utf-8")
    assert body == written.split("---\n\n", 1)[1].rstrip()
    assert body.count("<fill>") == 8


def test_new_takes_the_window_as_a_query_script_printed_it(repo, report):
    proc = run(
        repo,
        "new",
        "--repo",
        str(repo.root),
        "--service",
        "checkout",
        "--stack",
        "local",
        "--env",
        "local",
        "--mode",
        "post-hoc",
        "--depth",
        "full",
        "--run-name",
        "a",
        "--from",
        "2026-08-10T10:04:12Z",
        "--to",
        "2026-08-10T10:05:03Z",
    )
    assert proc.returncode == 0, proc.stderr
    assert frontmatter(report, Path(proc.stdout.splitlines()[0]))["window"] == WINDOW


def test_the_printed_frontmatter_elides_the_anchor_the_file_keeps(repo, report):
    path = new(repo)
    fill(path)
    proc = run(repo, "synthesis", str(path))
    assert proc.returncode == 0, proc.stderr
    assert "tree_anchor: <2 entries, in the file>" in proc.stdout
    assert len(frontmatter(report, path)["tree_anchor"]) == 2


def test_new_at_overrides_the_stamp(repo, report):
    path = new(repo, "--at", "2026-08-11T09:30:00Z")
    assert path.name == "2026-08-11-0930-checkout-sweep.md"
    assert frontmatter(report, path)["date"] == "2026-08-11"


def test_observe_mode_suffixes_the_observer_and_reduces_a_custom_stack_name(
    repo, report
):
    path = new(
        repo,
        "--mode",
        "observe",
        "--stack",
        "My.Stack Name",
        run_name="llmbench-store-load",
    )
    assert path.name == "2026-08-10-1004-llmbench-store-load-observe-my-stack-name.md"
    fm = frontmatter(report, path)
    assert fm["run_name"] == "llmbench-store-load-observe-my-stack-name"
    assert fm["stack"] == "My.Stack Name"


def test_observe_mode_keeps_a_suffix_the_caller_already_wrote(repo, report):
    path = new(repo, "--mode", "observe", run_name="load-observe-local")
    assert path.name == "2026-08-10-1004-load-observe-local.md"


def test_a_taken_path_gets_the_next_free_ordinal(repo, report):
    first = new(repo, "--mode", "observe", run_name="load")
    second = new(repo, "--mode", "observe", run_name="load")
    third = new(repo, "--mode", "observe", run_name="load")
    assert first.name == "2026-08-10-1004-load-observe-local.md"
    assert second.name == "2026-08-10-1004-load-observe-local-2.md"
    assert third.name == "2026-08-10-1004-load-observe-local-3.md"
    assert frontmatter(report, second)["run_name"] == "load-observe-local-2"


def test_a_slug_the_filename_rule_refuses_is_a_usage_error(repo):
    proc = run(repo, *NEW, "--repo", str(repo.root), "--run-name", "Checkout Sweep")
    assert proc.returncode == 2
    assert "run name" in proc.stderr.lower()
    assert not (repo.root / OBS).exists()


@pytest.mark.parametrize(
    "args, message",
    [
        (("--mode", "sideways"), "mode"),
        (("--depth", "deep"), "depth"),
        (("--window", "2026-08-10T10:00:00Z"), "window"),
        (("--window", "2026-08-10T10:05:00Z/2026-08-10T10:00:00Z"), "window"),
        (("--verifies", "x.md"), "verifies"),
    ],
)
def test_a_value_outside_the_contract_is_refused_before_anything_is_written(
    repo, args, message
):
    proc = run(repo, *NEW, "--repo", str(repo.root), "--run-name", "a", *args)
    assert proc.returncode == 2
    assert message in proc.stderr.lower()
    assert not (repo.root / OBS).exists()


# --- the frontmatter --------------------------------------------------------------


def test_the_frontmatter_records_the_repository_facts(repo, report):
    path = new(
        repo, "--workload", "repo-under-analysis", "--instance", "checkout=af6070c1"
    )
    fm = frontmatter(report, path)
    assert fm["services"] == ["checkout"]
    assert fm["stack"] == "local"
    assert fm["environment"] == "local"
    assert fm["mode"] == "drive"
    assert fm["depth"] == "full"
    assert fm["revision"] == repo.git("rev-parse", "--short", "HEAD")
    assert fm["repository"] == "github.com/example-org/checkout"
    assert fm["workload"] == "repo-under-analysis"
    assert fm["instance"] == {"checkout": "af6070c1"}
    assert "process_restarted" not in fm
    anchor = fm["tree_anchor"]
    expected = {}
    for line in repo.git("ls-tree", "HEAD").splitlines():
        meta, name = line.split("\t", 1)
        expected[name] = meta.split()[2]
    assert anchor == expected
    assert set(anchor) == {"src", "README.md"}


@pytest.mark.parametrize(
    "remote, expected",
    [
        (
            "https://github.com/Example-Org/checkout.git",
            "github.com/Example-Org/checkout",
        ),
        ("git@GitLab.com:group/sub/checkout.git", "gitlab.com/group/sub/checkout"),
        (
            "ssh://git@host.example.com:2222/srv/checkout/",
            "host.example.com/srv/checkout",
        ),
    ],
)
def test_the_repository_is_the_origin_remote_normalized(
    tmp_path, report, remote, expected
):
    r = Repo(tmp_path / "r", remote=remote)
    r.write("a.txt", "a\n")
    r.commit("init")
    assert frontmatter(report, new(r))["repository"] == expected


def test_no_remote_means_no_repository_never_a_local_path(tmp_path, report):
    r = Repo(tmp_path / "r", remote=None)
    r.write("a.txt", "a\n")
    r.commit("init")
    fm = frontmatter(report, new(r))
    assert "repository" not in fm
    assert "revision" in fm and "tree_anchor" in fm
    assert (
        str(r.root)
        not in (r.root / OBS / "2026-08-10-1004-checkout-sweep.md").read_text()
    )


def test_a_token_in_the_remote_never_reaches_the_report(tmp_path, report):
    r = Repo(
        tmp_path / "r",
        remote="https://oauth2:secret-token-value@github.com/example-org/checkout.git",
    )
    r.write("a.txt", "a\n")
    r.commit("init")
    path = new(r)
    assert frontmatter(report, path)["repository"] == "github.com/example-org/checkout"
    assert "secret-token-value" not in path.read_text()


def test_code_in_no_repository_omits_the_three_fields(tmp_path, report):
    store = tmp_path / "plain"
    store.mkdir()
    proc = run(store, *NEW, "--repo", str(store), "--run-name", "a", "--no-revision")
    assert proc.returncode == 0, proc.stderr
    fm = frontmatter(report, Path(proc.stdout.splitlines()[0]))
    assert not {"revision", "tree_anchor", "repository"} & set(fm)


def test_a_repository_override_stands_in_for_the_origin(repo, report):
    path = new(
        repo,
        "--repository",
        "{checkout: github.com/example-org/checkout, payment: github.com/example-org/payment}",
    )
    assert frontmatter(report, path)["repository"] == {
        "checkout": "github.com/example-org/checkout",
        "payment": "github.com/example-org/payment",
    }


def test_process_restarted_takes_a_boolean_or_a_per_service_map(repo, report):
    assert (
        frontmatter(report, new(repo, "--process-restarted", "true"))[
            "process_restarted"
        ]
        is True
    )
    path = new(
        repo,
        "--process-restarted",
        "checkout=true",
        "--process-restarted",
        "payment=false",
        run_name="two",
    )
    assert frontmatter(report, path)["process_restarted"] == {
        "checkout": True,
        "payment": False,
    }


def test_the_frontmatter_passes_the_hook_checker(repo, report, hook):
    path = new(repo)
    assert hook.check_file(path) == []
    assert report.check_file(path, written_now=True) == []


def test_environment_may_be_unknown_but_never_absent(repo, report):
    fm = frontmatter(report, new(repo, "--env", "unknown"))
    assert fm["environment"] == "unknown"
    proc = run(
        repo,
        "new",
        "--service",
        "a",
        "--stack",
        "local",
        "--mode",
        "drive",
        "--depth",
        "full",
        "--window",
        WINDOW,
        "--run-name",
        "a",
        "--repo",
        str(repo.root),
    )
    assert proc.returncode == 2
    assert "env" in proc.stderr.lower()


# --- the skeleton ----------------------------------------------------------------


def test_the_skeleton_carries_the_seven_sections_in_order_and_a_placeholder_each(
    repo, report
):
    path = new(repo)
    text = path.read_text(encoding="utf-8")
    _, body, _ = report.split_frontmatter(text)
    sections = report.raw_sections(body)
    assert [s["number"] for s in sections] == [1, 2, 3, 4, 5, 6, 7]
    assert [s["title"] for s in sections] == list(report.SECTION_TITLES)
    assert body.lstrip().startswith("# Observation report")
    assert text.count("<fill") == 8  # the headline and one per section


def test_check_refuses_a_placeholder_left_and_passes_once_filled(repo):
    path = new(repo)
    proc = run(repo, "check", str(path))
    assert proc.returncode == 2
    assert "placeholder" in proc.stderr
    fill(path)
    proc = run(repo, "check", str(path))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("ok")


def test_check_names_a_missing_section_and_a_frontmatter_problem(repo):
    path = new(repo)
    fill(path)
    text = path.read_text(encoding="utf-8")
    text = text.replace("## 5. Telemetry gaps\n", "").replace("depth: full\n", "")
    path.write_text(text, encoding="utf-8")
    proc = run(repo, "check", str(path))
    assert proc.returncode == 2
    assert "section 5" in proc.stderr
    assert "depth absent" in proc.stderr


def test_check_reads_an_instrumentation_report_by_the_hook_rules_and_its_body(repo):
    path = repo.write(
        f"{INS}/2026-08-09-1000-app-python.md",
        "---\nproject: myrepo/src\nstack: local\nrun_name: app-python\ndate: 2026-08-09\n---\n\n## 1. Stack inventory\n",
    )
    proc = run(repo, "check", str(path))
    assert proc.returncode == 2
    assert "section 2 absent" in proc.stderr and "section 5 absent" in proc.stderr
    assert "title absent" in proc.stderr
    path.write_text(path.read_text().replace("date: 2026-08-09", "date: 2026-08-10"))
    proc = run(repo, "check", str(path))
    assert proc.returncode == 2 and "date" in proc.stderr


# --- the instrumentation kind ---------------------------------------------------------


INSTRUMENTATION_NEW = (
    "new",
    "--kind",
    "instrumentation",
    "--project",
    "checkout/src",
    "--stack",
    "local",
    "--run-name",
    "checkout-python",
    "--at",
    "2026-08-09T10:00:00Z",
)


def new_instrumentation(repo: Repo, *extra: str) -> tuple[Path, str]:
    proc = run(repo, *INSTRUMENTATION_NEW, "--repo", str(repo.root), *extra)
    assert proc.returncode == 0, proc.stderr
    path = Path(proc.stdout.splitlines()[0])
    assert path.is_file(), proc.stdout
    return path, proc.stdout


INSTRUMENTATION_BODY = """\
# Instrumentation report — checkout-python

**One service, zero-code approach.**

## 1. Stack inventory

- **Recalled baseline:** no previous report.
- checkout — Python 3.12, FastAPI; entry `src/app.py`; container; no telemetry.

## 2. Summary table

| Service | Language + version | Runtime shape | Approach | Signals (maturity) | Key packages (pinned) | OTLP endpoint | Effort (S/M/L) | Risk flags |
|---|---|---|---|---|---|---|---|---|
| checkout | Python 3.12 | container | zero-code | traces (stable), metrics (stable) | opentelemetry-distro 0.60b0, opentelemetry-exporter-otlp 1.39.0 | http://host.docker.internal:4318 | S | none |
| worker | Python 3.12 | host process | libraries | traces (stable) | opentelemetry-sdk 1.39.0 | http://localhost:4318 | M | batch consumer: span links |

Implementation order: checkout first (the edge), then worker.

## 3. Decisions made, with rationale

- checkout — zero-code via `opentelemetry-instrument` ([docs](https://opentelemetry.io/docs/zero-code/python/)); `OTEL_SERVICE_NAME=checkout`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4318`.

### GenAI approach — worker

The plan adopts `opentelemetry-instrumentation-openai` 0.60b0 ([registry](https://opentelemetry.io/ecosystem/registry/)); it emits the `gen_ai.*` spans; cost stays hand-coded; `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` stays off.

## 4. Decisions the spec must settle

1. Sampling strategy — head sampling at 100 % on the local stack.
2. Content capture — whether `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` is turned on.
3. Cost attribution — who owns the price table.

## 5. Verification protocol

Start the stack with `odd_stack_up`, run each service with its `OTEL_*` block, then:

| Check | Query | Expected outcome | Attribution evidence |
|---|---|---|---|
| spans of checkout searchable | `grafana-traces.py operations checkout --since 10m` | one row per operation | `service.instance.id` = the run's value |
| gen_ai spans of worker | `grafana-traces.py operations worker --since 10m` | `gen_ai.*` operations | the same instance id |
"""


def test_new_instrumentation_names_the_file_and_writes_the_five_section_skeleton(
    repo, report
):
    path, out = new_instrumentation(repo, "--genai", "worker")
    assert path.name == "2026-08-09-1000-checkout-python.md"
    assert path.parent == repo.root / INS
    fm = frontmatter(report, path)
    assert fm["project"] == "checkout/src" and fm["stack"] == "local"
    assert fm["run_name"] == "checkout-python" and fm["date"] == "2026-08-09"
    assert fm["revision"] and isinstance(fm["tree_anchor"], dict)
    assert fm["repository"] == "github.com/example-org/checkout"
    assert "mode" not in fm and "services" not in fm
    assert list(fm)[:2] == ["project", "stack"]
    _, body, _ = report.split_frontmatter(path.read_text(encoding="utf-8"))
    sections = report.raw_sections(body)
    assert [s["title"] for s in sections] == list(report.INSTRUMENTATION_TITLES)
    assert body.lstrip().startswith("# Instrumentation report — checkout-python")
    assert "| " + " | ".join(report.SUMMARY_HEADER) + " |" in body
    assert "Implementation order: <fill>" in body
    assert "### GenAI approach — worker" in body
    assert "| " + " | ".join(report.CHECK_HEADER) + " |" in body
    assert "--- the file below its frontmatter" in out


def test_new_instrumentation_refuses_an_observation_flag_and_needs_its_own(repo):
    proc = run(repo, *INSTRUMENTATION_NEW, "--repo", str(repo.root), "--mode", "drive")
    assert proc.returncode == 2 and "observation report's flag" in proc.stderr
    proc = run(
        repo,
        "new",
        "--kind",
        "instrumentation",
        "--stack",
        "local",
        "--repo",
        str(repo.root),
    )
    assert proc.returncode == 2 and "--project is required" in proc.stderr
    proc = run(
        repo, *NEW, "--repo", str(repo.root), "--run-name", "x", "--project", "y"
    )
    assert proc.returncode == 2 and "belong to --kind instrumentation" in proc.stderr


def test_check_refuses_an_instrumentation_skeleton_and_passes_a_conformant_body(repo):
    path, _ = new_instrumentation(repo, "--genai", "worker")
    proc = run(repo, "check", str(path))
    assert proc.returncode == 2 and "placeholder" in proc.stderr
    path.write_text(
        path.read_text(encoding="utf-8").split("\n\n", 1)[0]
        + "\n\n"
        + INSTRUMENTATION_BODY,
        encoding="utf-8",
    )
    proc = run(repo, "check", str(path))
    assert proc.returncode == 0, proc.stderr


def test_persist_instrumentation_takes_the_kinds_branch_and_subject_and_shows(
    repo, report
):
    path, _ = new_instrumentation(repo, "--genai", "worker")
    draft = repo.write("scratch/draft.md", INSTRUMENTATION_BODY)
    proc = run(repo, "persist", str(path), "--body", str(draft))
    assert proc.returncode == 0, proc.stderr
    assert "branch: docs/odd-instrumentation-report-checkout-python" in proc.stdout
    assert (
        "subject: docs(odd): instrumentation investigation checkout-python"
        in proc.stdout
    )
    assert (
        "headline: **2 services, mixed approach, 3 pinned packages, 3 decisions open, "
        "GenAI approach for 1 service, no previous report**" in proc.stdout
    )
    assert (
        repo.git("branch", "--show-current")
        == "docs/odd-instrumentation-report-checkout-python"
    )
    assert repo.git("show", "--name-only", "--format=", "HEAD").splitlines() == [
        f"{INS}/2026-08-09-1000-checkout-python.md"
    ]
    shown = run(repo, "show", str(path))
    assert shown.returncode == 0, shown.stderr
    assert shown.stdout.startswith("**2 services, mixed approach, 3 pinned packages")
    assert (
        "| Service | Approach | Key packages (pinned) | Effort | Risk flags |"
        in shown.stdout
    )
    assert "Language + version" not in shown.stdout, "the widest columns are dropped"
    assert (
        "Implementation order: checkout first (the edge), then worker." in shown.stdout
    )
    assert "GenAI approach (section 3, prose): worker" in shown.stdout
    assert "Decisions the spec must settle: 3" in shown.stdout
    assert "Verification protocol: 2 replayable checks in section 5" in shown.stdout
    assert shown.stdout.rstrip().endswith(
        "then build the spec-driven instrumentation plan from the report."
    )
    synthesis = run(repo, "synthesis", str(path)).stdout
    assert (
        "--- section 5: replayable checks" in synthesis
        and "spans of checkout searchable" in synthesis
    )
    read = run(repo, "read", str(path)).stdout
    assert (
        "## 1. Stack inventory" in read
        and "## 4. Decisions" in read
        and "## 3." not in read
    )


def test_check_refuses_a_credential_projected_in_a_check(repo):
    path, _ = new_instrumentation(repo)
    leaking = INSTRUMENTATION_BODY.replace(
        "| `service.instance.id` = the run's value |",
        "| InstrumentationKey=0a1b2c3d-0000-4000-8000-000000000001 on the resource |",
    )
    path.write_text(
        path.read_text(encoding="utf-8").split("\n\n", 1)[0] + "\n\n" + leaking,
        encoding="utf-8",
    )
    proc = run(repo, "check", str(path))
    assert proc.returncode == 2 and "section 5 projects a credential" in proc.stderr
    projecting = INSTRUMENTATION_BODY.replace(
        "`grafana-traces.py operations worker --since 10m`",
        "`az monitor app-insights component show --app x -g y --query instrumentationKey`",
    )
    path.write_text(
        path.read_text(encoding="utf-8").split("\n\n", 1)[0] + "\n\n" + projecting,
        encoding="utf-8",
    )
    proc = run(repo, "check", str(path))
    assert proc.returncode == 2 and "section 5 projects a credential" in proc.stderr
    wired = INSTRUMENTATION_BODY.replace(
        "| `service.instance.id` = the run's value |",
        "| the header `Authorization: Bearer $OTEL_TOKEN` sourced from the env var by name |",
    )
    path.write_text(
        path.read_text(encoding="utf-8").split("\n\n", 1)[0] + "\n\n" + wired,
        encoding="utf-8",
    )
    assert run(repo, "check", str(path)).returncode == 0, (
        "wiring by name is not a value"
    )


def test_check_refuses_a_genai_table_row_and_a_summary_table_missing_a_column(repo):
    path, _ = new_instrumentation(repo)
    as_row = INSTRUMENTATION_BODY.replace(
        "### GenAI approach — worker\n",
        "| Item | Choice |\n|---|---|\n| GenAI approach | opentelemetry-instrumentation-openai |\n\n### GenAI approach — worker\n",
    )
    path.write_text(
        path.read_text(encoding="utf-8").split("\n\n", 1)[0] + "\n\n" + as_row,
        encoding="utf-8",
    )
    proc = run(repo, "check", str(path))
    assert (
        proc.returncode == 2
        and "renders the GenAI approach as a table row" in proc.stderr
    )
    narrow = (
        INSTRUMENTATION_BODY.replace(" | OTLP endpoint | ", " | ")
        .replace(" | http://host.docker.internal:4318 | ", " | ")
        .replace(" | http://localhost:4318 | ", " | ")
        .replace(
            "|---|---|---|---|---|---|---|---|---|", "|---|---|---|---|---|---|---|---|"
        )
    )
    path.write_text(
        path.read_text(encoding="utf-8").split("\n\n", 1)[0] + "\n\n" + narrow,
        encoding="utf-8",
    )
    proc = run(repo, "check", str(path))
    assert (
        proc.returncode == 2
        and "section 2 carries no summary table with the columns" in proc.stderr
    )
    assert "missing: endpoint" in proc.stderr
    no_checks = INSTRUMENTATION_BODY.split("| Check |")[0] + "The checks come later.\n"
    path.write_text(
        path.read_text(encoding="utf-8").split("\n\n", 1)[0] + "\n\n" + no_checks,
        encoding="utf-8",
    )
    proc = run(repo, "check", str(path))
    assert (
        proc.returncode == 2 and "section 5 carries no replayable check" in proc.stderr
    )


def test_instrumentation_checks_may_be_bullets_with_four_parts(repo):
    path, _ = new_instrumentation(repo)
    bullets = INSTRUMENTATION_BODY.split("| Check |")[0] + (
        "- spans of checkout searchable — `grafana-traces.py operations checkout --since 10m` — one row per operation — `service.instance.id` = the run's value\n"
    )
    path.write_text(
        path.read_text(encoding="utf-8").split("\n\n", 1)[0] + "\n\n" + bullets,
        encoding="utf-8",
    )
    assert run(repo, "check", str(path)).returncode == 0
    shown = run(repo, "show", str(path)).stdout
    assert "Verification protocol: 1 replayable check in section 5" in shown


# --- a replay: verify and re-measure ------------------------------------------------


BASELINE = """\
---
services: [checkout]
stack: local
environment: local
mode: drive
depth: full
window: 2026-08-08T10:00:00Z/2026-08-08T10:05:00Z
run_name: checkout-sweep
date: 2026-08-08
---

# Observation report — checkout-sweep

**2 anomalies.**

## 1. Mission and run record

- **Recalled baseline:** no previous report.

### Scenario record (verbatim)

Scenario: 30 GET /products.
Not reproducible: nothing.

## 2. Observed behavior

| Operation | Requests | p50 | p95 |
|---|---|---|---|
| GET /products | 30 | 4 ms | 9 ms |

## 3. Anomalies and probable causes

| # | Finding | Severity | Confidence | Evidence | Expected gain |
|---|---|---|---|---|---|
| F1 | N+1 query on GET /products | high | confirmed | trace abc | -40 ms |
| F2 | Missing db spans | low | suspected | none | none |

## 4. Improvement opportunities

## 5. Telemetry gaps

- **Logs carry no trace id** — new — `{service_name="checkout"} |= "trace_id"` → 0 lines
- **No profiles** — new — `profiles labels -l service_name` → []

## 6. Decisions the spec must settle

1. Whether the N+1 is intended.

## 7. Measurement protocol for the fix

| Check | Query | Before-value | Pass criterion | Validated |
|---|---|---|---|---|
| 1. p95 of GET /products | histogram_quantile(...) | 9 ms | < 5 ms | validated: before-shape |
"""


def baseline(repo: Repo, name: str = "2026-08-08-1000-checkout-sweep.md") -> str:
    repo.write(f"{OBS}/{name}", BASELINE)
    repo.commit("docs(odd): observation report checkout-sweep")
    return name


def test_a_verification_inherits_the_run_name_and_prefixes_the_filename(repo, report):
    name = baseline(repo)
    path = new(repo, "--mode", "verify", "--verifies", name, run_name=None)
    assert path.name == "2026-08-10-1004-verify-checkout-sweep.md"
    fm = frontmatter(report, path)
    assert fm["mode"] == "verify"
    assert fm["run_name"] == "checkout-sweep"
    assert fm["verifies"] == name


def test_a_re_measure_uses_its_own_prefix(repo, report):
    name = baseline(repo)
    path = new(repo, "--mode", "re-measure", "--verifies", name, run_name=None)
    assert path.name == "2026-08-10-1004-remeasure-checkout-sweep.md"
    assert frontmatter(report, path)["mode"] == "re-measure"


def test_a_replay_inherits_the_baseline_depth_and_quick_when_it_has_none(repo, report):
    name = baseline(repo)
    proc = run(
        repo,
        "new",
        "--repo",
        str(repo.root),
        "--service",
        "checkout",
        "--stack",
        "local",
        "--env",
        "local",
        "--mode",
        "verify",
        "--window",
        WINDOW,
        "--verifies",
        name,
    )
    assert proc.returncode == 0, proc.stderr
    assert frontmatter(report, Path(proc.stdout.splitlines()[0]))["depth"] == "full"
    repo.write(f"{OBS}/{name}", BASELINE.replace("depth: full\n", ""))
    proc = run(
        repo,
        "new",
        "--repo",
        str(repo.root),
        "--service",
        "checkout",
        "--stack",
        "local",
        "--env",
        "local",
        "--mode",
        "verify",
        "--window",
        WINDOW,
        "--verifies",
        name,
        "--at",
        "2026-08-11T10:00:00Z",
    )
    assert proc.returncode == 0, proc.stderr
    assert frontmatter(report, Path(proc.stdout.splitlines()[0]))["depth"] == "quick"
    assert "quick" in proc.stderr


def test_a_replay_pre_fills_the_ruling_table_from_the_baseline_findings(repo, report):
    name = baseline(repo)
    path = new(repo, "--mode", "verify", "--verifies", name, run_name=None)
    _, body, _ = report.split_frontmatter(path.read_text(encoding="utf-8"))
    section = next(s for s in report.raw_sections(body) if s["number"] == 3)
    table = section["tables"][0]
    assert table["header"] == ["#", "Baseline finding", "Verdict", "Evidence"]
    assert [row[0] for row in table["rows"]] == ["F1", "F2"]
    assert table["rows"][0][1] == "N+1 query on GET /products"
    assert table["rows"][0][2].startswith("<fill")
    # the baseline's gaps travel too, their fate left to the run
    gaps = next(s for s in report.raw_sections(body) if s["number"] == 5)
    text = "\n".join(gaps["lines"])
    assert "Logs carry no trace id" in text and "No profiles" in text
    assert text.count("<fill") == 2


def test_check_refuses_a_replay_whose_ruling_table_misses_a_baseline_finding(
    repo, report
):
    name = baseline(repo)
    path = new(repo, "--mode", "verify", "--verifies", name, run_name=None)
    fill(path, "fixed")
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("| F2 |", "| G2 |"), encoding="utf-8")
    proc = run(repo, "check", str(path))
    assert proc.returncode == 2
    assert "F2" in proc.stderr and "ruling" in proc.stderr


def test_a_replay_of_an_instrumentation_report_names_it_by_path(repo, report):
    rel = f"{INS}/2026-08-09-1000-app-python.md"
    repo.write(
        rel,
        "---\nproject: myrepo/src\nstack: local\nrun_name: app-python\ndate: 2026-08-09\n---\n\n## 2. Summary table\n",
    )
    repo.commit("docs(odd): instrumentation investigation app-python")
    proc = run(
        repo,
        "new",
        "--repo",
        str(repo.root),
        "--service",
        "checkout",
        "--stack",
        "local",
        "--env",
        "local",
        "--mode",
        "verify",
        "--window",
        WINDOW,
        "--verifies",
        rel,
    )
    assert proc.returncode == 0, proc.stderr
    path = Path(proc.stdout.splitlines()[0])
    assert path.name == "2026-08-10-1004-verify-app-python.md"
    fm = frontmatter(report, path)
    assert fm["verifies"] == rel
    assert fm["depth"] == "full"


def test_a_replay_names_a_baseline_that_is_not_stored_and_refuses(repo):
    proc = run(
        repo,
        *NEW,
        "--repo",
        str(repo.root),
        "--mode",
        "verify",
        "--verifies",
        "2026-08-08-1000-nope.md",
    )
    assert proc.returncode == 2
    assert "verifies" in proc.stderr


# --- persist -------------------------------------------------------------------------


def test_persist_leaves_the_default_branch_and_commits_the_report_alone(repo, report):
    repo.git("update-ref", "refs/remotes/origin/main", "HEAD")
    repo.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    path = new(repo)
    fill(path)
    repo.write("src/app.py", "print('dirty')\n")
    proc = run(repo, "persist", str(path))
    assert proc.returncode == 0, proc.stderr
    assert (
        repo.git("branch", "--show-current")
        == "docs/odd-observe-run-report-checkout-sweep"
    )
    assert (
        repo.git("log", "-1", "--format=%s")
        == "docs(odd): observation report checkout-sweep"
    )
    assert repo.git("show", "--stat", "--format=", "HEAD").count("|") == 1
    assert "src/app.py" in repo.git("status", "--porcelain")
    sha = repo.git("rev-parse", "--short", "HEAD")
    assert f"commit: {sha}" in proc.stdout
    assert f"path: {OBS}/2026-08-10-1004-checkout-sweep.md" in proc.stdout
    assert "branch: docs/odd-observe-run-report-checkout-sweep" in proc.stdout


def test_persist_body_splices_a_draft_under_the_frontmatter(repo, report):
    path = new(repo)
    before = frontmatter(report, path)
    draft = repo.root / "draft.md"
    body = "\n\n".join(
        ["# Observation report — checkout-sweep", "**Fine.**"]
        + [f"## {n}. {t}\n\ntext {n}" for n, t in enumerate(report.SECTION_TITLES, 1)]
    )
    draft.write_text("---\nstack: other\n---\n" + body + "\n", encoding="utf-8")
    proc = run(repo, "persist", str(path), "--body", str(draft))
    assert proc.returncode == 0, proc.stderr
    assert "frontmatter block: dropped" in proc.stderr
    assert frontmatter(report, path) == before
    text = path.read_text(encoding="utf-8")
    assert "<fill>" not in text and "text 7" in text and "stack: other" not in text
    assert (
        repo.git("log", "-1", "--format=%s")
        == "docs(odd): observation report checkout-sweep"
    )
    assert "draft.md" in repo.git(
        "status", "--porcelain"
    )  # the draft is never committed


def test_persist_body_refuses_a_broken_draft_and_keeps_what_new_wrote(repo):
    path = new(repo)
    before = path.read_text(encoding="utf-8")
    draft = repo.root / "draft.md"
    draft.write_text(
        "# Observation report\n\n## 1. Mission and run record\n\nonly one\n",
        encoding="utf-8",
    )
    proc = run(repo, "persist", str(path), "--body", str(draft))
    assert proc.returncode == 2
    assert "section 2 absent" in proc.stderr and "draft.md" in proc.stderr
    assert "could not be persisted" in proc.stderr
    assert path.read_text(encoding="utf-8") == before  # the skeleton stays as written
    assert repo.git("log", "-1", "--format=%s") == "feat: initial"


def test_persist_body_keeps_a_replay_ruling_table_when_the_draft_fails(repo, report):
    name = baseline(repo)
    path = new(repo, "--mode", "verify", "--verifies", name, run_name=None)
    draft = repo.root / "draft.md"
    sections = "\n\n".join(
        f"## {n}. {t}\n\nx" for n, t in enumerate(report.SECTION_TITLES, 1)
    )
    draft.write_text("# Observation report\n\n**x**\n\n" + sections, encoding="utf-8")
    proc = run(repo, "persist", str(path), "--body", str(draft))
    assert proc.returncode == 2 and "F1" in proc.stderr
    assert "| F1 |" in path.read_text(encoding="utf-8")


def test_check_requires_a_title_and_a_headline_before_section_1(repo):
    path = new(repo)
    fill(path)
    head, body = path.read_text(encoding="utf-8").split("---\n\n", 1)
    path.write_text(head + "---\n\n## 1." + body.split("## 1.", 1)[1], encoding="utf-8")
    proc = run(repo, "check", str(path))
    assert proc.returncode == 2
    assert "title absent" in proc.stderr and "headline absent" in proc.stderr


def test_a_local_path_is_never_a_repository_value(repo):
    base = (*NEW, "--repo", str(repo.root), "--run-name", "a", "--repository")
    proc = run(repo, *base, "/Users/example-user/code/thing")
    assert proc.returncode == 2 and "local path" in proc.stderr
    proc = run(repo, *base, "{a: github.com/example-org/checkout, b: ../payment}")
    assert proc.returncode == 2 and "local path" in proc.stderr


def test_a_frontmatter_problem_is_the_file_s_never_the_draft_s(repo, report):
    path = new(repo)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            "repository: github.com/example-org/checkout",
            "repository: /Users/someone/x",
        ),
        encoding="utf-8",
    )
    draft = repo.root / "draft.md"
    sections = "\n\n".join(
        f"## {n}. {t}\n\nx" for n, t in enumerate(report.SECTION_TITLES, 1)
    )
    draft.write_text("# Observation report\n\n**x**\n\n" + sections, encoding="utf-8")
    proc = run(repo, "persist", str(path), "--body", str(draft))
    assert proc.returncode == 2
    assert f"{path.name}: repository carries a local path" in proc.stderr
    assert "draft.md: repository" not in proc.stderr


def test_window_and_from_to_together_are_refused(repo):
    proc = run(
        repo,
        *NEW,
        "--repo",
        str(repo.root),
        "--run-name",
        "a",
        "--from",
        "2026-08-10T10:04:12Z",
        "--to",
        "2026-08-10T10:05:03Z",
    )
    assert proc.returncode == 2 and "pass one" in proc.stderr


def test_show_renders_a_re_measure_findings_table(store):
    proc = run(store, "show", f"{OBS}/2026-09-03-1756-remeasure-mcp-read-tools.md")
    assert proc.returncode == 0, proc.stderr
    assert "| Severity | Confidence | Finding |" in proc.stdout
    assert proc.stdout.count("\n| ") >= 4


def test_persist_commits_on_a_work_branch_it_is_already_on(repo):
    repo.git("checkout", "-q", "-b", "feat/anything")
    path = new(repo)
    fill(path)
    proc = run(repo, "persist", str(path))
    assert proc.returncode == 0, proc.stderr
    assert repo.git("branch", "--show-current") == "feat/anything"
    assert "branch: feat/anything" in proc.stdout


def test_persist_subjects_follow_the_mode(repo):
    name = baseline(repo)
    repo.git("checkout", "-q", "-b", "work")
    for mode, subject in (
        ("verify", "verification report"),
        ("re-measure", "re-measure report"),
    ):
        path = new(repo, "--mode", mode, "--verifies", name, run_name=None)
        fill(path, "fixed")
        proc = run(repo, "persist", str(path))
        assert proc.returncode == 0, proc.stderr
        assert (
            repo.git("log", "-1", "--format=%s")
            == f"docs(odd): {subject} checkout-sweep"
        )


def test_persist_refuses_a_report_that_fails_the_check(repo):
    path = new(repo)
    proc = run(repo, "persist", str(path))
    assert proc.returncode == 2
    assert "placeholder" in proc.stderr
    assert repo.git("log", "-1", "--format=%s") == "feat: initial"


def test_persist_with_no_commit_states_it(repo):
    path = new(repo)
    fill(path)
    proc = run(repo, "persist", str(path), "--no-commit")
    assert proc.returncode == 0, proc.stderr
    assert "commit: not committed (the caller said not to)" in proc.stdout
    assert repo.git("log", "-1", "--format=%s") == "feat: initial"


def test_persist_outside_a_repository_states_it(tmp_path):
    store = tmp_path / "plain"
    store.mkdir()
    proc = run(store, *NEW, "--repo", str(store), "--run-name", "a", "--no-revision")
    path = Path(proc.stdout.splitlines()[0])
    fill(path)
    proc = run(store, "persist", str(path))
    assert proc.returncode == 0, proc.stderr
    assert "commit: not committed (not a git repository)" in proc.stdout


def test_persist_prints_the_headline_never_the_synthesis_block(repo):
    path = new(repo)
    fill(path)
    proc = run(repo, "persist", str(path))
    assert proc.returncode == 0, proc.stderr
    assert "headline: **" in proc.stdout
    assert "--- frontmatter" not in proc.stdout  # the caller's show renders, once


# --- read, synthesis and show, on stored reports ---------------------------------------

DRIVE = "2026-09-04-1107-mcp-read-tools.md"
VERIFY = "2026-08-29-1107-verify-stack-config-lifecycle.md"
QUICK = "2026-09-04-1038-status-quick-check.md"


@pytest.fixture
def store(tmp_path: Path) -> Repo:
    """A repository holding three real stored reports: a drive, a verify, a quick."""
    r = Repo(tmp_path / "store")
    (r.root / OBS).mkdir(parents=True)
    for name in (
        DRIVE,
        VERIFY,
        QUICK,
        "2026-08-28-1531-stack-config-lifecycle.md",
        "2026-09-03-1756-remeasure-mcp-read-tools.md",
    ):
        shutil.copy(STORED / name, r.root / OBS / name)
    r.commit("docs(odd): reports")
    return r


def test_read_prints_the_frontmatter_and_the_named_sections_only(store):
    proc = run(store, "read", f"{OBS}/{DRIVE}", "--sections", "2,7")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert out.startswith("---\nservices: [oddyssey-mcp]")
    assert "## 2. Observed behavior" in out
    assert "## 7. Measurement protocol for the fix" in out
    assert "## 3. Anomalies" not in out
    assert "## 4. Improvement" not in out


def test_read_record_reduces_section_1_to_its_scenario_record_and_replay_notes(store):
    proc = run(store, "read", f"{OBS}/{DRIVE}", "--sections", "1", "--record")
    assert proc.returncode == 0, proc.stderr
    assert "### Scenario record (verbatim)" in proc.stdout
    assert "### Replay notes" in proc.stdout
    assert "**Service:**" not in proc.stdout  # the mission restatement stays out


def test_synthesis_of_an_observation_quotes_the_findings_gaps_and_decisions(store):
    proc = run(store, "synthesis", f"{OBS}/{DRIVE}")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert out.startswith(f"path: {OBS}/{DRIVE}\ncommit: ")
    assert "--- frontmatter" in out and "run_name: mcp-read-tools" in out
    assert "--- section 1" in out
    assert "2026-09-03-1756-remeasure-mcp-read-tools.md" in out
    assert "--- section 2" in out and "Deltas against the recalled baseline" in out
    assert "--- section 3" in out
    assert "| F1 |" in out and "| O3 |" in out
    assert "+82.3 → +111.0 ms" not in out  # the evidence column stays in the file
    assert "--- section 5" in out and out.count("\n- ") >= 7
    assert "--- section 6" in out and "Shared-slug cumulative temporality" in out


def test_synthesis_of_a_verification_quotes_the_rulings_and_the_checks(store):
    proc = run(store, "synthesis", f"{OBS}/{VERIFY}")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "| N1 |" in out and "| N2 |" in out and "FIXED" in out
    assert "| 1. Creation persists env |" in out and "**PASS**" in out
    assert "The N2 ruling" not in out  # prose stays in the file


def test_synthesis_of_a_quick_report_carries_its_not_queried_line(store):
    proc = run(store, "synthesis", f"{OBS}/{QUICK}")
    assert proc.returncode == 0, proc.stderr
    assert "not queried (quick): logs, profiles" in proc.stdout
    assert "None this run" in proc.stdout


def test_show_renders_the_observation_synthesis_in_order(store):
    proc = run(store, "show", f"{OBS}/{DRIVE}")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines[0].startswith("**") and "anomalies" in lines[0]
    assert "telemetry gaps" in lines[0]
    assert f"`{OBS}/{DRIVE}`" in out
    assert "services: oddyssey-mcp" in out
    assert "mode: drive" in out
    assert "baseline: 2026-09-03-1756-remeasure-mcp-read-tools.md" in out
    assert "| Severity | Confidence | Finding |" in out
    assert "Decisions the spec must settle: 6" in out
    assert out.rstrip().splitlines()[-1].startswith("Next:")


def test_show_renders_a_verification_verdict_first(store):
    proc = run(store, "show", f"{OBS}/{VERIFY}")
    assert proc.returncode == 0, proc.stderr
    first = next(ln for ln in proc.stdout.splitlines() if ln.strip())
    assert first.startswith("**PASS") and "18/18" in first
    assert "+8 more in the report" in proc.stdout  # 18 checks, 10 shown
    assert "baseline: 2026-08-29-0953-verify-stack-config-lifecycle.md" in proc.stdout


def test_show_renders_a_quick_report_as_quick(store):
    proc = run(store, "show", f"{OBS}/{QUICK}")
    assert proc.returncode == 0, proc.stderr
    first = next(ln for ln in proc.stdout.splitlines() if ln.strip())
    assert first.startswith("**quick")
    assert "not queried" in first


def test_show_of_a_file_never_committed_says_so(repo):
    path = new(repo)
    fill(path)
    proc = run(repo, "show", str(path))
    assert proc.returncode == 0, proc.stderr
    assert "not committed" in proc.stdout


# --- the shared reader ----------------------------------------------------------------


def test_the_status_and_recall_scripts_read_through_this_module(report):
    status = _load(
        "odd_status_shared", SKILLS / "get-status" / "scripts" / "odd_status.py"
    )
    recall = _load(
        "odd_recall_shared", SKILLS / "odd-memory" / "scripts" / "odd_recall.py"
    )
    ledger = _load(
        "odd_ledger_shared", SKILLS / "odd-memory" / "scripts" / "odd_ledger.py"
    )
    assert status.split_frontmatter is report.split_frontmatter
    assert status.raw_sections is report.raw_sections
    assert status.findings_at_a_glance is report.findings_at_a_glance
    assert status.normalize_remote is report.normalize_remote
    assert recall.read_report is report.read_report
    assert recall.check_report is report.check_report
    assert ledger.raw_sections is report.raw_sections


def test_check_report_agrees_with_the_hook_on_the_stored_reports(report, hook):
    for path in sorted(STORED.glob("*.md")):
        assert hook.check_file(path) == report.check_file(path, written_now=True), (
            path.name
        )


# --- a custom stack: section 8, stack friction ----------------------------------


def custom_body(report, friction: list[str] | None) -> str:
    """A filled body with the eighth section: one bullet per friction, or none."""
    sections = [
        f"## {n}. {t}\n\ntext {n}" for n, t in enumerate(report.SECTION_TITLES, 1)
    ]
    bullets = (
        "\n".join(f"- {f}" for f in friction)
        if friction
        else (
            "- none — every backend call of this run went through a shipped "
            "invocation, and each answered as its guide states"
        )
    )
    sections.append(
        f"## {report.FRICTION_NUMBER}. {report.FRICTION_TITLE}\n\n{bullets}"
    )
    return (
        "\n\n".join(["# Observation report — checkout-sweep", "**Fine.**", *sections])
        + "\n"
    )


def test_custom_stack_writes_the_counter_and_an_eighth_section(repo, report):
    path = new(repo, "--custom-stack")
    fm = frontmatter(report, path)
    assert fm["stack_friction"] == "0"
    assert list(fm)[-1] == "stack_friction"  # after the contract's other fields
    _, body, _ = report.split_frontmatter(path.read_text(encoding="utf-8"))
    sections = report.raw_sections(body)
    assert [s["number"] for s in sections] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert sections[-1]["title"] == report.FRICTION_TITLE
    assert path.read_text(encoding="utf-8").count("<fill") == 9


def test_without_the_flag_the_report_carries_neither(repo, report):
    path = new(repo)
    assert "stack_friction" not in frontmatter(report, path)
    assert f"## {report.FRICTION_NUMBER}." not in path.read_text(encoding="utf-8")


def test_persist_recounts_the_friction_from_section_8(repo, report):
    path = new(repo, "--custom-stack")
    draft = repo.root / "draft.md"
    draft.write_text(
        custom_body(
            report,
            [
                (
                    "seq-logs.py --json printed no `Slices` on a group by time — "
                    "`python3 .odd/observability-stacks/seq/scripts/seq-logs.py count`"
                    " — a top-level Rows array — read Rows instead"
                ),
                (
                    "the guide names no flag for a window end — `seq-traces.py ops"
                    " --from` — usage error — composed the seqcli call by hand"
                ),
            ],
        ),
        encoding="utf-8",
    )
    proc = run(repo, "persist", str(path), "--body", str(draft))
    assert proc.returncode == 0, proc.stderr
    assert "stack_friction: 2 (section 8 recounted)" in proc.stderr
    assert frontmatter(report, path)["stack_friction"] == "2"
    shown = run(repo, "show", str(path))
    assert "Stack friction: 2 — /odd-instrument-stack from report" in shown.stdout
    assert "seq-logs.py --json printed" in shown.stdout
    synthesis = run(repo, "synthesis", str(path))
    assert "--- section 8: stack friction" in synthesis.stdout


def test_a_none_bullet_counts_zero_and_shows_it(repo, report):
    path = new(repo, "--custom-stack")
    draft = repo.root / "draft.md"
    draft.write_text(custom_body(report, None), encoding="utf-8")
    proc = run(repo, "persist", str(path), "--body", str(draft))
    assert proc.returncode == 0, proc.stderr
    assert frontmatter(report, path)["stack_friction"] == "0"
    shown = run(repo, "show", str(path))
    assert (
        "Stack friction: 0 — every backend call went through a shipped invocation"
        in shown.stdout
    )


def test_check_refuses_a_custom_report_without_section_8_or_a_bullet(repo, report):
    path = new(repo, "--custom-stack")
    draft = repo.root / "draft.md"
    seven = custom_body(report, None).split(f"## {report.FRICTION_NUMBER}.")[0]
    draft.write_text(seven, encoding="utf-8")
    proc = run(repo, "persist", str(path), "--body", str(draft))
    assert proc.returncode == 2
    assert f"section {report.FRICTION_NUMBER} absent" in proc.stderr
    empty = seven + f"## {report.FRICTION_NUMBER}. {report.FRICTION_TITLE}\n\nprose\n"
    draft.write_text(empty, encoding="utf-8")
    proc = run(repo, "persist", str(path), "--body", str(draft))
    assert proc.returncode == 2
    assert "carries no bullet" in proc.stderr


def test_check_refuses_section_8_on_a_report_that_counts_nothing(repo, report):
    path = new(repo)
    draft = repo.root / "draft.md"
    draft.write_text(custom_body(report, None), encoding="utf-8")
    proc = run(repo, "persist", str(path), "--body", str(draft))
    assert proc.returncode == 2
    assert "carries no stack_friction" in proc.stderr


def test_the_credential_rule_tells_a_value_from_its_wiring(report):
    wiring = (
        "token: OTEL_EXPORTER_TOKEN (the env var name, never the value)",
        "password: POSTGRES_PASSWORD",
        "Secret: kubernetes-secret-reference",
        "Authorization: request-scoped header set from the env",
        "connection string: InstrumentationKey=<instrumentation_key>;IngestionEndpoint=<endpoint>",
        "OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer ${TOKEN}",
        "api key: redacted by the backend's show",
    )
    for text in wiring:
        assert report.credential_in(text) is None, text
    values = (
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdefgh",
        "token: ghp_16C7e42F292c6912E7710c838347Ae178B4a",
        "InstrumentationKey=0a1b2c3d-0000-4000-8000-000000000001",
        "--query instrumentationKey",
        "api_key=sk-abcdefghijklmnopqrstuvwxyz0123",
        "password: hunter2hunter2hunter2",
    )
    for text in values:
        assert report.credential_in(text), text


def test_check_refuses_a_summary_table_whose_first_column_is_not_service(repo):
    path, _ = new_instrumentation(repo)
    renamed = INSTRUMENTATION_BODY.replace(
        "| Service | Language", "| Service name | Language"
    )
    head = path.read_text(encoding="utf-8").split("\n\n", 1)[0]
    path.write_text(head + "\n\n" + renamed, encoding="utf-8")
    proc = run(repo, "check", str(path))
    assert proc.returncode == 2
    assert "opens with a column other than `Service`" in proc.stderr


def test_new_instrumentation_refuses_every_observation_flag(repo):
    for flags in (
        ("--workload", "k6 smoke"),
        ("--instance", "k=v"),
        ("--process-restarted", "true"),
        ("--from", "2026-08-09T10:00:00Z", "--to", "2026-08-09T10:05:00Z"),
    ):
        proc = run(repo, *INSTRUMENTATION_NEW, "--repo", str(repo.root), *flags)
        assert proc.returncode == 2 and "observation report's flag" in proc.stderr, (
            flags
        )
