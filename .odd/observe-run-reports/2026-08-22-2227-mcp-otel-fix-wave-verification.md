---
services: [oddyssey-mcp]
environment: local
mode: drive
window: 2026-08-22T22:27:45Z/2026-08-22T22:28:19Z
run_name: mcp-otel-fix-wave-verification
date: 2026-08-22
---

# Observation report — oddyssey-mcp fix-wave verification (replay of 2026-08-22-2154)

## 1. Mission and run record

- **Service:** `oddyssey-mcp` — MCP server built from branch `feat/mcp-otel`,
  HEAD `24d1636` (fix wave on top of baseline HEAD `4bacc36`: `e0797ea` "drop
  generated service.instance.id and quiet probe logging", `24d1636` "single
  canonical tool span and otlp-ingest-aware stack readiness"). Launched as
  `uv run --project src/mcp-server oddyssey-mcp` (stdio JSON-RPC), driven by a
  purpose-built driver — the session's installed PyPI 1.1.0 MCP tools were not
  used.
- **Environment:** local — oddyssey stack (`oddyssey-lgtm`,
  `grafana/otel-lgtm`, Grafana 13.1.3 on :3000, OTLP :4317/:4318). Backend:
  Grafana; query CLI: gcx (isolated `GCX_CONFIG` per the `setup-local-stack`
  skill; datasource UIDs `prometheus`/`tempo`/`loki`/`pyroscope`).
- **Mode:** drive — verbatim replay of the baseline's §7 measurement protocol,
  including the authorized Docker-engine kill (`pkill -f com.docker.backend`)
  and required engine restore. **Window:** the scenario's own bounds,
  2026-08-22T22:27:45Z → 2026-08-22T22:28:19Z. **Focus:** rule on every §7
  verification check, every anomaly (A1–A6), and every telemetry gap of the
  baseline report.
- **Baseline (recalled as directed by the mission):**
  `.odd/observe-run-reports/2026-08-22-2154-mcp-otel-instrumentation-verification.md`
  — its §7 before-values and pass criteria are the yardstick for every number
  below. Expected-by-design non-anomalies per the mission: export failures
  while the engine/stack is down, ~10 s metric flush, ≤60 s trace-search lag,
  down-span loss.
- **Defaults applied:** none beyond the contract's (window = scenario bounds in
  drive mode); all other fields caller-specified.

### Scenario record (verbatim)

