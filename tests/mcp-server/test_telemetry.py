import subprocess
import sys

import pytest
from oddyssey_mcp import telemetry
from opentelemetry.sdk.metrics import MeterProvider as SdkMeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind


@pytest.fixture()
def clean_otel_env(monkeypatch):
    for var in (
        "OTEL_SDK_DISABLED",
        "OTEL_SERVICE_NAME",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_SEMCONV_STABILITY_OPT_IN",
    ):
        monkeypatch.delenv(var, raising=False)


def test_disabled_is_a_no_op(clean_otel_env, monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    shutdown = telemetry.setup_telemetry()
    shutdown()  # callable, does nothing, raises nothing
    # The disabled path must not install defaults into the environment.
    import os

    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in os.environ


def test_force_flush_without_setup_is_safe():
    telemetry.force_flush()  # no provider installed: must not raise


def test_enabled_setup_writes_nothing_to_stdout():
    # Full real bootstrap + shutdown in a subprocess (global providers are
    # set-once per process; a subprocess keeps this test hermetic). The
    # stack is down, so exports fail: that is the NORMAL state and must
    # stay silent on stdout.
    code = (
        "from oddyssey_mcp import telemetry; "
        "shutdown = telemetry.setup_telemetry(); "
        "shutdown()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_bootstrap_failure_degrades_to_no_telemetry(clean_otel_env, monkeypatch):
    # Anything blowing up in the enabled path (missing package metadata, an
    # OTEL_* value an exporter rejects, ...) must cost telemetry, never the
    # server. The patch point is called BEFORE any global provider is set,
    # so no half-installed provider leaks into the rest of the session.
    def boom(*args, **kwargs):
        raise RuntimeError("no package metadata")

    monkeypatch.setattr(telemetry.importlib_metadata, "version", boom)

    shutdown = telemetry.setup_telemetry()

    assert callable(shutdown)
    shutdown()  # must not raise either


@pytest.fixture()
def span_capture(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = SdkTracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer("test"))
    return exporter


def test_traced_tool_emits_server_span_and_passes_through(span_capture):
    @telemetry.traced_tool
    def odd_dummy() -> dict:
        """Dummy tool."""
        return {"ok": True}

    assert odd_dummy.__name__ == "odd_dummy"
    assert odd_dummy.__doc__ == "Dummy tool."
    assert odd_dummy() == {"ok": True}

    (span,) = span_capture.get_finished_spans()
    assert span.name == "tools/call odd_dummy"
    assert span.kind == SpanKind.SERVER
    assert span.attributes["mcp.method.name"] == "tools/call"
    assert span.attributes["gen_ai.tool.name"] == "odd_dummy"
    assert span.attributes["network.transport"] == "pipe"
    assert span.attributes["jsonrpc.protocol.version"] == "2.0"


def test_traced_tool_records_exception_and_reraises(span_capture):
    @telemetry.traced_tool
    def odd_broken() -> dict:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        odd_broken()

    (span,) = span_capture.get_finished_spans()
    assert not span.status.is_ok
    assert span.events[0].name == "exception"


@pytest.fixture()
def metric_capture(monkeypatch):
    reader = InMemoryMetricReader()
    provider = SdkMeterProvider(metric_readers=[reader])
    histogram = provider.get_meter("test").create_histogram(
        "mcp.server.operation.duration",
        unit="s",
        description="Duration of MCP server tool operations",
    )
    monkeypatch.setattr(telemetry, "_duration_histogram", histogram)
    return reader


def test_traced_tool_records_duration_histogram(span_capture, metric_capture):
    @telemetry.traced_tool
    def odd_measured() -> dict:
        return {"ok": True}

    odd_measured()

    points = [
        point
        for resource_metric in metric_capture.get_metrics_data().resource_metrics
        for scope_metric in resource_metric.scope_metrics
        for metric in scope_metric.metrics
        if metric.name == "mcp.server.operation.duration"
        for point in metric.data.data_points
    ]

    assert len(points) == 1
    (point,) = points
    assert point.attributes["mcp.method.name"] == "tools/call"
    assert point.attributes["gen_ai.tool.name"] == "odd_measured"
    assert point.count == 1


def test_docker_span_names_and_attributes(span_capture):
    with telemetry.docker_span("inspect", container="oddyssey-lgtm") as span:
        span.set_attribute("oddyssey.docker.exit_code", 0)

    (finished,) = span_capture.get_finished_spans()
    assert finished.name == "oddyssey.docker.inspect"
    assert finished.attributes["oddyssey.docker.container"] == "oddyssey-lgtm"
    assert finished.attributes["oddyssey.docker.exit_code"] == 0
