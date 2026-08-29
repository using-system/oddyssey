---
services: [oddyssey-mcp]
stack: local
environment: local
mode: verify
window: 2026-08-29T11:07:57Z/2026-08-29T11:11:24Z
run_name: stack-config-lifecycle
verifies: 2026-08-29-0953-verify-stack-config-lifecycle.md
date: 2026-08-29
revision: 3090523
instance: {oddyssey-mcp: "service.instance.id=odd-verify-n2-1105 on every driven process (opt-in via OTEL_RESOURCE_ATTRIBUTES, one shared run slug per protocol; passed through MCP Inspector's -e flag - the parent shell env does NOT reach the spawned server). Co-resident servers exporting to the same stack: uvx oddyssey-mcp==1.8.1 (PID 1964, this Claude Code session's server, no instance id) and ==1.2.0 (PID 60321, exports nothing visible)"}
process_restarted: true
---

# Verification report — opt-in instance identity (#148, v1.8.2), protocol of 2026-08-29-0953 replayed

Verifies `2026-08-29-0953-verify-stack-config-lifecycle.md` — the #119
carve-out case: that report is itself a verification, and it is **its own
§7 protocol** (18 checks) that this run replays, so it is the legal
`verifies` target. Fix under test: **#148** (opt-in
`service.instance.id`), shipped in v1.8.2 via PR #153 (`f9ff9e0` — spec
decision #9 amended in the design doc, pinning tests, and run-scenario
guidance; the runtime opt-in path `telemetry.py:162` — keep the id only
when `service.instance.id=` appears in `OTEL_RESOURCE_ATTRIBUTES` —
already existed at the baseline's revision). The headline is the
baseline's check 13, whose fixed case was `not validated` to date.

## 1. Mission and run record

- **Service:** `oddyssey-mcp` built from branch `docs/close-n2-by-evidence`,
  HEAD `3090523` (= the v1.8.2 release commit), tree clean. Binary
  `src/mcp-server/.venv/bin/oddyssey-mcp`; `uv sync --project
  src/mcp-server` re-installed editable oddyssey-mcp 1.8.1 → **1.8.2**
  before the run; every landed trace and `target_info` series reports
  `service.version=1.8.2`, separating the driven processes from the
  installed 1.8.1.
- **Stack/backend:** local (Grafana LGTM, `grafana/otel-lgtm:0.31.0`,
  Grafana 13.1.3), ports 3000/4317/4318 (from `odd_config_get`, not
  assumed). Query CLI: gcx via the `setup-local-stack` isolated
  `GCX_CONFIG` context at `${TMPDIR}/oddyssey/gcx-local.yaml`;
  `gcx config check` ✔ online before and after the run.
- **Mode:** `verify` (frontmatter); executed as the baseline's drive mode
  — 8 one-shot MCP lifecycle calls (C0–C7) + 2 status probes (P1/P2),
  each its own stdio server process, driven with MCP Inspector CLI 2.3.0,
  cwd = repo root.
- **Protocol addition (deliberate, the point of this run):** every driven
  server process launched with
  `OTEL_RESOURCE_ATTRIBUTES=service.instance.id=odd-verify-n2-1105`
  (one slug for the whole run — one bounded label). **Execution detail
  that matters for every future replay:** the MCP Inspector's stdio
  client passes only a whitelisted default environment (HOME, PATH, ...)
  to the spawned server — an `OTEL_RESOURCE_ATTRIBUTES` exported in the
  parent shell **never arrives**. The variable must go through the
  inspector's own `-e` flag, placed **after** the server command
  (`--cli <server-cmd> -e "OTEL_RESOURCE_ATTRIBUTES=..." --method ...`);
  placed before the command, the variadic `-e` swallows the command and
  the CLI fails with "No servers found in config file". Proven by a
  probe: a throwaway `service.instance.id=test-envpass` call produced
  `target_info{service_instance_id="test-envpass"}` = 1 series.
- **False start, recorded as data:** a first attempt (C0a 11:04:42Z →
  C2a, shell-env variant) produced a creation trace **without** the
  instance id — the whitelist behavior above. Aborted at its W1, redone
  from scratch (fresh fakehome, fresh isolation proof); all telemetry of
  the aborted attempt and of the env-pass probes lived in the pre-C1
  store, which the definitive C1 `odd_stack_down` destroyed. Cost: the
  definitive C0 ran with a warm npx cache (1145 ms instead of the
  baseline-class cold ~10–11.6 s; the false start's C0a paid the cold
  hit: 10245 ms).
