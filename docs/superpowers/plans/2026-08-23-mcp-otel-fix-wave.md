# MCP OTel Observation Fix Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the four anomalies the first ODD observation report found in the instrumented MCP server: duplicate tool spans, unwanted `service.instance.id`, reset/boot spans lost to OTLP-ingest lag, and httpx INFO noise on stderr.

**Architecture:** Small surgical changes to the three existing files (`app/telemetry.py`, `app/server.py`, `app/stack.py`) plus a dated revision section in the spec recording the rulings. No new modules, no new dependencies.

**Tech Stack:** unchanged — Python ≥3.12, mcp==2.0.0, opentelemetry 1.44.0, uv, pytest 9.1.1, ruff 0.16.4.

**Spec:** `docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md` (this wave appends its Revision 2026-08-23 section).
**Evidence source:** `.odd/observe-run-reports/2026-08-22-2154-mcp-otel-instrumentation-verification.md` (findings 1-4 and the before-values the fixes must move).

## Global Constraints

- stdout is the MCP JSON-RPC wire: nothing writes to stdout, ever.
- Frozen names stay frozen: span `tools/call {tool}` with its four attributes, histogram `mcp.server.operation.duration` (unit `s`, buckets 0.05…300), docker spans `oddyssey.docker.*`.
- Tool behavior contract unchanged: same return values, same error messages; `stack_status` untouched.
- Telemetry failure never breaks the server (guarded bootstrap stays guarded).
- No new dependencies; nothing gRPC; mcp SDK internals accessed defensively (a broken internal import degrades, never crashes).
- Commands (repo root): tests `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v`; lint `uvx ruff@0.16.4 check src/mcp-server tests/mcp-server`; format `uvx ruff@0.16.4 format src/mcp-server tests/mcp-server`.
- Branch `feat/mcp-otel`; Conventional Commits; never a `!` or BREAKING CHANGE marker.

