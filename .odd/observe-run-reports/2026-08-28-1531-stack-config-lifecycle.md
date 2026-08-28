---
services: [oddyssey-mcp]
stack: local
environment: local
mode: drive
window: 2026-08-28T15:31:53Z/2026-08-28T15:37:00Z
run_name: stack-config-lifecycle
date: 2026-08-28
revision: ccd2c11
instance: {oddyssey-mcp: "one short-lived process per tool call (MCP Inspector CLI spawn); no service.instance.id emitted (by design, spec decision #9); identity = call label + UTC start. Caveat: two long-lived INSTALLED servers (uvx oddyssey-mcp==1.7.0 PID 43958, ==1.2.0 PID 60321) co-export to the same stack - see F4"}
process_restarted: true
---

# Observation report — stack-config env lifecycle (#117 persist/reapply, #112 null deletion), branch `fix/stack-config-lifecycle`

## 1. Mission and run record

- **Service:** `oddyssey-mcp` — the oddyssey MCP server built from branch
  `fix/stack-config-lifecycle`, HEAD `ccd2c11`, working tree clean. Binary
  `src/mcp-server/.venv/bin/oddyssey-mcp`; branch wiring proven before the
  run: `uv sync --project src/mcp-server` (re-installed editable
  oddyssey-mcp 1.6.1 → 1.7.2), `.venv/bin/python -c "import
  oddyssey_mcp.stack"` → `src/mcp-server/app/stack.py`,
  `hasattr(stack, 'persisted_env') == True`, `stack_up`/`stack_reset`
  signatures carry the new `persist` keyword. Reported
  `service.version=1.7.2` in every landed trace.
- **Stack/backend:** local (Grafana LGTM, container `oddyssey-lgtm`,
  `grafana/otel-lgtm:0.31.0`, Grafana 13.1.3), ports 3000/4317/4318
  (confirmed from `odd_config_get` result and `docker ps` port bindings —
  not assumed). Query CLI: gcx 1.x via the isolated `GCX_CONFIG` context of
  the `setup-local-stack` skill; `gcx config check` ✔ online before and
  after the run.
- **Mode:** drive — 8 one-shot MCP calls, each its own stdio server
  process, driven with MCP Inspector CLI 2.3.0
  (`integration-tests/mcp-server/lib.sh` pattern), cwd = repo root.
- **Config isolation (hard constraint):** every server process ran with
  `HOME` pointed at a scratch directory, proven before the run
  (`Path.home()` and `oddyssey_mcp.config.CONFIG_PATH` both resolved into
  the scratch dir; `load()` returned pure defaults with the same ports
  3000/4317/4318). C0's result showed `stack_config: {}` — the real
  config's `azure-monitor` entry absent — proving the server never read
  `~/.oddyssey/config.json`. The real file's SHA-256
  `f010281d5bf184f9fa2da4c24e8d187601f9506fa69c6e968c7b53ba51835c3e` was
  identical before, during, and after the run (3 measurements).
- **Window:** the scenario, 2026-08-28T15:31:53Z → 15:37:00Z (post-scenario
  queries until ~15:38Z read only stores produced inside the window).
- **Focus:** correctness of the new result fields (`env_persisted`,
  `env_reapplied`, `env_not_persisted`), the persist → reapply → delete
  lifecycle end to end, and the tool spans landing in the stack.
- **Deployment environment: `local`** — forced by construction on the
  local stack, and independently what the telemetry reports: pre-run
  `gcx traces labels -l resource.deployment.environment.name` →
  `["local"]` (single value), re-confirmed on the final store (same query,
  same single value) and in every fetched trace's resource attributes. No
  discrepancy, no provisional state.
- **Baseline (recalled per the create-observe-run-report procedure):**
  newest match on services+stack+environment is
  `2026-08-26-1039-verify-config-set-env-preservation.md` (read in full;
  its `verifies` chain reaches `2026-08-26-1003-config-set-env-preservation.md`,
  also consulted for findings F1–F5). The mission also named the 1003
  report explicitly. This run is a NEW observation (new scenario for
  issues #117/#112), not a replay of the stored protocol, hence
  `mode: drive`, no `verifies`.
- **Defaults applied:** none beyond the contract's (window = scenario
  bounds; focus and expectations were given).
