import pytest

from oddyssey_mcp.budget import evaluate_budget, load_budget
from oddyssey_mcp.errors import BudgetError

P95 = "http.server.request.duration.p95"
DB = "db.client.operation.count"
ERRORS = "http.server.error.count"


def _metrics(p95: float, db: int, errors: int) -> dict:
    return {
        P95: {"value": p95, "unit": "s"},
        "http.server.request.count": 200,
        ERRORS: errors,
        DB: db,
    }


def test_no_budget_returns_no_budget_verdict():
    verdict, violations = evaluate_budget(None, _metrics(0.02, 400, 0), _metrics(0.01, 400, 0))
    assert verdict == "no_budget"
    assert violations == []


def test_all_rules_hold_returns_pass():
    budget = {P95: {"max": 0.15}, ERRORS: {"max_increase": 0}, DB: {"max_increase": 0}}
    verdict, violations = evaluate_budget(budget, _metrics(0.0228, 10400, 0), _metrics(0.0049, 400, 0))
    assert verdict == "pass"
    assert violations == []


def test_max_rule_fails_on_current_value():
    budget = {P95: {"max": 0.010}}
    verdict, violations = evaluate_budget(budget, _metrics(0.0228, 400, 0), _metrics(0.020, 400, 0))
    assert verdict == "fail"
    assert violations == [
        {"metric": P95, "rule": "max", "limit": 0.010, "baseline": 0.0228, "current": 0.020}
    ]


def test_max_increase_rule_fails_on_delta():
    budget = {DB: {"max_increase": 0}}
    verdict, violations = evaluate_budget(budget, _metrics(0.02, 400, 0), _metrics(0.02, 401, 0))
    assert verdict == "fail"
    assert violations == [
        {"metric": DB, "rule": "max_increase", "limit": 0, "baseline": 400, "current": 401}
    ]


def test_load_budget_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("ODD_DIR", str(tmp_path))
    monkeypatch.delenv("ODD_BUDGET_FILE", raising=False)
    assert load_budget() is None


def test_load_budget_reads_committed_format(tmp_path, monkeypatch):
    budget_file = tmp_path / "perf-budget.yml"
    budget_file.write_text(
        'odd_version: "1"\n'
        "service: n-plus-one\n"
        "budget:\n"
        f"  {P95}:\n"
        "    max: 0.150\n"
        f"  {ERRORS}:\n"
        "    max_increase: 0\n"
    )
    monkeypatch.setenv("ODD_BUDGET_FILE", str(budget_file))
    budget = load_budget()
    assert budget == {P95: {"max": 0.150}, ERRORS: {"max_increase": 0}}


def test_load_budget_malformed_raises(tmp_path, monkeypatch):
    budget_file = tmp_path / "perf-budget.yml"
    budget_file.write_text("budget: [not, a, mapping]\n")
    monkeypatch.setenv("ODD_BUDGET_FILE", str(budget_file))
    with pytest.raises(BudgetError, match="budget"):
        load_budget()
