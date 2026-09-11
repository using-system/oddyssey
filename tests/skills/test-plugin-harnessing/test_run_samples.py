"""The harnessing kit's sample chain: one script that deploys a lab branch
into the fake user scope, clears what the next run must not read, launches
the measurement, runs the analysis, and journals one line per sample - the
loop every study used to rewrite by hand.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".claude" / "skills" / "test-plugin-harnessing" / "scripts"
RUN_SAMPLES = SCRIPTS / "run_samples.py"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "example-user",
    "GIT_AUTHOR_EMAIL": "example-user@example.com",
    "GIT_COMMITTER_NAME": "example-user",
    "GIT_COMMITTER_EMAIL": "example-user@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}

FAKE_MEASURE = """\
#!/usr/bin/env python3
import json, os, sys, time
args = sys.argv[1:]
out = args[args.index("--out") + 1]; tag = args[args.index("--tag") + 1]
open(os.path.join(out, tag + ".record.json"), "w").write(json.dumps({"tag": tag, "cwd": os.getcwd(), "home": os.environ.get("HOME"), "argv": args}))
open(os.path.join(out, tag + ".seen-branch"), "w").write(open(".git/HEAD").read())
if os.environ.get("FAKE_MEASURE_FAIL") == tag:
    print("boom", file=sys.stderr); sys.exit(2)
if os.environ.get("FAKE_MEASURE_LEAVE") == tag:
    # what a real run leaves behind: a report commit on the lab branch, a
    # report branch, an untracked report, a rewritten opencode.json
    import subprocess
    g = lambda *a: subprocess.run(["git", "-c", "commit.gpgsign=false", *a], check=True, capture_output=True)
    open(".odd/observe-run-reports/2026-09-11-1000-x.md", "w").write("report\\n")
    g("add", "-A"); g("commit", "-q", "-m", "docs(odd): observation report x")
    g("branch", "docs/odd-observe-run-report-x")
    open(".odd/observe-run-reports/2026-09-11-1100-y.md", "w").write("untracked\\n")
    open("opencode.json", "w").write('{"rewritten": true}\\n')
print(tag + ": whole 1m00s")
"""

FAKE_ANALYZE = """\
#!/usr/bin/env python3
import sys
print("analysed " + " ".join(sys.argv[1:]))
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        env={**os.environ, **GIT_ENV},
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def lab(tmp_path: Path) -> Path:
    """A lab clone with two deployed branches, the way prepare_branch leaves
    them: the opencode deploy committed, one skill differing per branch."""
    lab = tmp_path / "lab"
    lab.mkdir()
    git(lab, "init", "-q", "-b", "main")
    (lab / ".agents/skills/odd-memory").mkdir(parents=True)
    (lab / ".opencode/agents").mkdir(parents=True)
    (lab / ".odd/observe-run-reports").mkdir(parents=True)
    (lab / ".agents/skills/odd-memory/SKILL.md").write_text("main\n")
    (lab / ".opencode/agents/observe-run.md").write_text("agent\n")
    (lab / "opencode.json").write_text("{}\n")
    (lab / ".odd/observe-run-reports/.keep").write_text("")
    git(lab, "add", "-A")
    git(lab, "commit", "-q", "-m", "lab: main deploy")
    git(lab, "branch", "lab-main")
    git(lab, "checkout", "-q", "-b", "lab-after")
    (lab / ".agents/skills/odd-memory/SKILL.md").write_text("after\n")
    git(lab, "add", "-A")
    git(lab, "commit", "-q", "-m", "lab: after deploy")
    git(lab, "checkout", "-q", "lab-main")
    return lab


@pytest.fixture
def kit(tmp_path: Path) -> dict:
    fake = tmp_path / "fake"
    fake.mkdir()
    measure = fake / "measure_phase.py"
    analyze = fake / "analyze_run.py"
    measure.write_text(FAKE_MEASURE)
    analyze.write_text(FAKE_ANALYZE)
    home = tmp_path / "fakehome"
    (home / ".claude").mkdir(parents=True)
    mission = tmp_path / "mission.txt"
    mission.write_text("/odd-observe observe svc\n")
    return {"measure": measure, "analyze": analyze, "home": home, "mission": mission}


