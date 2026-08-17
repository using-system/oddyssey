import json
from pathlib import Path

import pytest

from oddyssey.summarize.app.errors import EmptyWindowError
from oddyssey.summarize.app.report import summarize

FIXTURES = Path(__file__).parent / "fixtures"


class FakeTempo:
    """Returns the DB fixture for DB queries, the full fixture otherwise."""

    def search(self, query, start, end, limit=500, spans_per_spanset=100):
        name = "tempo_search_db.json" if "db." in query else "tempo_search_all.json"
        return json.loads((FIXTURES / name).read_text())


class FakePrometheus:
    """Maps PromQL substrings to instant-query result vectors."""

    def __init__(self, p95=0.34, requests=200.0, errors=0.0):
        self._answers = [
            ("histogram_quantile", p95),
            ("5..", errors),          # error-count query filters on 5xx codes
            ("_count", requests),
        ]

    def query(self, promql, time):
        for needle, value in self._answers:
            if needle in promql:
                return [{"metric": {}, "value": [time, str(value)]}]
        return []


def test_summarize_builds_compact_report():
    report = summarize("n-plus-one", 100, 400, tempo=FakeTempo(), prometheus=FakePrometheus())

    assert report["odd_version"] == "1"
    assert report["service"] == "n-plus-one"
    assert report["window"] == {"start": 100, "end": 400}
    assert report["metrics"]["http.server.request.duration.p95"] == {"value": 0.34, "unit": "s"}
    assert report["metrics"]["http.server.request.count"] == 200
    assert report["metrics"]["http.server.error.count"] == 0
    assert report["metrics"]["db.client.operation.count"] == 4


def test_top_spans_grouped_by_name_sorted_by_total_duration():
    report = summarize("n-plus-one", 100, 400, tempo=FakeTempo(), prometheus=FakePrometheus())

    assert report["top_spans"][0] == {"name": "GET /users", "count": 2, "total_duration_ms": 660.0}
    assert report["top_spans"][1] == {"name": "SELECT posts", "count": 3, "total_duration_ms": 4.0}
    assert report["top_spans"][2] == {"name": "SELECT users", "count": 1, "total_duration_ms": 2.0}


def test_empty_window_raises():
    with pytest.raises(EmptyWindowError, match="no HTTP requests recorded"):
        summarize("n-plus-one", 100, 400, tempo=FakeTempo(), prometheus=FakePrometheus(requests=0.0))
