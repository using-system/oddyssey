# OpenTelemetry Instrumentation of `oddyssey-mcp` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The oddyssey MCP server emits its own OpenTelemetry traces and metrics (default-on) to the local stack it pilots, without ever touching stdout or changing any tool's behavior.

**Architecture:** One new module `app/telemetry.py` owns the whole OTel surface: SDK bootstrap/shutdown (default-on, env-overridable, `OTEL_SDK_DISABLED` kill-switch), a `traced_tool` decorator for the 4 tool handlers, a `docker_span` helper for the subprocess boundary, and `force_flush` for the pre-destroy flush. `server.py` and `stack.py` only call into it.

**Tech Stack:** Python ≥3.12, `mcp==2.0.0` (stdio), `opentelemetry-api/sdk/exporter-otlp-proto-http==1.44.0`, `opentelemetry-instrumentation-httpx==0.65b0`, uv, pytest 9.1.1, ruff 0.16.4.

**Spec:** `docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md`

## Global Constraints

- **stdout is the JSON-RPC wire**: no instrumentation code may write to stdout, ever. Console exporters are forbidden. Diagnostics only via Python logging (defaults to stderr).
- **Failed export is the normal state** (the backend is the stack this server starts/destroys): never raise, never spam — the `opentelemetry` logger tree is set to `CRITICAL`.
- **Tool registration must not change**: `tests/mcp-server/test_server.py` asserts the exact tool set `{odd_stack_up, odd_stack_down, odd_stack_status, odd_stack_reset}` and non-empty descriptions; `traced_tool` must preserve `__name__`/`__doc__`/signature via `functools.wraps`.
- **Pinned versions, verbatim**: `opentelemetry-api==1.44.0`, `opentelemetry-sdk==1.44.0`, `opentelemetry-exporter-otlp-proto-http==1.44.0`, `opentelemetry-instrumentation-httpx==0.65b0`. Never gRPC (`grpcio` is banned from this package).
- **Default-on**: in-code defaults applied only for env vars the user did NOT set (`os.environ.setdefault`): `OTEL_SERVICE_NAME=oddyssey-mcp`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_SEMCONV_STABILITY_OPT_IN=http`. `OTEL_SDK_DISABLED=true` restores pre-instrumentation behavior exactly.
- **Frozen names** (spec §3.10): span `tools/call {tool}`, attrs `mcp.method.name`, `gen_ai.tool.name`, `network.transport="pipe"`, `jsonrpc.protocol.version="2.0"`; histogram `mcp.server.operation.duration` (unit `s`); docker spans `oddyssey.docker.{run|start|rm|inspect}` with `oddyssey.docker.container`, `oddyssey.docker.exit_code`.
- **Commands** (run from the repo root):
  - Tests: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v`
  - Lint: `uvx ruff@0.16.4 check src/mcp-server tests/mcp-server`
  - Format: `uvx ruff@0.16.4 format src/mcp-server tests/mcp-server` (CI runs `format --check`)
- Branch: `feat/mcp-otel` (already created). Conventional Commits, English artifacts, no breaking markers.

---

### Task 1: Telemetry bootstrap module

**Files:**
- Modify: `src/mcp-server/pyproject.toml:7-10` (dependencies)
- Create: `src/mcp-server/app/telemetry.py`
- Test: `tests/mcp-server/test_telemetry.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: module `oddyssey_mcp.telemetry` with `setup_telemetry() -> Callable[[], None]` (returns the shutdown callable), `force_flush(timeout_ms: int = 2000) -> None`, and module globals `_tracer` (a `Tracer`, no-op until setup) and `_duration_histogram` (`Histogram | None`, `None` until setup) that Tasks 2–3 read at call time.

- [ ] **Step 1: Add the pinned dependencies**

In `src/mcp-server/pyproject.toml`, replace the `dependencies` list with:

```toml
dependencies = [
    "mcp==2.0.0",
    "httpx==0.28.1",
    "opentelemetry-api==1.44.0",
    "opentelemetry-sdk==1.44.0",
    "opentelemetry-exporter-otlp-proto-http==1.44.0",
    "opentelemetry-instrumentation-httpx==0.65b0",
]
```

Then run: `uv lock --project src/mcp-server`
Expected: `uv.lock` updated, no resolution error.

- [ ] **Step 2: Write the failing tests**

Create `tests/mcp-server/test_telemetry.py`:

```python
import subprocess
import sys

import pytest

