"""Tests for the get-status skill's deterministic renderer.

The renderer applies the skill's own rules to the fact sheet and prints
the status as tables; what a rule cannot decide lands under "Judgment
needed". Fixtures are throwaway git repositories, as in test_odd_status.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_odd_status import (
    DEFAULT_BODY,
    GIT_ENV,
    LEDGER_HEAD,
    SCRIPT,
    Repo,
    observation,
)

RENDER = SCRIPT.parent / "odd_render.py"


def _load(name: str, path: Path):
    sys.dont_write_bytecode = True
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def odd_render():
    return _load("odd_render", RENDER)


@pytest.fixture(scope="module")
def odd_status():
    return _load("odd_status", SCRIPT)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path)
    r.write("src/app.py", "print('v1')\n")
    r.write("docs/guide.md", "# guide\n")
    r.write("README.md", "# readme\n")
    r.commit("feat: initial", date="2026-08-01T10:00:00Z")
    return r


def rendered(repo: Repo, odd_status, odd_render, today="2026-08-20", **kwargs) -> str:
    """The full rendering - the working data most rules are asserted on."""
    facts = odd_status.build_facts(repo.root, recent=None, max_title=None, **kwargs)
    return odd_render.render(facts, today=today, full=True)


def screen(repo: Repo, odd_status, odd_render, today="2026-08-20", **kwargs) -> str:
    """The default rendering - one screen."""
    facts = odd_status.build_facts(repo.root, recent=None, max_title=None, **kwargs)
    return odd_render.render(facts, today=today)


def own_rows(odd_render, facts, suffix="1000-a.md") -> dict:
    return {
        r["id"]: r
        for r in odd_render.finding_rows(facts)
        if r["report"].endswith(suffix)
    }


VERIFY_BODY = """\
**Verdict: 2/2 checks PASS** on unchanged criteria.

## 1. Mission and run record

### Scenario record (verbatim)

Ad-hoc: 30 calls.

## 2. Observed behavior

| Operation | Requests | Rate | p50 | p95 | p99 | Error % | Notable |
|---|---|---|---|---|---|---|---|
| POST /checkout | 30 | 1/s | 70 ms | 90 ms | 131 ms | 0 % | - |
| GET /cart | 30 | 1/s | 10 ms | 12 ms | 14 ms | 3.4 % | - |
| GET /new | 30 | 1/s | 5 ms | 6 ms | 7 ms | 0 % | new here |

## 3. Anomalies and probable causes — fate of the baseline's findings

| # | Baseline finding | Fate | Evidence |
|---|---|---|---|
| F1 | N+1 on cart lines | FIXED | 1 span per call |
| F2 | Cold start | still present | 390 ms |

| # | Finding | Severity | Confidence | Evidence | Expected gain |
|---|---|---|---|---|---|
| V1 | Retry storm on /cart | medium | confirmed | 3 retries per call | error -3 % |

## 4. Improvement opportunities

- None.

## 5. Telemetry gaps — fate of the baseline's gaps

- **Logs: absent for checkout** — still missing.

## 6. Decisions the spec must settle

- Nothing.

## 7. Measurement protocol for the next run

| Check | Before | This run | Verdict |
|---|---|---|---|
| C1 p95 POST /checkout | 120 ms | 90 ms | PASS |
| C2 error rate GET /cart | 5 % | 3.4 % | PASS |
"""

INSTRUMENTATION_TEXT = """\
---
project: myrepo/src
stack: local
run_name: app-python
date: 2026-08-09
---

# Instrumentation report

## 1. Stack inventory

- `src/app.py`: Python, no telemetry.

## 2. Summary table

| Service | Language | Approach | Order |
|---|---|---|---|
| checkout | Python | SDK | 1 |

## 3. Decisions made, with rationale

| Package | Version |
|---|---|
| opentelemetry-sdk | 1.44.0 |

## 5. Verification protocol

- Prerequisites: local stack up.

