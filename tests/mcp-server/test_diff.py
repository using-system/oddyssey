import pytest

from oddyssey_mcp.diff import build_diff
from oddyssey_mcp.errors import BaselineMismatchError

P95 = "http.server.request.duration.p95"
DB = "db.client.operation.count"


def _report(p95: float, db: int) -> dict:
    return {
        "odd_version": "1",
        "service": "n-plus-one",
        "window": {"start": 1, "end": 2},
        "metrics": {
            P95: {"value": p95, "unit": "s"},
            "http.server.request.count": 200,
            "http.server.error.count": 0,
            DB: db,
        },
        "top_spans": [],
    }


def test_diff_deltas_and_pass_verdict():
    baseline, current = _report(0.0228, 10400), _report(0.0049, 400)
    budget = {P95: {"max": 0.15}, DB: {"max_increase": 0}}

    diff = build_diff(baseline, current, budget)

    assert diff["odd_version"] == "1"
    assert diff["service"] == "n-plus-one"
    assert diff["baseline"] == baseline
    assert diff["current"] == current
    assert diff["delta"][P95] == {"before": 0.0228, "after": 0.0049, "unit": "s"}
    assert diff["delta"][DB] == {"before": 10400, "after": 400}
    assert diff["verdict"] == "pass"
    assert diff["violations"] == []


def test_diff_fail_verdict_carries_violations():
    baseline, current = _report(0.0049, 400), _report(0.0228, 10400)
    budget = {DB: {"max_increase": 0}}

    diff = build_diff(baseline, current, budget)

    assert diff["verdict"] == "fail"
    assert diff["violations"] == [
        {"metric": DB, "rule": "max_increase", "limit": 0, "baseline": 400, "current": 10400}
    ]


def test_diff_without_budget():
    diff = build_diff(_report(0.02, 400), _report(0.01, 400), None)
    assert diff["verdict"] == "no_budget"
    assert diff["violations"] == []


def test_diff_rejects_baseline_from_another_service():
    baseline = _report(0.02, 400)
    baseline["service"] = "other-service"

    with pytest.raises(BaselineMismatchError, match="other-service"):
        build_diff(baseline, _report(0.01, 400), None)