- **Destruction accepted by the mission:** 1 `odd_stack_down` + 3
  `odd_stack_reset` wipes of the machine-wide store; every
  `services_wiped` recorded below. Pre-wipe store content (2026-08-28
  ~15:28Z): Tempo `service.name` = `[oddyssey-mcp]`, Prometheus `job` =
  `[oddyssey-mcp, otelcol-contrib]`, Loki service_name = none.
- **Pre-run container condition:** `6b863c0682c1` (created
  2026-08-26T20:36Z, image 0.31.0) still carried `GF_LOG_LEVEL=debug` from
  the 2026-08-26 runs — the known sticky-env end-state (baseline decision
  4), destroyed by C1.
- **Preflight (all four signals, pre-run store):** traces present
  (`{resource.service.name="oddyssey-mcp"}` → recent `tools/call` roots),
  metrics present (`target_info{service_name="oddyssey-mcp"}` → 1 series,
  then-version 1.7.0; `mcp_server_operation_duration_seconds_count` by
  tool → config_get 2 / status 4 / config_set 13), logs absent
  (`gcx logs labels -l service_name` → `data: null`), profiles absent for
  the service (`gcx profiles labels -l service_name` → `["pyroscope"]`).

### Scenario record (verbatim)

```text
Scenario: stack-config-lifecycle (#117 + #112) - 8 one-shot lifecycle calls,
          each its own stdio server process
Server:   src/mcp-server/.venv/bin/oddyssey-mcp  (branch fix/stack-config-lifecycle,
          cwd = repo root, telemetry default-on, HOME=<scratch>/fakehome so
          CONFIG_PATH is isolated; isolated config starts ABSENT = defaults,
          same ports 3000/4317/4318)
Driver:   HOME=<scratch>/fakehome npx -y @modelcontextprotocol/inspector@2.3.0
          --cli src/mcp-server/.venv/bin/oddyssey-mcp --method tools/call
          --tool-name <tool> [--tool-arg '<key>=<json>']
          stdout JSON + stderr captured per call; docker inspect + isolated
          config snapshot between calls
Backend:  C2 = odd_stack_up, env: {"GF_LOG_LEVEL": "debug"} (creation);
          C4 = odd_stack_reset, env: {"X_DEMO_TOKEN": "fake"}; C3/C6 = bare
          odd_stack_reset; embedded defaults otherwise
Warmup:   C0 only (npx cold cache in the fake HOME, 11.2 s; lifecycle
          one-shots - counts fixed at 1 per step by the mission:
          expensive-iteration carve-out, observations, not quantiles)
Started (UTC): 2026-08-28T15:31:53Z
Ended   (UTC): 2026-08-28T15:37:00Z
Commands (sequential; client = inspector wall time):
  C0 15:31:53 odd_config_get                    -> rc 0, defaults, stack_config:{}   11206.4 ms (cold npx)
  C1 15:32:20 odd_stack_down                    -> rc 0, running:false                3608.7 ms
     snapshot: container absent (pre-run 6b863c0682c1 destroyed)
  C2 15:32:30 odd_stack_up   env={"GF_LOG_LEVEL":"debug"}
              -> rc 0, env_applied:true, env_persisted:["GF_LOG_LEVEL"]               5863.8 ms
     snapshot: container ccef25ffceb3 (started 15:32:32.470Z), GF_LOG_LEVEL=debug
               in .Config.Env; isolated config = {"stack_config":{"local":
               {"GF_LOG_LEVEL":"debug"}}}
  C3 15:34:04 odd_stack_reset (bare)
              -> rc 0, env_reapplied:["GF_LOG_LEVEL"],
                 services_wiped:[oddyssey-mcp, otelcol-contrib]                       6215.6 ms
     snapshot: container dcf5338da26f (started 15:34:06.295Z), GF_LOG_LEVEL=debug;
               config unchanged
  C4 15:35:12 odd_stack_reset env={"X_DEMO_TOKEN":"fake"}
              -> rc 0, env_applied:true, env_reapplied:["GF_LOG_LEVEL"],
                 env_not_persisted:["X_DEMO_TOKEN"],
                 services_wiped:[oddyssey-mcp, otelcol-contrib]                       6274.8 ms
     snapshot: container f6e9e6cca801 (started 15:35:14.136Z), .Config.Env has
               GF_LOG_LEVEL=debug AND X_DEMO_TOKEN=fake; config still only
               GF_LOG_LEVEL (0 occurrences of the token value in the file)
  C5 15:35:29 odd_config_set config={"stack_config":{"local":{"GF_LOG_LEVEL":null}}}
              -> rc 0, effective stack_config.local = {} (key gone), NO reset         1445.6 ms
     snapshot: same container f6e9e6cca801, env untouched (sticky until reset);
               config = {"stack_config":{"local":{}}}
  C6 15:36:43 odd_stack_reset (bare, cleanup + deletion proof)
              -> rc 0, NO env_applied/env_reapplied/env_persisted/env_not_persisted,
                 services_wiped:[oddyssey-mcp, otelcol-contrib]                       6301.3 ms
     snapshot: container 68ef41552dbd (started 15:36:45.708Z), .Config.Env user
               entries = [PROMETHEUS_EXTRA_ARGS=--enable-feature=otlp-deltatocumulative]
               only (embedded default) - no GF_LOG_LEVEL, no X_DEMO_TOKEN
  C7 15:36:58 odd_stack_status                  -> rc 0, all four signals true        1529.5 ms
stderr: 0 bytes on C1-C7; C0's 522 bytes are npm cache/deprecation notices
        (cold fake-HOME npx cache), not server output
Not reproducible: none (fixed payloads; X_DEMO_TOKEN's value "fake" is the
        mission's own placeholder, not a credential; image pinned in the server)
```