from oddyssey_mcp import telemetry


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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_telemetry.py -v`
Expected: FAIL / collection error with `ModuleNotFoundError: No module named 'oddyssey_mcp.telemetry'` (or `ImportError`).

- [ ] **Step 4: Write the module**

Create `src/mcp-server/app/telemetry.py`:

```python
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
    except Exception:  # noqa: BLE001 - flushing is strictly best-effort
        pass
```

(`traced_tool` and `docker_span` are added in Tasks 2 and 3, each bringing its own imports — the module above imports only what it uses so ruff stays green at every commit.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_telemetry.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server
uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/pyproject.toml src/mcp-server/uv.lock src/mcp-server/app/telemetry.py tests/mcp-server/test_telemetry.py
git commit -m "feat(mcp): add opentelemetry bootstrap module (default-on, stdout-safe)"
```

---

### Task 2: `traced_tool` decorator and duration histogram

**Files:**
- Modify: `src/mcp-server/app/telemetry.py` (append)
- Test: `tests/mcp-server/test_telemetry.py` (append)

**Interfaces:**
- Consumes: Task 1's module globals `_tracer`, `_duration_histogram` (read at call time, never captured at import time).
- Produces: `traced_tool(fn: Callable[..., dict]) -> Callable[..., dict]` — decorator used by Task 4 under `@mcp.tool()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/mcp-server/test_telemetry.py`:

```python
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_telemetry.py -v`
Expected: the two new tests FAIL with `AttributeError: module 'oddyssey_mcp.telemetry' has no attribute 'traced_tool'`; the Task 1 tests still PASS.

- [ ] **Step 3: Implement the decorator**

In `src/mcp-server/app/telemetry.py`, add to the import block:

```python
import functools
import time

from opentelemetry.trace import SpanKind, Status, StatusCode
```

(`import functools` / `import time` join the stdlib imports; the `opentelemetry.trace` line merges with the existing `from opentelemetry import ...` block region — keep ruff-sorted order.)

Then append:

```python
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
```

Note: the wrapper must read the module globals `_tracer` / `_duration_histogram` at call time (plain module-global reference, as written) — never copy them into a local or default arg, or setup ordering breaks.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_telemetry.py -v`
Expected: all PASS.

- [ ] **Step 5: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server
uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/app/telemetry.py tests/mcp-server/test_telemetry.py
git commit -m "feat(mcp): trace tool calls with mcp semconv span and duration metric"
```

---

### Task 3: Docker spans and pre-destroy flush in `stack.py`

**Files:**
- Modify: `src/mcp-server/app/telemetry.py` (append)
- Modify: `src/mcp-server/app/stack.py:35-41` (`_docker`), `:74-77` (`stack_up` run branch), `:94-99` (`stack_down`)
- Test: `tests/mcp-server/test_telemetry.py` (append)

**Interfaces:**
- Consumes: Task 1's `_tracer` global; `stack.CONTAINER_NAME` (`"oddyssey-lgtm"`).
- Produces: `docker_span(verb: str, container: str)` context manager yielding the live span (Task 3 wires it into `stack.py` itself; no later task consumes it).

- [ ] **Step 1: Write the failing test**

Append to `tests/mcp-server/test_telemetry.py`:

```python
def test_docker_span_names_and_attributes(span_capture):
    with telemetry.docker_span("inspect", container="oddyssey-lgtm") as span:
        span.set_attribute("oddyssey.docker.exit_code", 0)

    (finished,) = span_capture.get_finished_spans()
    assert finished.name == "oddyssey.docker.inspect"
    assert finished.attributes["oddyssey.docker.container"] == "oddyssey-lgtm"
    assert finished.attributes["oddyssey.docker.exit_code"] == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_telemetry.py::test_docker_span_names_and_attributes -v`
Expected: FAIL with `AttributeError: ... no attribute 'docker_span'`.

- [ ] **Step 3: Implement the helper**

In `src/mcp-server/app/telemetry.py`, extend the import block:

```python
from collections.abc import Callable, Iterator
from contextlib import contextmanager
```

(`Iterator` joins the existing `collections.abc` import; `contextmanager` is a new stdlib import line.)