```text
Scenario: mcp-otel-fix-wave-verification (single stdio session, 18 tool calls —
          replay of 2026-08-22-2154 §7)
Server:   uv run --project src/mcp-server oddyssey-mcp   (cwd = repo root, env
          inherited, telemetry default-on -> OTLP http/protobuf to :4318)
Driver:   scratchpad/drive_scenario.py — newline-delimited JSON-RPC on
          stdin/stdout: initialize (protocolVersion 2025-06-18) ->
          notifications/initialized -> tools/list -> tools/call sequence below.
          Raw stdout bytes and stderr captured to files.
Prep:     docker rm -f -v oddyssey-lgtm  (container did not exist — cold path
          guaranteed);  uv sync --project src/mcp-server (pre-warmed)
Warmup:   none discarded (lifecycle operations are one-shot by nature)
Started (UTC): 2026-08-22T22:27:45Z
Ended   (UTC): 2026-08-22T22:28:19Z

Phase A — nominal lifecycle
  22:27:46  odd_stack_status   ->  running:false            (39.6 ms)
  22:27:50  odd_stack_up       ->  running:true  COLD start (4291.3 ms)
  22:27:50  odd_stack_status   ->  running:true             (20.5 ms)
  22:27:55  odd_stack_reset    ->  running:true  wipe+fresh (4678.9 ms)
  sleep 12 s

Phase B — failure case (authorized)
  22:28:07  pkill -f 'com[.]docker[.]backend'  (rc 0; down detected 22:28:09 =
            backend procs gone AND :3000 dead)
  22:28:09  odd_stack_status   ->  running:false            (17.6 ms)
  22:28:09  odd_stack_up       ->  isError:true             (239.0 ms)
            "Error executing tool odd_stack_up: docker run failed: docker:
             failed to connect to the docker API at unix:///Users/usingsystem/
             .docker/run/docker.sock ..."  (same failure text as baseline)
  22:28:09  odd_stack_status   ->  running:false            (22.4 ms)
  22:28:09  open -a Docker;  engine stable 22:28:16 (2 consecutive docker info OKs)

Phase C — recovery + measured phase
  22:28:19  odd_stack_up       ->  running:true  WARM       (2208.6 ms)
  22:28:19  odd_stack_status x 10 -> running:true           (18.2–23.5 ms each)
  22:28:19  stdin closed -> server exit rc 0 (shutdown flush into live stack)

Deviation vs baseline record: the baseline's failed `osascript quit "Docker"`
attempt was not replayed — the baseline's own §7 protocol codifies the direct
pkill. Consequence: this run's reset→kill gap is 12 s (the sleep), where the
baseline's was ~100 s (its AppleScript detour); phase-B blackout here ~10 s vs
~15 s. Same engine-kill failure mode (engine API + port proxies dead, Linux VM
and container alive), same machine, same image.

Post-scenario targeted probes (NOT part of the verbatim replay, run after all
main-run queries were recorded; both mini_session.py = initialize -> one
tools/call -> stdin close):
  P1  ~22:36Z  second server session, 1x odd_stack_status (50.1 ms), exit rc 0
      — the A2 "two sessions" cardinality check.
  P2  ~22:38Z  third server session, 1x odd_stack_reset (4698.5 ms), exit rc 0
      — the A3 confirm: a reset with NO engine kill afterwards. Wipes the
      stack's main-run telemetry (numbers below were all recorded first).
```

Sample-size note: 14 `odd_stack_status` calls — below the ≥30 threshold; the
quantiles quoted are bucket facts or backend estimates and labeled as such.

## 2. Observed behavior

| Operation | Requests | Rate | p50 | p95 | p99 | Error % | Probes/docker per req | Notable |
|---|---|---|---|---|---|---|---|---|
| `tools/call odd_stack_status` | 14 | burst (10 in ~220 ms) | ~21 ms (server mean 21.3 ms; spanmetrics p50 est. 23.3 ms, n=12) | n<30, not quoted; all 14 ≤ 0.05 bucket (spanmetrics p95 est. 31 ms) | — | 0 % | 2 httpx probes | client-observed 17.6–39.6 ms |
| `tools/call odd_stack_up` | 3 | one-shot | — | — | — | 33 % (1/3, injected engine-down) | cold: rm? no—run+inspect+probes+OTLP-ready POST; warm: inspect+start+4 probes+POST | cold 4.29 s, warm 2.21 s, failed 0.24 s; buckets ≤0.25:1, ≤2.5:2, ≤5:3 |
| `tools/call odd_stack_reset` | 1 | one-shot | — | — | — | 0 % | rm+run+inspect+probes+OTLP-ready POST | 4.68 s; trace lost to the 12 s-later engine kill (see A3) |
| httpx `GET` probes | 28 OK + 6 ERROR spans | — | 1.4–10.4 ms per probe | — | — | errors only during boot/engine-down | — | `..._count{http_response_status_code="200"}` = 28 |
| httpx `POST :4318/v1/traces` (new: OTLP-ready probe) | 3 (all 415 by design) | — | 2.2–3.3 ms | — | — | 415 = "endpoint parsing requests" signal | 1 per successful up/reset | new series `{http_response_status_code="415", error_type="415"}` = 3 |

Evidence queries (gcx, isolated local context):

- Counts: `gcx metrics query 'mcp_server_operation_duration_seconds_count'` →
  status 14, up 3, reset 1 (identical to baseline). Sums: status 0.29770 s,
  up 6.73379 s, reset 4.67686 s. Cross-check vs driver client-side: up
  6.7338 s server vs 6.7389 s client (4.2913+0.2390+2.2086) — RPC overhead
  ≈ 1.7 ms/call (baseline ≈ 2 ms).