- **Config isolation (hard constraint, reproven for the definitive
  run):** every server process ran with `HOME` pointed at a fresh scratch
  `fakehome`; pre-run, `Path.home()` and `oddyssey_mcp.config.CONFIG_PATH`
  resolved into it, the file was ABSENT, and `load()` returned pure
  defaults (ports 3000/4317/4318, `stack_config: {}`). C0's result showed
  `stack_config: {}` — the real config's `azure-monitor` entry absent.
  The real file's SHA-256
  `f010281d5bf184f9fa2da4c24e8d187601f9506fa69c6e968c7b53ba51835c3e`
  (byte-identical to both previous reports' recorded value) was identical
  before, during, and after the run.
- **Window:** 2026-08-29T11:07:57Z → 11:11:24Z (post-scenario queries
  until ~11:13Z read only stores produced inside the window).
- **Focus:** all 18 checks of the baseline's §7 with its before-values —
  headline check 13's previously-`not validated` fixed case — then the
  fate of the baseline's findings, with the **N2 ruling** on this
  evidence.
- **Deployment environment: `local`** — forced by construction on the
  local stack, and independently what the telemetry reports: pre-run
  `target_info{service_name="oddyssey-mcp"}` →
  `deployment_environment_name="local"` (single series), and all 7
  fetched traces carry `deployment.environment.name=local`. (The
  pre-run `gcx traces labels -l resource.deployment.environment.name`
  probe returned `[]` on the ~1 h-old store — Tempo's label-lookup
  recency window, recorded here; the attribute read fell back to
  `target_info` and was confirmed on every fetched trace.) **Matches
  the mission-stated baseline environment `local` — no divergence, no
  stop.** No provisional state.
- **Baseline:** `2026-08-29-0953-verify-stack-config-lifecycle.md`, named
  by the mission (recall walk skipped per mission; it is also the newest
  match on services+stack+environment). Read in full; its §7
  before-values and pass criteria are what this run rules on.
- **Maintainer decisions in force** (`.odd/decisions.md` read pre-run,
  never edited): baseline-chain N2 → **`tracked`** via issue #148 (row
  2026-08-29) — the mission states a superseding row will be appended by
  the caller AFTER this report's ruling; 2026-08-26-1003 F4 → wontfix;
  F5 → accepted-by-design; 2026-08-22-2154 A6 → accepted-by-design.
- **Defaults applied:** none beyond the contract's (window = scenario
  bounds; everything else was given).
- **Destruction accepted by the mission (maintainer-authorized):** 1
  `odd_stack_down` + 3 `odd_stack_reset` wipes of the machine-wide
  store. Pre-wipe store content (~11:02Z): Tempo `service.name` =
  `[oddyssey-mcp]`, `target_info` = 1 series (1.8.1),
  `mcp_server_operation_duration_seconds_count` by tool = config_get 2 /
  status 2 (the installed 1.8.1's session history, including this run's
  own two MCP preflight calls), Loki service_name absent. The pre-run
  `service_instance_id` label value
  `5353476c-1775-4442-a382-958050691834` belongs to `otelcol_*` series —
  the embedded collector's own UUID, not oddyssey-mcp's.
