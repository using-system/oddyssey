"""End-to-end check against the live otel-lgtm stack.

Prerequisites (see README):
1. docker compose -f docker-compose/docker-compose.yml up -d
2. seed + run the instrumented demo app
3. run the load scenario within the last 15 minutes

Run with: uv run pytest tests/ -m integration -o addopts=""
"""

import time

import pytest

from oddyssey_summarize.report import summarize

pytestmark = pytest.mark.integration


def test_summarize_against_live_stack():
    end = int(time.time())
    start = end - 900

    report = summarize("n-plus-one", start, end)

    assert report["odd_version"] == "1"
    assert report["metrics"]["http.server.request.count"] >= 200
    assert report["metrics"]["http.server.request.duration.p95"]["value"] > 0
    assert report["metrics"]["db.client.operation.count"] > 0
    assert report["top_spans"], "expected at least one aggregated span"