Then append:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_telemetry.py::test_docker_span_names_and_attributes -v`
Expected: PASS.

- [ ] **Step 5: Wire `stack.py`**

In `src/mcp-server/app/stack.py`, add the import after `import httpx`:

```python
from . import telemetry
```

Replace `_docker` (lines 35-41) with:

```python
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
```

In `stack_up`, replace the `absent` branch's bare `subprocess.run` call:

```python
    elif state == "absent":
        with telemetry.docker_span("run", container=CONTAINER_NAME) as span:
            result = subprocess.run(
                run_args(), capture_output=True, text=True, check=False
            )
            span.set_attribute("oddyssey.docker.exit_code", result.returncode)
        if result.returncode != 0:
            raise RuntimeError(f"docker run failed: {result.stderr.strip()}")
```

In `stack_down`, add the flush as the first line of the function body (spec §3.6 — child spans emitted so far get a chance to land before the backend dies; `stack_reset` inherits it via its `stack_down()` call):

```python
def stack_down() -> dict:
    """Destroy the stack container (and its data); absent is already down."""
    telemetry.force_flush()
    result = _docker("rm", "--force", "--volumes", CONTAINER_NAME)
    if result.returncode != 0 and "no such container" not in result.stderr.lower():
        raise RuntimeError(f"docker rm failed: {result.stderr.strip()}")
    return {"running": False}
```

- [ ] **Step 6: Run the full unit suite**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v`
Expected: all PASS (with no SDK installed, `docker_span` uses the no-op tracer — `test_stack.py` behavior is unchanged).

- [ ] **Step 7: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server
uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/app/telemetry.py src/mcp-server/app/stack.py tests/mcp-server/test_telemetry.py
git commit -m "feat(mcp): span the docker boundary and flush before stack destroy"
```

---

### Task 4: Wire `server.py` and verify end to end

**Files:**
- Modify: `src/mcp-server/app/server.py:16-45`
- Test: existing `tests/mcp-server/test_server.py` (unchanged — it is the gate)

**Interfaces:**
- Consumes: `telemetry.setup_telemetry() -> Callable[[], None]` (Task 1), `telemetry.traced_tool` (Task 2).
- Produces: the instrumented entry point; nothing downstream.

- [ ] **Step 1: Wire the module**

In `src/mcp-server/app/server.py`: add the import after `from . import stack as stack_ops`:

```python
from . import telemetry
```

Add `@telemetry.traced_tool` UNDER each `@mcp.tool()` (all 4 handlers), e.g.:

```python
@mcp.tool()
@telemetry.traced_tool
def odd_stack_up() -> dict:
    """Start the local LGTM observability stack (Grafana, Tempo, Prometheus, Loki, OTLP)."""
    return stack_ops.stack_up()
```

(same two-decorator stack for `odd_stack_down`, `odd_stack_status`, `odd_stack_reset` — the docstrings and bodies stay exactly as they are).

Replace `main`:

```python
def main() -> None:
    shutdown = telemetry.setup_telemetry()
    try:
        mcp.run()
    finally:
        shutdown()
```

- [ ] **Step 2: Run the full unit suite (registration gate)**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v`
Expected: all PASS — in particular `test_all_stack_tools_registered` (exact 4-tool set) and `test_tools_have_descriptions` prove `traced_tool` did not disturb registration.

- [ ] **Step 3: Prove the stdio wire stays clean end to end**

Run (no Docker needed; the stack being down IS the interesting case):

```bash
OUT=$(printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}\n{"jsonrpc":"2.0","method":"notifications/initialized"}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n' \
  | timeout 30 uv run --project src/mcp-server oddyssey-mcp 2>/dev/null)
echo "$OUT" | head -c 400
echo "$OUT" | python3 -c "import sys,json; [json.loads(l) for l in sys.stdin if l.strip()]; print('STDOUT IS CLEAN JSON-RPC')"
```

Expected: the tools/list response naming the 4 tools, then `STDOUT IS CLEAN JSON-RPC` (every stdout line parses as JSON — no stray bytes from the SDK or failed exports).

- [ ] **Step 4: Integration tests (Docker required)**

Run: `bash integration-tests/mcp-server/run.sh`
Expected: green, unchanged. (If Docker is unavailable in the execution environment, mark this step for the controller to run before the PR.)

- [ ] **Step 5: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server
uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/app/server.py
git commit -m "feat(mcp): bootstrap telemetry at startup and trace the four tools"
```

---

## Post-plan verification (controller, not a task)

Spec §7 integration protocol, using the product itself: `odd_stack_up`, drive status/stop/status/up, then `/odd-observe` on `oddyssey-mcp` — Tempo shows `service.name="oddyssey-mcp"` tool→httpx/docker span trees, Prometheus shows `mcp_server_operation_duration` series, resource attrs carry `service.version` + `deployment.environment.name=local`.