Store-scoped query points (traces need ~35–45 s to become searchable;
each store is wiped by the next reset, so queries were sequenced
per-store): W1 after C2 (post-C2 store), W2 after C3, W3 after C5
(post-C4 store, holds C4+C5), W4 after C7 (final store, holds C6+C7).

## 2. Observed behavior

All numbers are one-shot observations (n=1 per call, n=3 for bare/env
resets) under the expensive-iteration carve-out — structure and magnitude,
never quantiles.

| Operation | Requests | client (ms) | server root span (ms) | Error % | docker calls per req | Notable |
|---|---|---|---|---|---|---|
| `odd_config_get` (C0) | 1 | 11206.4 (cold npx) | trace lost (store destroyed by C1) | 0 | 0 | isolated defaults returned |
| `odd_stack_down` (C1) | 1 | 3608.7 | trace lost (exported into the dying store, by design) | 0 | rm | running:false |
| `odd_stack_up` creation (C2) | 1 | 5863.8 | 4385.9 — trace `a38529ffa29f76382ce889361a94cb73` | 0 | inspect(exit 1) + run (153.8 ms) | 14 spans; `env_applied:true`, `env_persisted` |
| `odd_stack_reset` (C3 bare, C4 env, C6 bare) | 3 | 6215.6 / 6274.8 / 6301.3 | 4767 / 4794 / 4823 — traces `c16fd168…`, `7d4a9dc5…`, `be89eb8c…` | 0 | 3x inspect + rm + run | identical 22-span shape 3/3, full pre-rm phase (F3 fix holds) |
| `odd_config_set` null deletion (C5) | 1 | 1445.6 | 25.3 — trace `9d649d337f27eb67b017fd49b956e2a4` | 0 | 1 inspect (23.8 ms = ~94% of the span) | no reset, config-file-only |
| `odd_stack_status` (C7) | 1 | 1529.5 | 50 — trace `944ce1c2c55094ed1929d8ee13332c51` | 0 | 0 (4 httpx GET-200) | pipeline sanity |
| httpx GET boot-poll (per creation/reset) | 8 | — | 1.2–9.3 each | 8/8 transport-error by design (booting) | — | ReadError + full stacktrace event per span (unchanged noise) |
| httpx GET pre-rm enumeration (per reset) | 3 | — | — | 0 (all 200) | — | pre-wipe stored-services GETs present in-trace (F3 fix) |
| httpx POST `/v1/traces` OTLP-ready (per creation/reset) | 1 | — | — | 415 by design | — | unchanged |

