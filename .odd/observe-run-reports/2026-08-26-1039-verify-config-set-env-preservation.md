---
services: [oddyssey-mcp]
stack: local
environment: local
mode: verify
window: 2026-08-26T10:39:57Z/2026-08-26T10:40:52Z
run_name: config-set-env-preservation
verifies: 2026-08-26-1003-config-set-env-preservation.md
date: 2026-08-26
revision: 14c0705
instance: {oddyssey-mcp: "one short-lived process per tool call (MCP Inspector CLI spawn); no service.instance.id emitted (by design, spec decision #9); identity = call label + UTC start"}
process_restarted: true
---

# Verification report — F3 fix (pre-rm span delivery through stack_reset), replay of 2026-08-26-1003

## 1. Mission and run record

- **Service:** `oddyssey-mcp`, branch `fix/62-preserve-env-through-config-set-reset`,
  HEAD `14c0705` (baseline observed `e147644`; delta under verification =
  `b1bfe46` + `14c0705`: `stack_down(flush: bool = True)`, `stack_reset` calls
  `stack_down(flush=False)` — stack.py:350-364,394 verified in source before the
  run). Binary `src/mcp-server/.venv/bin/oddyssey-mcp`; editable install
  verified: `uv sync --project src/mcp-server` (54 packages resolved, no
  changes), `.venv/bin/python -c "import app.stack; print(app.stack.__file__)"`
  → `src/mcp-server/app/stack.py`, and `inspect.signature(stack_down)` carries
  the `flush` parameter. Reported `service.version=1.6.1`.
- **Environment:** local — configured stack (`~/.oddyssey/config.json` before
  the run: `stack: local`, grafana 3000, otlp_http 4318; `odd_config_get` via
  the preflight call confirmed 3000/4317/4318). Backend: Grafana
  (`oddyssey-lgtm`, `grafana/otel-lgtm:0.30.2`, Grafana 13.1.3). Query CLI:
  gcx, isolated `GCX_CONFIG` per the `setup-local-stack` skill (`gcx config
  check` ✔ online before and after); a second isolated context on :3300 for
  the P1-store window, exactly as the protocol prescribes.
- **Mode:** drive — verbatim replay of the baseline's §1 scenario + §7
  protocol: MCP Inspector CLI 2.3.0 over stdio, `integration-tests/mcp-server/
  lib.sh` pattern, one server process per call, cwd = repo root, env inherited.
- **Window:** scenario 2026-08-26T10:39:57Z → 10:40:52Z; post-scenario probes
  P0/P1/P2 10:42:20Z → 10:45:18Z.
- **Focus:** the F3 verdict (pre-rm spans now landed?) inside a full replay of
  the baseline protocol's 13 checks, 5 anomalies, and 6 telemetry gaps.
- **Destruction authorization:** caller authorized the resets/wipes (the wipe
  is the behavior under measurement); environment left as found (§7 end-state).
- **Baseline (recalled — named by the mission, read in full):**
  `.odd/observe-run-reports/2026-08-26-1003-config-set-env-preservation.md`
  (same services, same environment, revision e147644). Its §7 protocol is the
  contract this run rules on.
- **Defaults applied:** none beyond the contract's (window = scenario bounds).
- **Preflight:** pipeline proven live before the wipe — `odd_config_get` via
  inspector (1542.0 ms, rc 0, stderr 0) → trace
  `89ed15b005e2efb4f90ce3c2c74b5630` (`tools/call odd_config_get`, found on
  poll 2 of the bounded Tempo search) and
  `mcp_server_operation_duration_seconds_count{gen_ai_tool_name="odd_config_get"}`
  = 1. Logs and profiles absent for the service (unchanged, §5).
- **Pre-run condition delta vs baseline:** the pre-scenario container was the
  baseline run's end-state (`e1af0e4befe0`, default ports, `GF_LOG_LEVEL=debug`
  already present — the baseline's documented sticky-env end-state), where the
  baseline started from a container with no GF_ env. Step 1 re-seeds the env
  either way; no check depends on the pre-scenario env.

### Scenario record (verbatim replay)