- Buckets: status all 14 in `le="0.05"`; up `0.25=1, 2.5=2, 5=3` — identical
  to baseline; seconds-scale advisory buckets (0.05…300) intact.
- httpx: `http_client_request_duration_seconds_count` → GET-200 = 28, exactly
  the baseline arithmetic (11 status returning `running:true` × 2 + 3
  successful up/reset × 2 final probes), **plus the new POST-415 = 3 series**
  — one OTLP-ingest readiness POST per successful up/reset, the fix's
  fingerprint in the metrics.
- Single landed metric export at ts 1787437699.254 = 22:28:19.254Z
  (`timestamp(mcp_server_operation_duration_seconds_count)`) — the shutdown
  flush; cumulative temporality again carried all three phases through the
  wipe and the blackout. No pre-kill Prometheus sample survived (range query
  22:27:40→22:28:40 shows only lookback-carried copies of the 22:28:19.254
  sample).

Traces (`gcx traces query '{resource.service.name="oddyssey-mcp"}' --limit 40`):
**14 traces landed vs baseline's 11** — the 10 phase-C status (17–22 ms), the
warm recovery up (2206 ms, `e51704cd72aa11e2dcef8d68302b51ee`), **and the
entire phase-B failure group that the baseline lost**: both engine-down status
calls (15/21 ms) and the failed up (237 ms,
`c5616895384d0a9baa0308d36eef81ea`). Lost: the 4 phase-A calls (2 status, cold
up, reset) — wiped by reset or destroyed by the kill (see A3).

Exemplar span trees:

- **Status exemplar** `a24755709e4b40a2e3a46eebcfae930f` (17.13 ms): **a single
  root `tools/call odd_stack_status` SERVER span**, scope `oddyssey-mcp`
  (`gen_ai.tool.name=odd_stack_status`, `mcp.method.name=tools/call`,
  `network.transport=pipe`, `jsonrpc.protocol.version=2.0` — the §5.1
  attributes) → 2 httpx CLIENT `GET` spans (prometheus ready 2.7 ms, tempo
  ready 1.4 ms, both 200). No `mcp-python-sdk` scope span anywhere in the
  trace (A1 fixed). ~13 of the 17 ms remain outside the httpx spans (per-call
  `httpx.Client` construction + TCP connects — unchanged from baseline).
- **Failed-up exemplar** `c5616895384d0a9baa0308d36eef81ea` (237 ms): root
  SERVER span **STATUS_CODE_ERROR** with 2 `exception` events and message
  "RuntimeError: docker run failed: … dial unix …docker.sock: connect: no such
  file or directory" → children `oddyssey.docker.inspect` (116.6 ms, exit_code
  1) and **`oddyssey.docker.run` (116.6 ms, exit_code 127)**. The baseline had
  no tool-level ERROR span in Tempo at all;
  `{resource.service.name="oddyssey-mcp" && status=error && name=~"tools/call.*"}`
  now returns this trace.
- **Warm-up exemplar** `e51704cd72aa11e2dcef8d68302b51ee` (2206.9 ms): root →
  `oddyssey.docker.inspect` (21 ms, exit 0) → `oddyssey.docker.start` (123 ms,
  exit 0) → 2 `GET` ERROR probes (`error.type=ReadError`, exception events —
  port proxy not yet re-established) → 2 s poll → 2 `GET` 200 → **`POST
  http://localhost:4318/v1/traces` → 415, the new OTLP-ingest readiness probe,
  visible in-trace** before the tool returned ready.
- Resource attributes on every trace: `service.name=oddyssey-mcp`,
  `service.version=1.1.0`, `deployment.environment.name=local`,
  `telemetry.sdk.version=1.44.0` — **and no `service.instance.id`** (A2 fixed).

