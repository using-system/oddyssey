---
services: [oddyssey-mcp]
stack: local
environment: local
mode: drive
window: 2026-08-22T21:54:26Z/2026-08-22T21:56:35Z
run_name: mcp-otel-instrumentation-verification
date: 2026-08-22
---

# Observation report — oddyssey-mcp OpenTelemetry instrumentation verification

## 1. Mission and run record

- **Service:** `oddyssey-mcp` — the MCP server built from branch `feat/mcp-otel`
  (HEAD `4bacc36`), launched as `uv run --project src/mcp-server oddyssey-mcp`
  (stdio JSON-RPC), NOT the installed PyPI 1.1.0. Driven directly over stdio by
  a purpose-built JSON-RPC driver (no session MCP tools used).
- **Environment:** local — the oddyssey stack (`oddyssey-lgtm`,
  `grafana/otel-lgtm:0.30.2`, Grafana 13.1.3 on :3000, OTLP :4317/:4318).
  Backend: Grafana; query CLI: gcx v1.0.0 (isolated `GCX_CONFIG` context per the
  `setup-local-stack` skill; datasource UIDs `prometheus`/`tempo`/`loki`/`pyroscope`).
- **Mode:** drive (caller-specified scenario, including an explicitly authorized
  Docker-engine failure injection). **Window:** the scenario's own bounds,
  2026-08-22T21:54:26Z → 2026-08-22T21:56:35Z. **Focus:** end-to-end verification
  of the branch's OTel instrumentation per spec
  `docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md` §7.
- **Baseline:** **no previous report** — `.odd/observe-run-reports/` did not exist
  (first run). Comparisons are within-run. Expected-by-design non-anomalies per
  the mission: down/reset span loss, export failures while the stack is down,
  ~10 s metric flush, ≤60 s trace-search lag.
- **Defaults applied:** none beyond the contract's (window = scenario bounds in
  drive mode); every other field was caller-specified.

### Scenario record (verbatim)

```text
Scenario: mcp-otel-instrumentation-verification (single stdio session, 18 tool calls)
Server:   uv run --project src/mcp-server oddyssey-mcp   (cwd = repo root, env inherited,
          telemetry default-on -> OTLP http/protobuf to http://localhost:4318)
Driver:   scratchpad/drive_scenario.py — newline-delimited JSON-RPC on stdin/stdout:
          initialize (protocolVersion 2025-06-18) -> notifications/initialized ->
          tools/list -> tools/call sequence below. Raw stdout bytes and stderr
          captured to files for wire-cleanliness verification.
Prep:     docker rm -f -v oddyssey-lgtm   (force the cold docker-run path)
          uv sync --project src/mcp-server (pre-warm; keeps build noise out of the run)
Warmup:   none discarded (lifecycle operations are one-shot by nature)
Started (UTC): 2026-08-22T21:54:26Z
Ended   (UTC): 2026-08-22T21:56:35Z

Phase A — nominal lifecycle
  21:54:27  odd_stack_status   ->  running:false            (44.4 ms)
  21:54:31  odd_stack_up       ->  running:true  COLD start (4299.2 ms)
  21:54:31  odd_stack_status   ->  running:true             (20.2 ms)
  21:54:36  odd_stack_reset    ->  running:true  wipe+fresh (4621.7 ms)
  sleep 12 s (let reset-tail span batches export into the fresh stack)

Phase B — failure case (authorized)
  21:54:48  osascript -e 'quit app "Docker"'   (rc 0 but engine survived — see deviation)
  21:56:16  pkill -f com.docker.backend        (engine killed; down detected 21:56:17)
  21:56:20  odd_stack_status   ->  running:false            (27.1 ms)
  21:56:20  odd_stack_up       ->  isError:true             (240.4 ms)
            "Error executing tool odd_stack_up: docker run failed: docker: failed
             to connect to the docker API at unix:///Users/usingsystem/.docker/..."
  21:56:21  odd_stack_status   ->  running:false            (19.5 ms)
  21:56:21  open -a Docker;  engine stable 21:56:27 (docker info OK twice)

Phase C — recovery + measured phase
  21:56:32  odd_stack_up       ->  running:true  WARM       (2220.2 ms)
  21:56:34  odd_stack_status x 10 -> running:true           (17.4–20.2 ms each)
  21:56:35  stdin closed -> server exit rc 0 (shutdown() flushed spans + metrics
            into the live stack)

Not reproducible exactly: Docker Desktop quit/restart timing; the AppleScript quit
was ignored in this run (deviation above), so the engine was killed with
`pkill -f com.docker.backend` — this kills the engine API and host port proxies but
leaves the Linux VM (and the stack container inside it) running, i.e. an
"engine-down, container-alive" failure mode rather than a full VM stop.
A first attempt (21:46:41–21:47:33Z, same phase-A results: cold up 4299 ms, reset
4650 ms) aborted in phase B on a driver bug (uncaught `docker info` hang); its
partial record is driver data, not service data — no service misbehavior involved.
```

