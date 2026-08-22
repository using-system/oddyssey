"""OpenTelemetry bootstrap for the oddyssey MCP server.

stdio transport: stdout is the JSON-RPC wire, so nothing here may ever
write to it - console exporters are forbidden and all diagnostics go
through Python logging (stderr by default). The export backend is the
very stack this server pilots, so failed exports are the normal state:
the ``opentelemetry`` logger tree is silenced and nothing ever raises
toward a tool result.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from importlib import metadata as importlib_metadata

from opentelemetry import metrics, trace
from opentelemetry.metrics import Histogram

_INSTRUMENTATION_NAME = "oddyssey-mcp"

# Applied with setdefault: anything the user sets in the MCP client's
# env block wins over these.
_DEFAULT_ENV = {
    "OTEL_SERVICE_NAME": "oddyssey-mcp",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_SEMCONV_STABILITY_OPT_IN": "http",
}

# Module globals read at call time by traced_tool/docker_span: the no-op
# API tracer until setup_telemetry installs the real one.
_tracer: trace.Tracer = trace.get_tracer(_INSTRUMENTATION_NAME)
_duration_histogram: Histogram | None = None
_tracer_provider = None


def setup_telemetry() -> Callable[[], None]:
    """Install the SDK (default-on) and return the shutdown callable.

    ``OTEL_SDK_DISABLED=true`` restores the exact pre-instrumentation
    behavior: nothing is installed and the returned shutdown is a no-op.
    """
    if os.environ.get("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        return lambda: None

    # Export failures (stack down) are normal: never let the exporters
    # spam the client's stderr view.
    logging.getLogger("opentelemetry").setLevel(logging.CRITICAL)

    for var, value in _DEFAULT_ENV.items():
        os.environ.setdefault(var, value)

    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    attributes = {
        "service.version": importlib_metadata.version("oddyssey-mcp"),
    }
    # Resource.create lets explicitly passed attributes win over
    # OTEL_RESOURCE_ATTRIBUTES, so only inject the default environment
    # name when the user did not state one.
    if "deployment.environment.name=" not in os.environ.get(
        "OTEL_RESOURCE_ATTRIBUTES", ""
    ):
        attributes["deployment.environment.name"] = "local"
    resource = Resource.create(attributes)

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(meter_provider)

    global _tracer, _duration_histogram, _tracer_provider
    _tracer_provider = tracer_provider
    _tracer = trace.get_tracer(_INSTRUMENTATION_NAME)
    _duration_histogram = metrics.get_meter(_INSTRUMENTATION_NAME).create_histogram(
        "mcp.server.operation.duration",
        unit="s",
        description="Duration of MCP server tool operations",
    )

    HTTPXClientInstrumentor().instrument()

    def shutdown() -> None:
        tracer_provider.shutdown()
        meter_provider.shutdown()

    return shutdown


def force_flush(timeout_ms: int = 2000) -> None:
    """Flush pending spans; failure is irrelevant (backend may be gone)."""
    provider = _tracer_provider
    if provider is None:
        return
    try:
        provider.force_flush(timeout_ms)
    except Exception:  # noqa: BLE001, S110 - flushing is strictly best-effort
        pass
