# OpenTelemetry Instrumentation of `oddyssey-mcp` — Design Spec

Date: 2026-08-22
Status: approved design, pending implementation (branch `feat/mcp-otel`)
Input: investigation report by the `otel-instrumentation-expert` agent
(conversation of 2026-08-22); its findings are restated here so this spec
is self-contained.

## 1. Goal

The oddyssey MCP server (`src/mcp-server`, published as `oddyssey-mcp`)
emits its own OpenTelemetry telemetry — traces and metrics — to the local
oddyssey stack it pilots, so the product self-demonstrates ODD and its
tool operations become observable like any other service.

**In scope:** traces (tool spans, httpx probe spans, docker subprocess
spans), one duration metric, SDK bootstrap and shutdown, exporter
quieting, tests.
**Out of scope:** the OTel logs signal (Development status in Python, and
the code has no logging today), profiling (requires publishing port 4040
on the stack container — a stack change, not an instrumentation change),
inbound context propagation (MCP clients do not send `traceparent` over
stdio today; noted as a future hook in §8).

## 2. Hard constraints

1. **stdout is the JSON-RPC wire** (stdio transport). Nothing
   instrumentation-related may ever write to stdout: console exporters
   are forbidden; all diagnostics go to stderr.
2. **The backend is the service's own workload.** The stack container the
   telemetry lands in is created by `odd_stack_up` and destroyed by
   `odd_stack_down`/`odd_stack_reset`. Export failure while the stack is
   down is the NORMAL state, never an error surfaced to the client.
3. **Tool registration must not change.** The unit tests assert the exact
   tool set; instrumentation wraps handler bodies without altering names,
   docstrings, signatures, or adding tools.