def run_samples(lab: Path, kit: dict, out: Path, *samples: str, extra=(), env=None):
    return subprocess.run(
        [
            sys.executable,
            str(RUN_SAMPLES),
            "--lab",
            str(lab),
            "--fake-home",
            str(kit["home"]),
            "--out",
            str(out),
            "--cli",
            "opencode",
            "--model",
            "google/gemini-3.7-flash",
            "--phase",
            "whole",
            "--measure-script",
            str(kit["measure"]),
            "--analyze-script",
            str(kit["analyze"]),
            "--pause",
            "0",
            *extra,
            *samples,
        ],
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV, **(env or {})},
        check=False,
    )


def test_each_sample_runs_on_its_branch_with_the_scope_synced_and_is_journaled(
    lab, kit, tmp_path
):
    out = tmp_path / "study"
    p = run_samples(
        lab,
        kit,
        out,
        f"base1=lab-main:{kit['mission']}",
        f"after1=lab-after:{kit['mission']}",
    )
    assert p.returncode == 0, p.stderr + p.stdout
    journal = (out / "samples.log").read_text().splitlines()
    assert [ln.split()[1:4] for ln in journal if " SAMPLE " in ln] == [
        ["SAMPLE", "DONE", "base1"],
        ["SAMPLE", "DONE", "after1"],
        ["SAMPLE", "CHAIN", "DONE"],
    ]
    base = json.loads((out / "base1.record.json").read_text())
    after = json.loads((out / "after1.record.json").read_text())
    assert base["cwd"] == str(lab.resolve()) and base["home"] == str(kit["home"])
    assert after["cwd"] == base["cwd"] and after["tag"] == "after1"
    assert "ref: refs/heads/lab-main" in (out / "base1.seen-branch").read_text()
    assert "ref: refs/heads/lab-after" in (out / "after1.seen-branch").read_text()
    # the fake user scope carries the branch under measurement, never the last one
    assert (kit["home"] / ".claude/skills/odd-memory/SKILL.md").read_text() == "after\n"
    assert (kit["home"] / ".claude/agents/observe-run.md").exists()
    assert (out / "after1.analysis.txt").read_text().startswith("analysed --record")
    assert "--cli opencode" in " ".join(base["argv"])
    assert "--prompt-file" in base["argv"]
    assert git(lab, "branch", "--show-current") == "lab-after"


def test_a_previous_runs_leftovers_are_cleared_before_the_next_sample(
    lab, kit, tmp_path
):
    """A report branch, a report commit on the lab branch, an untracked
    report and a rewritten opencode.json are what a run leaves behind."""
    out = tmp_path / "study"
    tip = git(lab, "rev-parse", "lab-main")
    p = run_samples(
        lab,
        kit,
        out,
        f"s1=lab-main:{kit['mission']}",
        f"s2=lab-main:{kit['mission']}",
        env={"FAKE_MEASURE_LEAVE": "s1"},
    )
    assert p.returncode == 0, p.stderr + p.stdout
    assert git(lab, "rev-parse", "HEAD") == tip
    assert "docs/odd-observe-run-report-x" not in git(lab, "branch")
    assert not (lab / ".odd/observe-run-reports/2026-09-11-1100-y.md").exists()
    assert git(lab, "status", "--porcelain") == ""
    journal = (out / "samples.log").read_text()
    assert (
        "cleared before lab-main: a report commit, branch docs/odd-observe-run-report-x"
        in journal
    )
    assert "SAMPLE DONE s2" in journal


def test_hooks_run_around_the_launch_with_the_samples_names_in_their_environment(
    lab, kit, tmp_path
):
    out = tmp_path / "study"
    before = tmp_path / "before.sh"
    before.write_text(
        '#!/bin/bash\necho "before $SAMPLE_TAG $SAMPLE_BRANCH $SAMPLE_OUT" >> "$SAMPLE_OUT/hooks.txt"\n'
    )
    alongside = tmp_path / "alongside.sh"
    alongside.write_text(
        '#!/bin/bash\necho "alongside $SAMPLE_TAG" >> "$SAMPLE_OUT/hooks.txt"\n'
    )
    after = tmp_path / "after.sh"
    after.write_text(
        '#!/bin/bash\necho "after $SAMPLE_TAG" >> "$SAMPLE_OUT/hooks.txt"\n'
    )
    p = run_samples(
        lab,
        kit,
        out,
        f"s1=lab-main:{kit['mission']}",
        extra=(
            "--before",
            f"bash {before}",
            "--alongside",
            f"bash {alongside}",
            "--after",
            f"bash {after}",
        ),
    )
    assert p.returncode == 0, p.stderr + p.stdout
    lines = (out / "hooks.txt").read_text().splitlines()
    assert lines[0] == f"before s1 lab-main {out}"
    assert set(lines[1:]) == {"alongside s1", "after s1"}


