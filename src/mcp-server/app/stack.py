"""LGTM stack lifecycle: the server drives Docker directly, no compose file.

The container definition is embedded here (image pin, name, ports), so the
server is standalone: Docker is the only prerequisite.
"""

from __future__ import annotations

import subprocess
import time

import httpx

IMAGE = "grafana/otel-lgtm:0.30.2"
CONTAINER_NAME = "oddyssey-lgtm"
PORTS = ("3000:3000", "4317:4317", "4318:4318")

# Readiness is probed through the Grafana datasource proxy: one request
# checks both Grafana and the backend behind it, and only Grafana's port
# needs to be exposed.
PROMETHEUS_READY = "http://localhost:3000/api/datasources/proxy/uid/prometheus/-/ready"
TEMPO_READY = "http://localhost:3000/api/datasources/proxy/uid/tempo/ready"
GRAFANA_URL = "http://localhost:3000"
OTLP_ENDPOINT = "http://localhost:4317"
STARTUP_TIMEOUT_S = 120
POLL_INTERVAL_S = 2


def run_args() -> list[str]:
    """The docker run command that creates the stack container."""
    port_flags = [flag for mapping in PORTS for flag in ("-p", mapping)]
    return ["docker", "run", "-d", "--name", CONTAINER_NAME, *port_flags, IMAGE]


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=False,
    )


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


def stack_status(transport: httpx.BaseTransport | None = None) -> dict:
    """Probe readiness endpoints; a down stack is a status, not an error."""
    with httpx.Client(timeout=3.0, transport=transport) as client:
        prometheus = _probe(client, PROMETHEUS_READY)
        tempo = _probe(client, TEMPO_READY)
    return {"running": prometheus and tempo, "prometheus": prometheus, "tempo": tempo}


def stack_up() -> dict:
    """Start the stack container (idempotent) and wait until it is ready."""
    state = _container_state()
    if state == "stopped":
        result = _docker("start", CONTAINER_NAME)
        if result.returncode != 0:
            raise RuntimeError(f"docker start failed: {result.stderr.strip()}")
    elif state == "absent":
        result = subprocess.run(run_args(), capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"docker run failed: {result.stderr.strip()}")
    status = stack_status()
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if status["running"]:
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


def stack_down() -> dict:
    """Destroy the stack container (and its data); absent is already down."""
    result = _docker("rm", "--force", "--volumes", CONTAINER_NAME)
    if result.returncode != 0 and "No such container" not in result.stderr:
        raise RuntimeError(f"docker rm failed: {result.stderr.strip()}")
    return {"running": False}


def stack_reset() -> dict:
    """Wipe all stored telemetry and return a fresh, ready stack.

    The stack runs without volumes, so destroying the container erases every
    stored signal (traces, metrics, logs, profiles) by construction; a new
    container then starts from the image. After a reset, everything the
    stack contains IS the next run - no window arithmetic needed.
    """
    stack_down()
    return stack_up()
