"""LGTM stack lifecycle: the server drives Docker directly, no compose file.

The container definition is embedded here (image pin, name, ports,
environment), so the server is standalone: Docker is the only prerequisite.
"""

from __future__ import annotations

import subprocess
import time

import httpx

from . import telemetry

IMAGE = "grafana/otel-lgtm:0.30.2"
CONTAINER_NAME = "oddyssey-lgtm"
PORTS = ("3000:3000", "4317:4317", "4318:4318")

# Part of the embedded definition, not an option (issue #34): CLI coding
# agents - the stack's target audience - export their claude_code.*
# metrics with delta temporality, which Prometheus's OTLP receiver
# silently rejects (HTTP 200, datapoints dropped) unless started with
# this feature flag. Experimental on Prometheus's side, but the image is
# pinned, so the behavior cannot drift until a deliberate bump.
DEFAULT_ENV = ("PROMETHEUS_EXTRA_ARGS=--enable-feature=otlp-deltatocumulative",)

# Readiness is probed through the Grafana datasource proxy: one request
# checks both Grafana and the backend behind it, and only Grafana's port
# needs to be exposed. All four signal backends are probed (issue #36):
# gating on a subset only covers the others by boot-timing coincidence.
PROMETHEUS_READY = "http://localhost:3000/api/datasources/proxy/uid/prometheus/-/ready"
TEMPO_READY = "http://localhost:3000/api/datasources/proxy/uid/tempo/ready"
LOKI_READY = "http://localhost:3000/api/datasources/proxy/uid/loki/ready"
PYROSCOPE_READY = "http://localhost:3000/api/datasources/proxy/uid/pyroscope/ready"
TEMPO_SERVICE_NAMES = (
    "http://localhost:3000/api/datasources/proxy/uid/tempo"
    "/api/search/tag/service.name/values"
)
PROMETHEUS_JOB_VALUES = (
    "http://localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/label/job/values"
)
LOKI_SERVICE_NAMES = (
    "http://localhost:3000/api/datasources/proxy/uid/loki"
    "/loki/api/v1/label/service_name/values"
)
GRAFANA_URL = "http://localhost:3000"
OTLP_ENDPOINT = "http://localhost:4317"
OTLP_HTTP_INGEST = "http://localhost:4318/v1/traces"
STARTUP_TIMEOUT_S = 120
POLL_INTERVAL_S = 2

# Widest lookback each backend accepts for the pre-wipe service listing:
# requests beyond the cap are rejected outright (not clamped), so the
# window sits just under Tempo's 168h search max_duration and Loki's
# 30d1h max_query_length. Signals older than these windows can be missed;
# Prometheus (queried without a range) covers its full TSDB.
TEMPO_SEARCH_WINDOW_S = 167 * 3600
LOKI_SEARCH_WINDOW_S = 30 * 24 * 3600


def run_args() -> list[str]:
    """The docker run command that creates the stack container."""
    port_flags = [flag for mapping in PORTS for flag in ("-p", mapping)]
    env_flags = [flag for entry in DEFAULT_ENV for flag in ("-e", entry)]
    return [
        "docker",
        "run",
        "-d",
        "--name",
        CONTAINER_NAME,
        *port_flags,
        *env_flags,
        IMAGE,
    ]


def _docker(*args: str) -> subprocess.CompletedProcess:
    with telemetry.docker_span(args[0], container=CONTAINER_NAME) as span:
        result = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        span.set_attribute("oddyssey.docker.exit_code", result.returncode)
        return result


def _container_state() -> str:
    """One of "running", "stopped", or "absent"."""
    result = _docker("inspect", "--format", "{{.State.Running}}", CONTAINER_NAME)
    if result.returncode != 0:
        return "absent"
    return "running" if result.stdout.strip() == "true" else "stopped"


def _probe(client: httpx.Client, url: str) -> bool:
    try:
        return client.get(url).status_code == 200
    except httpx.TransportError:
        return False


def _otlp_ingest_ready(client: httpx.Client) -> bool:
    """True once the OTLP HTTP listener answers - any HTTP response counts.

    The Grafana-proxy readiness probes can pass before the embedded
    collector accepts OTLP, and spans exported into that gap are dropped
    (observation report finding 3). Only a transport error means not-ready.
    """
    try:
        client.post(OTLP_HTTP_INGEST, content=b"")
        return True
    except httpx.TransportError:
        return False


def stack_status(transport: httpx.BaseTransport | None = None) -> dict:
    """Probe readiness endpoints; a down stack is a status, not an error."""
    with httpx.Client(timeout=3.0, transport=transport) as client:
        signals = {
            "prometheus": _probe(client, PROMETHEUS_READY),
            "tempo": _probe(client, TEMPO_READY),
            "loki": _probe(client, LOKI_READY),
            "pyroscope": _probe(client, PYROSCOPE_READY),
        }
    return {"running": all(signals.values()), **signals}