Sample-size note: 14 `odd_stack_status` calls total — below the ≥30 threshold for
quoting p95 from raw samples; quantiles below are bucket facts or backend
estimates and labeled as such.

## 2. Observed behavior

Per-operation summary (server-side histogram `mcp_server_operation_duration_seconds_*`,
cross-checked against the driver's client-side timings; probes = httpx GET child
spans per request):

| Operation | Requests | Rate | p50 | p95 | p99 | Error % | Probes/docker per req | Notable |
|---|---|---|---|---|---|---|---|---|
| `tools/call odd_stack_status` | 14 | burst (10 in 190 ms) | ~19 ms (mean 19.5 ms; spanmetrics p50 est. 24 ms) | n<30, not quoted; all 14 ≤ 50 ms bucket | — | 0 % | 2 httpx probes | client-observed 17.4–44.4 ms |
| `tools/call odd_stack_up` | 3 | one-shot | — | — | — | 33 % (1/3, injected engine-down) | cold: 1 docker run + inspect + probe loop; warm: inspect+start+4 probes | cold 4.30 s, warm 2.22 s, failed 0.24 s; buckets ≤0.25:1, ≤2.5:2, ≤5:3 |
| `tools/call odd_stack_reset` | 1 | one-shot | — | — | — | 0 % | rm + run + inspect + probe loop | 4.62 s; metric-visible, trace-invisible (see A3) |
| httpx `GET` readiness probes | 28 OK (+2 ERROR spans in Tempo) | — | 1.2–4.1 ms per probe | — | — | errors only during boot/engine-down | — | `http_client_request_duration_seconds_count{http_response_status_code="200"} = 28` |

Evidence queries (gcx, isolated local context):

- Counts/sums: `gcx metrics query 'mcp_server_operation_duration_seconds_count'` →
  status 14, up 3, reset 1; `..._sum` → status 0.27332 s, up 6.75103 s, reset
  4.62008 s. Sum cross-check vs driver: up 6.751 s server-side vs 6.758 s
  client-side (4.2992+0.2404+2.2202) — RPC overhead ≈ 2 ms/call.
- Buckets: `..._bucket{gen_ai_tool_name="odd_stack_status"}` → all 14 in `le="0.05"`;
  `{gen_ai_tool_name="odd_stack_up"}` → `0.25=1, 2.5=2, 5=3` — the injected failure
  (240 ms), warm recovery (2.2 s) and cold start (4.3 s) individually resolvable:
  the seconds-scale advisory buckets (0.05…300) landed exactly as speced.
- httpx: `http_client_request_duration_seconds_count` → one series,
  `{http_response_status_code="200"}` = 28. Exact reconciliation: 11 status calls
  returning `running:true` × 2 probes = 22, plus one successful final probe pair
  inside each of cold up, reset's internal up, warm up = 6 → 28. The 28 stderr
  `HTTP Request: ... 200 OK` lines match 1:1 (cross-confirmed, three ways).