```text
Scenario: config-set-env-preservation (#62) — replay for F3 verification
          3 one-shot lifecycle calls, each its own stdio server process
Server:   src/mcp-server/.venv/bin/oddyssey-mcp  (cwd = repo root, env
          inherited, telemetry default-on)
Driver:   npx -y @modelcontextprotocol/inspector@2.3.0 --cli <server-bin>
          --method tools/call --tool-name <tool> --tool-arg 'key=json'
          (integration-tests/mcp-server/lib.sh pattern); stdout JSON and
          stderr captured per call; docker/port snapshots between calls
Backend:  step 1 = odd_stack_reset, env: {"GF_LOG_LEVEL": "debug"}
Prep:     uv sync --project src/mcp-server; npx cache warm (preflight call);
          pre-scenario container e1af0e4befe0 (baseline end-state, default
          ports, GF_LOG_LEVEL=debug already present — see §1)
Warmup:   none (lifecycle one-shots; counts fixed at 1 each by the protocol —
          expensive-iteration carve-out: observations, not quantiles)
Started (UTC): 2026-08-26T10:39:57Z
Ended   (UTC): 2026-08-26T10:40:52Z
Commands (sequential):
  1  10:39:57  odd_stack_reset    env={"GF_LOG_LEVEL":"debug"}
               -> rc 0, isError:false, env_applied:true,
                  services_wiped:[oddyssey-mcp, otelcol-contrib]   6018.6 ms
     snapshot: container 005c93c9a5fe (started 10:39:58.988Z),
               GF_LOG_LEVEL=debug, grafana :3000=200, otlp :4318 POST=415
  2  10:40:10  odd_config_set     config={"local":{"grafana_port":3300,"otlp_http_port":4418}}
               -> rc 0, isError:false, env_preserved:["GF_LOG_LEVEL"],
                  stack_reset.env_applied:true,
                  services_wiped:[oddyssey-mcp, otelcol-contrib]  14007.5 ms
     snapshot: container 0843fb60eed9 (started 10:40:12.029Z),
               GF_LOG_LEVEL=debug, grafana :3300=200 (:3000 dead),
               otlp :4418 POST=415 (:4318 dead), :4317 mapping unchanged
  3  10:40:37  odd_config_set     config={"local":{"grafana_port":3000,"otlp_http_port":4318}}
               -> rc 0, isError:false, env_preserved:["GF_LOG_LEVEL"],
                  stack_reset.env_applied:true, services_wiped:[otelcol-contrib]
                                                                  15281.9 ms
     snapshot: container 9637638d366f (started 10:40:39.909Z),
               GF_LOG_LEVEL=debug, grafana :3000=200 (:3300 dead),
               otlp :4318 POST=415 (:4418 dead)
Not reproducible: none (fixed payloads, official image pin in the server)
```

Post-scenario targeted probes (after all scenario-store queries were
recorded; same inspector pattern):

```text
P0  10:42:20Z  odd_stack_status  -> rc 0, all four signals true   1579.5 ms
    (trace 4fa73b13fae3b555a7f0f0f6ecac1371, root span 50 ms; metric
    count=1 — pipeline healthy on default ports after the scenario)
P1  10:43:06Z  odd_config_set config={"local":{"grafana_port":3300}}
    -> rc 0, env_preserved:["GF_LOG_LEVEL"]                        6054.1 ms
    (otlp unchanged -> session lands; container 4733d0ec4ce6; store
    queried via the :3300 context BEFORE P2 — the F3 headline window)
P2  10:45:12Z  odd_config_set config={"local":{"grafana_port":3000}}
    -> rc 0, env_preserved:["GF_LOG_LEVEL"]                        6038.4 ms
    (restores defaults; wipes P1's store; container efcb21c41b6e; final
    store = exactly the P2 session)
```

## 2. Observed behavior

All numbers are one-shot observations (n as shown), per the protocol's
carve-out. "client" = inspector wall time (includes npx+handshake+shutdown
overhead — this run ~1.2-1.5 s, cf. P0 1579.5 ms client vs 50 ms span;
baseline measured ~1.6 s); "server" = landed root-span duration.