| Signal | Check |
|---|---|
| traces | one span per request |
"""


def write_verify(
    repo: Repo, name: str, verifies: str, body: str, mode: str = "verify"
) -> None:
    date = name[:10]
    repo.write(
        f".odd/observe-run-reports/{name}",
        observation(
            run_name="a",
            mode=mode,
            date=date,
            revision=repo.git("rev-parse", "--short", "HEAD"),
            extra_frontmatter=f"verifies: {verifies}\ntree_anchor: {repo.tree_anchor()}",
            body=body,
        ),
    )


def baseline_and_verification(repo: Repo, *, verify_date="2026-08-12") -> str:
    """An observation, a fix commit, and its verification; returns the fix sha."""
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(
            run_name="a",
            revision=rev,
            extra_frontmatter=f"tree_anchor: {repo.tree_anchor()}",
        ),
    )
    repo.commit("docs(odd): observation report a", date="2026-08-10T12:00:00Z")
    repo.write("src/app.py", "print('fixed')\n")
    fix = repo.commit("fix: batch the cart lines query", date="2026-08-11T12:00:00Z")
    write_verify(
        repo, f"{verify_date}-1000-verify-a.md", "2026-08-10-1000-a.md", VERIFY_BODY
    )
    repo.commit("docs(odd): verification report a", date=f"{verify_date}T12:00:00Z")
    return fix


# --- classifiers -------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "state"),
    [
        ("FIXED", "fixed-and-verified"),
        ("**closed**", "fixed-and-verified"),
        ("resolved by #12", "fixed-and-verified"),
        ("PASS", "fixed-and-verified"),
        ("GAP FILLED", "fixed-and-verified"),
        ("REGRESSED: p95 +40 %", "regressed"),
        ("still present", "open"),
        ("still missing", "open"),
        ("not ruled (quick)", "open"),
        ("present, unattributed", "open"),
        ("unchanged (spec-scoped out)", "open"),
        ("carried", "open"),
        ("FAIL", "open"),
        (
            "still correct - re-confirmed 5/5 (regression check passed)",
            "fixed-and-verified",
        ),
        ("no regression, FIXED", "fixed-and-verified"),
        (
            "**FIXED** by #149 - that is #117's design, not a regression",
            "fixed-and-verified",
        ),
        (
            '**improved** (the "regression"-looking p50 increase is the correct behavior)',
            "fixed-and-verified",
        ),
        (
            "**PASS per criterion - condition unmet** (not a regression)",
            "fixed-and-verified",
        ),
        ("FIXED for A, regressed for B", "unknown"),
        ("not fixed", "open"),
        ("unresolved", "open"),
        ("mostly, see below", "unknown"),
        (None, "unknown"),
    ],
)
def test_classify_ruling(odd_render, text, state):
    assert odd_render.classify_ruling(text) == state


def report_with(verdict_lines, findings, depth=None):
    return {
        "verdict_lines": verdict_lines,
        "headline": None,
        "findings": findings,
        "frontmatter": {"depth": depth} if depth else {},
    }


def test_verdict_label_reads_the_verdict_paragraph_then_the_rulings(odd_render):
    assert (
        odd_render.verdict_label(report_with(["**Verdict: 18/18 PASS**"], [])) == "PASS"
    )
    assert (
        odd_render.verdict_label(report_with(["**Verdict: FAIL** on C3"], [])) == "FAIL"
    )
    assert odd_render.verdict_label(report_with([], [])) == "no verdict stated"
    counted = report_with(["**Verdict: 18/18 — 17 passes on unchanged criteria**"], [])
    assert odd_render.verdict_label(counted) == "PASS (18/18)"
    counted = report_with(["**Verdict: 16/18**, two checks still failing"], [])
    assert odd_render.verdict_label(counted) == "FAIL (16/18)"


def test_verdict_label_counts_rulings_wherever_they_sit_and_states_quick_coverage(
    odd_render,
):
    rulings = report_with(
        [],
        [
            {"id": "C1", "ruling": "PASS", "section": 7},
            {"id": "C2", "ruling": "still present", "section": 3},
            {"id": "C3", "ruling": "not ruled (quick)", "section": 7},
            {"id": "F9", "ruling": None, "section": 3},
        ],
        depth="quick",
    )
    assert (
        odd_render.verdict_label(rulings)
        == "1 of 2 rulings closed (quick, 2 of 3 ruled)"
    )
    passed = report_with(
        ["**Verdict: PASS**"],
        [
            {"id": "C1", "ruling": "PASS", "section": 7},
            {"id": "C3", "ruling": "not ruled (quick)", "section": 7},
        ],
        depth="quick",
    )
    assert odd_render.verdict_label(passed) == "PASS (quick, 1 of 2 ruled)"


# --- the findings ledger ---------------------------------------------------------


def test_finding_states_follow_rulings_and_the_ledger(repo, odd_status, odd_render):
    baseline_and_verification(repo)
    repo.write(
        ".odd/decisions.md",
        LEDGER_HEAD
        + "| 2026-08-13 | 2026-08-10-1000-a.md / F2 | wontfix | Cold start is rare |\n",
    )
    repo.commit("docs(odd): decision")
    facts = odd_status.build_facts(repo.root, recent=None)
    rows = {
        (Path(r["report"]).name, r["id"]): r for r in odd_render.finding_rows(facts)
    }
    f1 = rows[("2026-08-10-1000-a.md", "F1")]
    assert f1["state"] == "fixed-and-verified"
    assert f1["ruled_by"] == "2026-08-12-1000-verify-a.md: FIXED"
    f2 = rows[("2026-08-10-1000-a.md", "F2")]
    assert f2["state"] == "declined"
    assert f2["ruled_by"] == "wontfix 2026-08-13: Cold start is rare"
    v1 = rows[("2026-08-12-1000-verify-a.md", "V1")]
    assert v1["state"] == "open"
    assert v1["ruled_by"] == "no verification yet"
    # a verification's own check rows are rulings, not findings of their own
    assert ("2026-08-12-1000-verify-a.md", "C1") not in rows
    assert odd_render.burn_down(list(rows.values())) == {
        "open": 1,
        "fixed-and-verified": 1,
        "regressed": 0,
        "declined": 1,
        "unknown": 0,
    }


def test_a_re_measure_never_rules_a_finding(repo, odd_status, odd_render):
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev),
    )
    write_verify(
        repo,
        "2026-08-12-1000-remeasure-a.md",
        "2026-08-10-1000-a.md",
        VERIFY_BODY,
        mode="re-measure",
    )
    repo.commit("docs(odd): reports")
    rows = own_rows(odd_render, odd_status.build_facts(repo.root, recent=None))
    assert rows["F1"]["state"] == "open"
    assert rows["F1"]["ruled_by"] == "no verification yet"


def test_a_later_verification_in_the_chain_rules_the_baseline_finding(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    second = VERIFY_BODY.replace(
        "| F2 | Cold start | still present | 390 ms |",
        "| F2 | Cold start | FIXED | 90 ms |",
    )
    write_verify(
        repo, "2026-08-14-1000-verify-a.md", "2026-08-12-1000-verify-a.md", second
    )
    repo.commit("docs(odd): second verification")
    rows = own_rows(odd_render, odd_status.build_facts(repo.root, recent=None))
    assert rows["F2"]["state"] == "fixed-and-verified"
    assert rows["F2"]["ruled_by"] == "2026-08-14-1000-verify-a.md: FIXED"


def test_the_newest_ruling_wins_and_a_regression_after_a_fix_is_regressed(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    second = VERIFY_BODY.replace(
        "| F1 | N+1 on cart lines | FIXED | 1 span per call |",
        "| F1 | N+1 on cart lines | REGRESSED | 40 spans |",
    )
    write_verify(
        repo, "2026-08-14-1000-verify-a.md", "2026-08-12-1000-verify-a.md", second
    )
    repo.commit("docs(odd): second verification")
    rows = own_rows(odd_render, odd_status.build_facts(repo.root, recent=None))
    assert rows["F1"]["state"] == "regressed"
    assert rows["F1"]["ruled_by"] == "2026-08-14-1000-verify-a.md: REGRESSED"


def test_verifications_that_disagree_are_deferred(repo, odd_status, odd_render):
    baseline_and_verification(repo)
    second = VERIFY_BODY.replace(
        "| F1 | N+1 on cart lines | FIXED | 1 span per call |",
        "| F1 | N+1 on cart lines | still present | 40 spans |",
    )
    write_verify(
        repo, "2026-08-14-1000-verify-a.md", "2026-08-12-1000-verify-a.md", second
    )
    repo.commit("docs(odd): second verification")
    facts = odd_status.build_facts(repo.root, recent=None)
    rows = own_rows(odd_render, facts)
    assert rows["F1"]["state"] == "unknown"
    assert "disagree" in rows["F1"]["ruled_by"]
    assert (
        "F1"
        in odd_render.render(facts, full=True, today="2026-08-15").split(
            "## Judgment needed"
        )[1]
    )


def test_instrumentation_reports_contribute_no_findings_and_no_gaps(
    repo, odd_status, odd_render
):
    repo.write(
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app-python.md",
        INSTRUMENTATION_TEXT,
    )
    repo.commit("docs(odd): plan")
    facts = odd_status.build_facts(repo.root, recent=None)
    assert odd_render.finding_rows(facts) == []
    assert odd_render.gap_rows(facts) == []
    text = odd_render.render(facts, full=True, today="2026-08-13")
    assert "No finding recorded" in text
    assert "No gap recorded" in text


def test_a_ruling_the_rules_cannot_read_is_unknown_and_deferred(
    repo, odd_status, odd_render
):
    body = VERIFY_BODY.replace(
        "| F1 | N+1 on cart lines | FIXED |",
        "| F1 | N+1 on cart lines | mostly, see below |",
    )
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev),
    )
    write_verify(repo, "2026-08-12-1000-verify-a.md", "2026-08-10-1000-a.md", body)
    repo.commit("docs(odd): reports")
    facts = odd_status.build_facts(repo.root, recent=None)
    rows = own_rows(odd_render, facts)
    assert rows["F1"]["state"] == "unknown"
    assert rows["F1"]["ruled_by"] == "2026-08-12-1000-verify-a.md: mostly, see below"
    text = odd_render.render(facts, full=True, today="2026-08-20")
    assert "## Judgment needed" in text
    assert "mostly, see below" in text.split("## Judgment needed")[1]


# --- trends ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("80 ms", 80.0),
        ("4.75", 4.75),
        ("1.65 ms (n=30: observation, not a p99)", 1.65),
        ("**779 ms** (n=39)", 779.0),
        ("~19 ms (mean 19.5 ms)", 19.0),
        ("< 1 ms", 1.0),
        ("0% 5xx (4× 404 by design)", 0.0),
        ("10 % (1×502)", 10.0),
        ("trace lost (§3 F3/F5)", None),
        ("n<30, not quoted; all 14 ≤ 50 ms bucket", None),
        ("max 54 ms (n<30)", None),
        ("4.75 ms (Prom.) / 3.3 ms (k6)", None),
        ("—", None),
        (None, None),
    ],
)
def test_measurement_accepts_only_a_bare_value(odd_render, text, value):
    assert odd_render.measurement(text) == value


def test_trend_thresholds_ignore_noise_and_a_broken_baseline(odd_render):
    def row(p95, err):
        return {"p50": None, "p95": p95, "p99": None, "error": err}

    trend = odd_render.trend_of
    assert trend(row("2 ms", "0"), row("1 ms", "0"), "p95") == "stable"
    assert (
        trend(row("120 ms", "0 %"), row("90 ms", "0 %"), "p95")
        == "improved (p95 -25 %)"
    )
    assert trend(row("50 ms", "5.1 %"), row("50 ms", "6.8 %"), "p95") == "stable"
    assert trend(row("50 ms", "0 %"), row("50 ms", "3.4 %"), "p95") == (
        "regressed (error 0 % -> 3.4 %)"
    )
    assert trend(row("2.5 ms", "100%"), row("472 ms", "20 %"), "p95") == (
        "n/a (baseline error rate >= 50 %, not comparable)"
    )
    assert trend(row("trace lost (§3)", "0"), row("40 ms", "0"), "p95") == (
        "n/a (latency not parsable)"
    )
    assert trend(row("50 ms", "8/12 by design"), row("50 ms", "0"), "p95") == (
        "n/a (error rate not parsable)"
    )


def test_trends_join_a_verification_with_its_baseline_by_operation(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    facts = odd_status.build_facts(repo.root, recent=None)
    rows, apart = odd_render.trend_rows(facts)
    by_op = {r["operation"]: r for r in rows}
    checkout = by_op["POST /checkout"]
    assert checkout["pair"] == "2026-08-10-1000-a.md -> 2026-08-12-1000-verify-a.md"
    assert checkout["p50"] == "80 ms -> 70 ms"
    assert checkout["p95"] == "120 ms -> 90 ms"
    assert checkout["p99"] == "130 ms -> 131 ms"
    assert checkout["error"] == "0 % -> 0 %"
    assert checkout["trend"] == "improved (p95 -25 %)"
    assert by_op["GET /cart"]["trend"] == "regressed (error 0 % -> 3.4 %)"
    assert "GET /new" not in by_op  # only operations both runs carry
    assert apart == []


def test_trends_fall_back_to_a_latency_column_when_the_table_has_no_percentiles(
    repo, odd_status, odd_render
):
    header = (
        "| Operation | Requests | client (ms) | server span (ms) | Error % |\n"
        "|---|---|---|---|---|\n"
    )
    before = (
        DEFAULT_BODY.split("| Operation")[0]
        + header
        + "| X | 10 | 70 | 62 | 0 % |\n\n## 3."
        + DEFAULT_BODY.split("## 3.", 1)[1]
    )
    after = (
        VERIFY_BODY.split("| Operation")[0]
        + header
        + "| X | 10 | 80 | 80 | 0 % |\n\n## 3."
        + VERIFY_BODY.split("## 3.", 1)[1]
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body=before),
    )
    write_verify(repo, "2026-08-12-1000-verify-a.md", "2026-08-10-1000-a.md", after)
    repo.commit("docs(odd): reports")
    rows, _ = odd_render.trend_rows(odd_status.build_facts(repo.root, recent=None))
    [row] = rows
    assert row["p50"] == "server span (ms): 62 -> 80"
    assert row["p95"] == "-"
    assert row["trend"] == "regressed (server span (ms) +29 %)"


def test_runs_that_are_not_a_verifies_pair_are_listed_apart(
    repo, odd_status, odd_render
):
    for day in (10, 11):
        repo.write(
            f".odd/observe-run-reports/2026-08-{day}-1000-run{day}.md",
            observation(run_name=f"run{day}", date=f"2026-08-{day}"),
        )
    repo.commit("docs(odd): reports")
    facts = odd_status.build_facts(repo.root, recent=None)
    rows, apart = odd_render.trend_rows(facts)
    assert rows == []
    assert apart == [
        {
            "reports": ["2026-08-10-1000-run10.md", "2026-08-11-1000-run11.md"],
            "reason": "not a verifies pair: comparability of the scenarios is a judgment",
        }
    ]
    # listed apart is information, not a deferral
    text = odd_render.render(facts, full=True, today="2026-08-12")
    assert "Listed apart" in text
    assert "listed apart" not in text.split("## Judgment needed")[1]


# --- boundaries and recommendations -------------------------------------------------


def test_loop_can_rest_after_a_verification_whose_anchor_matches_head(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    facts = odd_status.build_facts(repo.root, recent=None)
    [rec] = odd_render.recommendations(facts, today="2026-08-13")
    assert rec["lineage"] == "checkout / local / local"
    assert rec["action"] == "loop can rest"
    assert "2026-08-12-1000-verify-a.md" in rec["evidence"]
    assert "PASS" in rec["evidence"]
    assert "tree anchor equals HEAD" in rec["evidence"]


def test_unclassified_entries_defer_and_a_runtime_flag_settles_them(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    repo.write("src/app.py", "print('changed again')\n")
    repo.commit("fix: another change", date="2026-08-14T12:00:00Z")
    facts = odd_status.build_facts(repo.root, recent=None)
    [rec] = odd_render.recommendations(facts, today="2026-08-15")
    assert rec["action"] == "judgment needed"
    assert "boundary uncertain" in rec["evidence"]
    assert "src (src/app.py)" in rec["evidence"]
    assert (
        "src (src/app.py)"
        in odd_render.render(facts, full=True, today="2026-08-15").split(
            "## Judgment needed"
        )[1]
    )
    settled = odd_status.build_facts(repo.root, recent=None, runtime=["src"])
    [rec] = odd_render.recommendations(settled, today="2026-08-15")
    assert rec["action"] == "verification due"
    assert (
        "runtime entries differ since the tree anchor: src (src/app.py)"
        in rec["evidence"]
    )
    assert (
        "- nothing deferred"
        in odd_render.render(settled, full=True, today="2026-08-15").split(
            "## Judgment needed"
        )[1]
    )


def test_a_tree_entry_present_on_one_side_only_is_uncertain(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    repo.write("service/main.py", "print('new service')\n")
    repo.commit("feat: a whole new service", date="2026-08-14T12:00:00Z")
    [rec] = odd_render.recommendations(
        odd_status.build_facts(repo.root, recent=None), today="2026-08-15"
    )
    assert rec["action"] == "judgment needed"
    assert "only at HEAD: service" in rec["evidence"]


def test_only_non_runtime_entries_moved_keeps_the_loop_at_rest(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    repo.write("docs/guide.md", "# v2\n")
    repo.commit("docs: wording", date="2026-08-14T12:00:00Z")
    [rec] = odd_render.recommendations(
        odd_status.build_facts(repo.root, recent=None), today="2026-08-15"
    )
    assert rec["action"] == "loop can rest"
    assert "docs" in rec["evidence"]


def test_the_chain_says_fixed_only_when_the_boundary_says_code_moved(
    repo, odd_status, odd_render
):
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(
            run_name="a",
            revision=rev,
            extra_frontmatter=f"tree_anchor: {repo.tree_anchor()}",
        ),
    )
    repo.commit("docs(odd): report", date="2026-08-10T12:00:00Z")
    repo.write("docs/guide.md", "# v2\n")
    repo.commit("docs: wording", date="2026-08-11T12:00:00Z")
    text = odd_render.render(
        odd_status.build_facts(repo.root, recent=None), full=True, today="2026-08-12"
    )
    state = text.split("## Per-service loop state")[1].split("## Findings")[0]
    assert "observed 2026-08-10 (a) |" in state
    assert "fixed" not in state


def test_an_observation_with_no_fix_yet_waits_on_the_fix(repo, odd_status, odd_render):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=repo.git("rev-parse", "--short", "HEAD")),
    )
    repo.commit("docs(odd): report", date="2026-08-10T12:00:00Z")
    [rec] = odd_render.recommendations(
        odd_status.build_facts(repo.root, recent=None), today="2026-08-12"
    )
    assert rec["action"] == "fix pending"
    assert "no verification yet" in rec["evidence"]


def test_a_boundary_without_anchor_or_revision_is_judgment_needed_when_commits_landed(
    repo, odd_status, odd_render
):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision="0000000"),
    )
    repo.commit("docs(odd): report", date="2026-08-10T12:00:00Z")
    repo.write("src/app.py", "print('v2')\n")
    repo.commit("fix: something", date="2026-08-11T12:00:00Z")
    [rec] = odd_render.recommendations(
        odd_status.build_facts(repo.root, recent=None), today="2026-08-12"
    )
    assert rec["action"] == "judgment needed"
    assert "commit-date" in rec["evidence"]


def test_observation_overdue_when_the_cadence_lapsed(repo, odd_status, odd_render):
    for day in (1, 3, 5, 7):
        repo.write(
            f".odd/observe-run-reports/2026-08-{day:02d}-1000-run{day}.md",
            observation(run_name=f"run{day}", date=f"2026-08-{day:02d}"),
        )
    repo.commit("docs(odd): reports", date="2026-08-07T12:00:00Z")
    facts = odd_status.build_facts(repo.root, recent=None)
    [rec] = odd_render.recommendations(facts, today="2026-08-30")
    assert rec["action"] == "observation overdue"
    assert "every 2 days" in rec["evidence"]
    [rec] = odd_render.recommendations(facts, today="2026-08-08")
    assert rec["action"] != "observation overdue"


def test_a_quick_verification_states_its_coverage_and_defers_the_rest(
    repo, odd_status, odd_render
):
    body = VERIFY_BODY.replace(
        "| F2 | Cold start | still present | 390 ms |",
        "| F2 | Cold start | not ruled (quick) | - |",
    )
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(
            run_name="a",
            revision=rev,
            extra_frontmatter=f"tree_anchor: {repo.tree_anchor()}",
        ),
    )
    repo.commit("docs(odd): report", date="2026-08-10T12:00:00Z")
    text = observation(
        run_name="a",
        mode="verify",
        date="2026-08-12",
        revision=repo.git("rev-parse", "--short", "HEAD"),
        extra_frontmatter=f"verifies: 2026-08-10-1000-a.md\ntree_anchor: {repo.tree_anchor()}",
        body=body,
    ).replace("depth: full", "depth: quick")
    repo.write(".odd/observe-run-reports/2026-08-12-1000-verify-a.md", text)
    repo.commit("docs(odd): quick verification", date="2026-08-12T12:00:00Z")
    facts = odd_status.build_facts(repo.root, recent=None)
    rendered_text = odd_render.render(facts, full=True, today="2026-08-13")
    assert "PASS (quick, 3 of 4 ruled)" in rendered_text
    judgment = rendered_text.split("## Judgment needed")[1]
    assert "quick verification 2026-08-12-1000-verify-a.md ruled 3 of 4" in judgment
    rows = own_rows(odd_render, facts)
    assert rows["F2"]["state"] == "open"


# --- gaps ------------------------------------------------------------------------


# --- the rendering -----------------------------------------------------------------


def test_render_prints_every_section_with_its_inputs(repo, odd_status, odd_render):
    baseline_and_verification(repo)
    text = rendered(repo, odd_status, odd_render, today="2026-08-13")
    for heading in (
        "# ODD loop status",
        "## Inventory",
        "## Per-service loop state",
        "## Findings ledger",
        "## Trends",
        "## Open telemetry gaps",
        "## Next recommended action",
        "## Judgment needed",
    ):
        assert heading in text, heading
    assert "| POST /checkout |" in text
    assert "Logs: absent for checkout" in text


def test_golden_rendering_of_a_verified_lineage(repo, odd_status, odd_render):
    baseline_and_verification(repo)
    text = rendered(repo, odd_status, odd_render, today="2026-08-13")
    expected_state = (
        "| checkout / local / local "
        "| 2026-08-10 a (drive, depth full) "
        "| 2026-08-12 2026-08-12-1000-verify-a.md: PASS, verifies 2026-08-10-1000-a.md "
        "| observed 2026-08-10 (a) -> change since: uncertain -> verified 2026-08-12 (PASS) "
        "| tree anchor equals HEAD |"
    )
    assert expected_state in text
    assert (
        "| checkout / local / local | loop can rest | last report 2026-08-12-1000-verify-a.md "
        "(verify); verdict PASS; tree anchor equals HEAD |"
    ) in text
    assert (
        "Burn-down: open 2 · fixed-and-verified 1 · regressed 0 · declined 0." in text
    )
    assert (
        "| 2026-08-10-1000-a.md / F1 | N+1 on cart lines | high | fixed-and-verified "
        "| 2026-08-12-1000-verify-a.md: FIXED |"
    ) in text
    assert "- nothing deferred" in text.split("## Judgment needed")[1]


def test_degradations_reach_the_judgment_list(repo, odd_status, odd_render):
    rev = repo.git("rev-parse", "--short", "HEAD")
    broken = observation(run_name="a", revision=rev).replace(
        "services: [checkout]", "services:\n  - checkout"
    )
    repo.write(".odd/observe-run-reports/2026-08-10-1000-a.md", broken)
    no_verdict = (
        VERIFY_BODY.replace(
            "**Verdict: 2/2 checks PASS** on unchanged criteria.\n\n", ""
        )
        .replace("| C1 p95 POST /checkout | 120 ms | 90 ms | PASS |\n", "")
        .replace("| C2 error rate GET /cart | 5 % | 3.4 % | PASS |\n", "")
        .replace("| F1 | N+1 on cart lines | FIXED | 1 span per call |\n", "")
        .replace("| F2 | Cold start | still present | 390 ms |\n", "")
    )
    write_verify(
        repo, "2026-08-12-1000-verify-a.md", "2026-08-10-1000-a.md", no_verdict
    )
    (repo.root / ".odd/observe-run-reports/2026-08-13-1000-b.md").write_bytes(
        b"---\nservices: [x]\n---\n\xff"
    )
    repo.write(".odd/decisions.md", LEDGER_HEAD + "| 2026-08-13 | garbage |\n")
    repo.commit("docs(odd): degraded memory")
    facts = odd_status.build_facts(repo.root, recent=None, max_text=40)
    judgment = odd_render.render(facts, full=True, today="2026-08-14").split(
        "## Judgment needed"
    )[1]
    assert "frontmatter of 2026-08-10-1000-a.md: services: block-style" in judgment
    assert "2026-08-12-1000-verify-a.md states no verdict" in judgment
    assert "unreadable report" in judgment
    assert "ledger line" in judgment
    assert "section 5 of 2026-08-12-1000-verify-a.md truncated" in judgment


def test_render_says_the_loop_has_not_started(repo, odd_status, odd_render):
    text = rendered(repo, odd_status, odd_render)
    assert "has not started" in text
    assert "/odd-instrument-otel" in text and "/odd-observe" in text
    assert "## Findings ledger" not in text


def test_render_states_a_filter_that_matches_nothing(repo, odd_status, odd_render):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    text = rendered(
        repo, odd_status, odd_render, services=["payment"], environment="prod"
    )
    assert "No report matches" in text
    assert "service `payment`" in text and "environment `prod`" in text
    assert "services: checkout" in text and "environments: local" in text
    assert "## Findings ledger" not in text


def test_a_plan_lineage_shows_the_verification_that_covers_it(
    repo, odd_status, odd_render
):
    repo.write(
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app-python.md",
        INSTRUMENTATION_TEXT,
    )
    write_verify(
        repo,
        "2026-08-12-1000-verify-app-python.md",
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app-python.md",
        VERIFY_BODY,
    )
    repo.commit("docs(odd): plan and verification")
    facts = odd_status.build_facts(repo.root, recent=None)
    text = odd_render.render(facts, full=True, today="2026-08-13")
    state = text.split("## Per-service loop state")[1].split("## Findings")[0]
    plan_row = next(
        line
        for line in state.splitlines()
        if line.startswith("| myrepo/src (plan) / local |")
    )
    assert "2026-08-12-1000-verify-app-python.md: PASS" in plan_row
    assert "| myrepo/src (plan) / local | 2026-08-09 app-python (plan) | 0 |" in text
    assert "planned 2026-08-09 -> verified 2026-08-12 (PASS)" in plan_row
    _, apart = odd_render.trend_rows(facts)
    assert apart == []


def test_the_chain_starts_from_the_newest_observation_whatever_its_mode(
    repo, odd_status, odd_render
):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-remeasure-a.md",
        observation(
            run_name="a",
            mode="re-measure",
            date="2026-08-11",
            extra_frontmatter="verifies: 2026-08-10-1000-a.md",
        ),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-12-1000-b.md",
        observation(run_name="b", date="2026-08-12"),
    )
    repo.commit("docs(odd): reports")
    text = odd_render.render(
        odd_status.build_facts(repo.root, recent=None), full=True, today="2026-08-13"
    )
    assert "observed 2026-08-12 (b)" in text


# --- the command line ---------------------------------------------------------------


def test_cli_render_prints_markdown(repo):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--render", "--today", "2026-08-20"],
        cwd=repo.root,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_ENV},
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    assert proc.stdout.startswith("# ODD loop status")
    assert "## Loop state" in proc.stdout
    assert "## Findings ledger" not in proc.stdout
    with pytest.raises(json.JSONDecodeError):
        json.loads(proc.stdout)
    # importing the renderer must not leave bytecode in the packaged skill
    assert not (SCRIPT.parent / "__pycache__").exists()


def test_cli_rejects_render_only_flags_without_render(repo):
    for args in (
        ["--render", "--recent", "1"],
        ["--today", "2026-08-20"],
        ["--full"],
        ["--ruled", "2026-08-10-1000-a.md/F1=fixed"],
    ):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(repo.root), *args],
            capture_output=True,
            text=True,
            env={**os.environ, **GIT_ENV},
            check=False,
        )
        assert proc.returncode == 2, args
        assert "--render" in proc.stderr


def test_a_no_gap_statement_is_not_a_gap(repo, odd_status, odd_render):
    body = DEFAULT_BODY.replace(
        "- **Logs: absent for checkout** - no log stream carries the service.",
        "- No handoff to `otel-instrumentation-expert` needed: the instrumentation is complete.\n"
        "- Gaps do not dominate: nothing to instrument.\n"
        "- **Profiles: absent for checkout** - no profile carries the service.",
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body=body),
    )
    repo.commit("docs(odd): report")
    [row] = odd_render.gap_rows(odd_status.build_facts(repo.root, recent=None))
    assert row["gap"].startswith("**Profiles: absent for checkout**")


# --- third round: id collisions, mixed rulings, units, coverage ---------------------


def test_a_ruling_beyond_the_direct_verification_defers_when_an_intermediate_defines_the_id(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    # verify-a rules F1 still present and defines its own F1
    own_f1 = VERIFY_BODY.replace(
        "| F1 | N+1 on cart lines | FIXED | 1 span per call |",
        "| F1 | N+1 on cart lines | still present | 30 spans |",
    ).replace(
        "| V1 | Retry storm on /cart | medium | confirmed | 3 retries per call | error -3 % |",
        "| F1 | Log volume of the healthcheck | low | confirmed | 6 lines/min | none |",
    )
    write_verify(repo, "2026-08-13-1000-verify-a.md", "2026-08-10-1000-a.md", own_f1)
    # verify-b verifies verify-a and rules "F1 FIXED": whose F1?
    write_verify(
        repo, "2026-08-14-1000-verify-a.md", "2026-08-13-1000-verify-a.md", VERIFY_BODY
    )
    repo.commit("docs(odd): chain")
    facts = odd_status.build_facts(repo.root, recent=None)
    rows = own_rows(odd_render, facts)
    assert rows["F1"]["state"] == "unknown"
    assert "also defines" in rows["F1"]["ruled_by"]
    assert "2026-08-13-1000-verify-a.md" in rows["F1"]["ruled_by"]
    judgment = odd_render.render(facts, full=True, today="2026-08-15").split(
        "## Judgment needed"
    )[1]
    assert "F1" in judgment and "same finding" in judgment


@pytest.mark.parametrize(
    ("text", "state"),
    [
        (
            "**closed** for orders-api; load-generator **present, unattributed**",
            "unknown",
        ),
        (
            "**fixed in the fixed image**; **still present on the pre-fix container**",
            "unknown",
        ),
        ("PASS with caveat (finding 5, still present)", "unknown"),
        ("FIXED by #12", "fixed-and-verified"),
    ],
)
def test_a_fixed_word_beside_a_strong_open_word_is_deferred(odd_render, text, state):
    assert odd_render.classify_ruling(text) == state


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("0.9 s", 900.0),
        ("250 µs", 0.25),
        ("250 us", 0.25),
        ("1.2s", 1200.0),
        ("80 ms", 80.0),
    ],
)
def test_measurement_normalises_units_to_milliseconds(odd_render, text, value):
    assert odd_render.measurement(text) == value


def test_trend_in_seconds_is_not_stable_by_the_millisecond_floor(odd_render):
    def row(p95, err):
        return {"p50": None, "p95": p95, "p99": None, "error": err}

    assert odd_render.trend_of(row("0.9 s", "0"), row("2.4 s", "0"), "p95") == (
        "regressed (p95 +167 %)"
    )


def test_a_ruling_on_an_id_outside_the_chain_is_deferred_not_ignored(
    repo, odd_status, odd_render
):
    # report a (F1, F2) is verified by nobody; report b's verification rules "F2 FIXED",
    # an id report a also defines
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev),
    )
    body_b = DEFAULT_BODY.replace("| F1 |", "| G1 |").replace("| F2 |", "| G2 |")
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-b.md",
        observation(
            run_name="b",
            date="2026-08-11",
            revision=rev,
            services="[payment]",
            body=body_b,
        ),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-12-1000-verify-b.md",
        observation(
            run_name="b",
            mode="verify",
            date="2026-08-12",
            extra_frontmatter="verifies: 2026-08-11-1000-b.md",
            body=VERIFY_BODY,
        ),
    )
    repo.commit("docs(odd): reports")
    facts = odd_status.build_facts(repo.root, recent=None)
    rows = own_rows(odd_render, facts)
    assert rows["F2"]["state"] == "open"
    judgment = odd_render.render(facts, full=True, today="2026-08-13").split(
        "## Judgment needed"
    )[1]
    assert "2026-08-12-1000-verify-b.md rules F2" in judgment
    assert "outside its chain" in judgment


def test_a_quick_verification_leaving_baseline_findings_unruled_cannot_rest_the_loop(
    repo, odd_status, odd_render
):
    # the quick verification rules nothing of the baseline's F1/F2
    body = VERIFY_BODY.replace(
        "| F1 | N+1 on cart lines | FIXED | 1 span per call |\n", ""
    ).replace("| F2 | Cold start | still present | 390 ms |\n", "")
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(
            run_name="a",
            revision=rev,
            extra_frontmatter=f"tree_anchor: {repo.tree_anchor()}",
        ),
    )
    repo.commit("docs(odd): report", date="2026-08-10T12:00:00Z")
    text = observation(
        run_name="a",
        mode="verify",
        date="2026-08-12",
        revision=repo.git("rev-parse", "--short", "HEAD"),
        extra_frontmatter=f"verifies: 2026-08-10-1000-a.md\ntree_anchor: {repo.tree_anchor()}",
        body=body,
    ).replace("depth: full", "depth: quick")
    repo.write(".odd/observe-run-reports/2026-08-12-1000-verify-a.md", text)
    repo.commit("docs(odd): quick verification", date="2026-08-12T12:00:00Z")
    facts = odd_status.build_facts(repo.root, recent=None)
    [rec] = odd_render.recommendations(facts, today="2026-08-13")
    assert rec["action"] == "judgment needed"
    assert "2 finding(s) of 2026-08-10-1000-a.md unruled" in rec["evidence"]


def test_a_not_queried_item_is_dropped_whole_and_deferred(repo, odd_status, odd_render):
    body = DEFAULT_BODY.replace(
        "- **Logs: absent for checkout** - no log stream carries the service.",
        "Not queried (quick): logs, profiles — the probes (`gcx logs; labels`) showed nothing;\n"
        "the baseline's gaps stand: no startup span (F3).",
    )
    text = observation(run_name="a", body=body).replace("depth: full", "depth: quick")
    repo.write(".odd/observe-run-reports/2026-08-10-1000-a.md", text)
    repo.commit("docs(odd): report")
    facts = odd_status.build_facts(repo.root, recent=None)
    [row] = odd_render.gap_rows(facts)
    assert (
        row["gap"]
        == "(quick report) gaps mixed into the not-queried list - see Judgment needed"
    )
    text = odd_render.render(facts, full=True, today="2026-08-11")
    assert "No gap recorded" not in text
    judgment = text.split("## Judgment needed")[1]
    assert (
        "section 5 of 2026-08-10-1000-a.md mixes a not-queried list with its gaps"
        in judgment
    )


def test_a_not_queried_list_of_none_keeps_the_item(repo, odd_status, odd_render):
    body = DEFAULT_BODY.replace(
        "- **Logs: absent for checkout** - no log stream carries the service.",
        "**Not queried (quick): none** (logs for C4 only). Baseline gaps, ruled:\n"
        "`traces_spanmetrics_*` still carry no instance id — **still missing**.",
    )
    text = observation(run_name="a", body=body).replace("depth: full", "depth: quick")
    repo.write(".odd/observe-run-reports/2026-08-10-1000-a.md", text)
    repo.commit("docs(odd): report")
    facts = odd_status.build_facts(repo.root, recent=None)
    [row] = odd_render.gap_rows(facts)
    assert "still carry no instance id" in row["gap"]
    assert odd_render.mixed_not_queried(facts) == []


def test_gaps_recorded_as_a_table_are_read(repo, odd_status, odd_render):
    body = DEFAULT_BODY.replace(
        "- **Logs: absent for checkout** - no log stream carries the service.",
        "| Gap | Evidence | State |\n|---|---|---|\n"
        "| No profiles for checkout | no series | still missing |\n"
        "| Logs absent | no stream | filled |",
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body=body),
    )
    repo.commit("docs(odd): report")
    rows = odd_render.gap_rows(odd_status.build_facts(repo.root, recent=None))
    assert [r["gap"] for r in rows] == [
        "No profiles for checkout (still missing)",
        "Logs absent (filled)",
    ]


def test_two_verdict_words_are_deferred_as_two_verdicts(repo, odd_status, odd_render):
    body = VERIFY_BODY.replace(
        "**Verdict: 2/2 checks PASS** on unchanged criteria.",
        "**Verdict: FAIL** — 9 of 10 checks PASS.",
    )
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev),
    )
    write_verify(repo, "2026-08-12-1000-verify-a.md", "2026-08-10-1000-a.md", body)
    repo.commit("docs(odd): reports")
    judgment = odd_render.render(
        odd_status.build_facts(repo.root, recent=None), today="2026-08-13"
    ).split("## Judgment needed")[1]
    assert (
        "2026-08-12-1000-verify-a.md states two verdicts (PASS and FAIL both appear)"
        in judgment
    )


def test_a_verdict_paragraph_stating_both_words_is_deferred(odd_render):
    both = report_with(["**Verdict: FAIL** — 9 of 10 checks PASS"], [])
    assert (
        odd_render.verdict_label(both)
        == "no verdict stated (PASS and FAIL both appear)"
    )


def test_the_chain_cell_keeps_the_long_boundary_evidence_out(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    text = rendered(repo, odd_status, odd_render, today="2026-08-13")
    state = text.split("## Per-service loop state")[1].split("## Findings")[0]
    assert "change since: uncertain -> verified 2026-08-12 (PASS)" in state
    assert "src (src/app.py)" not in state


def test_rulings_on_plan_items_are_never_out_of_chain_findings(
    repo, odd_status, odd_render
):
    # a verification of a plan rules its items "1", "2": not the "1", "2" findings of a report
    repo.write(
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app-python.md",
        INSTRUMENTATION_TEXT,
    )
    numbered = DEFAULT_BODY.replace("| F1 |", "| 1 |").replace("| F2 |", "| 2 |")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", body=numbered),
    )
    plan_check = VERIFY_BODY.replace(
        "| F1 | N+1 on cart lines | FIXED | 1 span per call |\n| F2 | Cold start | still present | 390 ms |",
        "| 1 | traces exported | closed | one span per request |\n| 2 | metrics exported | closed | 4 series |",
    )
    write_verify(
        repo,
        "2026-08-12-1000-verify-app-python.md",
        ".odd/otel-instrumentation-reports/2026-08-09-1000-app-python.md",
        plan_check,
    )
    repo.commit("docs(odd): plan, report, plan verification")
    facts = odd_status.build_facts(repo.root, recent=None)
    assert odd_render.out_of_chain_rulings(facts) == []
    rows = own_rows(odd_render, facts)
    assert (
        rows["1"]["state"] == "open" and rows["1"]["ruled_by"] == "no verification yet"
    )


def test_a_runtime_entry_differing_only_in_packaging_files_is_deferred(
    repo, odd_status, odd_render
):
    repo.write("src/pyproject.toml", 'version = "1.0.0"\n')
    repo.write("src/uv.lock", "v1\n")
    repo.commit("chore: packaging", date="2026-08-02T10:00:00Z")
    baseline_and_verification(repo)
    repo.write("src/pyproject.toml", 'version = "1.0.1"\n')
    repo.write("src/uv.lock", "v2\n")
    repo.commit("chore(release): 1.0.1", date="2026-08-14T12:00:00Z")
    facts = odd_status.build_facts(repo.root, recent=None, runtime=["src"])
    [rec] = odd_render.recommendations(facts, today="2026-08-15")
    assert rec["action"] == "judgment needed"
    assert "only in packaging files" in rec["evidence"]
    assert "src/pyproject.toml" in rec["evidence"]
    # a source file among them keeps the rule's verdict
    repo.write("src/app.py", "print('changed')\n")
    repo.commit("fix: code", date="2026-08-15T12:00:00Z")
    [rec] = odd_render.recommendations(
        odd_status.build_facts(repo.root, recent=None, runtime=["src"]),
        today="2026-08-16",
    )
    assert rec["action"] == "verification due"


# --- the memory invariant section (issue #307) --------------------------------


def test_memory_invariant_section_says_clean_when_the_store_conforms(
    repo, odd_status, odd_render
):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.commit("docs(odd): report")
    text = rendered(repo, odd_status, odd_render)
    assert "## Memory invariant" in text
    section = text.split("## Memory invariant")[1].split("## ")[0]
    assert "1 of 1" in section
    assert "every stored report carries the contract's frontmatter" in section


def test_memory_invariant_section_lists_violations_and_skipped_ledger_rows(
    repo, odd_status, odd_render
):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a").replace("mode: drive", "mode: drove"),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-b.md",
        observation(run_name="b", date="2026-08-11").replace("depth: full\n", ""),
    )
    repo.write(
        ".odd/decisions.md",
        LEDGER_HEAD
        + "| 2026-08-13 | 2026-08-10-1000-a.md / F9 | wontfix | no such finding |\n",
    )
    repo.commit("docs(odd): report and decision")
    text = rendered(repo, odd_status, odd_render)
    section = text.split("## Memory invariant")[1].split("## ")[0]
    assert "1 of 2" in section
    assert (
        "1 predate the `depth` field and read as full (2026-08-11-1000-b.md)" in section
    )
    assert "2026-08-10-1000-a.md" in section and "mode 'drove'" in section
    assert "2026-08-11-1000-b.md | depth absent" not in section
    assert "line 7" in section and "carries no finding F9" in section
    assert "append-only" in section


def test_memory_invariant_note_caps_the_legacy_names(repo, odd_status, odd_render):
    for day in range(10, 15):
        repo.write(
            f".odd/observe-run-reports/2026-08-{day}-1000-r{day}.md",
            observation(run_name=f"r{day}", date=f"2026-08-{day}").replace(
                "depth: full\n", ""
            ),
        )
    repo.commit("docs(odd): reports")
    text = rendered(repo, odd_status, odd_render)
    section = text.split("## Memory invariant")[1].split("## ")[0]
    assert "5 predate the `depth` field" in section
    assert "2026-08-12-1000-r12.md, +2 more)" in section
    assert "r13.md" not in section


# --- the one-screen rendering --------------------------------------------------


def test_the_default_rendering_is_one_screen(repo, odd_status, odd_render):
    baseline_and_verification(repo)
    text = screen(repo, odd_status, odd_render, today="2026-08-13")
    assert text.startswith("# ODD loop status")
    # one line of inventory, one of invariant - no sections for them
    assert "## Inventory" not in text and "## Memory invariant" not in text
    assert "1 matched of 2 stored" not in text  # counts read from the reports
    assert "2 matched of 2 stored (2 observation, 0 instrumentation)" in text
    assert "memory invariant: clean" in text
    # the burn-down per lineage carries the action and its evidence
    assert "## Loop state" in text
    assert (
        "| checkout / local / local | 2026-08-12 verify-a (verify) "
        "| 2 | 1 | 0 | 0 | 0 | loop can rest |"
    ) in text
    # the evidence sits under the table, one line per lineage, so the table stays narrow
    assert (
        "- checkout / local / local: last report 2026-08-12-1000-verify-a.md "
        "(verify); verdict PASS; tree anchor equals HEAD"
    ) in text.split("## Loop state")[1].split("Not on this screen")[0]
    # the working tables stay behind --full, and the screen says what it dropped
    for heading in (
        "## Per-service loop state",
        "## Findings ledger",
        "## Trends",
        "## Open telemetry gaps",
        "## Next recommended action",
    ):
        assert heading not in text, heading
    assert "| POST /checkout |" not in text
    assert "3 findings, 1 trend pair, 1 gap" in text and "--full" in text
    assert "- nothing deferred" in text.split("## Judgment needed")[1]


def test_the_full_rendering_keeps_every_section_and_whole_titles(
    repo, odd_status, odd_render
):
    long_title = "N+1 on cart lines, " + "one extra round trip per line " * 4
    rev = repo.git("rev-parse", "--short", "HEAD")
    body = DEFAULT_BODY.replace("N+1 on cart lines", long_title.rstrip())
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev, body=body),
    )
    repo.commit("docs(odd): report")
    full = rendered(repo, odd_status, odd_render)
    assert "## Loop state" in full and "## Findings ledger" in full
    ledger = full.split("## Findings ledger")[1].split("## Trends")[0]
    assert long_title.rstrip() in ledger  # the exact key and the whole title, no cut
    assert "…" not in ledger


def test_a_named_scope_or_full_renders_the_working_tables_from_the_cli(repo):
    baseline_and_verification(repo)
    base = [sys.executable, str(SCRIPT), "--render", "--today", "2026-08-13"]
    for extra in (["--full"], ["--service", "checkout"], ["--stack", "local"]):
        proc = subprocess.run(
            [*base, *extra],
            cwd=repo.root,
            capture_output=True,
            text=True,
            env={**os.environ, **GIT_ENV},
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        assert "## Findings ledger" in proc.stdout, extra
        assert "## Loop state" in proc.stdout, extra


def test_a_caller_ruling_is_applied_before_the_rendering(repo, odd_status, odd_render):
    body = VERIFY_BODY.replace(
        "| F1 | N+1 on cart lines | FIXED |",
        "| F1 | N+1 on cart lines | mostly, see below |",
    )
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev),
    )
    write_verify(repo, "2026-08-12-1000-verify-a.md", "2026-08-10-1000-a.md", body)
    repo.commit("docs(odd): reports")
    facts = odd_status.build_facts(repo.root, recent=None)
    before = odd_render.render(facts, today="2026-08-20")
    assert (
        "| 2 | 0 | 0 | 0 | 1 |" in before
    )  # open, fixed, regressed, declined, unknown
    assert "mostly, see below" in before.split("## Judgment needed")[1]

    ruled = ["2026-08-10-1000-a.md/F1=fixed"]
    after = odd_render.render(facts, today="2026-08-20", ruled=ruled)
    assert "| 2 | 1 | 0 | 0 | 0 |" in after
    assert "mostly, see below" not in after.split("## Judgment needed")[1]
    full = odd_render.render(facts, today="2026-08-20", full=True, ruled=ruled)
    assert (
        "| 2026-08-10-1000-a.md / F1 | N+1 on cart lines | high | fixed-and-verified "
        "| ruled by the caller (2026-08-12-1000-verify-a.md: mostly, see below) |"
    ) in full
    # the same key with spaces around the slash, and the long state name, both read
    assert "| 2 | 1 | 0 | 0 | 0 |" in odd_render.render(
        facts,
        today="2026-08-20",
        ruled=["2026-08-10-1000-a.md / F1=fixed-and-verified"],
    )


def test_a_ruling_on_an_unknown_key_or_a_declined_finding_is_deferred(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    repo.write(
        ".odd/decisions.md",
        LEDGER_HEAD
        + "| 2026-08-13 | 2026-08-10-1000-a.md / F2 | wontfix | Cold start is rare |\n",
    )
    repo.commit("docs(odd): decision")
    facts = odd_status.build_facts(repo.root, recent=None)
    text = odd_render.render(
        facts,
        today="2026-08-13",
        ruled=[
            "2026-08-10-1000-a.md/F9=fixed",
            "2026-08-10-1000-a.md/F2=open",
            "2026-08-10-1000-a.md/F1=maybe",
            "no-equals-sign",
        ],
    )
    judgment = text.split("## Judgment needed")[1]
    assert "ruling 2026-08-10-1000-a.md / F9: no such finding" in judgment
    assert (
        "ruling 2026-08-10-1000-a.md / F2: declined by the ledger (wontfix 2026-08-13)"
        in judgment
    )
    assert "ruling 2026-08-10-1000-a.md / F1: unknown state 'maybe'" in judgment
    assert "ruling no-equals-sign: not <report>/<id>=<state>" in judgment
    # the ledger's row stands: F2 stays declined, F1 stays as the verification ruled
    assert "| 1 | 1 | 0 | 1 | 0 |" in text


def test_the_screen_caps_evidence_and_judgment_items(repo, odd_status, odd_render):
    baseline_and_verification(repo)
    for n in range(16):
        repo.write(f"top-level-directory-{n:02d}/file.py", "print('x')\n")
    repo.commit("feat: many entries", date="2026-08-14T12:00:00Z")
    facts = odd_status.build_facts(repo.root, recent=None)
    text = odd_render.render(facts, today="2026-08-15")
    assert "| judgment needed |" in text
    prefix = "- checkout / local / local: "
    line = next(
        line
        for line in text.split("## Loop state")[1].splitlines()
        if line.startswith(prefix)
    )
    evidence = line[len(prefix) :]
    assert evidence.endswith("…")
    assert len(evidence) <= odd_render.MAX_SCREEN_EVIDENCE + 1
    assert "whole items and evidence" in text and "--full" in text
    # the lineage's item points at the row instead of repeating the evidence
    judgment = text.split("## Judgment needed")[1]
    assert (
        "checkout / local / local: judgment needed - see its evidence under Loop state"
        in judgment
    )
    assert "boundary uncertain" not in judgment
    full = odd_render.render(facts, today="2026-08-15", full=True)
    assert "top-level-directory-15" in full.split("## Judgment needed")[1]
    assert "see its evidence under" not in full


def test_the_screen_lists_the_invariant_violations_only(repo, odd_status, odd_render):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a").replace("mode: drive", "mode: drove"),
    )
    repo.write(
        ".odd/decisions.md",
        LEDGER_HEAD
        + "| 2026-08-13 | 2026-08-10-1000-a.md / F9 | wontfix | no such finding |\n",
    )
    repo.commit("docs(odd): report and decision")
    text = screen(repo, odd_status, odd_render)
    line = next(l for l in text.splitlines() if "memory invariant" in l)
    assert "1 violation" in line and "mode 'drove'" in line
    assert "1 ledger row skipped" in line and "carries no finding F9" in line
    assert "append-only" not in text


def test_a_ruling_settles_the_out_of_chain_item_it_names(repo, odd_status, odd_render):
    # a second verification of the same lineage rules F1 of a report outside
    # its chain: the rules defer; the caller's ruling on that finding settles it
    baseline_and_verification(repo)
    # b defines F3 only; its verification rules F1, which only a defines
    body_b = DEFAULT_BODY.replace("| F1 | N+1 on cart lines", "| F3 | Lock contention")
    body_b = body_b.replace(
        "| F2 | Cold start | low | suspected | first call 400 ms | none |\n", ""
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-13-1000-b.md",
        observation(run_name="b", date="2026-08-13", body=body_b),
    )
    write_verify(
        repo, "2026-08-14-1000-verify-b.md", "2026-08-13-1000-b.md", VERIFY_BODY
    )
    repo.commit("docs(odd): reports")
    facts = odd_status.build_facts(repo.root, recent=None)
    before = odd_render.render(facts, today="2026-08-15", full=True)
    f1_item = "2026-08-14-1000-verify-b.md rules F1"
    f2_item = "2026-08-14-1000-verify-b.md rules F2"
    judgment = before.split("## Judgment needed")[1]
    assert f1_item in judgment and f2_item in judgment
    after = odd_render.render(
        facts, today="2026-08-15", full=True, ruled=["2026-08-10-1000-a.md/F1=fixed"]
    )
    judgment = after.split("## Judgment needed")[1]
    assert f1_item not in judgment  # settled: every finding it names is ruled
    assert f2_item in judgment  # untouched


def test_the_burn_down_is_attributed_per_lineage(repo, odd_status, odd_render):
    baseline_and_verification(repo)  # checkout: F1 fixed, F2 open, V1 open
    repo.write(
        ".odd/observe-run-reports/2026-08-13-1000-p.md",
        observation(
            services="[payment]", run_name="p", date="2026-08-13", body=DEFAULT_BODY
        ),
    )
    repo.commit("docs(odd): payment report")
    text = odd_render.render(
        odd_status.build_facts(repo.root, recent=None), today="2026-08-14", full=True
    )
    loop = text.split("## Loop state")[1].split("## Per-service loop state")[0]
    checkout = next(l for l in loop.splitlines() if l.startswith("| checkout /"))
    payment = next(l for l in loop.splitlines() if l.startswith("| payment /"))
    assert "| 2 | 1 | 0 | 0 | 0 |" in checkout
    assert "| 2 | 0 | 0 | 0 | 0 |" in payment
    assert (
        "Burn-down: open 4 · fixed-and-verified 1 · regressed 0 · declined 0." in text
    )


def test_the_screen_caps_the_judgment_items_in_length_and_in_count(
    repo, odd_status, odd_render
):
    # twelve findings, each ruled in words the rules cannot read, at length
    findings = "".join(
        f"| F{n} | Finding {n} | low | suspected | evidence | none |\n"
        for n in range(1, 13)
    )
    body = DEFAULT_BODY.replace(
        "| F1 | N+1 on cart lines | high | confirmed | 30 spans per call | p95 -60 ms |\n"
        "| F2 | Cold start | low | suspected | first call 400 ms | none |\n",
        findings,
    )
    rulings = "".join(
        f"| F{n} | Finding {n} | mostly, see the long note {'x' * 200} | - |\n"
        for n in range(1, 13)
    )
    verify_body = VERIFY_BODY.replace(
        "| F1 | N+1 on cart lines | FIXED | 1 span per call |\n"
        "| F2 | Cold start | still present | 390 ms |\n",
        rulings,
    )
    rev = repo.git("rev-parse", "--short", "HEAD")
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(run_name="a", revision=rev, body=body),
    )
    write_verify(
        repo, "2026-08-12-1000-verify-a.md", "2026-08-10-1000-a.md", verify_body
    )
    repo.commit("docs(odd): reports")
    text = screen(repo, odd_status, odd_render, today="2026-08-13")
    items = [
        line
        for line in text.split("## Judgment needed")[1].splitlines()
        if line.startswith("- ")
    ]
    assert len(items) == odd_render.MAX_SCREEN_ITEMS + 1
    assert items[-1] == f"- +{12 - odd_render.MAX_SCREEN_ITEMS} more - `--full`"
    for item in items[:-1]:
        assert item.endswith("…") and len(item) <= odd_render.MAX_SCREEN_ITEM + 3
    full = rendered(repo, odd_status, odd_render, today="2026-08-13")
    full_items = [
        line
        for line in full.split("## Judgment needed")[1].splitlines()
        if line.startswith("- ")
    ]
    assert len(full_items) == 12 and "more - `--full`" not in full
    assert not any(i.endswith("…") for i in full_items)


def test_a_ruling_with_nothing_to_rule_is_said(repo, odd_status, odd_render):
    facts = odd_status.build_facts(repo.root, recent=None)
    text = odd_render.render(facts, ruled=["x/F1=fixed"])
    assert "has not started" in text and "1 ruling not applied" in text
    assert "ruling" not in odd_render.render(facts)


def test_a_ruling_key_may_carry_the_report_path(repo, odd_status, odd_render):
    assert odd_render.parse_ruling(".odd/observe-run-reports/a.md/F1=fixed") == (
        "a.md / F1",
        "fixed-and-verified",
    )


# --- the entry-classification ledger ------------------------------------------------


CLASSIFICATIONS_HEAD = (
    "# ODD entry classifications\n\nRows are appended, never rewritten.\n\n"
    "| Date | Entry | Class | Rationale |\n|---|---|---|---|\n"
)


def test_an_entry_the_ledger_classifies_is_not_deferred(repo, odd_status, odd_render):
    baseline_and_verification(repo)
    repo.write("src/app.py", "print('changed again')\n")
    repo.commit("fix: another change", date="2026-08-14T12:00:00Z")
    deferred = odd_status.build_facts(repo.root, recent=None)
    assert odd_render.recommendations(deferred, today="2026-08-15")[0]["action"] == (
        "judgment needed"
    )
    repo.write(
        ".odd/entry-classifications.md",
        CLASSIFICATIONS_HEAD + "| 2026-08-15 | src | runtime | the service |\n",
    )
    repo.commit(
        "docs(odd): entry classification src runtime", date="2026-08-15T12:00:00Z"
    )
    facts = odd_status.build_facts(repo.root, recent=None)
    [rec] = odd_render.recommendations(facts, today="2026-08-15")
    assert rec["action"] == "verification due"
    text = odd_render.render(facts, today="2026-08-15")
    assert "- nothing deferred" in text.split("## Judgment needed")[1]
    assert "classifications: 1 row(s)" in text
    full = odd_render.render(facts, today="2026-08-15", full=True)
    assert "- Entry classifications: present, 1 row(s) read, 0 skipped" in full
    assert "- Classifications: 0 row(s) skipped - every ruling names" in full


def test_a_non_runtime_ruling_lets_the_loop_rest(repo, odd_status, odd_render):
    baseline_and_verification(repo)
    repo.write("src/app.py", "print('changed again')\n")
    repo.write(
        ".odd/entry-classifications.md",
        CLASSIFICATIONS_HEAD
        + "| 2026-08-14 | src | non-runtime | a vendored mirror |\n",
    )
    repo.commit("feat: change and classify", date="2026-08-14T12:00:00Z")
    facts = odd_status.build_facts(repo.root, recent=None)
    [rec] = odd_render.recommendations(facts, today="2026-08-15")
    assert rec["action"] == "loop can rest"
    assert (
        "only non-runtime entries moved since the tree anchor: src" in rec["evidence"]
    )


def test_a_skipped_classification_row_is_reported_never_fatal(
    repo, odd_status, odd_render
):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md", observation(run_name="a")
    )
    repo.write(
        ".odd/entry-classifications.md",
        CLASSIFICATIONS_HEAD + "| 2026-08-13 | nope | runtime | no such entry |\n",
    )
    repo.commit("docs(odd): report and a bad classification")
    text = screen(repo, odd_status, odd_render)
    line = next(l for l in text.splitlines() if "memory invariant" in l)
    assert "1 ledger row skipped" in line
    assert (
        "entry-classifications.md line 7 - no top-level entry named nope at HEAD"
        in line
    )
    assert "classifications: 0 row(s), 1 skipped" in text
    assert (
        "classification line 7 skipped: no top-level entry named nope at HEAD"
        in text.split("## Judgment needed")[1]
    )
    full = rendered(repo, odd_status, odd_render)
    section = full.split("## Memory invariant")[1].split("## ")[0]
    assert "- Classifications: 1 row(s) skipped" in section
    assert (
        "| entry-classifications.md line 7 | no top-level entry named nope at HEAD |"
        in section
    )
    assert "- Entry classifications: absent (no entry classified yet)" not in full


def test_an_absent_classification_ledger_is_a_fact_in_both_renderings(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    text = screen(repo, odd_status, odd_render, today="2026-08-13")
    assert "· classifications: absent ·" in text
    full = rendered(repo, odd_status, odd_render, today="2026-08-13")
    assert "- Entry classifications: absent (no entry classified yet)" in full
    assert "- Classifications: 0 row(s) skipped (no entry classified yet)" in full


def test_a_ruling_never_settles_an_entry_present_on_one_side_only(
    repo, odd_status, odd_render
):
    baseline_and_verification(repo)
    repo.write("vendor/lib.py", "print('new')\n")
    repo.write(
        ".odd/entry-classifications.md",
        CLASSIFICATIONS_HEAD + "| 2026-08-14 | vendor | non-runtime | a mirror |\n",
    )
    repo.commit("feat: add vendor and classify it", date="2026-08-14T12:00:00Z")
    facts = odd_status.build_facts(repo.root, recent=None)
    [rec] = odd_render.recommendations(facts, today="2026-08-15")
    assert rec["action"] == "judgment needed"
    assert "only at HEAD: vendor" in rec["evidence"]


# --- the repository field ------------------------------------------------------------


def test_the_inventory_names_the_repositories_the_reports_carry(
    repo, odd_status, odd_render
):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(
            run_name="a",
            extra_frontmatter="repository: github.com/example-org/checkout",
        ),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-b.md",
        observation(
            services="[checkout, payment]",
            run_name="b",
            date="2026-08-11",
            extra_frontmatter=(
                "repository: {checkout: github.com/example-org/checkout, "
                "payment: gitlab.com/example-group/payment}"
            ),
        ),
    )
    repo.commit("docs(odd): reports")
    text = screen(repo, odd_status, odd_render)
    assert (
        "· repositories: github.com/example-org/checkout, gitlab.com/example-group/payment ·"
        in text
    )
    full = rendered(repo, odd_status, odd_render)
    assert (
        "; repositories: github.com/example-org/checkout, gitlab.com/example-group/payment"
        in full.split("## Inventory")[1].split("## ")[0]
    )


def test_the_repositories_come_from_the_whole_store_even_under_a_scope(
    repo, odd_status, odd_render
):
    repo.write(
        ".odd/observe-run-reports/2026-08-10-1000-a.md",
        observation(
            run_name="a",
            extra_frontmatter="repository: github.com/example-org/checkout",
        ),
    )
    repo.write(
        ".odd/observe-run-reports/2026-08-11-1000-p.md",
        observation(
            services="[payment]",
            run_name="p",
            date="2026-08-11",
            extra_frontmatter="repository: {payment: gitlab.com/example-group/payment, cart: }",
        ),
    )
    (repo.root / ".odd/observe-run-reports/2026-08-12-1000-bad.md").write_bytes(
        b"---\n\xff\xfe\n---\n"
    )
    repo.commit("docs(odd): reports")
    facts = odd_status.build_facts(repo.root, recent=None, services=["payment"])
    # the inventory is the whole readable store, an empty map value dropped
    assert facts["inventory"]["repositories"] == [
        "github.com/example-org/checkout",
        "gitlab.com/example-group/payment",
    ]
    text = odd_render.render(facts, today="2026-08-13")
    assert (
        "repositories: github.com/example-org/checkout, gitlab.com/example-group/payment"
        in text
    )
    nothing = odd_status.build_facts(repo.root, recent=None, services=["orders"])
    assert "repositories: github.com/example-org/checkout" in odd_render.render(nothing)


def test_reports_without_a_repository_render_as_before(repo, odd_status, odd_render):
    baseline_and_verification(repo)
    assert "repositories:" not in screen(
        repo, odd_status, odd_render, today="2026-08-13"
    )
    assert "repositories:" not in rendered(
        repo, odd_status, odd_render, today="2026-08-13"
    )