- Single landed metric point at ts 1787435794.916 = 21:56:34.916Z (query:
  `timestamp(mcp_server_operation_duration_seconds_count{gen_ai_tool_name="odd_stack_reset"})`)
  — cumulative temporality carried phases A and B **through** the reset wipe and
  the engine-down export blackout in one shutdown-flush export. The periodic
  60 s export (~21:55:27) fell in the blackout and was dropped, silently, as designed.

Traces (Tempo, `gcx traces query '{resource.service.name="oddyssey-mcp"}' --limit 40`):
11 traces landed — the 10 final status calls (16–19 ms) and the warm recovery up
(2217 ms, trace `ade79c8f9beef60264d17db90226018`). Exemplar span trees:

- **Status exemplar** `82873820edcf012d5acc8270dbf09987` (17 ms): root
  `tools/call odd_stack_status` SERVER span, scope `mcp-python-sdk`
  (`gen_ai.operation.name=execute_tool`, `mcp.protocol.version=2025-06-18`,
  `jsonrpc.request.id=18`) → child `tools/call odd_stack_status` SERVER span,
  scope `oddyssey-mcp` (`mcp.method.name=tools/call`,
  `gen_ai.tool.name=odd_stack_status`, `network.transport=pipe`,
  `jsonrpc.protocol.version=2.0` — the spec §5.1 attributes, all present) →
  2 httpx CLIENT `GET` spans (prometheus ready 2.6 ms, tempo ready 1.2 ms, both
  200). ~13 of the 17 ms are outside the httpx spans (per-call `httpx.Client`
  construction + 2 TCP connects — no pooling across probes).
