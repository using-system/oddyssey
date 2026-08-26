---
services: [oddyssey-mcp]
environment: local
mode: drive
window: 2026-08-26T10:03:13Z/2026-08-26T10:03:48Z
run_name: config-set-env-preservation
date: 2026-08-26
revision: e147644
instance: {oddyssey-mcp: "one short-lived process per tool call (MCP Inspector CLI spawn); no service.instance.id emitted (by design, spec decision #9)"}
process_restarted: true
---

# Observation report — oddyssey-mcp #62 env preservation through odd_config_set auto-reset

## 1. Mission and run record

- **Service:** `oddyssey-mcp` — the oddyssey MCP server, branch
  `fix/62-preserve-env-through-config-set-reset`, HEAD `e147644`, run from
  `src/mcp-server/.venv/bin/oddyssey-mcp` (verified editable install:
  `.venv/bin/python -c "import app.stack; print(app.stack.__file__)"` →
  `src/mcp-server/app/stack.py`; `uv sync --project src/mcp-server` re-run
  before the scenario). Reported `service.version=1.6.1`.
- **Environment:** local — configured stack (`odd_config_get` before the run:
  `stack: local`, ports 3000/4317/4318). Backend: Grafana (`oddyssey-lgtm`,
  `grafana/otel-lgtm:0.30.2`, Grafana 13.1.3). Query CLI: gcx, isolated
  `GCX_CONFIG` per the `setup-local-stack` skill (`gcx config check` ✔
  online before and after the run); a second isolated context on :3300 was
  used for the mid-probe query window.
- **Mode:** drive — MCP Inspector CLI 2.3.0 over stdio, the
  `integration-tests/mcp-server/lib.sh` pattern. Each call spawns its own
  server process (fresh cumulative state per call — no cross-instance
  mixing; identity = call label + UTC start below).
- **Window:** the scenario's own bounds, 2026-08-26T10:03:13Z →
  2026-08-26T10:03:48Z; post-scenario targeted probes 10:06:07Z → 10:11:19Z.
- **Focus:** the #62 fix — env carry-over through odd_config_set's
  auto-reset — plus two specific checks: (a) no env VALUE anywhere in
  telemetry or tool results (key names only); (b) the new
  `docker image inspect` span's verb/attribute shape (code-review flag).
- **Destruction authorization:** the caller authorized the resets/wipes —
  the machine-wide telemetry wipe IS the behavior under observation.
- **Baseline (recalled per the create-observe-run-report skill):**
  `.odd/observe-run-reports/2026-08-22-2227-mcp-otel-fix-wave-verification.md`
  (newest match on services+environment; read in full). Its per-operation
  numbers and its A1/A2/A4 fixed-state are the no-regression yardstick.
- **Defaults applied:** none beyond the contract's (window = scenario bounds
  in drive mode); all other fields caller-specified.
- **Preflight:** traces — `gcx traces query
  '{resource.service.name="oddyssey-mcp"}'` → trace
  `a043a7866688eae303b6a38f065532b0` (`tools/call odd_config_get`, the
  preflight call itself); metrics —
  `mcp_server_operation_duration_seconds_count{gen_ai_tool_name="odd_config_get"}`
  = 1; logs and profiles absent for the service (see §5). Pipeline proven
  live before the wipe.

### Scenario record (verbatim)