| Operation | Requests | client (ms) | server span (ms) | Error % | docker calls per req | Notable |
|---|---|---|---|---|---|---|
| `odd_stack_reset` (step 1) | 1 | 6018.6 | trace lost (F5: wiped by step 2) | 0 | rm + inspects + run | `env_applied: true`; wiped [oddyssey-mcp, otelcol-contrib] |
| `odd_config_set` port-move (steps 2, 3) | 2 | 14007.5 / 15281.9 | traces lost (F4/F5, unchanged) | 0 | (unobservable in-backend, F5) | `env_preserved: ["GF_LOG_LEVEL"]` both; still ~2.3x the grafana-only client time |
| `odd_config_set` grafana-port-only (P1, P2) | 2 | 6054.1 / 6038.4 | 4876.8 / 4841.0 | 0 | **landed, now incl. pre-rm phase:** 4x inspect exit 0 + image + rm (392 ms) + inspect exit 1 + run (146-175 ms) | traces `d024282dc6ae7572c659d717cd1eaa10`, `76ebcd795582b1f3adbad458cd2301eb`; identical **25-span** structure (was 17) |
| `odd_stack_status` (P0) | 1 | 1579.5 | 50 | 0 | 0 (httpx probes only) | trace `4fa73b13fae3b555a7f0f0f6ecac1371` |
| httpx GET boot-poll (per landed config_set) | 12 | — | — | 8/12 transport-fail by design (booting) | — | 3 rounds x 4 readiness probes, unchanged |
| httpx GET pre-rm enumeration (per landed config_set) | 3 | — | — | 0 (all 200) | — | **NEW in traces** — the pre-wipe stored-services GETs against the old container, previously metric-only |
| httpx POST `/v1/traces` OTLP-ready (per landed config_set) | 1 | — | — | 415 by design | — | unchanged |