- **Pre-run container condition:** the 0953 baseline's own end-state
  container (created 2026-08-29T09:59:27Z, embedded defaults only,
  `env: {}` via the installed server's `odd_stack_status`), Up (healthy).
  Present, so C1 exercises the down, as the protocol requires.
- **Preflight (all four signals, pre-run store):** traces present
  (`{resource.service.name="oddyssey-mcp"}` → results), metrics present
  (`target_info` above), logs absent (`gcx logs labels -l service_name`
  → `data: null`), profiles absent for the service
  (`gcx profiles labels -l service_name -d pyroscope` → `["pyroscope"]`).
- **Co-resident servers, read first as the protocol demands:**
  `ps aux | grep oddyssey-mcp` → uvx `oddyssey-mcp==1.8.1` (PID 1964,
  this Claude Code session's server, started 09:48Z) and `==1.2.0`
  (PID 60321, days old). The mission anticipated "the installed 1.8.2";
  reality is 1.8.1 — recorded as observed. The 1.2.0 process exports
  nothing visible (no series carries it), as in the baseline.

### Scenario record (verbatim)

```text
Scenario: stack-config-lifecycle (verify replay of 2026-08-29-0953 §7)
          - 8 one-shot lifecycle calls C0-C7 (verbatim) + 2 status probes
          P1/P2, each its own stdio server process
Server:   src/mcp-server/.venv/bin/oddyssey-mcp  (branch docs/close-n2-by-evidence
          3090523, oddyssey-mcp 1.8.2, cwd = repo root, telemetry default-on,
          HOME=<scratch>/fakehome, isolated config starts ABSENT = defaults,
          ports 3000/4317/4318)
Identity: OTEL_RESOURCE_ATTRIBUTES=service.instance.id=odd-verify-n2-1105
          on every call, passed via the inspector's -e flag AFTER the server
          command (shell-env export does NOT reach the spawned server -
          stdio-client env whitelist; -e before the command breaks parsing)
Driver:   HOME=<scratch>/fakehome npx -y @modelcontextprotocol/inspector@2.3.0
          --cli src/mcp-server/.venv/bin/oddyssey-mcp
          -e "OTEL_RESOURCE_ATTRIBUTES=service.instance.id=odd-verify-n2-1105"
          --method tools/call --tool-name <tool> [--tool-arg '<key>=<json>']
          stdout JSON + stderr captured per call; docker inspect + isolated
          config snapshot between calls
Backend:  C2 = odd_stack_up, env: {"GF_LOG_LEVEL": "debug"} (creation);
          C4 = odd_stack_reset, env: {"X_DEMO_TOKEN": "fake"}; C3/C6 = bare
          odd_stack_reset; embedded defaults otherwise
Warmup:   none discarded; C0 ran warm (npx cache warmed by the recorded
          false start C0a, which paid the cold 10245 ms; counts fixed at 1
          per step by the protocol: expensive-iteration carve-out,
          observations, not quantiles)
False start (aborted, telemetry wiped by the definitive C1):
  C0a 11:04:42 (10245 ms cold) / C1a 11:04:59 / C2a 11:05:12 - shell-env
  variant; its creation trace carried NO instance id (inspector env
  whitelist); plus one test-envpass probe call
Started (UTC): 2026-08-29T11:07:57Z
Ended   (UTC): 2026-08-29T11:11:24Z
Commands (sequential; client = inspector wall time):
  C0 11:07:58 odd_config_get                    -> rc 0, defaults, stack_config:{}    1145.0 ms (warm)
  C1 11:07:59 odd_stack_down                    -> rc 0, running:false                3487.0 ms
     snapshot: container absent (baseline end-state container destroyed)
  C2 11:08:07 odd_stack_up   env={"GF_LOG_LEVEL":"debug"}
              -> rc 0, env_applied:true, env_persisted:["GF_LOG_LEVEL"]               5435.0 ms
     snapshot: container 21b38e055d2a (started 11:08:08.871Z), GF_LOG_LEVEL=debug
               in .Config.Env; isolated config = {"stack_config":{"local":
               {"GF_LOG_LEVEL":"debug"}}}
  P1 11:09:02 odd_stack_status
              -> rc 0, all four true, image grafana/otel-lgtm:0.31.0,
                 created/started 11:08:08Z, env:{"GF_LOG_LEVEL":"debug"}              1735.0 ms
  C3 11:09:11 odd_stack_reset (bare)
              -> rc 0, env_reapplied:["GF_LOG_LEVEL"],
                 services_wiped:[oddyssey-mcp, otelcol-contrib]                       6001.0 ms
     snapshot: container 6a97dc893453 (started 11:09:12.842Z), GF_LOG_LEVEL=debug;
               config unchanged
  C4 11:09:57 odd_stack_reset env={"X_DEMO_TOKEN":"fake"}
              -> rc 0, env_applied:true, env_reapplied:["GF_LOG_LEVEL"],
                 env_not_persisted:["X_DEMO_TOKEN"],
                 services_wiped:[oddyssey-mcp, otelcol-contrib]                       6467.0 ms
     snapshot: container 00feab68be07 (started 11:09:59.684Z), .Config.Env has
               GF_LOG_LEVEL=debug AND X_DEMO_TOKEN=fake; config still only
               GF_LOG_LEVEL (0 occurrences of the token name or value)
  P2 11:10:09 odd_stack_status (C4's window)
              -> rc 0, env:{"X_DEMO_TOKEN":null,"GF_LOG_LEVEL":"debug"}
                 (credential-named value REDACTED to null; 0 occurrences of
                 the value in the whole result)                                       1631.0 ms
  C5 11:10:17 odd_config_set config={"stack_config":{"local":{"GF_LOG_LEVEL":null}}}
              -> rc 0, effective stack_config.local = {} (key gone), NO reset         1331.0 ms
     snapshot: same container 00feab68be07, env untouched (sticky until reset);
               config = {"stack_config":{"local":{}}}
  C6 11:11:16 odd_stack_reset (bare, cleanup + deletion proof)
              -> rc 0, NO env_applied/env_reapplied/env_persisted/env_not_persisted,
                 services_wiped:[oddyssey-mcp, otelcol-contrib]                       6340.0 ms
     snapshot: container ee7e42b8e2a2 (started 11:11:18.318Z), .Config.Env user
               entries = [PROMETHEUS_EXTRA_ARGS=--enable-feature=otlp-deltatocumulative]
               only - no GF_LOG_LEVEL, no X_DEMO_TOKEN
  C7 11:11:22 odd_stack_status                  -> rc 0, all four true, env:{}        1268.0 ms
stderr: 0 bytes on all 10 calls (the cold-npx notices landed on the false
        start's C0a, 522 bytes of npm cache/deprecation output)
Deviation from the replayed protocol: the instance-identity env on every
        process (mission-mandated, the fix under test) and the false start
        above; nothing else
Not reproducible: none (fixed payloads; X_DEMO_TOKEN's value "fake" is the
        protocol's own placeholder, not a credential; image pinned in the server)
```

Store-scoped query points (traces searchable after ~10–20 s this run;
each store wiped by the next reset): W1 after C2 (post-C2 store, holds
C2 only — queried before P1), W2 after C3, W3 after C5 (post-C4 store,
holds C4+P2+C5), W4 after C7 (final store, holds C6+C7).

## 2. Observed behavior

All numbers are one-shot observations (n=1 per call, n=3 for resets)
under the expensive-iteration carve-out — structure and magnitude, never
quantiles.

| Operation | Requests | client (ms) | server root span (ms) | Error % | docker calls per req | Notable |
|---|---|---|---|---|---|---|
| `odd_config_get` (C0) | 1 | 1145.0 (warm npx) | trace lost (store destroyed by C1, by design) | 0 | 0 | isolated defaults returned |
| `odd_stack_down` (C1) | 1 | 3487.0 | trace lost (exported into the dying store, by design) | 0 | rm | running:false |
| `odd_stack_up` creation (C2) | 1 | 5435.0 | 4311.7 — trace `56731a992aec057cbdffd00bd1a55852` | 0 | inspect(exit 1) + run | 16 spans; `env_applied:true`, `env_persisted`; 0 exception events; **resource carries `service.instance.id=odd-verify-n2-1105`** |
| `odd_stack_reset` (C3 bare, C4 env, C6 bare) | 3 | 6001.0 / 6467.0 / 6340.0 | 4784.2 / 4858.0 / 4828.5 — traces `664e0f50e99cb3ed4e6b46441704a471`, `c55094472e883cd3520b10b32b177934`, `8123cc834318c68eb5e43745d1a45740` | 0 | 3x inspect(0,0,1) + rm + run | identical 22-span shape 3/3, pre-rm phase intact, 0 exception events 3/3, slug on all 3 resources |
| `odd_stack_status` (P1, P2, C7) | 3 | 1735.0 / 1631.0 / 1268.0 | 132.7 (P2 `b5a9c89874f69359336386d634ac322e`) / 111.8 (C7 `1f285741ef599d0bf2792ab370909d21`) | 0 | 2x inspect + image-inspect | 8 spans; identity read (#146) intact; env in result 3/3 |
| `odd_config_set` null deletion (C5) | 1 | 1331.0 | 21.3 — trace `626fda4c605700cfdbbe5c05386f6aec` | 0 | 1 inspect (19.9 ms = ~93% of the span) | no reset, config-file-only |
| httpx GET boot-poll (per creation/reset) | 8 | — | short | 8/8 transport-error by design (booting) | — | ERROR status + `error.type=ReadError`, 0 stacktrace events (N4 holds); counted in `oddyssey_stack_probe_failures_total{service_instance_id="odd-verify-n2-1105"}` = 8, 4/4 stores (A5 holds, now attributable) |
| httpx GET pre-rm enumeration (per reset) | 3 | — | — | 0 (all 200) | — | present in-trace 3/3 (F3 holds) |
| httpx POST `/v1/traces` OTLP-ready (per creation/reset) | 1 | — | — | 415 by design | — | unchanged |

**The 18-check protocol, ruled check by check** (before-values = the
baseline's §7 table):

| Check | Baseline before-value | This run | Verdict |
|---|---|---|---|
| 1. Creation persists env | `env_applied:true`, `env_persisted:["GF_LOG_LEVEL"]` | identical fields, exact (C2 result JSON) | **PASS** |
| 2. Config file holds persisted value | `{"stack_config":{"local":{"GF_LOG_LEVEL":"debug"}}}` | identical (post-C2 snapshot) | **PASS** |
| 3. Bare reset reapplies | `env_reapplied:["GF_LOG_LEVEL"]`; var in .Config.Env; no `env_persisted`/`env_applied` | identical: C3 result + `docker inspect 6a97dc893453` → `GF_LOG_LEVEL=debug` | **PASS** |
| 4. Credential exclusion | `env_not_persisted:["X_DEMO_TOKEN"]`; 0 name/value hits in config | identical; container `00feab68be07` carries both vars; config grep: 0 hits for name and value | **PASS** |
| 5. Null deletion | `stack_config.local == {}`, no reset (same container id) | identical: same container `00feab68be07`, env sticky (both vars still in .Config.Env), config `{"stack_config":{"local":{}}}` | **PASS** |
| 6. Deletion honored on recreation | no env fields; user env = embedded default only | identical: C6 result has no env fields; `ee7e42b8e2a2` carries only `PROMETHEUS_EXTRA_ARGS=…` | **PASS** |
| 7. Reset trace, pre-rm phase, quiet boot-polls | 22 spans (root + inspect x3(0,0,1) + rm + run + 3 pre-rm GET-200 + 8 GET ERR + 4 GET 200 + POST 415), 0 exception events, `error.type=ReadError` kept, 3/3 | same grouped 22-span structure 3/3 (`664e0f50…`, `c5509447…`, `8123cc83…`), 0 exception events 3/3, ERROR GETs intact | **PASS** |
| 8. Creation trace lands, quiet | 16 spans, root 4358.9 ms; criterion: same structure, root 3–7 s, 0 exception events, JSON < 40 KB | 16 spans (same census), root 4311.7 ms, 0 exception events, JSON 30.3 KB (`56731a99…`) | **PASS** |
| 9. Null-deletion trace | 2 spans (root 24.0 + inspect 22.7 ms), criterion root < 100 ms | 2 spans: root 21.3 ms + inspect 19.9 ms (`626fda4c…`) | **PASS** |
| 10. No secret in config/results/telemetry | 0/0/0/0 outside contracted surfaces | value `fake`: 0 in isolated config, 0 in all 10 stdout captures, 0 in 178 KB of fetched trace JSON (7 traces), 0 in 48.6 KB series output; name `X_DEMO_TOKEN`: 0 in trace JSONs and series. Positive controls: the name appears exactly where contracted — C4's `env_not_persisted` and P2's `env` key (value null) | **PASS** |
| 11. Resource attrs | `service.version=1.8.0`, env local, **no instance id** (criterion: id absent **unless spec #9 amended via #148**) | `service.version=1.8.2`, `deployment.environment.name=local`, **`service.instance.id=odd-verify-n2-1105`** on all 7 fetched traces and on `target_info` — a DELIBERATE protocol deviation from the "id absent" before-value, justified by the opt-in under test: spec decision #9 as amended by #148/#153 is exactly the criterion's carve-out. NOT a regression | **PASS** (per the amended criterion) |
| 12. Spanmetrics match driven calls | reset=1, status=1, inspect=5, image-inspect=1, rm=1, run=1, GET ERR=8, GET UNSET=11, POST ERR=1 (= C6's 22 + C7's 8 spans) | identical, value for value: `sum by (span_name)(traces_spanmetrics_calls_total{service="oddyssey-mcp"})` → reset=1, status=1, inspect=5, image-inspect=1, rm=1, run=1, GET=19 (UNSET=11 + ERR=8), POST ERR=1 — sums to exactly 30 landed spans | **PASS** |
| 13. Contamination marker → **attribution by opt-in (headline)** | polluted: status +2, config_get +2 beyond driven calls (no-id 1.8.1); fixed-case criterion "counts equal driven calls per process" was **`not validated`** | **VALIDATED POSITIVE.** `ps aux` read first (uvx 1.8.1 PID 1964, uvx 1.2.0 PID 60321), then `target_info` (1.8.2+slug / 1.8.1+no-id). Seconds-old final store, `sum by (gen_ai_tool_name, service_instance_id)(mcp_server_operation_duration_seconds_count)`: **`{service_instance_id="odd-verify-n2-1105"}` → reset=1, status=1 = exactly the store's driven calls (C6+C7)**; W3 store: reset=1, status=1, config_set=1 = exactly C4+P2+C5. The co-resident 1.8.1's pollution is still present AND now cleanly separable: its series carry no id (config_get=3, status=3 — its process-lifetime totals re-exported into the fresh store; cross-consistent with its no-id httpx GET-200=12 = 3 status calls x 4 probes). Cross-signal: `…_sum{odd_stack_reset, slug}` = 4.8286 s = C6's root span 4828.5 ms to the ms. Residual, expected and documented: processes sharing the run slug still share cumulative httpx series — slug GET-200:3000 = 4 = C7's lifetime total overwriting C6's 7 (last-writer-wins), so within a same-slug group spanmetrics remain the counters (run-scenario guidance added by #153 says exactly this: one bounded label per run, attribution by name) | **PASS — fixed case confirmed** |
| 14. Real user config untouched | SHA-256 `f010281d…35c3e` unchanged | identical SHA before, mid-run (x2), and after — and identical to both previous reports' recorded value | **PASS** |
| 15. Pipeline sanity + identity surface | all four true; identity fields present; `env:{}` clean; root 126.8 ms, 8 spans | all four true; `image`/`created`/`started` present; `env:{}` (C7); root 111.8 ms; 8 spans (root + 4 GET-200 + 2 inspect + image-inspect) | **PASS** |
| 16. Probe-failure counter (A5 regression) | `{error_type="ReadError"} = 8` per boot, 4/4 stores | `= 8` on W1, W2, W3, W4 — and the series now carries `service_instance_id="odd-verify-n2-1105"`, so probe failures are attributable too | **PASS** |
| 17. Status env surface (N3 regression) | P1 `env:{"GF_LOG_LEVEL":"debug"}`; P2 adds `"X_DEMO_TOKEN": null`; C7 `env:{}` | identical 3/3: P1 exact; P2 `{"X_DEMO_TOKEN":null,"GF_LOG_LEVEL":"debug"}`, 0 value occurrences; C7 `{}` | **PASS** |
| 18. image-inspect span (F2 regression) | 1 per status call, attr `oddyssey.docker.image=<sha256 .Image id>`, no container attr | present in both fetched status traces (`b5a9c898…` 37.0 ms, `1f285741…` 33.7 ms) with `oddyssey.docker.image=sha256:f1e548c2…` (same pinned image as the baseline) + `exit_code=0`, no container attr; `traces_spanmetrics_calls_total{span_name="oddyssey.docker.image-inspect"}` = 1 on the final store | **PASS** |

**Verdict: 18/18 — 17 passes on unchanged criteria, check 11 passed on
its own amended-spec carve-out, and check 13's previously-unvalidatable
fixed case is now validated positive.**

**Metrics evidence (per store):**

- A5 counter: `sum by (error_type, service_instance_id)(oddyssey_stack_probe_failures_total)`
  → `{ReadError, odd-verify-n2-1105} = 8` on each fresh store (W1–W4),
  matching each trace's 8 ERROR boot-poll GETs one-for-one.
- `target_info{service_name="oddyssey-mcp"}` → exactly two identities
  wherever both exported: `("1.8.2", "odd-verify-n2-1105", "local")` and
  `("1.8.1", <no id>, "local")`. On W1 (seconds after the wipe) only the
  driven identity existed — the polluter re-exports on its next periodic
  cycle, which is why a seconds-old store is the protocol's read point.
- httpx accounting by instance id (final store): slug → GET-200:3000 = 4,
  POST-415:4318 = 1; no-id → GET-200:3000 = 12. The slug's 4 is the
  same-series interleave described in check 13. The 8 failed boot-poll
  GETs appear in traces and in the A5 counter but produce no
  `http_client_request_duration_seconds` row — unchanged from the
  baseline (same decomposition there), an instrumentation behavior on
  transport errors, and A5 exists precisely to cover it.
- Service graph: `traces_service_graph_request_total` →
  `user → oddyssey-mcp` = 2 (`connection_type="virtual_node"`), no
  outbound edges — unchanged, leaf service driving subprocesses.

**Verdict deltas vs baseline (per operation):**

| Item | Baseline (0953) | This run | Delta |
|---|---|---|---|
| Lifecycle contract fields (checks 1–6) | 6/6 exact | 6/6 exact | **unchanged — holds on v1.8.2** |
| Bare/env reset client / root | 6001.9–6472.1 / 4790–4855 ms (n=3) | 6001.0–6467.0 / 4784.2–4858.0 ms (n=3) | unchanged magnitude |
| Creation root span | 4358.9 ms | 4311.7 ms | unchanged |
| status root span | 126.8–135.3 ms (n=2) | 111.8–132.7 ms (n=2) | unchanged (identity read cost stable) |
| config_set null-deletion root | 24.0 ms | 21.3 ms | unchanged |
| Creation / reset trace JSON | 30.1 / 38.8 KB | 30.3 / 39.0 KB | unchanged |
| Boot-poll exception events | 0 per trace | 0 per trace, 4/4 creation+reset traces | holds (N4) |
| Probe-failure counter | 8/boot, 4/4 stores | 8/boot, 4/4 stores, **now with instance id** | holds (A5), improved attribution |
| Status env surface | present 3/3 | present 3/3 | holds (N3) |
| image-inspect span | in status traces, sha256 attr | identical, same image sha | holds (F2) |
| **Instance identity** | absent everywhere (spec #9 pre-amendment) | **`service.instance.id=odd-verify-n2-1105` on all 7 traces, `target_info`, `mcp_server_*`, `http_client_*`, `oddyssey_stack_probe_failures_total`** | **new — the #148 opt-in, working end-to-end** |
| stderr silence / secret hygiene / real-config SHA | hold | hold (0 bytes x10; 0 hits; SHA identical) | hold |

## 3. Anomalies and probable causes — fate of every baseline finding

| # | Baseline finding | Fate | Confidence | Evidence |
|---|---|---|---|---|
| N1 | #117/#112 lifecycle contract fully correct | **still correct** — 6/6 on v1.8.2 | confirmed (cross-signal: results + docker inspect + config snapshots + traces) | §2 checks 1–6 |
| N2 | Co-resident servers pollute fresh-store metrics; attribution impossible without an instance identity | **FIXED** — ruling below | confirmed | check 13; §2 metrics evidence |
| N3 | Sticky container env invisible | **holds fixed** (#146) | confirmed (tool results x3 + docker inspect cross-check) | check 17 |
| N4 | Boot-poll exception noise | **holds fixed** (#149): 0 exception events on all 4 creation/reset traces; ERROR statuses + `error.type` intact | confirmed | check 7, 8; trace fetches |
| N5 | config_set null deletion ~94% on one state-inspect | **unchanged, by design** — 19.9 of 21.3 ms (~93%) | confirmed | trace `626fda4c…` |
| N6 | C0/C1 telemetry unobservable-by-construction | **unchanged, by design** — W1 store held C2's trace only | confirmed | W1 inventory: `["tools/call odd_stack_up"]` |
| A5 (2026-08-22-2227) | probe failures trace-only | **holds fixed** (#149) — and the counter now carries the opt-in id | confirmed | check 16 |
| F2 (2026-08-26-1003) | image-read span backend-invisible | **holds fixed** (#149) | confirmed | check 18 |

**The N2 ruling (the mission's ask):**

**N2 is FIXED by #148 (v1.8.2, PR #153), on this evidence:**

1. **Attribution is achievable by opt-in, proven end-to-end in the
   backend:** every driven process launched with
   `OTEL_RESOURCE_ATTRIBUTES=service.instance.id=odd-verify-n2-1105`
   put the id on its traces' resource, on `target_info`, and on every
   `mcp_server_*`, `http_client_*`, and
   `oddyssey_stack_probe_failures_total` series. Filtering by the slug
   returned **exactly the driven calls** on two independent stores (W3:
   reset=1/status=1/config_set=1 = C4+P2+C5; W4: reset=1/status=1 =
   C6+C7), with a to-the-millisecond duration cross-check
   (`…_sum` 4.8286 s = the reset root span 4828.5 ms). The co-resident
   1.8.1's re-exported history sat in the same stores and separated
   cleanly as the no-id remainder. What the 0953 report could only rule
   "expected pollution present" is now a positive attribution result.
2. **The default-pollution mechanism remains for non-opted processes —
   by design, and documented:** the no-id series (config_get=3,
   status=3, GET-200=12) still landed in every seconds-old store.
   That is the documented default (spec decision #9 as amended: default
   strips the id for bounded cardinality; opt-in when attribution
   matters), carried by the run-scenario skill's guidance (`f9ff9e0`),
   not an open defect.
3. **Known residual, also documented:** processes sharing one run slug
   share cumulative httpx series (slug GET-200 = last writer's 4, not
   C6+C7's 11) — one bounded label buys attribution-by-name, not
   per-process cumulative correctness; within a same-slug group,
   trace-derived `traces_spanmetrics_*` remain the counters. This is
   the trade-off #153 chose and wrote down, re-confirmed here.

The decision ledger's `tracked` row (2026-08-29) predates this ruling;
per the mission, the caller appends the superseding row after reading
it. This report edits no ledger.

## 4. Improvement opportunities

1. **Close issue #148 / the N2 chain** — the opt-in is proven working
   end-to-end (§3 ruling); proof queries are in §7 check 13. Nothing
   further to implement in this wave.
2. **(carried, cosmetic)** `oddyssey.docker.image` carries the sha256
   image ID, not the human tag — correct per the #83 design; attach both
   only if a real correlation need appears. No wave on its own.
3. **(new, documentation-only, low)** The MCP-Inspector env-whitelist
   trap (§1): any future driver that sets `OTEL_RESOURCE_ATTRIBUTES` in
   the shell instead of the inspector's `-e` silently loses the
   identity — this run lost its first attempt to it. Worth one line in
   the run-scenario skill's opt-in paragraph ("for MCP Inspector, pass
   it via `-e` after the server command"); the verification query is
   simply `target_info{service_instance_id="<slug>"}` returning 1 series
   seconds after the first call.

## 5. Telemetry gaps — fate of every baseline gap

- **Logs: absent for oddyssey-mcp** — unchanged (spec-scoped out).
  `gcx logs labels -l service_name` → `data: null` pre-run and on the
  final store.
- **Profiles: absent for oddyssey-mcp** — unchanged (spec-scoped out).
  `gcx profiles labels -l service_name -d pyroscope` → `["pyroscope"]`
  (stack self-profile only), pre-run and final store.
- **Metric identity gap (N2's driver)** — **closed for opted-in
  processes** (48.6 KB of `gcx metrics series
  '{service_name="oddyssey-mcp"}'` output now carries
  `service_instance_id="odd-verify-n2-1105"` on 132 series entries);
  open **by documented design** for non-opted processes (the default
  strips the id — bounded cardinality, spec #9 as amended).
- **The wiper's own down-path is dark (N6)** — unchanged by design; W1
  held only C2's trace.
- **Grafana debug-level effectiveness not re-probed** — carried a fourth
  time: C2–C5's containers ran with `GF_LOG_LEVEL=debug` but no
  `docker logs` grep happened before C6 recreated the container.
  (Evidence of absence of the probe, not of the feature.)
- **httpx metrics on transport-errored requests** — the 8 failed
  boot-poll GETs produce trace spans and A5 counter increments but no
  `http_client_request_duration_seconds` row (unchanged from baseline;
  single-signal-by-construction on the metrics side, covered by A5's
  counter and the traces). Recorded as instrumentation behavior, not a
  new gap.
- No `otel-instrumentation-expert` handoff needed: every gap is
  design-scoped, documented, or closed.

## 6. Decisions the spec must settle

1. **(carried)** Empty `stack_config.local: {}` after the last deletion —
   present-but-empty re-observed verbatim (C5); confirm as the intended
   public contract or prune empty entries.
2. **(carried, cosmetic)** `oddyssey.docker.image` value: sha256 ID vs
   human tag vs both — see §4.2.
3. **(new, small)** Whether the run-scenario opt-in guidance should name
   the MCP-Inspector `-e` mechanics (§4.3) — a docs decision, no
   telemetry can answer it.
4. Baseline decisions #1 (N2 design question) is settled by the §3
   ruling + #153's documentation; #4 (boot-poll ERROR semantics) stays
   settled by evidence — shape coherent, failures countable via A5.

## 7. Measurement protocol for the next run

**Replay:** the §1 scenario record verbatim — C0–C7 + P1/P2, same
driver, order, isolated-HOME arrangement (ABSENT scratch config), env
payloads (C2 `{"GF_LOG_LEVEL":"debug"}`, C4 `{"X_DEMO_TOKEN":"fake"}` —
the placeholder, not a credential), per-store query points W1–W4, ports
3000/4317/4318, stack starting from a present container so C1 exercises
the down. **Keep the opt-in identity**: every driven process gets
`OTEL_RESOURCE_ATTRIBUTES=service.instance.id=<one fresh run slug>` via
the inspector's `-e` flag placed AFTER the server command (shell-env
export does not reach the spawned server; `-e` before the command breaks
the CLI's parsing — both failure modes observed and recorded this run).
Prove the chain before driving: one probe call, then
`target_info{service_instance_id="<slug>"}` must return 1 series within
~15 s. All counts n=1 per call (expensive-iteration carve-out): compare
by structure and magnitude, never value-to-value.

Checks, before-values (this run), pass criteria, validation status:

| Check | Query / method | Before-value (this run) | Pass criterion | Validated |
|---|---|---|---|---|
| 1. Creation persists env | C2 result JSON | `env_applied:true`, `env_persisted:["GF_LOG_LEVEL"]` | identical fields | positive this run |
| 2. Config file holds persisted value | cat isolated config after C2 | `{"stack_config":{"local":{"GF_LOG_LEVEL":"debug"}}}` | identical | positive this run |
| 3. Bare reset reapplies | C3 result + `docker inspect --format '{{json .Config.Env}}'` | `env_reapplied:["GF_LOG_LEVEL"]`; var in .Config.Env | both present, no `env_persisted`/`env_applied` | positive this run |
| 4. Credential exclusion | C4 result + config grep | `env_not_persisted:["X_DEMO_TOKEN"]`; 0 name/value hits in config | identical; 0 hits | positive this run |
| 5. Null deletion | C5 result + config | `stack_config.local == {}`, no reset (same container id), env sticky | identical | positive this run |
| 6. Deletion honored on recreation | C6 result + `docker inspect` | no env fields; user env = embedded default only | identical | positive this run |
| 7. Reset trace, pre-rm phase, quiet boot-polls | `gcx traces query '{resource.service.name="oddyssey-mcp" && name="tools/call odd_stack_reset"}'` per store, then get | 22 spans (root + inspect x3(0,0,1) + rm + run + 3 pre-rm GET-200 + 8 GET ERR + 4 GET 200 + POST 415), 0 exception events, `error.type=ReadError` kept, 3/3, roots 4784.2–4858.0 ms | same grouped structure AND 0 exception events | positive on 3 stores this run |
| 8. Creation trace lands, quiet | same search for `odd_stack_up` on the post-C2 store | 16 spans, root 4311.7 ms, 0 exception events, JSON 30.3 KB | same structure; root 3–7 s; 0 exception events; JSON < 40 KB | positive this run |
| 9. Null-deletion trace | `gcx traces get <C5-trace>` | 2 spans (root 21.3 + inspect 19.9 ms) | 2 spans, root < 100 ms | positive this run |
| 10. No secret in config/results/telemetry | grep value + name over config, stdout captures, fetched trace JSONs, series output — scanning artifact files only (a scratch path containing the substring, e.g. `fakehome`, false-positives a raw grep of session logs) | 0/0/0/0 outside contracted surfaces (name in C4's `env_not_persisted` and P2's null-valued `env` key only) | all 0 outside contracted surfaces | positive control this run |
| 11. Resource attrs | trace resource + `target_info` | `service.version=1.8.2`, `deployment.environment.name=local`, **`service.instance.id=<run slug>` present** (spec #9 as amended by #148) | version = built revision's; env local; **id = the run's chosen slug on every driven trace and series** (its absence is now the regression) | positive this run |
| 12. Spanmetrics match driven calls | `sum by (span_name)(traces_spanmetrics_calls_total{service="oddyssey-mcp"})` on final store | reset=1, status=1, inspect=5, image-inspect=1, rm=1, run=1, GET ERR=8, GET UNSET=11, POST ERR=1 (= C6's 22 + C7's 8 spans) | equals the store's landed spans | positive this run |
| 13. Attribution by instance id (N2/#148 regression check) | `ps aux \| grep oddyssey-mcp` first, then on a seconds-old store: `sum by (gen_ai_tool_name, service_instance_id)(mcp_server_operation_duration_seconds_count)` and `sum by (service_instance_id, http_response_status_code, server_port)(http_client_request_duration_seconds_count{service_name="oddyssey-mcp"})`, plus `target_info` identities | `{slug}`: W4 reset=1 + status=1, W3 reset=1 + status=1 + config_set=1 — exactly the driven calls per store; `…_sum{reset, slug}` = C6's root to the ms; no-id remainder = the co-resident's (config_get=3, status=3, GET-200=12, cross-consistent); slug httpx GET-200 = last writer's 4 (shared-slug interleave, documented residual) | slug-filtered `mcp_server_*` counts equal the store's driven calls exactly; co-resident series carry no slug; a slug-filtered count that includes foreign calls, or a driven call landing without the slug, is the regression | **validated positive this run** (was `not validated` in the baseline) |
| 14. Real user config untouched | `shasum -a 256 ~/.oddyssey/config.json` before/after | `f010281d5bf1…35c3e` unchanged | identical before/after | positive this run |
| 15. Pipeline sanity + identity surface | C7 status result + its trace | all four true; `image`/`created`/`started` present; `env:{}`; root 111.8 ms; 8 spans | lands, all true, identity fields present, root < 500 ms | positive this run |
| 16. Probe-failure counter (A5 regression) | `sum by (error_type, service_instance_id)(oddyssey_stack_probe_failures_total)` per fresh store, ~15 s after the creating call | `{ReadError, <slug>} = 8` per boot, 4/4 stores, = the trace's ERROR GET count | series present with the slug, value = matching trace's ERROR GET count, bounded `error_type` values only | positive on 4 stores this run |
| 17. Status env surface (N3 regression) | P1/P2/C7 result JSONs | P1 `env:{"GF_LOG_LEVEL":"debug"}`; P2 adds `"X_DEMO_TOKEN": null` (0 value occurrences); C7 `env:{}` | names always listed; credential-named values null; clean container → `{}` | positive this run |
| 18. image-inspect span (F2 regression) | `gcx traces get <any status trace>`; `traces_spanmetrics_calls_total{span_name="oddyssey.docker.image-inspect"}` | 1 per status call, attr `oddyssey.docker.image=sha256:f1e548c2…`, `exit_code`, no container attr | span present in status traces with the image attribute | positive this run (2 traces + spanmetrics) |

**Backend/env record for replay:** C2 `odd_stack_up` env
`{"GF_LOG_LEVEL": "debug"}`; C4 `odd_stack_reset` env
`{"X_DEMO_TOKEN": "fake"}` (placeholder, not a credential); C3/C6 bare;
plus the per-process `OTEL_RESOURCE_ATTRIBUTES` identity above. A replay
must reproduce all of these or checks 1–6, 11, and 13 are meaningless.

**Environment left as found and ready:** `oddyssey-lgtm` =
`ee7e42b8e2a2`, Up (healthy), image `grafana/otel-lgtm:0.31.0`, ports
3000/4317/4318, embedded defaults only — no leftover scenario env
(proven by check 6 and C7's `env:{}`). `gcx config check` ✔ online after
the run (Grafana 13.1.3). **The stack stays UP for the main agent's next
measurement.** Final store contents = exactly C6's reset trace + C7's
status trace and their metrics, plus the installed 1.8.1's no-id
background export (the documented default). The user's real
`~/.oddyssey/config.json` is byte-identical (check 14). The scratch
fakehome, capture files, and analysis script are ephemeral under the
session scratchpad. The repo stayed on `docs/close-n2-by-evidence`
throughout; only this report file is committed.
