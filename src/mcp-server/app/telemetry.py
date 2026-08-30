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
from contextlib import AbstractContextManager, contextmanager
from importlib import metadata as importlib_metadata

from mcp.server.mcpserver.exceptions import ToolError
from opentelemetry import metrics, trace
from opentelemetry.metrics import Counter, Histogram
from opentelemetry.trace import SpanKind, Status, StatusCode

_INSTRUMENTATION_NAME = "oddyssey-mcp"

# Applied with setdefault: anything the user sets in the MCP client's
# env block wins over these.
_DEFAULT_ENV = {
    "OTEL_SERVICE_NAME": "oddyssey-mcp",
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
_probe_failure_counter: Counter | None = None
_tracer_provider = None


class _NoExceptionEventTracer(trace.Tracer):
    """Delegating tracer whose spans never record an exception event.

    Everything else - span, kind, attributes, and the ERROR status the
    API sets on an escaping exception - is the delegate's.
    """

    def __init__(self, tracer: trace.Tracer) -> None:
        self._tracer = tracer

    def start_span(self, *args: object, **kwargs: object) -> trace.Span:
        return self._tracer.start_span(*args, **{**kwargs, "record_exception": False})

    def start_as_current_span(
        self, *args: object, **kwargs: object
    ) -> AbstractContextManager[trace.Span]:
        return self._tracer.start_as_current_span(
            *args, **{**kwargs, "record_exception": False}
        )


class _NoExceptionEventTracerProvider(trace.TracerProvider):
    """The provider handed to the httpx instrumentation, and only to it.

    Every httpx call this server makes is a probe of a stack that may be
    down or still booting, so a transport error is an expected outcome -
    yet each one attached a full ``exception.stacktrace`` event to its
    span (~30 KB of a 65 KB creation trace; observation finding N4).
    opentelemetry-instrumentation-httpx 0.65b0 exposes no
    ``record_exception`` knob (its levers are tracer_provider,
    meter_provider, the request/response hooks, and excluded URLs -
    which would drop the spans themselves), and the event comes from the
    API's ``use_span(record_exception=True)`` default. Handing the
    instrumentor a provider that flips that default is the supported
    mechanism that keeps every probe span, its ``error.type`` attribute
    and its ERROR status, and drops only the stacktrace payload. Our own
    spans (traced_tool, docker_span) keep the real provider and their
    exception events.
    """

    def __init__(self, provider: trace.TracerProvider) -> None:
        self._provider = provider

    def get_tracer(self, *args: object, **kwargs: object) -> trace.Tracer:
        return _NoExceptionEventTracer(self._provider.get_tracer(*args, **kwargs))


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

        from . import config

        # Resolved at startup because the exporter is built once: a
        # changed OTLP port reaches the server's own telemetry after
        # the next MCP server restart (odd_config_set says so).
        os.environ.setdefault(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            f"http://localhost:{config.load()['local']['otlp_http_port']}",
        )

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
        # SDK 1.44 generates a service.instance.id UUID by default; spec
        # decision #9 forbids it (per-session Prometheus label growth).
        # Keep it only when the user asked for one explicitly.
        if "service.instance.id=" not in os.environ.get("OTEL_RESOURCE_ATTRIBUTES", ""):
            resource = Resource(
                {
                    k: v
                    for k, v in resource.attributes.items()
                    if k != "service.instance.id"
                }
            )

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        )
        metrics.set_meter_provider(meter_provider)

        global _tracer, _duration_histogram, _probe_failure_counter, _tracer_provider
        _tracer_provider = tracer_provider
        _tracer = trace.get_tracer(_INSTRUMENTATION_NAME)
        meter = metrics.get_meter(_INSTRUMENTATION_NAME)
        _duration_histogram = meter.create_histogram(
            "mcp.server.operation.duration",
            unit="s",
            description="Duration of MCP server tool operations",
            explicit_bucket_boundaries_advisory=_DURATION_BUCKETS_SECONDS,
        )
        # A probe that gets no HTTP response leaves no
        # http.client.request.duration point behind (the instrumentation
        # records that histogram only after re-raising), so probe error
        # rates were answerable in TraceQL only - observation finding A5.
        _probe_failure_counter = meter.create_counter(
            "oddyssey.stack.probe.failures",
            unit="{failure}",
            description="Stack probes that got no HTTP response (transport errors)",
        )

        HTTPXClientInstrumentor().instrument(
            tracer_provider=_NoExceptionEventTracerProvider(tracer_provider)
        )
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
    docstring, and signature reach MCP registration unchanged. Exceptions
    are recorded and re-raised, except a ``ValueError`` - oddyssey's
    validation-failure contract - which is re-raised as a ``ToolError`` so
    its message reaches the client (see the ``except`` clause below).
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
            except ValueError as exc:
                # mcp 2.1.1 treats a bare exception raised from a tool body as
                # an unexpected crash and withholds its message from the
                # client - only a deliberate ToolError keeps it. oddyssey's
                # tool bodies raise ValueError for validation failures the
                # caller must see (bad stack name, bad port, ...); translate
                # it here so every tool keeps that contract without each call
                # site importing mcp's exception type itself (issue #187).
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise ToolError(str(exc)) from exc
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


def record_probe_failure(error_type: str) -> None:
    """Count one stack probe that got no HTTP response (finding A5).

    error_type is the exception class name and the only dimension:
    bounded by httpx's transport-error tree, never a URL or a host. A
    no-op while the counter is None (SDK disabled, or a bootstrap that
    degraded to no telemetry) - same contract as the duration histogram.
    """
    if _probe_failure_counter is None:
        return
    _probe_failure_counter.add(1, {"error.type": error_type})


@contextmanager
def docker_span(
    operation: str, *, container: str | None = None, image: str | None = None
) -> Iterator[trace.Span]:
    """Span for one docker subprocess call - bounded attributes only.

    No semconv exists for subprocess execution; names follow the OTel
    custom-naming rules with the app prefix (spec 2026-08-22, frozen -
    deliberately amended by issue #149 for operations acting on an
    image: observation finding F2 caught `oddyssey.docker.image` with a
    container attribute on an image inspect, so such a call now names
    the whole operation, e.g. `image-inspect`, and carries
    `oddyssey.docker.image` as its subject instead).

    Exactly one subject is passed: the container for container
    operations, the image reference for image ones.
    """
    attributes = {}
    if container is not None:
        attributes["oddyssey.docker.container"] = container
    if image is not None:
        attributes["oddyssey.docker.image"] = image
    with _tracer.start_as_current_span(
        f"oddyssey.docker.{operation}",
        attributes=attributes,
    ) as span:
        yield span