**Controller rulings this plan encodes** (from the observation report's open decisions):
- Finding 1: the branch's decorator span is CANONICAL; the SDK's default `OpenTelemetryMiddleware` is removed (its own code marks the middleware API "expected to change before v2 is final"). Revisit via spec revision when mcp v2 finalizes.
- Finding 3: `odd_stack_up`'s notion of "ready" now includes the OTLP HTTP listener accepting requests, and a post-ready `force_flush` pushes queued spans into the just-born backend. Residual loss (batches already dropped during boot) is accepted and documented.

---

### Task 1: Strip `service.instance.id`, quiet httpx stderr noise (findings 2 + 4)

**Files:**
- Modify: `src/mcp-server/app/telemetry.py` (resource block inside `setup_telemetry`)
- Modify: `src/mcp-server/app/server.py` (`main()`)
- Test: `tests/mcp-server/test_telemetry.py` (append)
- Modify: `docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md` (append revision entries)

**Interfaces:**
- Consumes: `setup_telemetry()`'s existing enabled path (guarded `try`), the `Resource.create(attributes)` call.
- Produces: nothing new for later tasks (Task 2 touches different regions of the same files — server.py's module level vs main(), telemetry's resource block is untouched by Task 2).

- [ ] **Step 1: Write the failing test (finding 2)**

Append to `tests/mcp-server/test_telemetry.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_telemetry.py::test_resource_has_no_service_instance_id -v`
Expected: FAIL on the last assert (`instance_id_present=True` — the SDK generated the UUID).

- [ ] **Step 3: Implement the strip (finding 2)**

In `src/mcp-server/app/telemetry.py`, inside `setup_telemetry`'s enabled body, right after `resource = Resource.create(attributes)`:

```python
        # SDK 1.44 generates a service.instance.id UUID by default; spec
        # decision #9 forbids it (per-session Prometheus label growth).
        # Keep it only when the user asked for one explicitly.
        if "service.instance.id=" not in os.environ.get(
            "OTEL_RESOURCE_ATTRIBUTES", ""
        ):
            resource = Resource(
                {
                    k: v
                    for k, v in resource.attributes.items()
                    if k != "service.instance.id"
                }
            )
```

(If the pinned SDK's `Resource.__init__` signature rejects a plain dict, use `Resource.create({...}).attributes`-free construction via `Resource(attributes=...)` — verify against the installed package and keep whichever constructs cleanly; the test is the arbiter.)

- [ ] **Step 4: Run the test to verify it passes**

Run: same command as Step 2. Expected: PASS. Then the full suite: all pass.

- [ ] **Step 5: Quiet the probe noise (finding 4)**

In `src/mcp-server/app/server.py`, `main()`, add BEFORE `setup_telemetry()`:

```python
def main() -> None:
    # The mcp SDK configures INFO logging, which lets httpx announce every
    # readiness probe on stderr (28 lines per observed session). Quiet the
    # HTTP client loggers; real errors still surface at WARNING+.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    shutdown = telemetry.setup_telemetry()
    try:
        mcp.run()
    finally:
        shutdown()
```

Add `import logging` to server.py's stdlib imports.

- [ ] **Step 6: Spec revision entries**

Append to `docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md` (create the section if this task runs first):

```markdown
## Revision 2026-08-23 (post-observation fix wave)

Driven by the first observation report
(`.odd/observe-run-reports/2026-08-22-2154-mcp-otel-instrumentation-verification.md`).

- **Decision #9 enforced in code**: opentelemetry-sdk 1.44 generates a
  `service.instance.id` UUID by default; `setup_telemetry` now strips it
  unless the user sets one in `OTEL_RESOURCE_ATTRIBUTES`.
- **stderr hygiene**: `httpx`/`httpcore` loggers capped at WARNING in
  `main()` — the mcp SDK's INFO logging otherwise announces every
  readiness probe.
- Corrections to earlier text: `Resource.create` gives PASSED attributes
  precedence over `OTEL_RESOURCE_ATTRIBUTES` (§5.1 said the opposite);
  histogram buckets are pinned in code to 0.05…300 s (the original spec
  was silent); user-facing docs are in scope (README documents the
  default-on behavior).
```

- [ ] **Step 7: Lint, format, full suite, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server
uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v
git add src/mcp-server/app/telemetry.py src/mcp-server/app/server.py tests/mcp-server/test_telemetry.py docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md
git commit -m "fix(mcp): drop generated service.instance.id and quiet probe logging"
```

---

### Task 2: Deduplicate tool spans, OTLP-ingest readiness + post-ready flush (findings 1 + 3)

**Files:**
- Modify: `src/mcp-server/app/server.py` (module level, after `mcp = MCPServer("oddyssey")`)
- Modify: `src/mcp-server/app/stack.py` (`stack_up`, new `_otlp_ingest_ready` helper + constant)
- Test: `tests/mcp-server/test_server.py` (append), `tests/mcp-server/test_stack.py` (append)
- Modify: `docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md` (append to the Revision 2026-08-23 section)

**Interfaces:**
- Consumes: `telemetry.force_flush(timeout_ms: int = 2000)` (existing); `mcp.middleware` (public list property on MCPServer, backed by the lowlevel server; the SDK prepends `OpenTelemetryMiddleware()` by default — `mcp/server/lowlevel/server.py:439` in the installed package).
- Produces: nothing later tasks rely on (final task).

- [ ] **Step 1: Write the failing test (finding 1)**

Append to `tests/mcp-server/test_server.py`:

```python
def test_sdk_otel_middleware_removed():
    # mcp 2.0 installs its own OpenTelemetryMiddleware by default, which
    # duplicated every tool span (observation report finding 1). The
    # branch's decorator span is canonical; the SDK middleware must be gone.
    assert not any(
        type(m).__name__ == "OpenTelemetryMiddleware" for m in server.mcp.middleware
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_server.py::test_sdk_otel_middleware_removed -v`
Expected: FAIL (the default middleware is present).

- [ ] **Step 3: Remove the SDK middleware (finding 1)**

In `src/mcp-server/app/server.py`, directly after `mcp = MCPServer("oddyssey")`:

```python
# mcp 2.0 ships its own OpenTelemetryMiddleware on by default, which would
# duplicate every tool span (and double the spanmetrics counts). The
# decorator span below is the canonical one - the spec froze its contract,
# and the SDK marks its middleware API as subject to change before v2
# final. Defensive: if the SDK moves the class, keep the duplicates rather
# than crash the server.
try:
    from mcp.server._otel import OpenTelemetryMiddleware

    mcp.middleware[:] = [
        m for m in mcp.middleware if not isinstance(m, OpenTelemetryMiddleware)
    ]
except Exception:  # noqa: BLE001 - degraded telemetry beats a dead server
    pass
```

- [ ] **Step 4: Run the test to verify it passes**

Run: same command as Step 2. Expected: PASS. Registration tests must still pass (`test_all_stack_tools_registered`).

- [ ] **Step 5: Write the failing tests (finding 3)**

Append to `tests/mcp-server/test_stack.py`:

```python
from oddyssey_mcp.stack import _otlp_ingest_ready


def test_otlp_ingest_ready_true_on_any_http_response():
    # Any HTTP response (even 4xx) proves the OTLP listener accepts
    # connections; only transport errors mean not-ready.
    transport = httpx.MockTransport(lambda request: httpx.Response(415))
    with httpx.Client(transport=transport) as client:
        assert _otlp_ingest_ready(client) is True


def test_otlp_ingest_ready_false_on_transport_error():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    transport = httpx.MockTransport(refuse)
    with httpx.Client(transport=transport) as client:
        assert _otlp_ingest_ready(client) is False
```

(`httpx` is already imported at the top of `test_stack.py`; merge the new
`from oddyssey_mcp.stack import ...` names into the existing import line.)

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_stack.py -v`
Expected: collection error `ImportError: cannot import name '_otlp_ingest_ready'`.

- [ ] **Step 7: Implement OTLP-ingest readiness + post-ready flush (finding 3)**

In `src/mcp-server/app/stack.py`:

Add next to the other endpoint constants:

```python
OTLP_HTTP_INGEST = "http://localhost:4318/v1/traces"
```

Add after `_probe`:

```python
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
```

In `stack_up`, replace the ready-return inside the wait loop so readiness includes OTLP ingest and the queued telemetry flushes into the newborn backend (keep the returned dict IDENTICAL):

```python
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
```

- [ ] **Step 8: Run the full unit suite**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v`
Expected: all pass (new stack tests use injected transports — no Docker touched).

- [ ] **Step 9: Integration tests (Docker required, available on this machine)**

Run: `bash integration-tests/mcp-server/run.sh`
Expected: green — the added OTLP wait must not break the lifecycle scripts (it adds at most a few poll iterations to `stack_up`).

- [ ] **Step 10: Spec revision entries**

Append to the `## Revision 2026-08-23 (post-observation fix wave)` section of the spec:

```markdown
- **Canonical tool span**: mcp 2.0's default `OpenTelemetryMiddleware` is
  removed at server construction - the decorator span (frozen contract,
  exception recording, histogram attachment) is the single tool span.
  Revisit via a new revision when the mcp v2 middleware API stabilizes;
  its inbound `_meta` trace-context extraction is the natural path for
  the §8 propagation hook.
- **"Ready" includes OTLP ingest**: `odd_stack_up` now also waits for the
  OTLP HTTP listener (`:4318/v1/traces`) to answer, then force-flushes
  queued spans into the newborn backend. Batches the exporter already
  dropped during boot remain lost - accepted residual.
```

- [ ] **Step 11: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server
uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/app/server.py src/mcp-server/app/stack.py tests/mcp-server/test_server.py tests/mcp-server/test_stack.py docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md
git commit -m "fix(mcp): single canonical tool span and otlp-ingest-aware stack readiness"
```