Span-derived metrics (Tempo metrics-generator):
`traces_spanmetrics_calls_total{service="oddyssey-mcp"}` → `tools/call
odd_stack_status` SERVER = **12 for 12 landed status calls** (baseline: 20 for
10 — the dedup halved it exactly); `tools/call odd_stack_up` = 1 UNSET + 1
ERROR (2 landed calls); `GET` = 22 UNSET + 6 ERROR = 28; `POST` = 1 ERROR;
`oddyssey.docker.inspect` = 2, `oddyssey.docker.start` = 1,
**`oddyssey.docker.run` = 1** (first time in Tempo). GET arithmetic
cross-check: 10 C-status ×2 + 2 B-status ×2 (engine-down → ERROR) + warm-up
2 ERROR + 2 OK = 22 OK + 6 ERROR ✓. `traces_service_graph_request_total` →
`user → oddyssey-mcp` = 14 (= landed root traces); still no outbound edge
(uninstrumented Grafana peer).

Wire cleanliness: raw stdout capture = 4455 bytes, 20 lines, **20/20 parse as
JSON-RPC 2.0, 0 stray bytes** — through the engine-down window. The failed
`odd_stack_up` returned as a proper tool result (`isError: true`), the server
served 11 more calls and exited rc 0 on stdin EOF. **stderr = 0 bytes: zero
`HTTP Request:` lines (baseline 28), zero opentelemetry/exporter lines.**

### Deltas vs baseline (per operation and per finding)

| Item | Baseline | This run | Delta |
|---|---|---|---|
| status: count / mean / bucket | 14 / 19.5 ms / ≤0.05 | 14 / 21.3 ms / ≤0.05 | unchanged (mean +1.8 ms, within one-shot noise) |
| up: cold / warm / failed | 4299 / 2220 / 240 ms | 4291 / 2209 / 239 ms | unchanged (readiness POST adds ≈2–3 ms, invisible at this scale) |
| reset | 4622 ms | 4679 ms | unchanged (+1.2 %) |
| Traces landed / lost | 11 / 7 | 14 / 4 | improved — phase-B failure telemetry now survives |
| Tool SERVER spans per call | 2 | 1 | improved (A1 fixed) |
| spanmetrics status count vs calls | 20 vs 10 | 12 vs 12 | improved (A1 fixed) |
| `service.instance.id` | on all telemetry, 63 series/session | absent everywhere | improved (A2 fixed) |
| stderr lines/session | 28 | 0 | improved (A4 fixed) |
| stdout stray bytes | 0 | 0 | unchanged (held) |
| Tool-level ERROR span in Tempo | none | 1 (failed up, full exception) | new/improved |
| `oddyssey.docker.run`/`rm` in Tempo | unverified | verified (run: main run; rm: probe P2) | gap filled |

## 3. Verification verdicts — every §7 check of the baseline

