"""OpenTelemetry bootstrap for llmbench-agent.

Four signals, three transports: traces, metrics and logs leave over OTLP
HTTP; profiles do not - Python has no OTLP profile exporter, so the
Pyroscope SDK pushes them straight to Pyroscope's own ingest API.

Everything is configured from the environment so the container needs no
code change to point at another stack: ``OTEL_SERVICE_NAME``,
``OTEL_EXPORTER_OTLP_ENDPOINT`` (the collector's HTTP root, the exporters
append ``/v1/traces`` and friends), ``DEPLOYMENT_ENV``,
``PYROSCOPE_SERVER_ADDRESS``.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "llmbench-agent")
SERVICE_VERSION = "0.1.0"

_shutdowns: list = []


def _resource() -> Resource:
    return Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": SERVICE_VERSION,
            "service.namespace": "llms-benchmark",
            "deployment.environment.name": os.environ.get("DEPLOYMENT_ENV", "local"),
        }
    )


def _setup_profiles() -> None:
    """Push profiles to Pyroscope's ingest API (Python has no OTLP profile exporter)."""
    address = os.environ.get("PYROSCOPE_SERVER_ADDRESS")
    if not address:
        return
    try:
        import pyroscope
    except Exception:  # noqa: BLE001 - a missing profiler must not stop the service
        logging.getLogger(__name__).warning("pyroscope-io unavailable, no profiles")
        return
    pyroscope.configure(
        application_name=SERVICE_NAME,
        server_address=address,
        oncpu=True,
        gil_only=False,
        enable_logging=False,
        tags={
            "service_name": SERVICE_NAME,
            "service_namespace": "llms-benchmark",
            "environment": os.environ.get("DEPLOYMENT_ENV", "local"),
        },
    )


def setup_telemetry() -> None:
    """Install the SDK for the three OTLP signals, then start the profiler."""
    resource = _resource()

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)
    _shutdowns.append(tracer_provider.shutdown)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(meter_provider)
    _shutdowns.append(meter_provider.shutdown)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger().addHandler(
        LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    )
    _shutdowns.append(logger_provider.shutdown)

    _setup_profiles()


def shutdown_telemetry() -> None:
    for close in reversed(_shutdowns):
        try:
            close()
        except Exception:  # noqa: BLE001, S110 - shutdown must never raise on the way out
            pass


def tracer() -> trace.Tracer:
    return trace.get_tracer(SERVICE_NAME, SERVICE_VERSION)


def meter() -> metrics.Meter:
    return metrics.get_meter(SERVICE_NAME, SERVICE_VERSION)