```text
Scenario: config-set-env-preservation (#62) — 3 one-shot lifecycle calls,
          each its own stdio server process via MCP Inspector CLI
Server:   src/mcp-server/.venv/bin/oddyssey-mcp  (cwd = repo root, env
          inherited, telemetry default-on; OTLP endpoint resolved at process
          start from config's otlp_http_port — telemetry.py:79-82)
Driver:   npx -y @modelcontextprotocol/inspector@2.3.0 --cli <server-bin>
          --method tools/call --tool-name <tool> --tool-arg 'key=json'
          (integration-tests/mcp-server/lib.sh pattern); stdout JSON and
          stderr captured per call; docker/port snapshots between calls
          (read-only, not tool calls)
Backend:  step 1 = odd_stack_reset, env: {"GF_LOG_LEVEL": "debug"}
Prep:     uv sync --project src/mcp-server; pre-scenario container
          5b5076845bba (up 3 days, default ports, NO GF_ env)
Warmup:   none (lifecycle one-shots; caller fixed the counts at 1 each —
          expensive-iteration carve-out: observations, not quantiles)
Started (UTC): 2026-08-26T10:03:13Z
Ended   (UTC): 2026-08-26T10:03:48Z
Commands (sequential):
  1  10:03:13  odd_stack_reset    env={"GF_LOG_LEVEL":"debug"}
               -> rc 0, isError:false, env_applied:true,
                  services_wiped:[oddyssey-mcp, otelcol-contrib]   6411.0 ms
     snapshot: container 24e59e5c8e51 (started 10:03:15.455Z),
               GF_LOG_LEVEL=debug, grafana :3000=200, otlp :4318 POST=415
  2  10:03:19  odd_config_set     config={"local":{"grafana_port":3300,"otlp_http_port":4418}}
               -> rc 0, isError:false, env_preserved:["GF_LOG_LEVEL"],
                  stack_reset.env_applied:true, services_wiped:[oddyssey-mcp]
                                                                  14523.0 ms
     snapshot: container 9712a670c656 (started 10:03:21.840Z),
               GF_LOG_LEVEL=debug, grafana :3300=200 (:3000 dead),
               otlp :4418 POST=415 (:4318 dead), :4317 mapping unchanged
  3  10:03:34  odd_config_set     config={"local":{"grafana_port":3000,"otlp_http_port":4318}}
               -> rc 0, isError:false, env_preserved:["GF_LOG_LEVEL"],
                  stack_reset.env_applied:true, services_wiped:[otelcol-contrib]
                                                                  14184.0 ms
     snapshot: container 8a5e2c0f2921 (started 10:03:36.312Z),
               GF_LOG_LEVEL=debug, grafana :3000=200, otlp :4318 POST=415
Not reproducible: none (fixed payloads, official image pin in the server)
```

Post-scenario targeted probes (NOT part of the verbatim scenario; run after
all main-window queries were recorded; same inspector invocation pattern):

```text
P0  10:06:07Z  odd_stack_status  -> rc 0, all four signals true   1642.0 ms
    (pipeline sanity after the scenario: its trace and metric landed on the
    default ports — proves the scenario's losses were not exporter breakage)
P1  10:06:56Z  odd_config_set config={"local":{"grafana_port":3300}}
    -> rc 0, env_preserved:["GF_LOG_LEVEL"]                        6689.0 ms
    (otlp_http_port unchanged -> the session's own dying flush lands: the
    first-ever landed odd_config_set trace; queried via a :3300 context)
P2  10:11:13Z  odd_config_set config={"local":{"grafana_port":3000}}
    -> rc 0, env_preserved:["GF_LOG_LEVEL"]                        6484.0 ms
    (restores defaults; wipes P1's store; its own trace lands on :3000 —
    the final store holds exactly the P2 session)
```

## 2. Observed behavior

All numbers are one-shot observations (n as shown), never quantiles — the
caller fixed the counts. "client" = wall time of the whole inspector
invocation (includes ~1.6 s npx+handshake overhead, measured on P0:
1642 ms client vs 57 ms server span, and includes server shutdown/flush);
"server" = the landed root-span duration.

| Operation | Requests | client (ms) | server span (ms) | Error % | docker calls per req | Notable |
|---|---|---|---|---|---|---|
| `odd_stack_reset` (step 1) | 1 | 6411.0 | trace lost (§3 F3/F5) | 0 | rm + state-inspect + run | `env_applied: true`; wiped [oddyssey-mcp, otelcol-contrib] |
| `odd_config_set` port-move (steps 2, 3) | 2 | 14523.0 / 14184.0 | traces lost (§3 F4/F5) | 0 | inspect + image + rm + state-inspect + run (from source; unobservable in-backend) | `env_preserved: ["GF_LOG_LEVEL"]` both; ~2.2x the client time of the grafana-only variant |
| `odd_config_set` grafana-port-only (P1, P2) | 2 | 6689.0 / 6484.0 | 4969.4 / 4904.7 | 0 | landed: rm (391–396 ms) + inspect exit 1 (35–47 ms) + run (167–175 ms); created-but-wiped: inspect exit 0 + image (§3 F3) | traces `c8144cb0a39e5b917c7d42d8844f250d`, `89ffedfe4c24a1ff471bb8852b022663`; identical 17-span structure |
| `odd_stack_status` (P0) | 1 | 1642.0 | 57 | 0 | 0 (httpx probes only) | trace `a24a7e25c290853b8f3ec68bfefc8ac0` |
| httpx GET boot-poll (per landed config_set) | 12 | — | 1.2–9.6 each | 8/12 transport-fail by design (booting) | — | 3 rounds x 4 datasource readiness probes; 2 failed rounds, then 4x 200 |
| httpx POST `/v1/traces` OTLP-ready (per landed config_set) | 1 | — | 1.7–1.8 | 415 by design | — | the ingest-readiness probe from the previous fix wave, intact |