| Check | Query | Before | After | Pass criterion | Verdict |
|---|---|---|---|---|---|
| Tool-span dedup (A1) | `traces_spanmetrics_calls_total{span_name="tools/call odd_stack_status", service="oddyssey-mcp"}` | 20 for 10 landed calls | **12 for 12 landed calls** | equals landed call count | **PASS** |
| One SERVER span per call (A1) | `gcx traces get a24755709e4b40a2e3a46eebcfae930f --llm` | 2 nested SERVER spans (scopes `mcp-python-sdk` + `oddyssey-mcp`) | **1** (scope `oddyssey-mcp` only, §5.1 attributes intact) | 1 | **PASS** |
| Instance-id cardinality (A2) | `count(count by (service_instance_id)(target_info{service_name="oddyssey-mcp"}))` after 2 sessions (probe P1) | +1 per session (63 series each) | **1, constant across sessions**; `count({service_name="oddyssey-mcp", service_instance_id=~".+"})` = 0; label values query shows the only remaining instance-id UUIDs belong to `otelcol-contrib` (stack self-telemetry, 121 series) | constant | **PASS** |
| Reset trace lands (A3) | `gcx traces query '{name="tools/call odd_stack_reset"}'` | 0 traces | verbatim replay: **0** (see A3 verdict below); no-kill probe P2: **1 trace** `8eba34bdd7b14f4c9f2434e2b389b14e` (4696 ms) with `oddyssey.docker.rm` (386 ms, exit 0), `oddyssey.docker.run` (138 ms, exit 0), probe loop, OTLP-ready POST | ≥1 trace with docker rm/run children | **PASS** (criterion met in probe P2; in the verbatim replay the trace is destroyed 12 s later by the authorized engine kill — expected-by-design down-span loss, see A3) |
| stderr noise (A4) | `HTTP Request:` lines in captured stderr | 28 | **0** (stderr 0 bytes) | 0 | **PASS** |
| Wire cleanliness | raw stdout: non-JSON-RPC lines | 0 of 20 | **0 of 20** (20/20 parse, jsonrpc=2.0) | 0 | **PASS** (no regression) |
| Failure semantics | phase-B `odd_stack_up` response | tool result `isError:true`, server survives, exit rc 0 | identical — same error text, 11 further calls served, rc 0 | identical | **PASS** (no regression) |
| Histogram integrity | `mcp_server_operation_duration_seconds_count` by tool; buckets | 14/3/1; status ≤0.05; up 0.25/2.5/5 = 1/2/3 | **14/3/1; status ≤0.05; up 1/2/3** | counts match driver record; seconds-scale buckets | **PASS** (no regression) |
| httpx probe accounting | `http_client_request_duration_seconds_count{http_response_status_code="200"}` | 28 | **28** (same arithmetic) + new intentional POST-415 series = 3 (readiness probes) | equals successful-probe arithmetic | **PASS** (no regression; new series is the A3 fix's instrument, not drift) |

### Fate of the baseline's anomalies

| # | Baseline finding | Verdict | Evidence |
|---|---|---|---|
| A1 | Duplicate nested `tools/call` SERVER spans (SDK + decorator) | **FIXED** | single-span exemplar; spanmetrics 12 = 12 landed calls; no `mcp-python-sdk` scope in any fetched trace |
| A2 | `service.instance.id` UUID per session, ~63 series/session | **FIXED** | no `service_instance_id` on any oddyssey-mcp series or trace resource; two-session count constant at 1; remaining UUIDs attributed to `otelcol-contrib` |
| A3 | Reset trace entirely absent; suspected cause: OTLP ingest not ready + exporter no-retry | **FIXED (mechanism), confirmed by probe** | (a) readiness now provably waits for OTLP ingest: `POST :4318/v1/traces → 415` in warm-up trace + metric series count 3; (b) probe P2 (reset, no kill): full reset trace lands incl. rm/run children; (c) in the verbatim replay the trace is still absent — but so is *every* pre-kill sample in Prometheus (only the 22:28:19.254 shutdown flush exists), pinning the in-scenario loss on the hard engine kill 12 s after reset (freshly ingested Tempo/Prometheus data not yet durable), not on export refusal. Baseline's suspected cause (ingest-not-ready refusal) is superseded. Down-span loss under an engine kill is expected-by-design per the mission. |
| A4 | 28 `HTTP Request:` INFO lines on stderr | **FIXED** | stderr capture 0 bytes; httpx/httpcore capped at WARNING held through boot, blackout, and recovery |
| A5 | Failed probes trace-only (no error dimension on `http_client_request_duration`) | **STILL PRESENT (narrowed)** | 6 ERROR GET spans in Tempo (ReadError, no response) have no metric series — connection-level failures remain trace-only; but response-coded errors now do appear (`{http_response_status_code="415", error_type="415"}` = 3), so the gap is confined to no-response failures. Single-signal by nature. No fix was in this wave — expected. |
| A6 | Pyroscope query path 500 ("failed to open object … block.bin: read 0 bytes") | **STILL PRESENT during the run, cause now CONFIRMED, clears on reset** | reproduced after this run's kill (fresh corrupt segment `01M0NSD760CSVZ33RHHMSEW6CK`); after probe P2's clean reset, `gcx profiles labels -l service_name` returns cleanly (`["pyroscope"]`) — the baseline's suspected cause (segment corrupted by hard container kill) and its predicted remedy (next reset) both confirmed. Environment-level, recreated by the failure phase itself. |

## 4. Improvement opportunities

1. **Pool the readiness-probe HTTP client** (carried from baseline §2 note,
   still present): ~13 of a 17 ms status call sits outside the two httpx spans
   (per-call `httpx.Client` construction + 2 TCP connects). A pooled client
   should cut status p50 from ~21 ms toward ~10 ms. Proof: replay phase C;
   `histogram_quantile(0.5, …traces_spanmetrics_latency_bucket{span_name="tools/call odd_stack_status"}…)`
   (today est. 23 ms) and the gap between root-span and probe-span durations.
2. **Bound exception payloads on boot-poll probes** (baseline #5, unaddressed):
   each failed probe span still carries a full stacktrace `exception` event
   (warm-up and reset traces show them). Worst-case 120 s boot ≈ ~120 such
   spans ≈ ~180 KB. Same options as baseline (`record_exception=False` or
   accept). Proof: failed-probe spans in a boot trace carry no `exception`
   event.
3. **Error dimension for no-response probe failures** (A5 remainder, optional):
   6 ReadError GETs produced 0 metric points this run. If PromQL-visible probe
   error rates matter, record a counter (or rely on spanmetrics
   `status_code=STATUS_CODE_ERROR`, which does capture them: GET ERROR = 6).
   Proof: an engine-down replay yields a non-empty error series without
   TraceQL.
4. **A3 verification needs a kill-free measurement point** (protocol, not
   code): the verbatim scenario destroys the reset trace 12 s after creating
   it, so the "reset trace lands" check can never pass inside it. Adopt probe
   P2 (post-scenario clean reset) as a standing step — §7 below does — or
   accept trace-loss for resets immediately preceding an engine failure.

## 5. Telemetry gaps

- **Logs signal: still absent** (spec-scoped out, unchanged). Evidence:
  `gcx logs labels` → `data: null`;
  `gcx logs series -M '{service_name="oddyssey-mcp"}'` → `[]`.
- **Profiles: still absent for oddyssey-mcp** (spec-scoped out; stack has no
  push endpoint published). Evidence: `gcx profiles list-profile-types` →
  only the LGTM stack's own Go profile types; after P2's reset,
  `gcx profiles labels -l service_name` → `["pyroscope"]` (stack itself only).
- **Lost-by-construction traces this run (reduced vs baseline):** 4 of 18
  calls trace-invisible (baseline: 7 of 18) — phase-A cold up (incl. its
  `oddyssey.docker.run`), 2 phase-A status, and the phase-A reset: wiped by
  the reset or destroyed by the engine kill before Tempo made them durable.
  The duration histogram again is the surviving record (counts 14/3/1 vs 14
  traces; the overlap differs per phase).
- **`oddyssey.docker.run` / `oddyssey.docker.rm` spans: GAP FILLED** — `run`
  verified in the landed failed-up trace (exit_code 127) and in P2's reset
  trace (exit_code 0); `rm` verified in P2's reset trace (386 ms, exit 0).
- **No outbound service-graph edge** (unchanged, inherent):
  `traces_service_graph_request_total` has only `user → oddyssey-mcp` = 14;
  the Grafana peer is uninstrumented.
- Gaps remain design-scoped; no `otel-instrumentation-expert` handoff needed.

## 6. Decisions the spec must settle

1. **Reset-before-failure trace loss** (successor to baseline decision 3,
   which is now settled at the mechanism level): with OTLP-ingest-aware
   readiness in place, a reset trace still cannot survive a hard engine kill
   in the following seconds (backend-side durability, outside the server's
   control). Accept as expected-by-design (matching the mission's "down-span
   loss"), or require a durability fallback? (Baseline decision 5 asked the
   same for engine-down operations generally — this run's data narrows it:
   short-blackout spans *did* survive via the post-recovery flush; only
   pre-kill-ingested backend data was lost.)
2. **Probe error metrics** (A5 remainder): accept connection-level probe
   failures as trace/spanmetrics-only, or add a PromQL-native error series?
3. **Pyroscope corruption on engine kill** (A6): accept as a known transient
   of the failure scenario (clean reset clears it), or have the stack tooling
   detect/heal it?
4. **Same-series collision without `service.instance.id`**: two concurrent or
   successive server sessions now write identical series (that is the point of
   the fix), so overlapping sessions would interleave cumulative counters
   (counter-reset semantics in Prometheus). Not observed causing damage in
   this run (`suspected`, not probed with concurrent sessions): accept for the
   single-user local stack, or document a constraint?
5. Baseline decisions 1 (canonical span), 2 (instance-id policy), and 4
   (stderr verbosity) are settled by the implemented and now-verified fixes;
   restated here only for sign-off in the spec text.

## 7. Measurement protocol for the next run

Replay (drive mode, same machine, image pre-pulled, uv env pre-synced):

1. Prep: `docker rm -f -v oddyssey-lgtm`; `uv sync --project src/mcp-server`.
2. Run the driver (`drive_scenario.py` semantics, §1 verbatim): one stdio
   session; initialize (2025-06-18) → initialized → tools/list → phase A
   `status, up, status, reset` + 12 s sleep → phase B
   `pkill -f 'com[.]docker[.]backend'` (down = backend procs gone AND :3000
   dead) → `status, up, status` → `open -a Docker`, wait 2 consecutive
   `docker info` OKs → phase C `up` + 10× `status` → close stdin. Capture raw
   stdout, stderr, per-call timings.
3. **Post-scenario probes (standing additions, run after all main queries):**
   P1 second session with 1× `status` (instance-id cardinality across
   sessions); P2 third session with 1× `reset`, no kill after it (reset-trace
   durability) — P2 wipes the stack, so it must be last.
4. Waits: ≥10 s after each server exit for metrics; ≤60 s for Tempo search
   (poll with a bounded until-loop; cross-check empty searches with a fetch).
5. Comparability: phase B must be the engine-kill (VM survives); final queries
   run with the stack UP.

Verification checks (before-values from this run → pass criterion):

| Check | Query | This run | Pass next run |
|---|---|---|---|
| Tool-span dedup holds | `traces_spanmetrics_calls_total{span_name="tools/call odd_stack_status", service="oddyssey-mcp"}` | 12 = landed calls | equals landed call count |
| Single SERVER span per call | `gcx traces get <status trace> --llm` | 1 | 1 |
| Instance-id stays absent | `count({service_name="oddyssey-mcp", service_instance_id=~".+"})` after P1 | 0 | 0 |
| Reset trace (kill-free) | P2 then `gcx traces query '{name="tools/call odd_stack_reset"}'` | 1 trace with rm(386 ms)/run(138 ms) children | ≥1 with rm/run children |
| stderr silence | bytes/`HTTP Request:` lines in stderr capture | 0 / 0 | 0 / 0 |
| Wire cleanliness | non-JSON-RPC stdout lines | 0 of 20 | 0 |
| Failure semantics | phase-B up response | `isError:true`, server survives, rc 0 | identical |
| Histogram integrity | counts by tool; status buckets | 14/3/1; all status ≤0.05; up 0.25/2.5/5=1/2/3 | match driver record; seconds-scale |
| httpx accounting | GET-200 count; POST-415 count | 28; 3 (one per successful up/reset) | replay arithmetic; 415s = successful up/reset count |
| Phase-B trace survival | error-span search `{… status=error && name=~"tools/call.*"}` | 1 failed-up trace with docker.run exit 127 | ≥1 (short-blackout spans keep surviving) |
| If improvement 1 lands | spanmetrics status p50 est. | 23.3 ms | measurable drop (~10 ms target) |

Environment left as found and ready: `oddyssey-lgtm` **Up (healthy)**, Grafana
13.1.3 online (`gcx config check` ✔ connectivity), Docker engine restored
(`docker info` OK, 29.0.1), stack left UP per the mission. The stack currently
holds probe P2's session telemetry (its reset trace + counts) — the main run's
numbers live in this report, and the main agent measures next against it.
