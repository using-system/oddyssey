"""OpenTelemetry bootstrap for the oddyssey MCP server.

stdio transport: stdout is the JSON-RPC wire, so nothing here may ever
write to it - console exporters are forbidden and all diagnostics go
through Python logging (stderr by default). The export backend is the
very stack this server pilots, so failed exports are the normal state:
the ``opentelemetry`` logger tree is silenced and nothing ever raises
toward a tool result.
"""

from __future__ import annotations

import functools
import logging
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from importlib import metadata as importlib_metadata

from opentelemetry import metrics, trace
from opentelemetry.metrics import Histogram
from opentelemetry.trace import SpanKind, Status, StatusCode

_INSTRUMENTATION_NAME = "oddyssey-mcp"

# Applied with setdefault: anything the user sets in the MCP client's
# env block wins over these.
_DEFAULT_ENV = {
    "OTEL_SERVICE_NAME": "oddyssey-mcp",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_SEMCONV_STABILITY_OPT_IN": "http",
}

# The metric is in seconds; the SDK's default explicit buckets are
# millisecond-shaped (5, 10, 25, ... 10000) and would collapse every
# sub-5s tool call into the first bucket.
_DURATION_BUCKETS_SECONDS = [
    0.05,
    0.1,
    0.25,
    0.5,
    1,
    2.5,
    5,
    10,
    30,
    60,
    120,
    300,
]

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

    try:
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
            explicit_bucket_boundaries_advisory=_DURATION_BUCKETS_SECONDS,
        )

        HTTPXClientInstrumentor().instrument()
    except Exception:  # noqa: BLE001 - telemetry must never take the server down
        # A broken bootstrap (missing package metadata, an OTEL_* value an
        # exporter rejects, ...) degrades to no telemetry, never no server.
        return lambda: None

    def shutdown() -> None:
        # Best-effort: a flush/shutdown error must not mask mcp.run()'s
        # own exit through main()'s finally block.
        try:
            tracer_provider.shutdown()
            meter_provider.shutdown()
        except Exception:  # noqa: BLE001, S110 - shutdown is best-effort
            pass

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


def traced_tool(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Wrap a tool handler in its MCP server span + duration metric.

    Applied UNDER ``@mcp.tool()`` with ``functools.wraps`` so the name,
    docstring, and signature reach MCP registration unchanged. The MCP
    error path is untouched: exceptions are recorded and re-raised.
    """
    tool_name = fn.__name__
    metric_attributes = {
        "mcp.method.name": "tools/call",
        "gen_ai.tool.name": tool_name,
    }

    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> dict:
        start = time.monotonic()
        with _tracer.start_as_current_span(
            f"tools/call {tool_name}",
            kind=SpanKind.SERVER,
            attributes={
                "mcp.method.name": "tools/call",
                "gen_ai.tool.name": tool_name,
                "network.transport": "pipe",
                "jsonrpc.protocol.version": "2.0",
            },
        ) as span:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            finally:
                if _duration_histogram is not None:
                    _duration_histogram.record(
                        time.monotonic() - start, metric_attributes
                    )

    return wrapper


@contextmanager
def docker_span(verb: str, container: str) -> Iterator[trace.Span]:
    """Span for one docker subprocess call - bounded attributes only.

    No semconv exists for subprocess execution; names follow the OTel
    custom-naming rules with the app prefix (spec 2026-08-22, frozen).
    """
    with _tracer.start_as_current_span(
        f"oddyssey.docker.{verb}",
        attributes={"oddyssey.docker.container": container},
    ) as span:
        yield span
