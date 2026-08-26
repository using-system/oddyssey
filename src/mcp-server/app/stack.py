"""LGTM stack lifecycle: the server drives Docker directly, no compose file.

The container definition is embedded here (image pin, name, environment;
host ports come from the global configuration), so the server is
standalone: Docker is the only prerequisite.
"""

from __future__ import annotations

import json
import subprocess
import time

import httpx

from . import config, telemetry

# The image's environment surface (ENABLE_LOGS_*, *_EXTRA_ARGS, OTLP
# forwarding, OBI, GF_*) is cataloged in the setup-local-stack skill's
# otel-lgtm-env reference, built from this exact tag - re-validate it on
# every pin bump.
IMAGE = "grafana/otel-lgtm:0.31.0"
CONTAINER_NAME = "oddyssey-lgtm"

# Part of the embedded definition, not an option (issue #34): CLI coding
# agents - the stack's target audience - export their claude_code.*
# metrics with delta temporality, which Prometheus's OTLP receiver
# silently rejects (HTTP 200, datapoints dropped) unless started with
# this feature flag. Experimental on Prometheus's side, but the image is
# pinned, so the behavior cannot drift until a deliberate bump.
DEFAULT_ENV = ("PROMETHEUS_EXTRA_ARGS=--enable-feature=otlp-deltatocumulative",)

# When a DEFAULT_ENV entry changes, move the OLD exact entry here: a
# surviving container still carries it, and container_user_env must not
# read it as a user choice (it would be carried forward and suppress the
# new default). Empty until a default actually changes.
SUPERSEDED_DEFAULT_ENV: tuple[str, ...] = ()

# Container-side ports are fixed by the image; only the host side is
# configurable (issue #59). Ports and URLs are resolved at call time so
# a configuration change is honored without restarting the server.
CONTAINER_PORTS = {"grafana_port": 3000, "otlp_grpc_port": 4317, "otlp_http_port": 4318}


def local_ports() -> dict:
    return config.load()["local"]


def grafana_base(ports: dict | None = None) -> str:
    """Grafana's base URL, from the configuration unless ports says otherwise.

    The override exists for callers that must reach the container as it
    is published right now rather than as the configuration describes it.
    """
    return f"http://localhost:{(ports or local_ports())['grafana_port']}"


def otlp_endpoint() -> str:
    return f"http://localhost:{local_ports()['otlp_grpc_port']}"


def otlp_http_ingest() -> str:
    return f"http://localhost:{local_ports()['otlp_http_port']}/v1/traces"


def _proxy(uid: str, path: str, ports: dict | None = None) -> str:
    # Readiness and metadata are queried through the Grafana datasource
    # proxy: one request checks both Grafana and the backend behind it,
    # and only Grafana's port needs to be exposed.
    return f"{grafana_base(ports)}/api/datasources/proxy/uid/{uid}{path}"


STARTUP_TIMEOUT_S = 120
POLL_INTERVAL_S = 2

# Widest lookback each backend accepts for the pre-wipe service listing:
# requests beyond the cap are rejected outright (not clamped), so the
# window sits just under Tempo's 168h search max_duration and Loki's
# 30d1h max_query_length. Signals older than these windows can be missed;
# Prometheus (queried without a range) covers its full TSDB.
TEMPO_SEARCH_WINDOW_S = 167 * 3600
LOKI_SEARCH_WINDOW_S = 30 * 24 * 3600


def _validate_env(env: dict[str, str] | None) -> None:
    """Reject malformed keys with a clear message.

    Pure and free, so every entry point runs it FIRST: a rejected request
    must destroy and create nothing (a reset that wipes before validating
    would trade the whole machine's telemetry for an error). Injection is
    impossible by construction (argv list, no shell) - only the key shape
    needs guarding.
    """
    for key in env or {}:
        if not key or "=" in key:
            raise ValueError(f"invalid environment variable name: {key!r}")