## 3. Settled decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Activation | **Default-on** with in-code defaults; kill-switch `OTEL_SDK_DISABLED=true`; every `OTEL_*` env var set by the user overrides the defaults | The product self-observes out of the box; failed exports are silent (see §6) |
| 2 | Dependency placement | **Core dependencies** (not an extra) | Coherent with default-on; `http/protobuf` chosen precisely to keep the uvx cold start cheap (no `grpcio`) |
| 3 | Sampling | Keep the SDK default `parentbased_always_on`, not set explicitly | Human-driven tool calls; volume is trivial |
| 4 | Collector topology | Direct OTLP export to the stack (no collector) | otel-lgtm embeds a collector; dev-scale traffic |
| 5 | Probe spans | Keep them (bounded: 2 s polling over a ≤ 120 s boot across the probe URLs → at most ~120 spans) | They tell the stack-boot story under the `odd_stack_up` span |
| 6 | down/reset span loss | Accepted; `force_flush` before the destroying `docker` call so child spans emitted so far get a chance to land (reset wipes them anyway; down's are lost with the backend) | The alternative is a second backend, contradicting the product |
| 7 | Logs | Skipped entirely this wave (`OTEL_LOGS_EXPORTER=none`); no stdlib logging introduced beyond exporter quieting | Logs API is Development in Python; nothing to bridge today |
| 8 | Inbound propagation | Out of scope; future hook documented in §8 | No client sends context over stdio today |
| 9 | `service.instance.id` | Not set | Avoids per-session Prometheus label growth for near-zero value |
| 10 | Semconv pin | Names in this spec follow the genai semconv MCP page (status Development) as of 2026-08-22; they are FROZEN here — any upstream rename is adopted only through a new spec revision | Development-status conventions may change under us |

## 4. Packages

Added to `src/mcp-server/pyproject.toml` `[project] dependencies`, then
`uv lock --project src/mcp-server`:

| Package | Pin |
|---|---|
| `opentelemetry-api` | `1.44.0` |
| `opentelemetry-sdk` | `1.44.0` |
| `opentelemetry-exporter-otlp-proto-http` | `1.44.0` |
| `opentelemetry-instrumentation-httpx` | `0.65b0` |

(Pins read from PyPI on 2026-08-22. The release workflow's version bumps
do not touch these lines.)

## 5. Architecture

One new module, two touched files. No behavior change to any tool.

```
src/mcp-server/app/
  telemetry.py   (new)  — bootstrap, shutdown, tool decorator, docker span helper
  server.py      (mod)  — setup call in main(), decorator on the 4 handlers
  stack.py       (mod)  — docker calls routed through the span helper; force_flush before destroy
```

### 5.1 `app/telemetry.py` (new)

- `setup_telemetry() -> Callable[[], None]` — called once at the top of
  `main()`. Honors `OTEL_SDK_DISABLED=true` (returns a no-op shutdown and
  installs nothing). Otherwise:
  - Builds a `Resource` with `service.name="oddyssey-mcp"` (overridable
    via `OTEL_SERVICE_NAME`), `service.version` from
    `importlib.metadata.version("oddyssey-mcp")`, and
    `deployment.environment.name="local"` — user-provided
    `OTEL_RESOURCE_ATTRIBUTES` merge on top per SDK rules.
  - Applies in-code defaults ONLY for env vars the user did not set:
    `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`,
    `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`,
    `OTEL_SEMCONV_STABILITY_OPT_IN=http`.
  - Installs a `TracerProvider` + `BatchSpanProcessor` + OTLP HTTP span
    exporter, and a `MeterProvider` + periodic OTLP HTTP metric reader.
  - Instruments httpx via `HTTPXClientInstrumentor().instrument()`.
  - Quiets the exporters: sets the `opentelemetry` logger tree to
    `CRITICAL` so retry/connection failures (stack down = normal) never
    spam the client's stderr view. Python logging defaults to stderr, so
    even that residual output never touches stdout.
  - Returns a `shutdown()` that calls `TracerProvider.shutdown()` and
    `MeterProvider.shutdown()`; `main()` runs it in a `finally` around
    `mcp.run()` so the last batch flushes before the process exits.
- `traced_tool(fn) -> fn` — decorator for the 4 handlers, applied UNDER
  `@mcp.tool()` and using `functools.wraps` so name/docstring/signature
  reach MCP registration unchanged. Per call it:
  - opens a span named `tools/call {tool_name}` (e.g.
    `tools/call odd_stack_up`), kind `SERVER`, attributes
    `mcp.method.name="tools/call"`, `gen_ai.tool.name=<tool_name>`,
    `network.transport="pipe"`, `jsonrpc.protocol.version="2.0"`;
  - records the elapsed time into the histogram (below);
  - on exception: records it on the span, sets status ERROR, re-raises —
    the MCP error path is untouched.
- Histogram: `mcp.server.operation.duration`, unit `s`, attributes
  `mcp.method.name` and `gen_ai.tool.name` (4 values — bounded).
- `docker_span(verb: str, *, exit_code: int | None) -> context manager`
  (or an equivalent wrapper) producing spans `oddyssey.docker.run`,
  `oddyssey.docker.start`, `oddyssey.docker.rm`, `oddyssey.docker.inspect`
  with attributes `oddyssey.docker.container="oddyssey-lgtm"` and
  `oddyssey.docker.exit_code`. No arguments, no output captured — bounded
  values only (no semconv exists for subprocess execution; names follow
  the OTel custom-naming rules with an app prefix).
- `force_flush() -> None` — flushes the span processor with a short
  timeout (~2 s); called by `stack.py` right before the `docker rm` of
  `down`/`reset`. Failure is swallowed.
- When the SDK is disabled, `traced_tool` and `docker_span` become
  pass-throughs (the API's no-op tracer covers this naturally).

### 5.2 `app/server.py` (modified)

- `main()`: `shutdown = setup_telemetry()` first, `try: mcp.run()
  finally: shutdown()`.
- Each of the 4 handlers gains `@traced_tool` beneath `@mcp.tool()`.
  Nothing else changes.

### 5.3 `app/stack.py` (modified)

- Every `subprocess.run(["docker", ...])` call is wrapped in the
  matching `docker_span(...)`, recording the exit code.
- `stack_down` and `stack_reset` call `telemetry.force_flush()`
  immediately before the container-destroying docker command.
- The httpx readiness probes need no code change (library
  instrumentation).

## 6. Failure semantics

- Stack down → OTLP exports fail → BatchSpanProcessor drops after
  retries. No exception escapes to a tool result, no stdout output, no
  stderr noise (logger tree at CRITICAL). `odd_stack_status` on a down
  stack must return exactly what it returns today.
- Telemetry never changes a tool's return value, error message, or
  timing beyond the negligible span overhead.
- `OTEL_SDK_DISABLED=true` restores the exact pre-instrumentation
  behavior (no providers installed, no httpx patching).

## 7. Testing

**Unit (`tests/mcp-server/`, pytest, no Docker):**
- Existing tool-set test keeps passing unchanged (registration intact).
- `test_telemetry_disabled`: with `OTEL_SDK_DISABLED=true`,
  `setup_telemetry()` installs no global providers and returns a working
  no-op shutdown.
- `test_traced_tool_span`: with an in-memory span exporter
  (`InMemorySpanExporter` + `SimpleSpanProcessor`), calling a decorated
  dummy tool produces one span named `tools/call <name>`, kind SERVER,
  with the §5.1 attributes; the function's return value passes through;
  an exception is re-raised with span status ERROR.
- `test_docker_span`: the wrapper emits `oddyssey.docker.<verb>` with
  the exit-code attribute.
- `test_no_stdout`: capsys-style assertion that `setup_telemetry()` and
  a traced call write nothing to stdout.

**Integration (existing harness, Docker required):** the current
`integration-tests/mcp-server/run.sh` must stay green as-is. A follow-up
verification uses the ODD loop itself:

1. `odd_stack_up` (breaks the egg deliberately).
2. Drive `odd_stack_status` (up), `docker stop` + `odd_stack_status`
   (down path), `odd_stack_up` again.
3. `/odd-observe` on `oddyssey-mcp` against the local stack: Tempo shows
   `service.name="oddyssey-mcp"` traces with tool → httpx/docker span
   trees; Prometheus shows `mcp_server_operation_duration` series;
   resource attributes carry `service.version` and
   `deployment.environment.name=local`.
4. Negative: MCP Inspector session shows no stray stdout bytes;
   `odd_stack_down` returns normally (its own span is lost by
   construction — expected).

## 8. Future hooks (explicitly not now)

- **Inbound trace context**: if an MCP client ever forwards W3C context
  (e.g. via `_meta`), extract it in `traced_tool` so client sessions
  parent the tool spans.
- **Logs**: introduce stdlib logging to stderr, then the OTel
  `LoggingHandler` bridge once the Python logs API stabilizes.
- **Profiling**: `pyroscope-io` push, gated on the stack container
  publishing port 4040.
- **Remote export**: works already via user-set `OTEL_*` env vars
  (endpoint + `OTEL_EXPORTER_OTLP_HEADERS` from a secret source); no
  code change anticipated.
