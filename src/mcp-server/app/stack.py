"""LGTM stack lifecycle: compose file resolution, status probe, up/down."""

from __future__ import annotations

import importlib.resources
import os
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

# Readiness is probed through the Grafana datasource proxy: one request
# checks both Grafana and the backend behind it, and only Grafana's port
# needs to be exposed.
PROMETHEUS_READY = "http://localhost:3000/api/datasources/proxy/uid/prometheus/-/ready"
TEMPO_READY = "http://localhost:3000/api/datasources/proxy/uid/tempo/ready"
GRAFANA_URL = "http://localhost:3000"
OTLP_ENDPOINT = "http://localhost:4317"
STARTUP_TIMEOUT_S = 120
POLL_INTERVAL_S = 2

_materialized: Path | None = None


def compose_file() -> Path:
    """The compose file to drive: env override, else the packaged copy."""
    override = os.environ.get("ODD_COMPOSE_FILE")
    if override:
        return Path(override)
    global _materialized
    if _materialized is None or not _materialized.exists():
        content = (
            importlib.resources.files("oddyssey_mcp") / "resources" / "docker-compose.yml"
        ).read_text()
        target = Path(tempfile.gettempdir()) / "oddyssey-docker-compose.yml"
        target.write_text(content)
        _materialized = target
    return _materialized


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


def _compose(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", str(compose_file()), *args],
        capture_output=True,
        text=True,
    )


def stack_up() -> dict:
    result = _compose("up", "-d")
    if result.returncode != 0:
        raise RuntimeError(f"docker compose up failed: {result.stderr.strip()}")
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        status = stack_status()
        if status["running"]:
            return {"running": True, "grafana_url": GRAFANA_URL, "otlp_endpoint": OTLP_ENDPOINT}
        time.sleep(POLL_INTERVAL_S)
    raise RuntimeError(f"stack did not become ready within {STARTUP_TIMEOUT_S}s: {status}")


def stack_down() -> dict:
    result = _compose("down")
    if result.returncode != 0:
        raise RuntimeError(f"docker compose down failed: {result.stderr.strip()}")
    return {"running": False}