def run_args(env: dict[str, str] | None = None) -> list[str]:
    """The docker run command that creates the stack container.

    User entries win over the embedded defaults on key collision - what
    the caller states explicitly is what the container gets, same policy
    as telemetry.py's setdefault handling of OTEL_* variables.
    """
    _validate_env(env)
    merged = dict(entry.split("=", 1) for entry in DEFAULT_ENV)
    merged.update(env or {})
    ports = local_ports()
    port_flags = [
        flag
        for key, container_port in CONTAINER_PORTS.items()
        for flag in ("-p", f"{ports[key]}:{container_port}")
    ]
    env_flags = [
        flag for key, value in merged.items() for flag in ("-e", f"{key}={value}")
    ]
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


def _container_host_ports() -> dict | None:
    """Host ports the existing container actually publishes, or None.

    Read from docker inspect so the guard in stack_up can compare them
    with the configuration - best-effort: unreadable means no guard,
    never a blocked start.
    """
    result = _docker(
        "inspect", "--format", "{{json .HostConfig.PortBindings}}", CONTAINER_NAME
    )
    if result.returncode != 0:
        return None
    try:
        bindings = json.loads(result.stdout.strip())
        return {
            key: int(bindings[f"{container_port}/tcp"][0]["HostPort"])
            for key, container_port in CONTAINER_PORTS.items()
        }
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def container_user_env() -> dict[str, str] | None:
    """User-set environment of the existing container, or None.

    The auto-reset of odd_config_set recreates the container and must carry
    forward what the user applied through stack_up/stack_reset (issue #62):
    everything in the container's .Config.Env minus its image's own env and
    the exact embedded defaults - both are recreated anyway, and an
    overridden default is a user choice so only the exact entry is dropped.
    The subtraction targets the image the container was CREATED from
    (.Image ID), never the pinned IMAGE constant: after a pin bump with a
    surviving old container the two differ, and diffing against the new
    image would misclassify old-image-baked entries as user env (#83).
    Best-effort by contract: an unreadable inspect preserves nothing and
    never raises - losing env on that path beats blocking the reset.
    """
    container = _docker(
        "inspect",
        "--format",
        '{"env": {{json .Config.Env}}, "image": {{json .Image}}}',
        CONTAINER_NAME,
    )
    if container.returncode != 0:
        return None
    try:
        parsed = json.loads(container.stdout.strip())
        container_env = parsed["env"]
        image_ref = parsed["image"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(container_env, list) or not isinstance(image_ref, str):
        return None
    image = _docker("image", "inspect", "--format", "{{json .Config.Env}}", image_ref)
    if image.returncode != 0:
        return None
    try:
        image_env = json.loads(image.stdout.strip())
    except ValueError:
        return None
    inherited = (
        set(image_env if isinstance(image_env, list) else [])
        | set(DEFAULT_ENV)
        | set(SUPERSEDED_DEFAULT_ENV)
    )
    return dict(
        entry.split("=", 1)
        for entry in container_env
        if isinstance(entry, str) and "=" in entry and entry not in inherited
    )


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
        client.post(otlp_http_ingest(), content=b"")
        return True
    except httpx.TransportError:
        return False


def stack_status(transport: httpx.BaseTransport | None = None) -> dict:
    """Probe readiness endpoints; a down stack is a status, not an error.

    All four signal backends are probed (issue #36): gating on a subset
    only covers the others by boot-timing coincidence.
    """
    with httpx.Client(timeout=3.0, transport=transport) as client:
        signals = {
            "prometheus": _probe(client, _proxy("prometheus", "/-/ready")),
            "tempo": _probe(client, _proxy("tempo", "/ready")),
            "loki": _probe(client, _proxy("loki", "/ready")),
            "pyroscope": _probe(client, _proxy("pyroscope", "/ready")),
        }
    return {"running": all(signals.values()), **signals}


def stack_up(env: dict[str, str] | None = None) -> dict:
    """Start the stack container (idempotent) and wait until it is ready.

    Docker only applies env at container creation, so env reaches the
    container only when this call creates one; the result's env_applied
    field (present whenever env was requested) tells the caller whether
    it landed or a reset is needed.
    """
    _validate_env(env)
    state = _container_state()
    if state != "absent":
        actual = _container_host_ports()
        configured = local_ports()
        if actual is not None and actual != configured:
            raise RuntimeError(
                f"container publishes host ports {actual} but the configuration "
                f"says {configured} - run odd_stack_reset to recreate it on the "
                "configured ports"
            )
    created = False
    if state == "stopped":
        result = _docker("start", CONTAINER_NAME)
        if result.returncode != 0:
            raise RuntimeError(f"docker start failed: {result.stderr.strip()}")
    elif state == "absent":
        with telemetry.docker_span("run", container=CONTAINER_NAME) as span:
            result = subprocess.run(
                run_args(env), capture_output=True, text=True, check=False
            )
            span.set_attribute("oddyssey.docker.exit_code", result.returncode)
        if result.returncode != 0:
            raise RuntimeError(f"docker run failed: {result.stderr.strip()}")
        created = True
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
            up_result = {
                "running": True,
                "grafana_url": grafana_base(),
                "otlp_endpoint": otlp_endpoint(),
            }
            if env:
                up_result["env_applied"] = created
            return up_result
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
    # The pre-wipe enumeration must see the container about to be
    # destroyed, not the configuration's future: odd_config_set stores the
    # new ports and then resets, while the doomed container still
    # publishes the old ones. Querying the configured port would hit dead
    # URLs and report an empty wipe over real data (issue #35). Without a
    # container to inspect, the configuration is the only truth left.
    ports = _container_host_ports()
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
                _proxy("tempo", "/api/search/tag/service.name/values", ports),
                params={"start": now_s - TEMPO_SEARCH_WINDOW_S, "end": now_s},
            ).json()
            services.update(values(tempo, "tagValues"))
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        try:
            loki = client.get(
                _proxy("loki", "/loki/api/v1/label/service_name/values", ports),
                params={
                    "start": (now_s - LOKI_SEARCH_WINDOW_S) * 1_000_000_000,
                    "end": now_s * 1_000_000_000,
                },
            ).json()
            services.update(values(loki, "data"))
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        try:
            prometheus = client.get(
                _proxy("prometheus", "/api/v1/label/job/values", ports)
            ).json()
            services.update(job.split("/", 1)[-1] for job in values(prometheus, "data"))
        except (httpx.HTTPError, ValueError, TypeError):
            pass
    return sorted(services)