- **Warm-up exemplar** `ade79c8f9beef60264d17db90226018` (2217 ms): sdk root →
  app span → `oddyssey.docker.inspect` (44 ms, `oddyssey.docker.exit_code=0`,
  `oddyssey.docker.container=oddyssey-lgtm`) → `oddyssey.docker.start` (128 ms,
  exit_code 0) → 2 httpx probes with `STATUS_CODE_ERROR`,
  `error.type=ReadError`, full `exception` events ("[Errno 54] Connection reset
  by peer" — the port proxy not yet re-established after the engine restart) →
  2 s poll wait → 2 probes 200. The whole stack-boot story is in one tree.
- Resource attributes on every trace: `service.name=oddyssey-mcp`,
  `service.version=1.1.0`, `deployment.environment.name=local`,
  `telemetry.sdk.version=1.44.0` — **plus `service.instance.id`
  74fc0cc6-2b90-45e3-a02c-827423f5559b** (see A2).

Span-derived metrics (Tempo metrics-generator) and service graph:
`traces_spanmetrics_calls_total{service="oddyssey-mcp"}` → `tools/call
odd_stack_status`=20 (for 10 landed calls — double-counted, see A1), `tools/call
odd_stack_up`=2 (1 call), `GET`=24 (22 OK + 2 error), `oddyssey.docker.inspect`=1,
`oddyssey.docker.start`=1. `traces_service_graph_request_total` →
`user → oddyssey-mcp` = 11; no outbound edge (the Grafana peer is uninstrumented,
so probe CLIENT spans produce no client-server pair).

Wire cleanliness (failure case core): raw stdout capture = 4456 bytes, 20 lines,
**20/20 parse as JSON-RPC 2.0, 0 stray bytes** — including during the
engine-down window. The failed `odd_stack_up` came back as a proper tool result
(`isError: true`, message quoted in §1), the server survived it and served 11
more calls, and exited rc 0 on stdin EOF. stderr contained **zero**
opentelemetry/exporter lines (logger-tree silencing held through the export
blackout) but 28 `HTTP Request:` INFO lines (see A4).

Spec §7 focus checklist — all core claims verified:

| Spec claim | Verdict | Evidence |
|---|---|---|
| Tempo traces with `service.name="oddyssey-mcp"` | PASS | 11 traces, search query above |
| Span names `tools/call odd_stack_*` + §5.1 attributes | PASS | exemplars above |
| httpx probe child spans | PASS | 2 per status; error+success mix under up |
| `oddyssey.docker.*` spans with `oddyssey.docker.exit_code` | PASS (inspect, start) | warm-up exemplar; `run`/`rm` exercised but their traces lost by design (wiped/blackout) |
| `mcp_server_operation_duration_*` seconds-scale buckets | PASS | bucket queries above |
| Resource `service.version` + `deployment.environment.name=local` | PASS | target_info + trace resources |
| Failure: server alive, clean JSON-RPC, silent export degradation | PASS | wire capture + stderr counts |

## 3. Anomalies and probable causes

| # | Finding | Severity | Confidence | Evidence | Expected gain |
|---|---|---|---|---|---|
| A1 | Every tool call emits TWO nested `tools/call <tool>` SERVER spans: mcp 2.0.0 SDK's own instrumentation (scope `mcp-python-sdk`) + the branch's decorator (scope `oddyssey-mcp`) | medium | confirmed | exemplar trees §2; `traces_spanmetrics_calls_total{span_name="tools/call odd_stack_status"}`=20 for 10 calls | one SERVER span per call; RED metrics stop double-counting (20→10) |
| A2 | `service.instance.id` present on all telemetry despite spec decision #9 ("Not set") — opentelemetry-sdk 1.44.0 `Resource.create()` generates a UUID4 by default | medium | confirmed | trace resource + Prometheus label `service_instance_id="74fc0cc6-…"`; `count({service_instance_id="74fc0cc6-…"})` = **63 series for this one session**; repro: `Resource.create({})` returns a fresh `service.instance.id` UUID | stop ~63-series-per-session Prometheus growth (every MCP client session = new UUID) |
| A3 | The `odd_stack_reset` trace is entirely absent — not just pre-destroy children: the root span and post-recreate children (docker run/inspect, probes) never landed although the server kept exporting for 100 s to a stack whose readiness probes returned 200 | low (design-adjacent, but wider loss than spec §3 decision 6 implies) | absence confirmed; cause suspected | `gcx traces query '{name="tools/call odd_stack_reset"}'` → `[]`; cross-signal: `..._count{gen_ai_tool_name="odd_stack_reset"}`=1 (metric-visible, trace-invisible); Phase-C spans exported to the same container 2 min later landed fine | reset/up traces land; suspected cause: OTLP ingest inside otel-lgtm becomes ready later than the Grafana-proxy readiness the probes check, and the Python OTLP HTTP exporter does not retry connection errors — probe the confirm: after `odd_stack_reset`, POST to `:4318/v1/traces` and time when it first accepts |
| A4 | 28 `HTTP Request: … 200 OK` INFO lines on stderr — `MCPServer` (`mcp/server/mcpserver/server.py:253 configure_logging(...)`) installs an INFO stderr handler, exposing httpx's request logging | low | confirmed | stderr capture (28 lines = exactly the 28 successful probes); grep of the installed mcp package | stderr quiet in MCP client logs (28→0 lines/session) |
| A5 | Failed probes produce ERROR spans but no `http_client_request_duration` series (no `error.type` metric dimension) — failures are trace-only | low | confirmed absence, single-signal by nature | series listing shows only the `http_response_status_code="200"` series while Tempo holds 2 ReadError GET spans in the same window | error-rate PromQL on probes possible; today it needs TraceQL |
| A6 | Pyroscope query path degraded: `gcx profiles labels -l service_name` → HTTP 500 "failed to open object … block.bin: read 0 bytes" (twice) | low (environment, not the observed service) | confirmed error, cause suspected (segment corrupted when run-1's interrupted engine quit killed the container, `Exited (255)`) | error payload quoted; `list-profile-types` works (returns the stack's own Go profile types) | clean profile queries after next `odd_stack_reset` |

## 4. Improvement opportunities

1. **Deduplicate the tool span** (A1). Either drop the custom span and keep only
   the SDK's (then move the §5.1 frozen attributes + duration histogram recording
   onto it or alongside it), or suppress the SDK instrumentation. Expected gain:
   span volume per tool call −50 %; `traces_spanmetrics_calls_total{span_name=~"tools/call.*"}`
   equals the true call count. Proof query after fix: drive 10 status calls →
   `traces_spanmetrics_calls_total{span_name="tools/call odd_stack_status"}`
   increases by 10 (today: 20).