def test_a_failed_measurement_is_journaled_and_the_chain_goes_on(lab, kit, tmp_path):
    out = tmp_path / "study"
    p = run_samples(
        lab,
        kit,
        out,
        f"s1=lab-main:{kit['mission']}",
        f"s2=lab-after:{kit['mission']}",
        env={"FAKE_MEASURE_FAIL": "s1"},
    )
    assert p.returncode == 1, p.stderr + p.stdout
    journal = (out / "samples.log").read_text()
    assert "SAMPLE FAILED s1 (measure exit 2)" in journal
    assert "SAMPLE DONE s2" in journal
    assert "SAMPLE CHAIN DONE 1 of 2" in journal


def test_a_dirty_lab_or_an_unknown_branch_refuses_before_launching(lab, kit, tmp_path):
    out = tmp_path / "study"
    p = run_samples(lab, kit, out, f"s1=lab-nope:{kit['mission']}")
    assert p.returncode == 1 and "lab-nope" in p.stderr
    assert not (out / "s1.record.json").exists()
    (lab / "stray.txt").write_text("x\n")
    p = run_samples(lab, kit, out, f"s1=lab-main:{kit['mission']}")
    assert p.returncode == 1 and "not clean" in p.stderr
    assert not (out / "s1.record.json").exists()
    assert "SAMPLE CHAIN ABORTED at s1" in (out / "samples.log").read_text()


def test_a_report_commit_at_the_branchs_own_tip_is_not_reset(lab, kit, tmp_path):
    """The reset is bounded to what a run added after the tip recorded when
    the chain started: a lab branch legitimately ending in a docs(odd)
    commit keeps it."""
    (lab / ".odd/observe-run-reports/2026-09-11-1000-x.md").write_text("report\n")
    git(lab, "add", "-A")
    git(lab, "commit", "-q", "-m", "docs(odd): observation report x")
    tip = git(lab, "rev-parse", "HEAD")
    out = tmp_path / "study"
    p = run_samples(lab, kit, out, f"s1=lab-main:{kit['mission']}")
    assert p.returncode == 0, p.stderr + p.stdout
    assert git(lab, "rev-parse", "HEAD") == tip


def test_a_missing_scope_source_is_refused_and_scratch_is_cleared_only_when_named(
    lab, kit, tmp_path
):
    out = tmp_path / "study"
    p = run_samples(
        lab,
        kit,
        out,
        f"s1=lab-main:{kit['mission']}",
        extra=("--scope", "nope/dir:.claude/x"),
    )
    assert p.returncode == 1 and "not deployed" in p.stderr
    scratch = tmp_path / "scratch"
    (scratch / "keep").mkdir(parents=True)
    p = run_samples(lab, kit, out, f"s2=lab-main:{kit['mission']}")
    assert p.returncode == 0, p.stderr + p.stdout
    assert (scratch / "keep").is_dir()
    p = run_samples(
        lab,
        kit,
        out,
        f"s3=lab-main:{kit['mission']}",
        extra=("--scratch", str(scratch)),
    )
    assert p.returncode == 0, p.stderr + p.stdout
    assert not scratch.exists()
    p = run_samples(
        lab, kit, out, f"s4=lab-main:{kit['mission']}", extra=("--cli", "claude")
    )
    assert p.returncode == 1 and "--scope" in p.stderr


def test_a_sample_spec_needs_all_three_parts():
    p = subprocess.run(
        [
            sys.executable,
            str(RUN_SAMPLES),
            "--lab",
            ".",
            "--fake-home",
            ".",
            "--out",
            ".",
            "s1=lab-main",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode != 0 and "tag=branch:mission" in (p.stderr + p.stdout)