def stack_up() -> dict:
    """Start the stack container (idempotent) and wait until it is ready."""
    state = _container_state()
    if state == "stopped":
        result = _docker("start", CONTAINER_NAME)
        if result.returncode != 0:
            raise RuntimeError(f"docker start failed: {result.stderr.strip()}")
    elif state == "absent":
        with telemetry.docker_span("run", container=CONTAINER_NAME) as span:
            result = subprocess.run(
                run_args(), capture_output=True, text=True, check=False
            )
            span.set_attribute("oddyssey.docker.exit_code", result.returncode)
        if result.returncode != 0:
            raise RuntimeError(f"docker run failed: {result.stderr.strip()}")
    status = stack_status()
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if status["running"]:
            with httpx.Client(timeout=3.0) as client:
                while time.monotonic() < deadline and not _otlp_ingest_ready(client):
                    time.sleep(POLL_INTERVAL_S)
            # Push spans queued while the stack was down/booting into the
            # just-ready backend (best effort - already-dropped batches are
            # gone, and that residual loss is accepted by the spec).
            telemetry.force_flush()
            return {
                "running": True,
                "grafana_url": GRAFANA_URL,
                "otlp_endpoint": OTLP_ENDPOINT,
            }
        time.sleep(POLL_INTERVAL_S)
        status = stack_status()
    raise RuntimeError(
        f"stack did not become ready within {STARTUP_TIMEOUT_S}s: {status}"
    )


def stored_services(transport: httpx.BaseTransport | None = None) -> list[str]:
    """Best-effort list of service.name values currently stored in the stack.

    Union across the queryable backends, since a service may have emitted
    only one signal: Tempo's service.name tag values, Loki's service_name
    label values, and Prometheus job values (OTLP ingestion maps
    service.name onto job, prefixed by one service.namespace/ segment when
    a namespace is set). Tempo and Loki need an explicit start/end pair:
    unscoped, Tempo only reads its live store (flushed blocks are
    invisible) and Loki defaults to a 6-hour lookback, so day-old services
    would be wiped without ever being listed. The list exists to warn
    before a wipe, so every failure degrades to fewer names, never to an
    error.
    """
    now_s = int(time.time())

    def values(payload: object, field: str) -> list[str]:
        if not isinstance(payload, dict):
            return []
        items = payload.get(field)
        if not isinstance(items, list):
            return []
        return [v for v in items if isinstance(v, str)]

    services: set[str] = set()
    with httpx.Client(timeout=3.0, transport=transport) as client:
        try:
            tempo = client.get(
                TEMPO_SERVICE_NAMES,
                params={"start": now_s - TEMPO_SEARCH_WINDOW_S, "end": now_s},
            ).json()
            services.update(values(tempo, "tagValues"))
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        try:
            loki = client.get(
                LOKI_SERVICE_NAMES,
                params={
                    "start": (now_s - LOKI_SEARCH_WINDOW_S) * 1_000_000_000,
                    "end": now_s * 1_000_000_000,
                },
            ).json()
            services.update(values(loki, "data"))
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        try:
            prometheus = client.get(PROMETHEUS_JOB_VALUES).json()
            services.update(job.split("/", 1)[-1] for job in values(prometheus, "data"))
        except (httpx.HTTPError, ValueError, TypeError):
            pass
    return sorted(services)


def stack_down() -> dict:
    """Destroy the stack container (and its data); absent is already down."""
    telemetry.force_flush()
    result = _docker("rm", "--force", "--volumes", CONTAINER_NAME)
    if result.returncode != 0 and "no such container" not in result.stderr.lower():
        raise RuntimeError(f"docker rm failed: {result.stderr.strip()}")
    return {"running": False}


def stack_reset() -> dict:
    """Wipe all stored telemetry and return a fresh, ready stack.

    The stack runs without volumes, so destroying the container erases every
    stored signal (traces, metrics, logs, profiles) by construction; a new
    container then starts from the image. After a reset, everything the
    stack contains IS the next run - no window arithmetic needed.

    The stack is shared machine-wide (issue #35), so the wipe is never
    scoped to one project: the result names the services that were stored
    so the destruction is at least visible to the caller. A stopped
    container (normal after a host reboot) still holds telemetry but
    answers nothing on :3000, so it is booted first to be enumerable -
    best-effort, because wiping a container too broken to boot is also
    reset's job.
    """
    if _container_state() == "stopped":
        try:
            stack_up()
        except RuntimeError:
            pass
    services = stored_services()
    stack_down()
    return {**stack_up(), "services_wiped": services}