Landed config_set trace structure (2/2 identical, ports mirrored):
root `tools/call odd_config_set` + 4x `oddyssey.docker.inspect` (exit 0,
20-26 ms) + `oddyssey.docker.image` (exit 0, 37 ms) + 3x GET-200 against the
**old** grafana port (pre-rm enumeration: :3000 in P1's trace, :3300 in
P2's) + `oddyssey.docker.rm` (392 ms) + `oddyssey.docker.inspect` (exit 1)
+ `oddyssey.docker.run` (146 ms) + 12 boot-poll GETs on the **new** port
(8 ERROR + 4x 200) + POST-415 = **25 spans**. The baseline's landed shape
started at `rm`; the entire pre-rm phase is now present.

Evidence queries (gcx; :3300 context for the P1 store, default for the rest):

- F3 headline: `gcx traces query '{name="oddyssey.docker.image"}'` →
  **1 trace** on the P1 store (`d024282d...`) and, after P2, 1 trace on the
  final store (`76ebcd79...`). Baseline before-value: 0.
- Tool histogram: `mcp_server_operation_duration_seconds_count{gen_ai_tool_name="odd_config_set"}`
  = 1 on each store; `..._sum` = 4.8769 s (P1 store) and 4.8411 s (final) —
  each matching its root span to the millisecond (4876.8 / 4841.0 ms).
  Client-server gap ≈ 1.18/1.20 s (npx+handshake+shutdown; baseline ~1.6 s —
  driver-side variance, not a service delta).
- httpx accounting (final store):
  `sum by (server_port, http_request_method, http_response_status_code)(http_client_request_duration_seconds_count{service_name="oddyssey-mcp"})`
  → GET-200 :3300 = 3, GET-200 :3000 = 4, POST-415 :4318 = 1 — same totals
  as baseline, but the 3 pre-rm GET-200s are now **also spans in the trace**
  (baseline: metric-only survivors). Failed boot-poll GETs remain trace-only
  (A5 remainder, unchanged).
- Span-derived metrics (both stores, identical shape):
  `traces_spanmetrics_calls_total{service="oddyssey-mcp"}` →
  `tools/call odd_config_set` UNSET = 1 (dedup holds),
  **`oddyssey.docker.image` = 1 (baseline: absent everywhere)**,
  `inspect` = 5, `rm` = 1, `run` = 1, GET ERROR = 8, GET UNSET = 7
  (4 boot + 3 pre-rm), POST ERROR = 1.
- Service graph: `traces_service_graph_request_total` → `user → oddyssey-mcp`
  = 1; no outbound edge (unchanged).
- Resource attributes (both landed traces): `service.name=oddyssey-mcp`,
  `service.version=1.6.1`, `deployment.environment.name=local`,
  `telemetry.sdk.version=1.44.0`, no `service.instance.id`; no instance
  label in any of the 27.4 KB of series output.
- Scenario store sweep (before P0):
  `mcp_server_operation_duration_seconds_count` → empty vector;
  `count({service_name="oddyssey-mcp"})` → empty;
  `{resource.service.name="oddyssey-mcp"}` trace search → empty across
  6 polls / ~60 s. Scenario telemetry still self-erasing (F5, by design);
  P0 then proved the pipeline healthy.

Env carry-over cross-checks (#62 behavior, per recreation):

| After | Container | `.Config.Env` | Ports |
|---|---|---|---|
| step 1 (reset, env seeded) | 005c93c9a5fe | GF_LOG_LEVEL=debug | 3000/4317/4318 |
| step 2 (port-move) | 0843fb60eed9 | GF_LOG_LEVEL=debug | 3300/4317/4418 |
| step 3 (restore) | 9637638d366f | GF_LOG_LEVEL=debug | 3000/4317/4318 |
| P1 (grafana-only) | 4733d0ec4ce6 | GF_LOG_LEVEL=debug | 3300/4317/4318 |
| P2 (restore) | efcb21c41b6e | GF_LOG_LEVEL=debug | 3000/4317/4318 |

`docker exec oddyssey-lgtm env` on the final container: `GF_LOG_LEVEL=debug`.
4/4 auto-resets reported `env_preserved: ["GF_LOG_LEVEL"]` (key name only).

Side observation (single-signal, timing-suspected): step 2's
`services_wiped` now lists `[oddyssey-mcp, otelcol-contrib]` where the
baseline saw `[oddyssey-mcp]` — consistent with more telemetry landing in
step 1's short-lived store (retry delivery and/or collector self-metrics
timing); not separately probed, no check depends on it.

### Deltas vs baseline (2026-08-26-1003)

| Item | Baseline | This run | Delta |
|---|---|---|---|
| Landed config_set trace | 17 spans, starts at `rm` | 25 spans, full pre-rm phase, 2/2 identical | **improved (F3 fixed)** |
| `oddyssey.docker.image` in backend | 0 (traces + spanmetrics) | 1 trace per store; spanmetrics = 1 | **improved (headline flip)** |
| Port-move client latency | 14523/14184 ms (n=2) | 14007.5/15281.9 ms (n=2) | unchanged magnitude (F4 open; predicted ~2 s reduction **not observed**) |
| grafana-only config_set client / span | 6689/6484 ms; 4969/4905 ms | 6054.1/6038.4 ms; 4876.8/4841.0 ms | unchanged magnitude |
| Scenario store darkness (F5) | empty/empty | empty/empty | unchanged (by design) |
| Env carry-over (F1) | 4/4 + 5/5 | 4/4 + 5/5 | holds |
| Tool-span dedup (A1) | 1 span/call | 1 span/call | holds |
| `service.instance.id` absent (A2) | absent | absent | holds |
| stderr silence (A4) | 0 bytes x 6 | 0 bytes x 7 | holds |
| Boot-poll exception payloads | 8 stacktrace events/trace | 8/trace (2/2) | unchanged (open) |
| A5 failed probes trace-only | unchanged | unchanged | unchanged (open) |
| status call | 57 ms span | 50 ms span | comparable |

## 3. Anomalies and probable causes — fate of the baseline's findings

| # | Baseline finding | Verdict | Confidence | Evidence |
|---|---|---|---|---|
| F1 | Env carried through auto-reset, key names only | **still passing** | confirmed | 4/4 `env_preserved`; 5/5 `.Config.Env`; `docker exec`; 0 value-string hits in 7 stdout captures, 2 full trace JSONs (67 KB each), 27.4 KB series output |
| F2 | Image-inspect span: verb `image`, container attribute | **still present** (expected — improvement 2 not implemented) | confirmed — **upgraded from harness-only to stored-telemetry evidence** | landed span in both traces: `oddyssey.docker.image {oddyssey.docker.container="oddyssey-lgtm", oddyssey.docker.exit_code=0}`, no image attribute |
| F3 | Pre-rm spans deterministically wiped | **FIXED** | confirmed (cross-signal) | headline query flips 0 → 1 on both stores; 17 → 25 spans 2/2; spanmetrics gained `image`=1, `inspect` 1→5, GET UNSET 4→7; pre-rm GET-200s now in trace AND metrics |
| F4 | Port-move ~2.2x client latency (+~7.8 s) | **still present** | measured (n=2) / attribution still suspected (sessions still dark) | 14007.5/15281.9 ms vs 6054.1/6038.4 ms; the review's predicted ~2 s marginal reduction **not observed** — same ~14.5 s magnitude as baseline (improvement 3 not implemented; criterion condition unmet) |
| F5 | Port-moving config_set orphans its session's telemetry | **unchanged (by design)** | confirmed | scenario store: empty metrics vector + empty trace search 6 polls/60 s; P0 healthy right after |

F3 detail: with `stack_down(flush=False)` on the reset path, the pre-rm
spans stay queued in the BatchSpanProcessor and are delivered into the
recreated store (SDK worker retries, with stack_up's post-readiness flush
as backstop — the two are indistinguishable in stored data and need no
distinction: the spans land, 2/2). The fix's docstring caveat ("a boot
slower than the retry deadline still drops the batch") produced no loss in
either landed session this run.

## 4. Improvement opportunities

1. **Baseline improvement 1 (F3): landed — close it.** Verified by the
   headline query on two independent stores.
2. **Baseline improvement 2 (F2): still open.** The flagged shape is now
   backend-visible (F3 fixed), so the fix is now provable end-to-end with
   `gcx traces query '{name="oddyssey.docker.image"}'` → expect the new
   name/attribute after the spec amendment. Expected gain unchanged.
3. **Baseline improvement 3 (F4): still open, now sharper.** The ~14.5 s
   port-move magnitude is fully reproduced (n=2+2 across two runs:
   14184-15282 ms) and the F3 fix did not reduce it — the pre-rm flush it
   removed was aimed at a then-alive endpoint, so the hang lives in the
   post-move readiness/shutdown flushes against the dead endpoint
   (attribution still suspected; the baseline's `OTEL_SDK_DISABLED=true`
   probe remains the confirming experiment). Expected gain unchanged:
   ~14.5 s → ~6.5 s.
4. **Carried from baseline (unchanged):** boot-poll stacktrace `exception`
   events (8 per landed trace, 2/2 this run) and metrics-invisible failed
   probes (8 ERROR GETs → 0 error series; spanmetrics GET ERROR = 8 does
   capture them). Same proofs as before.

## 5. Telemetry gaps — fate of the baseline's gaps

- **Pre-rm phase unobservable (F3): FILLED.** Discovery query
  `gcx traces query '{name="oddyssey.docker.image"}'` → 1 trace (was
  empty); spanmetrics carry the pre-rm span names.
- **Port-moving sessions fully dark (F5): still open, by design**
  (telemetry.py:76-82). Evidence: empty scenario-store sweep with P0 healthy.
- **Logs: still absent** (spec-scoped out) — `gcx logs labels -l
  service_name` → `data: null`.
- **Profiles: still absent for oddyssey-mcp** (spec-scoped out) —
  `gcx profiles labels -l service_name` → `["pyroscope"]` (stack only).
- **Grafana debug-level effectiveness: still not observable** — env proven
  in container and process (5/5 inspects + docker exec), but `docker logs
  oddyssey-lgtm` = 41 lines, 0 matching `lvl=debug|level=debug`
  (boot banner only). Image/verification gap, unchanged.
- **No outbound service-graph edge: still open, inherent** —
  `traces_service_graph_request_total` → `user → oddyssey-mcp` = 1 only.
- No `otel-instrumentation-expert` handoff needed: the one instrumentation
  gap that mattered (F3) is closed; the rest are design-scoped.

## 6. Decisions the spec must settle

1. **Baseline decision 1 (reset-path flush ordering): settled by the fix**
   — `flush=False` on the reset path, `flush=True` kept for terminal
   `odd_stack_down`; verified working. Remaining sub-question: is the
   documented best-effort caveat (slow boot may still drop the batch)
   acceptable, or does it need a bounded post-readiness re-flush guarantee?
   (No loss observed in 2/2 sessions this run.)
2. **Baseline decision 2 (port-move semantics, F4/F5): still open** — the
   ~14.5 s hang is reproduced and unimproved; the darkness is documented.
3. **Baseline decision 3 (image-inspect span naming, F2): still open** —
   and now user-visible in the backend, which raises its priority slightly:
   the shape is no longer hidden by F3.
4. **Baseline decision 4 (sticky env surfacing): still open** — this run
   re-confirmed the stickiness (pre-scenario container still carried
   `GF_LOG_LEVEL=debug` from the baseline run, 3 days of resets later would
   too); `odd_config_get`/`odd_stack_status` still do not surface active
   user-env keys.

## 7. Measurement protocol for the next run

Replay unchanged from the baseline report §7 (same scenario, same probes,
same order, P1's store queried on :3300 before P2). Verdicts on the
baseline's 13 checks, and the updated before-values for the next run:

| Check | Query / method | Baseline before-value | This run (after) | Recorded pass criterion | Verdict | Validated |
|---|---|---|---|---|---|---|
| 1. Env carried on auto-reset | `env_preserved` in step 2, 3, P1, P2 | `["GF_LOG_LEVEL"]` 4/4 | `["GF_LOG_LEVEL"]` 4/4 | identical 4/4 | **PASS** | positive result both runs |
| 2. Env on the container | `docker inspect --format '{{json .Config.Env}}'` per recreation | 5/5 | 5/5 + `docker exec` | present after every recreation | **PASS** | positive result both runs |
| 3. No env value in tool results | grep value string in captured stdout JSONs | 0/6 files | 0/7 files | 0 | **PASS** | positive control: key name present in `env_preserved` |
| 4. No env value in telemetry | grep in fetched trace JSON + series output | 0 / 0 | 0 in 2x 67 KB trace JSON, 0 in 27.4 KB series | 0 / 0 | **PASS** | ran against stores provably holding a config_set trace |
| 5. Landed config_set trace structure | `gcx traces get <id>` on P1/P2 | 17 spans starting at `rm` | **25 spans** incl. `oddyssey.docker.image` + 4x inspect exit 0 + 3 pre-rm GETs, 2/2 identical | ~22 spans incl. image + inspect(0) after improvement 1 | **PASS** (protocol's ~22 undercounted the 3 pre-rm enumeration GETs) | n=2 structural match |
| 6. Pre-rm spans observable (F3 headline) | `gcx traces query '{name="oddyssey.docker.image"}'` after P1 | 0 traces | **1 trace** (P1 store) + 1 (final store) | ≥1 trace | **PASS — F3 FIXED** | query validated on the baseline's healthy store; positive on two stores here |
| 7. Tool-span dedup | `traces_spanmetrics_calls_total{span_name="tools/call odd_config_set"}` | 1 | 1 = 1 landed call (both stores) | equals landed calls | **PASS** | positive both runs |
| 8. Instance-id absent | series labels + trace resource sweep | absent | absent (2 traces + series) | absent | **PASS** | positive both runs |
| 9. stderr silence | bytes per stderr capture | 0 x 6 | 0 x 7 | 0 | **PASS** | positive both runs |
| 10. Port-move client latency | wall time steps 2/3 vs P1/P2 | 14523/14184 vs 6689/6484 ms | 14007.5/15281.9 vs 6054.1/6038.4 ms | unchanged magnitude (flip conditioned on improvement 3) | **PASS per criterion — condition unmet** (improvement 3 not implemented; not a regression). Predicted ~2 s marginal reduction not observed (n=2, same magnitude) | measured both runs |
| 11. config_set server span magnitude | root span of landed P1/P2 trace | 4969/4905 ms | 4876.8/4841.0 ms | 4–7 s | **PASS** | positive both runs |
| 12. Scenario store darkness | post-scenario metrics + trace search | empty/empty | empty/empty (6 polls/60 s; P0 healthy) | empty today (flip conditioned on improvement 3) | **PASS — condition unmet** | not validated for the flipped case (unchanged) |
| 13. Pipeline sanity | P0 trace + metric on default ports | 57 ms span | trace `4fa73b13...`, 50 ms span, metric = 1 | lands | **PASS** | positive both runs |

**13/13 checks pass their recorded criteria.** No empty/NaN after-value
occurred, so the query-suspect rule was never triggered; every query form
from the baseline protocol worked as recorded (one driver-side note: gcx
rejects `--jq` combined with `-o agents` — use `--jq` alone; affects no
recorded check query).

For the next run (improvements 2 and 3 are the open flips):

- Check 5's expected structure is now **25 spans** (the validated
  before-value of this run); after improvement 2 the `image` span's
  name/attributes change per the spec amendment.
- Check 6's query gains `≥1` as its validated steady-state; after
  improvement 2 query the new name.
- Check 10 flips after improvement 3: port-move within ~1 s of
  grafana-only (~6.0-6.7 s observed range, n=4 across two runs).
- All numbers remain n=1/n=2 observations under the carve-out; compare by
  structure and magnitude only.

**Environment left as found and ready:** `oddyssey-lgtm` = `efcb21c41b6e`,
Up (healthy), default ports 3000/4317/4318 (config file re-read:
grafana_port 3000, otlp_http_port 4318; container mappings confirmed;
grafana :3000=200, OTLP :4318 POST=415), `gcx config check` ✔ online,
Grafana 13.1.3 — stack left UP. Known end-state deltas: the store holds
exactly the P2 session (1 config_set trace `76ebcd79...` + its metrics),
and `GF_LOG_LEVEL=debug` remains active on the container (the observed #62
sticky-env behavior, as after the baseline run; clearable with a bare
`odd_stack_reset`).