def stack_down(flush: bool = True) -> dict:
    """Destroy the stack container (and its data); absent is already down.

    flush pushes queued telemetry out before the destruction - right for a
    standalone down (the export target may be a remote store that survives
    the local container), wrong from stack_reset: the flushed spans land
    in the very store the next line destroys, a deterministic loss of the
    whole pre-rm phase (observation report 2026-08-26, F3). The reset path
    passes False so the SDK worker's scheduled exports (with their retry
    backoff) deliver the spans once the recreated container listens, with
    stack_up's post-readiness flush as the backstop - best effort either
    way: a boot slower than the retry deadline still drops the batch.
    """
    if flush:
        telemetry.force_flush()
    result = _docker("rm", "--force", "--volumes", CONTAINER_NAME)
    if result.returncode != 0 and "no such container" not in result.stderr.lower():
        raise RuntimeError(f"docker rm failed: {result.stderr.strip()}")
    return {"running": False}


def stack_reset(env: dict[str, str] | None = None) -> dict:
    """Wipe all stored telemetry and return a fresh, ready stack.

    The stack runs without volumes, so destroying the container erases every
    stored signal (traces, metrics, logs, profiles) by construction; a new
    container then starts from the image. After a reset, everything the
    stack contains IS the next run - no window arithmetic needed.

    The stack is shared machine-wide (issue #35), so the wipe is never
    scoped to one project: the result names the services that were stored
    so the destruction is at least visible to the caller. A stopped
    container (normal after a host reboot) still holds telemetry but
    answers nothing on Grafana's port, so it is booted first to be enumerable -
    best-effort, because wiping a container too broken to boot is also
    reset's job.
    """
    _validate_env(env)
    if _container_state() == "stopped":
        try:
            stack_up()
        except RuntimeError:
            pass
    services = stored_services()
    stack_down(flush=False)
    # Reset always recreates, so env - unlike on stack_up - always applies.
    return {**stack_up(env), "services_wiped": services}