2. **Settle `service.instance.id`** (A2): pass an explicit override in
   `Resource.create(...)` (empty/stable value) or accept and document the
   per-session UUID. Gain if cleared: −63 new Prometheus series per MCP session
   (measured: `count({service_instance_id="74fc0cc6-…"})` = 63). Proof query:
   start two server sessions, `count(count by (service_instance_id)(target_info{service_name="oddyssey-mcp"}))`
   stays 1 (today: grows by 1 per session).
3. **Make stack readiness include OTLP ingest** (A3): have `stack_up` (and hence
   `reset`) also wait until `:4318` accepts an OTLP POST before returning ready
   — cheap, uses the exporter's own path. Gain: the reset/up trace tail (root +
   docker run/inspect + probes) lands in the fresh stack instead of being
   dropped. Proof query after fix: `gcx traces query '{name="tools/call odd_stack_reset"}'`
   → ≥1 trace (today: 0, while the count metric says 1 call).
4. **Quiet httpx INFO logging** (A4): `logging.getLogger("httpx").setLevel(logging.WARNING)`
   in `setup_telemetry()` (or document the mcp `log_level` setting). Gain:
   stderr lines per session 28 → 0. Proof: rerun scenario, count stderr
   `HTTP Request:` lines.
5. **Bound exception payloads on boot-poll probes** (optional): each failed probe
   span carries a full stacktrace event (~1.5 KB); a worst-case 120 s boot ≈ up
   to ~120 such spans. Consider `record_exception=False` on the httpx
   instrumentor or accepting the cost. Gain: ~180 KB less span payload per
   worst-case boot.

## 5. Telemetry gaps

- **Logs signal: absent** (spec-scoped out this wave). Evidence:
  `gcx logs labels -o agents` → `data: null`;
  `gcx logs series -M '{service_name="oddyssey-mcp"}'` → `[]`. Consequence:
  nothing to correlate by trace ID in Loki.
- **Profiles: absent for oddyssey-mcp** (spec-scoped out; stack does not publish
  :4040 for push). Evidence: `gcx profiles list-profile-types` returns only the
  LGTM stack's own Go profile types; `service_name` label query 500s (A6).
- **Lost-by-construction traces this run** (expected, quantified): phase-A
  pre-reset traces (cold `odd_stack_up` incl. its `oddyssey.docker.run` span,
  2 status traces) wiped by reset; phase-B failure spans (2 status + the ERROR
  `odd_stack_up`) dropped in the export blackout — `gcx traces query
  '{resource.service.name="oddyssey-mcp" && status=error}'` finds no tool-level
  ERROR span, only the probe ReadErrors inside the recovery trace. The duration
  histogram is the only surviving record of those calls (counts 14/3/1 vs 11
  traces).
- **`oddyssey.docker.run` / `oddyssey.docker.rm` spans unverified in Tempo** —
  exercised (cold up, reset) but only in the wiped/blacked-out traces; fixing
  improvement 3 would make `run` verifiable after a reset.
- **No outbound service-graph edge**: probe CLIENT spans point at an
  uninstrumented Grafana, so `traces_service_graph_request_total` has no
  `oddyssey-mcp → grafana` edge — inherent to single-sided instrumentation, note
  only.
- Gaps are design-scoped (spec §1/§8), not instrumentation defects — no
  `otel-instrumentation-expert` handoff needed beyond the §6 decisions.

## 6. Decisions the spec must settle

