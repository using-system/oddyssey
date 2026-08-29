import os
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


def test_docker_span_of_an_image_operation_carries_the_image(span_capture):
    # Observation finding F2: an operation whose subject is the image must
    # be named for the operation and carry the image reference - a
    # container attribute on an image inspect is simply wrong. Deliberate
    # amendment of the 2026-08-22 frozen naming (issue #149).
    with telemetry.docker_span("image-inspect", image="sha256:cafe") as span:
        span.set_attribute("oddyssey.docker.exit_code", 0)

    (finished,) = span_capture.get_finished_spans()
    assert finished.name == "oddyssey.docker.image-inspect"
    assert finished.attributes["oddyssey.docker.image"] == "sha256:cafe"
    assert "oddyssey.docker.container" not in finished.attributes
    assert finished.attributes["oddyssey.docker.exit_code"] == 0


@pytest.fixture()
def probe_failure_capture(monkeypatch):
    reader = InMemoryMetricReader()
    provider = SdkMeterProvider(metric_readers=[reader])
    counter = provider.get_meter("test").create_counter(
        "oddyssey.stack.probe.failures",
        unit="{failure}",
        description="Stack probes that got no HTTP response",
    )
    monkeypatch.setattr(telemetry, "_probe_failure_counter", counter)
    return reader


def _counter_points(reader, name: str) -> dict:
    return {
        point.attributes.get("error.type"): point.value
        for resource_metric in reader.get_metrics_data().resource_metrics
        for scope_metric in resource_metric.scope_metrics
        for metric in scope_metric.metrics
        if metric.name == name
        for point in metric.data.data_points
    }


def test_record_probe_failure_counts_one_series_per_error_type(probe_failure_capture):
    # Observation finding A5: a probe that gets NO response produces no
    # http.client.request.duration point (the instrumentation records the
    # histogram only after re-raising), so probe error rates are
    # unanswerable in PromQL. This counter is the answer - keyed by the
    # exception class name only: bounded, never a URL or a host.
    telemetry.record_probe_failure("ConnectError")
    telemetry.record_probe_failure("ConnectError")
    telemetry.record_probe_failure("ReadError")

    assert _counter_points(probe_failure_capture, "oddyssey.stack.probe.failures") == {
        "ConnectError": 2,
        "ReadError": 1,
    }


def test_record_probe_failure_is_a_no_op_without_telemetry(monkeypatch):
    # Same contract as the duration histogram: with the SDK disabled (or a
    # failed bootstrap) the instrument is None and recording must stay a
    # silent no-op - telemetry never breaks a tool.
    monkeypatch.setattr(telemetry, "_probe_failure_counter", None)

    telemetry.record_probe_failure("ConnectError")  # must not raise


@pytest.fixture()
def dead_otlp_port(tmp_path, monkeypatch):
    """Point the bootstrap at a port nothing listens on.

    A real setup_telemetry() builds real exporters that flush on
    shutdown: the suite must never push its own telemetry into the
    machine's shared stack on the default port.
    """
    from oddyssey_mcp import config

    path = tmp_path / "config.json"
    path.write_text('{"local": {"otlp_http_port": 4418}}')
    monkeypatch.setattr(config, "CONFIG_PATH", path)


def test_setup_creates_the_probe_failure_counter(clean_otel_env, dead_otlp_port):
    # The metric name is the PromQL surface of finding A5
    # (oddyssey_stack_probe_failures_total): pin it here, since the
    # capture fixture above creates its own instrument.
    shutdown = telemetry.setup_telemetry()
    try:
        assert telemetry._probe_failure_counter is not None
        assert telemetry._probe_failure_counter.name == "oddyssey.stack.probe.failures"
    finally:
        shutdown()


def test_probe_spans_keep_their_error_status_without_a_stacktrace_event():
    # Observation finding N4: boot-poll GETs fail by design while the
    # stack starts, and each failure attached a full exception.stacktrace
    # event (~30 KB of a 65 KB creation trace). The installed httpx
    # instrumentation exposes no record_exception knob, so the lever is
    # the tracer provider it is handed: spans, error.type and the ERROR
    # status stay, only the event goes.
    exporter = InMemorySpanExporter()
    provider = SdkTracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = telemetry._NoExceptionEventTracerProvider(provider).get_tracer("test")
    with (
        pytest.raises(RuntimeError, match="connection refused"),
        tracer.start_as_current_span("GET", kind=SpanKind.CLIENT),
    ):
        raise RuntimeError("connection refused")

    (span,) = exporter.get_finished_spans()
    assert span.name == "GET"
    assert span.kind == SpanKind.CLIENT
    assert span.events == ()
    assert not span.status.is_ok


def test_httpx_instrumentation_gets_the_quiet_tracer_provider(
    clean_otel_env, dead_otlp_port, monkeypatch
):
    # The N4 mechanism only reaches the probe spans if the instrumentor
    # is actually handed the quiet provider - assert the wiring, not just
    # the class above. instrument() is stubbed: this test must not patch
    # the process's real httpx transports.
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    captured: dict = {}
    monkeypatch.setattr(
        HTTPXClientInstrumentor,
        "instrument",
        lambda self, **kwargs: captured.update(kwargs),
    )

    shutdown = telemetry.setup_telemetry()
    try:
        assert isinstance(
            captured.get("tracer_provider"),
            telemetry._NoExceptionEventTracerProvider,
        )
    finally:
        shutdown()


def test_resource_has_no_service_instance_id():
    # SDK 1.44 Resource.create() generates a service.instance.id UUID by
    # default -> one Prometheus series set per MCP session (observation
    # report finding 2, spec decision #9 says: not set). Full bootstrap in
    # a subprocess (global providers are set-once); verdict via stderr,
    # stdout must stay empty.
    code = (
        "import sys; from opentelemetry import trace; "
        "from oddyssey_mcp import telemetry; "
        "shutdown = telemetry.setup_telemetry(); "
        "attrs = trace.get_tracer_provider().resource.attributes; "
        "sys.stderr.write('instance_id_present=%s' % ('service.instance.id' in attrs)); "
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
    assert "instance_id_present=False" in result.stderr


def test_export_endpoint_follows_the_configured_otlp_port(
    clean_otel_env, tmp_path, monkeypatch
):
    # The exporter is built once at startup, so the configured OTLP port
    # must reach the environment before the SDK reads it.
    from oddyssey_mcp import config

    path = tmp_path / "config.json"
    path.write_text('{"local": {"otlp_http_port": 4418}}')
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    shutdown = telemetry.setup_telemetry()
    try:
        assert os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:4418"
    finally:
        shutdown()