**The lifecycle contract, field by field (the focus) — all exact:**

| Step | Expected (mission contract) | Observed | Verdict |
|---|---|---|---|
| C2 up-creation with env | `env_applied: true`, `env_persisted: ["GF_LOG_LEVEL"]`, value stored in `stack_config.local` | exactly that; config file `{"stack_config":{"local":{"GF_LOG_LEVEL":"debug"}}}`; container env carries it | PASS |
| C3 bare reset | `env_reapplied: ["GF_LOG_LEVEL"]`, recreated container still carries the variable | exactly that; `docker inspect` on `dcf5338da26f` → `GF_LOG_LEVEL=debug`; no spurious `env_applied`/`env_persisted` | PASS |
| C4 reset with credential-named var | applied to container, `env_not_persisted: ["X_DEMO_TOKEN"]`, absent from config | exactly that, plus `env_applied: true` and `env_reapplied: ["GF_LOG_LEVEL"]`; container carries both vars; config file has 0 occurrences of name and value | PASS |
| C5 null deletion | key gone from config | `stack_config.local` = `{}` (present-but-empty = documented "not configured"); no reset triggered; container untouched | PASS |
| C6 bare reset after deletion | recreated container no longer carries GF_LOG_LEVEL | result has NO env fields at all; `.Config.Env` user entries = embedded default only | PASS |

Secret-hygiene cross-check: the string `fake` appears 0 times in the
isolated config file, 0 times in 64.5 KB + 3.3 KB of fetched trace JSON
(C4, C5), 0 times in 62.2 KB of series output
(`gcx metrics series '{service_name="oddyssey-mcp"}'`); the name
`X_DEMO_TOKEN` also appears 0 times in the trace JSON — env reaches
telemetry neither by name nor by value.

**Trace evidence per store** (every store produced by the scenario was
queried before its wipe):

- W1 (post-C2): `{resource.service.name="oddyssey-mcp"}` → 1 trace,
  `tools/call odd_stack_up` `a38529ff…` — root SERVER span
  (`gen_ai.tool.name=odd_stack_up`, `mcp.method.name=tools/call`,
  `network.transport=pipe`) + `oddyssey.docker.inspect` exit 1 +
  `oddyssey.docker.run` exit 0 + 8 GET ERROR + 4 GET 200 + POST 415 = 14
  spans. Resource: `service.version=1.7.2`,
  `deployment.environment.name=local`, no `service.instance.id`.
- W2 (post-C3): reset trace `c16fd168…` = 22 spans: root + 3x
  `oddyssey.docker.inspect` (exits 0,0,1) + `rm` + `run` + 3 pre-rm
  GET-200 (stored-services enumeration) + 8 boot-poll GET ERROR + 4
  readiness GET-200 + POST-415. The pre-rm phase is present — the
  baseline's F3 fix is intact on this branch.
- W3 (post-C4/C5): C4 reset trace `7d4a9dc5…` grouped-identical to C3's
  (22 spans); C5 config_set trace `9d649d33…` = 2 spans (root 25.3 ms +
  one state-inspect 23.8 ms) — the null deletion is config-file-only, no
  stack activity, exactly as documented.
- W4 (final): C6 reset trace `be89eb8c…` grouped-identical (22 spans); C7
  status trace `944ce1c2…` = root 50 ms + 4 GET-200.

**Metrics evidence (final store)** — and the caveat that comes with it:

- `sum by (gen_ai_tool_name)(mcp_server_operation_duration_seconds_count)`
  → `odd_stack_reset=1` (C6), `odd_stack_status=5`, `odd_config_get=2`,
  `odd_config_set=13`. Only the reset count is this run's; the rest is the
  cumulative history of a co-resident live server — see F4.
  `…_sum{gen_ai_tool_name="odd_stack_reset"}` = 4.8240 s, matching C6's
  root span (4823 ms) to the millisecond.
- Span-derived metrics (per-store, trace-derived, **clean**):
  `traces_spanmetrics_calls_total{service="oddyssey-mcp"}` → reset root=1,
  status root=1, inspect=3, rm=1, run=1, GET ERROR=8, GET UNSET=11
  (4 boot + 4 status + 3 pre-rm), POST ERROR=1 — exactly C6+C7's spans,
  nothing else. On shared-store metrics questions, spanmetrics are the
  trustworthy counter here, `mcp_server_*` is not (F4).
- httpx accounting (final store,
  `sum by (method, status, server_port)(http_client_request_duration_seconds_count{service_name="oddyssey-mcp"})`):
  GET-200 :3000=27, POST-415 :4318=3, and GET-200 **:3001**=7 — my
  processes account for 11 of the :3000 GETs and 1 POST; the rest,
  including the :3001 series (a port this scenario never used), is the
  live installed server's process-lifetime history re-exported into the
  fresh store (single-signal attribution via `target_info` versions, part
  of F4).
