"""Aggregate Tempo and Prometheus data into the compact ODD report.

The report is the contract handed to the agent: compact enough for a
context window, versioned, and named after OpenTelemetry semantic
conventions.
"""

from __future__ import annotations

from collections import defaultdict

from oddyssey.summarize.app.errors import EmptyWindowError
from oddyssey.summarize.app.prometheus import PrometheusClient
from oddyssey.summarize.app.tempo import TempoClient

ODD_VERSION = "1"
# Backend-side names, verified against the live stack during the spike
# (docs/superpowers/spike-notes-2026-08-17.md). Output field names below
# follow OTel semantic conventions and are the stable contract.
HTTP_DURATION_METRIC = "http_server_request_duration_seconds"
STATUS_CODE_LABEL = "http_response_status_code"
DB_SPAN_QUERY = '{{resource.service.name="{service}" && span.db.system != nil}}'
# `select(name)` is required: TraceQL search omits the `name` intrinsic from
# the returned spans unless it is explicitly selected, and _top_spans groups
# by span name.
ALL_SPAN_QUERY = '{{resource.service.name="{service}"}} | select(name)'
TOP_SPANS_LIMIT = 5


def _scalar(result: list[dict]) -> float:
    """Sum the values of an instant-query result vector (0.0 when empty)."""
    return sum(float(item["value"][1]) for item in result)


def _matched_count(search_result: dict) -> int:
    return sum(
        span_set.get("matched", 0)
        for trace in search_result.get("traces", [])
        for span_set in trace.get("spanSets", [])
    )


def _top_spans(search_result: dict) -> list[dict]:
    grouped: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_duration_ms": 0.0})
    for trace in search_result.get("traces", []):
        for span_set in trace.get("spanSets", []):
            for span in span_set.get("spans", []):
                entry = grouped[span["name"]]
                entry["count"] += 1
                entry["total_duration_ms"] += int(span["durationNanos"]) / 1e6
    ranked = sorted(grouped.items(), key=lambda item: item[1]["total_duration_ms"], reverse=True)
    return [
        {"name": name, "count": data["count"], "total_duration_ms": round(data["total_duration_ms"], 1)}
        for name, data in ranked[:TOP_SPANS_LIMIT]
    ]


def summarize(
    service: str,
    start: int,
    end: int,
    tempo: TempoClient | None = None,
    prometheus: PrometheusClient | None = None,
) -> dict:
    """Summarize one run of `service` over [start, end] (unix epoch seconds)."""
    tempo = tempo or TempoClient()
    prometheus = prometheus or PrometheusClient()
    window = f"{end - start}s"

    # last_over_time (cumulative read), not increase(): a short run finishes
    # inside one metric-export interval, so the counter's first sample already
    # holds the final value and increase() evaluates to 0/NaN (see the spike
    # notes). Assumes one fresh app process per measured run.
    p95 = _scalar(
        prometheus.query(
            f"histogram_quantile(0.95, sum by (le) "
            f'(last_over_time({HTTP_DURATION_METRIC}_bucket{{job="{service}"}}[{window}])))',
            time=end,
        )
    )
    request_count = _scalar(
        prometheus.query(
            f'sum(last_over_time({HTTP_DURATION_METRIC}_count{{job="{service}"}}[{window}]))',
            time=end,
        )
    )
    error_count = _scalar(
        prometheus.query(
            f"sum(last_over_time({HTTP_DURATION_METRIC}_count"
            f'{{job="{service}", {STATUS_CODE_LABEL}=~"5.."}}[{window}]))',
            time=end,
        )
    )
    if request_count == 0:
        raise EmptyWindowError(
            f"no HTTP requests recorded for service {service!r} between {start} and {end}; "
            "did the load scenario run?"
        )

    db_result = tempo.search(DB_SPAN_QUERY.format(service=service), start, end)
    all_result = tempo.search(ALL_SPAN_QUERY.format(service=service), start, end)

    return {
        "odd_version": ODD_VERSION,
        "service": service,
        "window": {"start": start, "end": end},
        "metrics": {
            "http.server.request.duration.p95": {"value": round(p95, 4), "unit": "s"},
            "http.server.request.count": int(request_count),
            "http.server.error.count": int(error_count),
            "db.client.operation.count": _matched_count(db_result),
        },
        "top_spans": _top_spans(all_result),
    }