Evidence queries (gcx, isolated contexts; final store = P2 session only):

- Tool histogram: `gcx metrics query 'mcp_server_operation_duration_seconds_count'`
  → `{gen_ai_tool_name="odd_config_set"}` = 1;
  `..._sum` = 4.9048 s (matches P2's root span 4904.7 ms; client-server gap
  6484−4905 ≈ 1.6 s = npx+handshake+shutdown, same as P0's overhead).
- httpx accounting:
  `sum by (server_port, http_request_method, http_response_status_code, error_type)(http_client_request_duration_seconds_count{service_name="oddyssey-mcp"})`
  → GET-200 :3300 = **3**, GET-200 :3000 = 4, POST-415 :4318 = 1.
  The three :3300 GET-200s are P2's **pre-rm** stored-services enumeration
  against the old container — their spans were wiped (F3) but their
  cumulative metrics survived via the exit flush into the new store:
  metrics prove the pre-rm phase executed. (Failed boot-poll GETs remain
  trace-only — baseline A5's known remainder, unchanged.)
- Span-derived metrics: `traces_spanmetrics_calls_total{service="oddyssey-mcp"}`
  → `tools/call odd_config_set` SERVER UNSET = 1 (= landed calls: dedup
  holds), `oddyssey.docker.rm`/`inspect`/`run` = 1 each, GET ERROR = 8,
  GET UNSET = 4, POST ERROR = 1 — exactly the P2 trace. **No
  `oddyssey.docker.image` anywhere** (F3).
- Service graph: `traces_service_graph_request_total` → `user →
  oddyssey-mcp` = 1 (virtual node); no outbound edge (unchanged — Grafana
  peer uninstrumented).
- Resource attributes on landed traces: `service.name=oddyssey-mcp`,
  `service.version=1.6.1`, `deployment.environment.name=local`,
  `telemetry.sdk.version=1.44.0`, **no `service.instance.id`** (A2 fix
  holds); no `service_instance_id` label on any metric series.
- Scenario store sweep (before P1): `mcp_server_operation_duration_seconds_count`
  → empty vector; `{resource.service.name="oddyssey-mcp"}` trace search →
  empty across 6 polls over ~60 s. **Zero scenario telemetry survived**
  (see F5) — P0 then proved the pipeline itself healthy.

Env carry-over cross-checks (the #62 behavior, per recreation):

| After | Container | `docker inspect .Config.Env` | Ports |
|---|---|---|---|
| step 1 (reset, env seeded) | 24e59e5c8e51 | GF_LOG_LEVEL=debug | 3000/4317/4318 |
| step 2 (port-move config_set) | 9712a670c656 | GF_LOG_LEVEL=debug | 3300/4317/4418 |
| step 3 (restore config_set) | 8a5e2c0f2921 | GF_LOG_LEVEL=debug | 3000/4317/4318 |
| P1 (grafana-only config_set) | ccc8a5620ab8 | GF_LOG_LEVEL=debug | 3300/4317/4318 |
| P2 (restore config_set) | e1af0e4befe0 | GF_LOG_LEVEL=debug | 3000/4317/4318 |

`docker exec oddyssey-lgtm env` on the final container also shows
`GF_LOG_LEVEL=debug` in the running process environment. 4/4 auto-reset
recreations carried the env; `env_preserved` reported `["GF_LOG_LEVEL"]`
(key name only) 4/4 times.

### Deltas vs baseline (2026-08-22-2227)

| Item | Baseline | This run | Delta |
|---|---|---|---|
| Tool-call error rate (nominal path) | 0 % | 0 % (6/6 isError:false; landed tool spans all STATUS_CODE_UNSET) | no regression |
| status call | first-call 39.6–50.1 ms client-side | P0 57 ms server span (cold process, n=1) | comparable, no regression |
| reset (client-observed minus ~1.6 s overhead) | 4679 ms span | step 1 ≈ 4.8 s inferred (6411 − ~1.6 s); P1/P2 config_set spans 4905–4969 ms incl. reset | unchanged |
| Tool-span dedup (A1) | 1 span/call | 1 span/call (spanmetrics 1 = 1 landed call) | holds |
| `service.instance.id` absent (A2) | absent | absent (traces + series) | holds |
| stderr silence (A4) | 0 bytes | 0 bytes x 6 processes | holds |
| Boot-poll exception payloads (baseline improvement 2) | full stacktrace per failed probe | still present: 8 `exception` events with stacktraces in each landed config_set trace | unchanged (open) |
| A5 no-response probe failures trace-only | narrowed | unchanged (8 ERROR GETs, no metric series) | unchanged (open) |
| Pyroscope query path (A6) | corrupt after engine kill, clean after reset | clean (`gcx profiles labels -l service_name` → `["pyroscope"]`) | healthy (no kill this run) |
| `oddyssey.docker.rm/run` observable | verified | verified again (P1/P2) | holds |
| New: `odd_config_set` operation | not exercised | fully characterized (this report) | new |

## 3. Anomalies and probable causes

| # | Finding | Severity | Confidence | Evidence | Expected gain |
|---|---|---|---|---|---|
| F1 | #62 fix works: user env carried through every auto-reset, key names only in results | — (pass, not an anomaly) | confirmed | 4/4 `env_preserved:["GF_LOG_LEVEL"]`; 4/4 docker inspect Config.Env; `docker exec env` | — |
| F2 | Image-inspect span emits verb `image` and a container attribute on an image operation | cosmetic | confirmed | in-memory harness capture; stack.py:121,174; telemetry.py:220-222 | correct span semantics |
| F3 | Pre-rm spans (env-read inspect+image, state-inspect, stored-services GETs) are deterministically wiped: flushed into the store `rm` destroys next line | medium | confirmed | stack.py:352-353; both landed traces missing exactly the pre-rm spans (2/2); harness proves creation; surviving :3300 GET-200 metrics prove execution | config_set/reset traces gain their first ~5 spans, incl. the #62 spans |
| F4 | Port-moving config_set costs ~2.2x client latency (~+7.8 s shutdown hang) | low-medium | measured (timings) / suspected (attribution) | 14523/14184 ms (n=2) vs 6689/6484 ms (n=2); telemetry.py:79-82 endpoint frozen at startup; installed exporter retries ConnectionError with backoff (up to 6 retries) | port-move call from ~14.5 s toward ~6.5 s |
| F5 | A port-moving config_set orphans its session's entire telemetry (endpoint resolved at startup + wipe) | low (documented design) | confirmed | scenario store empty (metrics vector [], trace search empty 6 polls/60 s) while P0 proved the pipeline healthy; telemetry.py:76-82 comment says "odd_config_set says so" | observability of the exact operation under test |

Detail:

- **F1 — the fix under observation, confirmed end to end.** Every one of
  the four auto-reset recreations (steps 2, 3 and probes P1, P2) reported
  `env_preserved: ["GF_LOG_LEVEL"]` and produced a container whose
  `.Config.Env` carries `GF_LOG_LEVEL=debug` — including through the
  double port-move where Grafana answered on 3300 and OTLP HTTP on 4418
  mid-scenario, exactly as the tool results advertised
  (`grafana_url: http://localhost:3300`, snapshots: :3300→200/:3000→dead,
  then restored). Baseline expectation met in full. **Check (a) also holds
  everywhere it can be checked**: 0 occurrences of the value string in all
  6 tool results, both landed traces (grep of full OTLP JSON), and every
  metric series label (`gcx metrics series '{service_name="oddyssey-mcp"}'`
  grep = 0); the wiped spans carry only `oddyssey.docker.container` +
  `oddyssey.docker.exit_code` (harness capture + docker_span source) — no
  surface records the value. Positive control: the key name does appear
  where contracted (`env_preserved`), so the greps measure something real.
- **F2 — check (b) confirmed, with a twist.** `container_user_env()`
  (stack.py:173-174) runs both docker calls through `_docker()`, which
  names the span from `args[0]` and always attaches
  `oddyssey.docker.container="oddyssey-lgtm"` (stack.py:121). The harness
  (in-memory exporter, no code change) captured exactly:
  `oddyssey.docker.inspect {container: oddyssey-lgtm, exit_code: 0}` and
  **`oddyssey.docker.image {container: oddyssey-lgtm, exit_code: 0}`** —
  the flagged shape: verb truncated to `image`, and a *container*
  attribute on an operation whose subject is the image
  `grafana/otel-lgtm:0.30.2`. The twist: this span is **unobservable in
  the backend in every real run** (F3) — the review flag is confirmed from
  source+harness, not from stored telemetry, because stored telemetry can
  never contain it as coded today.
- **F3 — deterministic self-wipe of the pre-rm phase.**
  `stack_reset` → `stack_down()` calls `telemetry.force_flush()`
  (stack.py:352) immediately before `docker rm -f --volumes`
  (stack.py:353). By that point the session has already ended the
  env-read `inspect`+`image` spans, the reset's state-inspect, and the
  stored-services enumeration GET spans; the flush delivers them into the
  volume-less store that the very next line destroys. Everything ending
  after `rm` reaches the *new* store (post-readiness flush at stack.py:272
  + shutdown flush) — which is why both landed config_set traces
  (`c8144cb0...`, `89ffedfe...`) have the identical 17-span shape starting
  at `rm` (+203.6 ms into the root), missing the same first spans, 2/2.
  Cross-confirmed in three signals: trace absence (Tempo), span creation
  (harness), and the surviving pre-rm cumulative metrics (Prometheus:
  GET-200 `server_port="3300"` = 3 in a session whose boot-polls were all
  on :3000). The flush that saves spans for a *terminal* `stack_down` is
  the exact mechanism that loses them on the *reset* path.
- **F4 — port-move shutdown hang.** Steps 2 and 3 took 14523/14184 ms
  client-observed vs 6689/6484 ms for the grafana-only variant (same tool,
  same reset work, n=2 each) — a consistent ~+7.7 s. Attribution
  (suspected, single-signal by construction since those sessions' server
  telemetry is lost — F5): the OTLP endpoint is frozen at process start
  (telemetry.py:79-82), so after the port moves, the readiness
  `force_flush` (2 s timeout) and the shutdown flush of both trace and
  metric exporters retry a dead endpoint with exponential backoff (the
  installed `opentelemetry-exporter-otlp-proto-http` retries
  `ConnectionError` up to 6 times within its deadline). A targeted probe
  that would confirm: strace/timestamped stderr with exporter logging
  un-silenced, or a port-move call with `OTEL_SDK_DISABLED=true` (expected
  ~6.5 s if the hang is exporter-side).
- **F5 — the scenario is self-erasing, per documented design.** After the
  three-step scenario the store contained zero oddyssey-mcp series and
  zero traces (queries in §2) — step 1's flush was wiped by step 2's
  reset; steps 2 and 3 flushed to the endpoint their processes resolved at
  start, which the mid-call port move had killed. telemetry.py:76-78
  documents this: "a changed OTLP port reaches the server's own telemetry
  after the next MCP server restart (odd_config_set says so)". Recorded as
  expected-by-design; the operational consequence (a port-move is a fully
  dark operation) is a §6 decision.

## 4. Improvement opportunities

1. **Make the pre-rm phase survive the reset (F3):** skip the
   `stack_down()` force-flush when called from `stack_reset` (or flush
   after recreation instead) so the pre-rm spans stay queued in the
   BatchSpanProcessor and land in the *new* store with the post-readiness
   flush. Expected gain: a landed grafana-only `odd_config_set` trace goes
   from 17 spans to ~22 and finally shows the #62 env-read pair
   (`oddyssey.docker.inspect` exit 0 + the image-inspect span) plus the
   stored-services enumeration. Proof query:
   `gcx traces query '{name="oddyssey.docker.image"}'` (or its post-I2
   name) returns ≥1 trace after a grafana-port-only config_set — today it
   returns 0 (validated against a store that provably holds a config_set
   trace).
2. **Fix the image-inspect span shape (F2, cosmetic — needs spec
   amendment, naming frozen per telemetry.py comment):** name it for the
   operation (e.g. `oddyssey.docker.image-inspect`) and attach
   `oddyssey.docker.image="grafana/otel-lgtm:0.30.2"` instead of (or next
   to) the container attribute. Proof: harness capture shows the new
   name/attribute; combined with improvement 1, the backend query above
   proves it end-to-end.
3. **Bound the port-move shutdown hang (F4):** cap or skip the final
   exporter flush when the configured endpoint just changed (the server
   knows — it performed the change), or re-resolve the endpoint for the
   dying flush. Expected gain: port-move `odd_config_set` client time from
   ~14.4 s (n=2) toward ~6.5 s (the grafana-only observation). Proof:
   replay step 2/3 and compare wall time; optionally the flush lands and
   F5's darkness shrinks to the wipe-only loss.
4. **Carried from baseline (still open, re-confirmed):** boot-poll failed
   probes each carry a full stacktrace `exception` event (8 per landed
   config_set trace ≈ 12 KB of the 27.6 KB trace); and connection-level
   probe failures remain metrics-invisible (8 ERROR GETs → 0 series;
   spanmetrics GET ERROR = 8 does capture them). Same options and proofs
   as the baseline report's improvements 2 and 3.

## 5. Telemetry gaps

- **The pre-rm phase of every reset/config_set is structurally
  unobservable (F3)** — evidence:
  `gcx traces query '{name="oddyssey.docker.image"}'` → empty and
  spanmetrics show no `oddyssey.docker.image`, in a store that holds a
  complete landed config_set trace; harness proves the spans are created.
  This is the gap that hides the #62 fix's own fingerprint.
- **Port-moving config_set sessions are fully dark (F5)** — expected by
  design (telemetry.py:76-82); evidence: empty store sweep after the
  scenario (§2) with a healthy pipeline (P0).
- **Logs: absent** (spec-scoped out, unchanged) — `gcx logs labels -l
  service_name` → `data: null` (no oddyssey-mcp stream; the lgtm stack
  self-logs nothing for it either).
- **Profiles: absent for oddyssey-mcp** (spec-scoped out, unchanged) —
  `gcx profiles labels -l service_name` → `["pyroscope"]` (stack itself
  only).
- **Grafana debug-level effectiveness not observable:** the env is in the
  container and process environment (docker inspect + docker exec), but
  the otel-lgtm image exposes no Grafana log stream (`docker logs` carries
  only the boot banner; no grafana log file found; `/api/admin/settings`
  returns empty log section) — single-signal remainder: env present ≠
  logger verbosity proven. Not a service gap; an image/verification gap.
- **No outbound service-graph edge** (unchanged, inherent):
  `traces_service_graph_request_total` → `user → oddyssey-mcp` = 1 only.
- Gaps beyond F3 remain design-scoped; no `otel-instrumentation-expert`
  handoff needed — F3/F2 are flush-ordering and naming issues in existing
  instrumentation, precisely located above.

## 6. Decisions the spec must settle

1. **Reset-path flush ordering (F3):** keep the pre-rm force-flush
   (deterministically losing the reset's own preparatory spans) or buffer
   through recreation (improvement 1)? The flush is correct for a terminal
   `odd_stack_down`; the question is only the reset path.
2. **Port-move semantics (F4/F5):** accept the documented
   next-restart-only telemetry endpoint plus the ~+7.8 s shutdown hang, or
   bound the dying flush / re-resolve the endpoint? (The darkness is
   documented; the hang is not.)
3. **Image-inspect span naming (F2):** amend the frozen naming spec
   (2026-08-22) to `image-inspect` + an image attribute, or accept the
   current shape as a known cosmetic?
4. **Sticky env:** the carried env now persists indefinitely — every
   future auto-reset re-applies `GF_LOG_LEVEL=debug` until an explicit
   `odd_stack_reset` without env clears it (from source: `stack_reset(None)`
   recreates with no `-e` flags — not exercised this run). Is key-only
   reporting enough for an operator to know what is active, or should
   `odd_config_get`/`odd_stack_status` surface the active user-env keys?

## 7. Measurement protocol for the fix

Replay (drive mode, same machine, image `grafana/otel-lgtm:0.30.2` present,
uv env synced; stack up on default ports 3000/4317/4318 before starting):

1. The §1 scenario verbatim: the three inspector CLI commands with the
   exact `--tool-arg` payloads, sequential, one process each; step 1's
   backend env is `{"GF_LOG_LEVEL": "debug"}` (a replayed reset without it
   measures nothing). Snapshot docker id/Env/ports after each call.
2. Query sweep of the (expected-empty today) scenario store, then probes
   P0, P1, P2 verbatim, querying P1's store on :3300 before P2 wipes it.
   Waits: ≥10 s for metrics, ≤60 s bounded polls for Tempo search.
3. All quoted numbers are n=1 or n=2 observations; comparisons are
   structural or magnitude-bounded per the run-scenario carve-out.

Verification checks (before-values from this run → pass criterion; each
check states its validation):

| Check | Query / method | This run | Pass next run | Validated |
|---|---|---|---|---|
| Env carried on auto-reset | `env_preserved` in step 2, 3, P1, P2 results | `["GF_LOG_LEVEL"]` 4/4 | identical 4/4 | positive result this run |
| Env on the container | `docker inspect oddyssey-lgtm --format '{{json .Config.Env}}'` after each recreation | GF_LOG_LEVEL=debug 5/5 snapshots | present after every recreation | positive result this run |
| No env value in tool results | grep value string across all captured stdout JSONs | 0 occurrences / 6 files | 0 | positive control: key name present in `env_preserved` |
| No env value in telemetry | grep value string in fetched trace JSON + `gcx metrics series '{service_name="oddyssey-mcp"}'` output | 0 / 0 | 0 / 0 | ran against a store provably holding a config_set trace + 100 series |
| Landed config_set trace structure | `gcx traces get <id> --llm` on the P1 or P2 trace | 17 spans: root + rm + inspect(exit 1) + run + 12 GET + POST-415 (2/2 identical) | same structure; after improvement 1: ~22 spans incl. `oddyssey.docker.image`* + inspect(exit 0) | n=2 structural match this run |
| Pre-rm spans observable (flips after improvement 1) | `gcx traces query '{name="oddyssey.docker.image"}'` after P1 | 0 traces | ≥1 trace (name may change per improvement 2) | span creation proven by in-memory harness; query ran on healthy store |
| Tool-span dedup holds | `traces_spanmetrics_calls_total{span_name="tools/call odd_config_set", service="oddyssey-mcp"}` | 1 = 1 landed call | equals landed call count | positive result this run |
| Instance-id stays absent | series labels + trace resource sweep | absent | absent | positive result this run |
| stderr silence | bytes in per-call stderr captures | 0 x 6 | 0 | positive result this run |
| Port-move client latency (flips after improvement 3) | wall time of steps 2 and 3 vs P1/P2 | 14523/14184 ms vs 6689/6484 ms (n=2 each) | unchanged magnitude; after improvement 3: port-move within ~1 s of grafana-only | measured this run |
| config_set server span magnitude | root span of the landed P1/P2 trace | 4969/4905 ms (n=2) | 4–7 s (magnitude-bounded) | positive result this run |
| Scenario store darkness (flips partially after improvement 3) | post-scenario `mcp_server_operation_duration_seconds_count` + trace search | empty / empty (pipeline health via P0) | empty today; improvement 3 may land the port-move flush | not validated for the flipped case |
| Pipeline sanity | P0 trace + metric on default ports | landed (57 ms span) | lands | positive result this run |

Environment left as found and ready: `oddyssey-lgtm` = `e1af0e4befe0`,
**Up (healthy)**, default ports 3000/4317/4318 (config restored by step 3
and re-confirmed by P2's result + container port mappings), `gcx config
check` ✔ online, Grafana 13.1.3 — stack left UP; the main agent measures
next against this report. Known end-state deltas vs pre-run: the store
holds the P2 session's telemetry (1 config_set trace + its metrics), and
`GF_LOG_LEVEL=debug` remains active on the container and will be carried
by future auto-resets (clearable with a bare `odd_stack_reset`; that is
the observed #62 behavior, not residue of the observation method).