- `target_info{service_name="oddyssey-mcp"}` → **two series**:
  `service_version="1.7.2"` (this run's branch processes) and
  `service_version="1.7.0"` (the installed live server) — both
  `deployment_environment_name="local"`.

Baseline deltas (vs 2026-08-26-1039 verify / 2026-08-26-1003):

| Item | Baseline | This run | Delta |
|---|---|---|---|
| New result fields env_persisted / env_reapplied / env_not_persisted | did not exist (pre-#117 code) | present, exact per contract, 5/5 lifecycle checks | **new — the fix under test, PASS** |
| Bare reset client / root span | 6018.6–6411 ms / (trace lost pre-fix) | 6215.6–6301.3 ms / 4767–4823 ms (n=3) | unchanged magnitude |
| Reset trace pre-rm phase (F3 fix) | fixed at 25 spans on config_set path | present on plain-reset path too: 22 spans 3/3 | **holds** |
| status root span | 50 / 57 ms | 50 ms | unchanged |
| Tool-span dedup (1 span per call) | holds | holds (spanmetrics root=1 per landed call) | holds |
| `service.instance.id` absent | absent | absent (all traces + all series) | holds |
| stderr silence | 0 bytes x 7 | 0 bytes x 7 (C1–C7) | holds |
| Boot-poll stacktrace events | 8 per reset trace | 8 per reset trace (3/3) | unchanged (open) |
| Env value never in results/telemetry | 0 hits | 0 hits (config, stdout, 130 KB telemetry) | holds |
| Sticky env on container (#62 side effect) | GF_LOG_LEVEL=debug left active | pre-run container still carried it (2 days later); **end state now clean** via null deletion + reset | improved end-state hygiene (the mechanism — persisted config — is the #117 design) |
| Port-move latency F4 / darkness F5 (baseline findings) | ~14.5 s / dark | not exercised (no port change in this scenario) | not measured |

Service graph (final store): `traces_service_graph_request_total` →
`user → oddyssey-mcp` = 2 (`connection_type="virtual_node"`); no outbound
edges — unchanged, inherent to a leaf service driving subprocesses.

## 3. Anomalies and probable causes

| # | Finding | Severity | Confidence | Evidence | Expected gain |
|---|---|---|---|---|---|
| N1 | #117/#112 lifecycle contract fully correct — persist on creation, reapply on bare recreation, credential exclusion, null deletion honored by next recreation | — (pass, the fix under test) | confirmed (cross-signal: tool results + docker inspect + config snapshots + landed traces) | §2 lifecycle table, 5/5 exact | close #117 and #112 |
| N2 | Co-resident installed servers pollute every fresh store's metrics: a long-lived `uvx oddyssey-mcp==1.7.0` (PID 43958) re-exports its cumulative history into each recreated store within one export interval; without `service.instance.id` (spec decision #9) its series are indistinguishable from the observed processes' | medium (for the ODD loop's metric-based verification on shared machines) | confirmed | fresh post-C2 store already held config_get=2/status=4/config_set=13 (pre-wipe values) 40 s after creation; reproduced on all 4 stores; after C5, config_set read 14 (13+1 merged); `target_info` shows both 1.7.0 and 1.7.2; `ps` shows the live processes; alien GET-200 :3001=7 series in the final store | metric checks become attributable; until then, trace-derived spanmetrics are the reliable counter |
| N3 | Sticky container env is real and invisible: the pre-run container still carried `GF_LOG_LEVEL=debug` 2 days after the run that applied it; `odd_config_get`/`odd_stack_status` do not surface active container env (baseline decision 4, still open) — #117's persistence now makes the config file the visible source of truth, but only for persisted vars (X_DEMO_TOKEN-class vars remain dark until the next reset drops them) | low | confirmed | pre-run `docker inspect 6b863c0682c1` → GF_LOG_LEVEL=debug with no trace in any config; C4→C5 window: container carried X_DEMO_TOKEN while config showed nothing | surfacing active env closes the gap |
| N4 | Boot-poll exception noise unchanged: every creation/reset trace carries 8 ERROR GET spans each with a full `exception.stacktrace` event (~30 KB of a 65 KB trace JSON) for connection failures that are expected during boot | low | confirmed | C2 trace `a38529ff…` events; 8 ERROR GETs in 4/4 creation traces; carried open from both baselines | leaner traces; expected-failure semantics |
| N5 | `odd_config_set` null deletion spends ~94% of its server span on one docker state-inspect (23.8 of 25.3 ms) that exists only to decide reset-necessity — for a stack_config-only partial that can never trigger a reset | negligible (25 ms absolute) | confirmed | C5 trace `9d649d33…` span breakdown | none worth taking; recorded for completeness |
| N6 | C0/C1 telemetry is unobservable-by-construction: C0's spans flushed into the pre-run store that C1 destroyed; C1's own spans flushed toward the store dying under it (`stack_down(flush=True)` is the terminal-down design) | low (by design) | confirmed | W1 store held exactly 1 trace (C2's); baseline F5 chain | none — documented cost of observing the wiper |

## 4. Improvement opportunities

1. **Close #117 and #112** — the observed contract matches the mission's
   expectation on all five lifecycle checks with zero deviations. Proof
   queries for the closing PR are this report's §2 lifecycle table; the
   whole scenario replays in ~5 minutes via §7.
2. **Make shared-store metrics attributable (N2)** — e.g. an opt-in
   per-process identity (revisit spec decision #9 with a bounded-cardinality
   alternative: a `service.instance.id` only when `OTEL_RESOURCE_ATTRIBUTES`
   opts in is already supported — document it for observation runs), or a
   documented rule that ODD-loop metric checks on the local stack must use
   `traces_spanmetrics_*` instead of `mcp_server_*`. Expected gain: a fresh
   store's `mcp_server_operation_duration_seconds_count` equals the driven
   calls (today: off by the polluter's full history, 13+ counts within
   60 s). Verification query:
   `sum by (gen_ai_tool_name)(mcp_server_operation_duration_seconds_count)`
   on a store created seconds earlier — expect only the driving session's
   tools. Validated against this run's four stores (all showed the
   contamination; the query itself returns data — `not validated` for the
   fixed case).
3. **Surface active container env (N3)** — one `env_active` (names-only)
   field on `odd_stack_status` or `odd_config_get`, read from
   `docker inspect .Config.Env` minus image/defaults (the
   `container_user_env()` helper already computes exactly this). Expected
   gain: the X_DEMO_TOKEN-class dark window (applied-but-not-persisted)
   becomes visible without docker access. Verification: after a reset with
   a credential-named var, the status result lists its name. `not
   validated` (field does not exist yet).
4. **Demote expected boot-poll failures (N4)** — suppress the stacktrace
   event (or the ERROR status) on readiness-probe transport errors during
   the boot loop. Expected gain: creation/reset trace JSON shrinks ~45%
   (30 of 65 KB measured), signal-to-noise up. Verification:
   `gcx traces get <new reset trace>` → 0 `exception` events on boot-poll
   GETs. Validated: the current count (8/trace) is reproducibly measurable
   with the same fetch.

## 5. Telemetry gaps

- **Logs: absent for oddyssey-mcp** (spec-scoped out, unchanged) —
  `gcx logs labels -l service_name` → `{"status":"success","data":null}`
  (pre-run and final store).
- **Profiles: absent for oddyssey-mcp** (spec-scoped out, unchanged) —
  `gcx profiles labels -l service_name -d pyroscope` → `["pyroscope"]`
  (stack self-profile only), pre-run and final store.
- **Metric identity gap (drives N2):** no per-process label on
  `mcp_server_*`/`http_client_*` series — spec decision #9. Discovery
  evidence: 62.2 KB of `gcx metrics series '{service_name="oddyssey-mcp"}'`
  output contains no instance-shaped label; only `target_info`'s
  `service_version` separates the two co-exporting processes, and only
  while their versions differ.
- **The wiper's own down-path is dark (N6):** `odd_stack_down` and
  anything before it in the same store cannot be observed after the down —
  by design (`flush=True` on terminal down). Evidence: W1 store held only
  C2's trace; C0/C1 traces nowhere (bounded search, 2 stores).
- **Grafana debug-level effectiveness not re-probed** — the container ran
  with `GF_LOG_LEVEL=debug` during C2–C5 but this run did not repeat the
  baseline's `docker logs` grep before C6 recreated the container; the
  baseline's verdict (env proven in container, no debug lines observed in
  the image's boot log) stands unre-tested.
- No `otel-instrumentation-expert` handoff needed: every gap is either
  design-scoped (logs, profiles, down-path) or a spec decision (identity),
  not missing instrumentation code.

## 6. Decisions the spec must settle

1. **Metric attribution on a shared stack (from N2):** is spec decision #9
   (no `service.instance.id`) to be amended with a bounded-cardinality
   identity, or is the loop's contract "metric counts on the local stack
   are advisory; trace-derived spanmetrics are the counters"? Today both
   installed and under-test servers write the same series.
2. **Active-env visibility (from N3, baseline decision 4, third run
   carrying it):** should the server surface the container's live user env
   (names only)? #117 answers it for persisted vars; the
   applied-but-not-persisted class remains invisible by design unless a
   surface is added.
3. **Empty `stack_config.local` entry after the last deletion:** C5 left
   `{"stack_config":{"local":{}}}` — the code documents present-but-empty
   as "not configured". Confirm this shape is the intended public contract
   (it is what `odd_config_get` will show users), or prune empty entries.
4. **Boot-poll error semantics (from N4):** are readiness-probe transport
   failures during boot ERROR spans with stacktraces, or expected events?

## 7. Measurement protocol for the fix / next run

**Replay:** the exact 8 commands of §1's scenario record (same driver,
same order, same isolated-HOME arrangement with an ABSENT scratch config,
same env payloads, same per-store query points W1–W4). The stack must
start from a present container so C1 exercises the down; ports
3000/4317/4318. All counts n=1 per call by design (expensive-iteration
carve-out): compare by structure and magnitude, never value-to-value.

Checks, before-values (this run), and pass criteria:

| Check | Query / method | Before-value (this run) | Pass criterion | Validated |
|---|---|---|---|---|
| 1. Creation persists env | C2 result JSON | `env_applied:true`, `env_persisted:["GF_LOG_LEVEL"]` | identical fields | positive this run |
| 2. Config file holds persisted value | cat isolated config after C2 | `{"stack_config":{"local":{"GF_LOG_LEVEL":"debug"}}}` | identical | positive this run |
| 3. Bare reset reapplies | C3 result + `docker inspect --format '{{json .Config.Env}}'` | `env_reapplied:["GF_LOG_LEVEL"]`; var in .Config.Env | both present, no `env_persisted`/`env_applied` fields | positive this run |
| 4. Credential exclusion | C4 result + config grep | `env_not_persisted:["X_DEMO_TOKEN"]`; 0 name/value hits in config | identical; 0 hits | positive this run |
| 5. Null deletion | C5 result + config | `stack_config.local == {}`, no reset (same container id) | identical | positive this run |
| 6. Deletion honored on recreation | C6 result + `docker inspect` | no env fields; user env = embedded default only | identical | positive this run |
| 7. Reset trace lands with pre-rm phase | `gcx traces query '{resource.service.name="oddyssey-mcp" && name="tools/call odd_stack_reset"}'` per store, then get | 22 spans: root + inspect x3(0,0,1) + rm + run + 3 pre-rm GET-200 + 8 GET ERR + 4 GET 200 + POST 415; 3/3 identical | same grouped structure (N4 fix would remove the 8 stacktrace events, not the spans) | positive on 3 stores this run |
| 8. Creation trace lands | same search for `odd_stack_up` on the post-C2 store | 14 spans, root 4385.9 ms | same structure; root 3–7 s | positive this run |
| 9. Null-deletion trace | `gcx traces get <C5-trace>` | 2 spans (root 25.3 ms + inspect 23.8 ms) | 2 spans, root < 100 ms | positive this run |
| 10. No secret in config/results/telemetry | grep value + name over config, stdout captures, fetched trace JSONs, series output | 0 / 0 / 0 / 0 | all 0 | positive control: token name present in C4's `env_not_persisted` result while absent everywhere else |
| 11. Resource attrs | trace resource + `target_info` | `service.version=1.7.2`, `deployment.environment.name=local`, no instance id | version = built branch's; env local; id absent unless spec #9 amended | positive this run |
| 12. Spanmetrics match driven calls | `traces_spanmetrics_calls_total{service="oddyssey-mcp"}` on final store | reset=1, status=1, inspect=3, rm=1, run=1, GET ERR=8, GET UNSET=11, POST ERR=1 | equals the store's landed spans | positive this run |
| 13. Shared-store contamination marker (N2) | `sum by (gen_ai_tool_name)(mcp_server_operation_duration_seconds_count)` on a seconds-old store | polluted: config_set=13, status=4–5, config_get=2 beyond driven calls | after an N2 fix: only driven calls; until then: expect pollution when an installed server runs (check `ps aux \| grep oddyssey-mcp` and `target_info` versions to interpret) | query validated this run (returned the polluter's counts); `not validated` for the fixed case |
| 14. Real user config untouched | `shasum -a 256 ~/.oddyssey/config.json` before/after | `f010281d5bf1…35c3e` unchanged (3 measurements) | identical before/after | positive this run |
| 15. Pipeline sanity | C7 status result + its trace | all four true; root 50 ms | lands, all true | positive this run |

**Backend/env record for replay:** C2 `odd_stack_up`
env `{"GF_LOG_LEVEL": "debug"}`; C4 `odd_stack_reset`
env `{"X_DEMO_TOKEN": "fake"}` (placeholder, not a credential); C3/C6 bare.
A replay must reproduce these payloads or checks 1–6 are meaningless.

**Environment left as found and ready:** `oddyssey-lgtm` = `68ef41552dbd`,
Up (healthy), image `grafana/otel-lgtm:0.31.0`, default ports
3000/4317/4318 (grafana :3000 → 200, OTLP :4318 POST → 415), embedded
defaults only — no leftover scenario env (proven by check 6). `gcx config
check` ✔ online. The stack stays UP for the main agent's next measurement.
Final store contents = exactly C6's reset trace + C7's status trace and
their metrics (plus the installed servers' ongoing background export, per
N2). The user's real `~/.oddyssey/config.json` is byte-identical
(check 14). The isolated scratch config and capture files live under the
session scratchpad and are ephemeral.