1. **Which `tools/call` span is canonical** now that mcp 2.0.0 ships its own
   (scope `mcp-python-sdk`, `gen_ai.operation.name=execute_tool`,
   `mcp.protocol.version`, `jsonrpc.request.id`) — keep SDK + retarget the
   frozen §5.1 attributes/histogram, or suppress SDK and keep the decorator?
   The spec froze semconv names (decision #10) before the SDK grew
   instrumentation; the two attribute sets differ.
2. **`service.instance.id` policy** (decision #9 is currently unenforceable as
   written): explicitly clear it, pin it stable, or accept per-session UUIDs and
   their ~63-series/session cost?
3. **Readiness contract of `odd_stack_up`/`odd_stack_reset`**: should "ready"
   include OTLP ingest accepting data (improvement 3), or is the trace-tail loss
   after reset acceptable spec behavior?
4. **stderr verbosity for MCP clients**: is INFO-level request logging desirable
   diagnostics or noise (A4)? stdout is contractually clean either way.
5. **Failure-case telemetry durability**: is metric-only survival of
   engine-down operations (via cumulative temporality) sufficient, or is a
   bounded file/disk fallback for spans worth its complexity? (Today: by design,
   sufficient per spec §6 — restating for an explicit sign-off.)

## 7. Measurement protocol for the fix

Replay (drive mode, same machine, image `grafana/otel-lgtm:0.30.2` already pulled,
uv env pre-synced):

1. Prep: `docker rm -f -v oddyssey-lgtm`; `uv sync --project src/mcp-server`.
2. Run the driver (`drive_scenario.py` semantics, recorded verbatim in §1): one
   stdio session of `uv run --project src/mcp-server oddyssey-mcp`; JSON-RPC
   `initialize` (2025-06-18) → `notifications/initialized` → `tools/list` →
   phase A `status, up, status, reset` + 12 s sleep → phase B kill engine
   (`pkill -f com.docker.backend`; down = backend procs gone AND :3000 dead) →
   `status, up, status` → `open -a Docker`, wait 2 consecutive `docker info` OKs
   → phase C `up` + 10× `status` → close stdin. Capture raw stdout, stderr, and
   per-call timings.
3. Waits before querying: ≥10 s after server exit for metrics; ≤60 s for Tempo
   search (cross-check any suspicious empty search with a `gcx traces get` by ID).
4. Environment note for comparability: phase B must use the engine-kill (not a
   VM stop) so the stack container survives with its data, and the final queries
   must run with the stack UP (it is left up by the scenario).

Verification checks (before-values from this run → pass criterion):

| Check | Query | Before | Pass after fix |
|---|---|---|---|
| Tool-span dedup (A1) | `traces_spanmetrics_calls_total{span_name="tools/call odd_stack_status", service="oddyssey-mcp"}` after the 10-call phase | 20 | equals landed call count (10) |
| One SERVER span per call (A1) | `gcx traces get <any status trace> --llm` | 2 nested `tools/call` SERVER spans | 1 |
| Instance-id cardinality (A2) | `count(count by (service_instance_id)(target_info{service_name="oddyssey-mcp"}))` after 2 sessions | +1 per session (63 series each) | constant across sessions (or explicit spec acceptance) |
| Reset trace lands (A3/impr. 3) | `gcx traces query '{name="tools/call odd_stack_reset"}'` | 0 traces (vs `..._count{gen_ai_tool_name="odd_stack_reset"}`=1) | ≥1 trace with docker rm/run children |
| stderr noise (A4) | count of `HTTP Request:` lines in captured stderr | 28 | 0 |
| Wire cleanliness (must not regress) | raw stdout capture: non-JSON-RPC lines | 0 of 20 | 0 |
| Failure semantics (must not regress) | phase-B `odd_stack_up` response | tool result `isError:true`, server survives, exit rc 0 | identical |
| Histogram integrity (must not regress) | `mcp_server_operation_duration_seconds_count` by `gen_ai_tool_name`; status buckets | 14/3/1; all status ≤0.05 | counts match the driver record; buckets stay seconds-scale (0.05…300) |
| httpx probe accounting (must not regress) | `http_client_request_duration_seconds_count{http_response_status_code="200"}` | 28 | equals successful-probe arithmetic of the replay |

Environment left as found and ready for the next measurement: `oddyssey-lgtm`
Up (healthy), Grafana/gcx online (`gcx config check` ✔), Docker engine restored
(`docker info` OK). The stack currently holds exactly this run's phase-C
telemetry plus the cumulative metrics point — a follow-up fix run can either
reset for a clean slate or reuse it as the "before" side.
