---
services: [oddyssey-mcp]
stack: local
environment: local
mode: verify
window: 2026-08-29T09:53:25Z/2026-08-29T09:59:38Z
run_name: stack-config-lifecycle
verifies: 2026-08-28-1531-stack-config-lifecycle.md
date: 2026-08-29
revision: 62430fe
instance: {oddyssey-mcp: "one short-lived process per tool call (MCP Inspector CLI spawn); no service.instance.id (spec decision #9); identity = call label + UTC start + service.version=1.8.0 (branch build). Co-resident installed servers exporting to the same stack: uvx oddyssey-mcp==1.8.1 (PID 1964, this Claude Code session's server) and ==1.2.0 (PID 60321) - see check 13"}
process_restarted: true
---

# Verification report — stack-config env lifecycle protocol replay, branch `fix/check-odd-status`

Verifies `2026-08-28-1531-stack-config-lifecycle.md` (§7 protocol replayed
verbatim, plus two mission-mandated status probes P1/P2 for the N3
ruling). Fixes under test: **#146** (`odd_stack_status` container
identity — image/created/started/env; shipped in the installed v1.8.1 and
an ancestor of this branch) and **#149** (commit 29fcd5f: A5 probe-failure
counter, F2 image-inspect span shape, N4 quiet boot-poll errors).

## 1. Mission and run record

- **Service:** `oddyssey-mcp` built from branch `fix/check-odd-status`,
  HEAD `62430fe`, working tree clean (the branch was checked out at run
  start; the mission asserted it, `main` was found checked out, and the
  clean tree made the switch safe). Binary
  `src/mcp-server/.venv/bin/oddyssey-mcp`; branch wiring proven before the
  run: `uv sync --project src/mcp-server` (re-installed editable
  oddyssey-mcp → **1.8.0**), `oddyssey_mcp.stack.__file__` →
  `src/mcp-server/app/stack.py`, `hasattr(telemetry,
  'record_probe_failure') == True`, `hasattr(telemetry,
  '_NoExceptionEventTracerProvider') == True`. Every landed trace reports
  `service.version=1.8.0` (the branch's pyproject version — main's 1.8.1
  release bump post-dates the branch point), which cleanly separates the
  branch processes from the installed 1.8.1 in `target_info`.
- **Stack/backend:** local (Grafana LGTM, container `oddyssey-lgtm`,
  `grafana/otel-lgtm:0.31.0`, Grafana 13.1.3), ports 3000/4317/4318
  (from `odd_config_get` + `docker ps` port bindings, not assumed). Query
  CLI: gcx via the `setup-local-stack` isolated `GCX_CONFIG` context at
  `${TMPDIR}/oddyssey/gcx-local.yaml`; `gcx config check` ✔ online before
  and after the run.
- **Mode:** `verify` (frontmatter); executed as the baseline's drive mode
  — 8 one-shot MCP lifecycle calls (C0–C7) + 2 status probes (P1/P2),
  each its own stdio server process, driven with MCP Inspector CLI 2.3.0,
  cwd = repo root.
- **Config isolation (hard constraint, reproven):** every server process
  ran with `HOME` pointed at a fresh scratch `fakehome`; pre-run,
  `Path.home()` and `oddyssey_mcp.config.CONFIG_PATH` both resolved into
  it, the file was ABSENT, and `load()` returned pure defaults (ports
  3000/4317/4318, `stack_config: {}`). C0's result showed
  `stack_config: {}` — the real config's `azure-monitor` entry absent —
  proving the server never read `~/.oddyssey/config.json`. The real
  file's SHA-256 `f010281d5bf184f9fa2da4c24e8d187601f9506fa69c6e968c7b53ba51835c3e`
  (byte-identical to the baseline's recorded value) was identical before
  and after the run.
- **Window:** 2026-08-29T09:53:25Z → 09:59:38Z (post-scenario queries
  until ~10:01Z read only stores produced inside the window).
- **Focus:** verbatim replay of the baseline's §7 protocol — all 15
  checks — then the fate of baseline anomalies N1–N6, the baseline's
  telemetry gaps, and the older still-open findings F2 (2026-08-26-1003)
  and A5 (2026-08-22-2227).
- **Deployment environment: `local`** — forced by construction on the
  local stack, and independently what the telemetry reports: pre-run
  `gcx traces labels -l resource.deployment.environment.name` →
  `["local"]` (single value), and every fetched trace's resource carries
  `deployment.environment.name=local`. **Matches the baseline's recorded
  `local` — no divergence, no stop.** No provisional state.
- **Baseline:** `2026-08-28-1531-stack-config-lifecycle.md`, named by the
  mission (recall walk skipped per mission; it is also the newest match
  on services+stack+environment, so the recall procedure would have
  chosen it). Read in full; its §7 before-values and pass criteria are
  what this run rules on. Older reports consulted for the reach-back
  rulings: `2026-08-26-1003-config-set-env-preservation.md` (F2) and
  `2026-08-22-2227-verify-mcp-otel-instrumentation-verification.md` (A5).
- **Maintainer decisions in force** (`.odd/decisions.md`, 2026-08-29
  rows): baseline N2 → **tracked** (issue #148); 2026-08-26-1003 F4 →
  wontfix; F5 → accepted-by-design; 2026-08-22-2154 A6 →
  accepted-by-design. None re-ruled here.
- **Defaults applied:** none beyond the contract's (window = scenario
  bounds; everything else was given).
- **Destruction accepted by the mission:** 1 `odd_stack_down` + 3
  `odd_stack_reset` wipes of the machine-wide store, maintainer-
  authorized. Pre-wipe store content (2026-08-29 ~09:53Z): Tempo
  `resource.service.name` = `[oddyssey-mcp]`, Prometheus `job` =
  `[oddyssey-mcp, otelcol-contrib]`,
  `mcp_server_operation_duration_seconds_count` by tool = config_get 2 /
  status 2 (the installed 1.8.1's session history), Loki service_name
  absent.
- **Pre-run container condition:** `68ef41552dbd` — the baseline's own
  end-state container (created 2026-08-28T15:36:45Z, embedded defaults
  only, `env: {}` per the installed server's `odd_stack_status`), Up
  (healthy). Present, so C1 exercises the down, as the protocol requires.
- **Preflight (all four signals, pre-run store):** traces present
  (`{resource.service.name="oddyssey-mcp"}` → this session's
  `tools/call odd_stack_status` / `odd_config_get` roots), metrics
  present (`target_info{service_name="oddyssey-mcp"}` → 1 series,
  version 1.8.1;
  `oddyssey_stack_probe_failures_total` → **empty pre-run**, which makes
  the counter uniquely attributable to the branch build — the installed
  1.8.1 predates #149), logs absent (`gcx logs labels -l service_name` →
  `data: null`), profiles absent for the service
  (`gcx profiles labels -l service_name -d pyroscope` → `["pyroscope"]`).

### Scenario record (verbatim)

```text
Scenario: stack-config-lifecycle (verify replay of 2026-08-28-1531 §7)
          - 8 one-shot lifecycle calls C0-C7 (verbatim) + 2 mission-mandated
          status probes P1/P2 (N3 ruling), each its own stdio server process
Server:   src/mcp-server/.venv/bin/oddyssey-mcp  (branch fix/check-odd-status
          62430fe, oddyssey-mcp 1.8.0, cwd = repo root, telemetry default-on,
          HOME=<scratch>/fakehome, isolated config starts ABSENT = defaults,
          ports 3000/4317/4318)
Driver:   HOME=<scratch>/fakehome npx -y @modelcontextprotocol/inspector@2.3.0
          --cli src/mcp-server/.venv/bin/oddyssey-mcp --method tools/call
          --tool-name <tool> [--tool-arg '<key>=<json>']
          stdout JSON + stderr captured per call; docker inspect + isolated
          config snapshot between calls
Backend:  C2 = odd_stack_up, env: {"GF_LOG_LEVEL": "debug"} (creation);
          C4 = odd_stack_reset, env: {"X_DEMO_TOKEN": "fake"}; C3/C6 = bare
          odd_stack_reset; embedded defaults otherwise
Warmup:   C0 only (npx cold cache in the fresh fake HOME, 11.6 s; counts
          fixed at 1 per step by the protocol: expensive-iteration
          carve-out, observations, not quantiles)
Started (UTC): 2026-08-29T09:53:25Z
Ended   (UTC): 2026-08-29T09:59:38Z
Commands (sequential; client = inspector wall time):
  C0 09:53:25 odd_config_get                    -> rc 0, defaults, stack_config:{}   11617.2 ms (cold npx)
  C1 09:53:36 odd_stack_down                    -> rc 0, running:false                3585.6 ms
     snapshot: container absent (pre-run 68ef41552dbd destroyed)
  C2 09:53:45 odd_stack_up   env={"GF_LOG_LEVEL":"debug"}
              -> rc 0, env_applied:true, env_persisted:["GF_LOG_LEVEL"]               5782.3 ms
     snapshot: container 8788db5b1938 (started 09:53:47.230Z), GF_LOG_LEVEL=debug
               in .Config.Env; isolated config = {"stack_config":{"local":
               {"GF_LOG_LEVEL":"debug"}}}
  P1 09:55:37 odd_stack_status (mission probe, N3)
              -> rc 0, all four true, image grafana/otel-lgtm:0.31.0,
                 created/started 09:53:47Z, env:{"GF_LOG_LEVEL":"debug"}              1916.6 ms
  C3 09:55:46 odd_stack_reset (bare)
              -> rc 0, env_reapplied:["GF_LOG_LEVEL"],
                 services_wiped:[oddyssey-mcp, otelcol-contrib]                       6001.9 ms
     snapshot: container d66e32bf8ccd (started 09:55:48.613Z), GF_LOG_LEVEL=debug;
               config unchanged
  C4 09:57:34 odd_stack_reset env={"X_DEMO_TOKEN":"fake"}
              -> rc 0, env_applied:true, env_reapplied:["GF_LOG_LEVEL"],
                 env_not_persisted:["X_DEMO_TOKEN"],
                 services_wiped:[oddyssey-mcp, otelcol-contrib]                       6472.1 ms
     snapshot: container 3d74751f3f2a (started 09:57:36.433Z), .Config.Env has
               GF_LOG_LEVEL=debug AND X_DEMO_TOKEN=fake; config still only
               GF_LOG_LEVEL (0 occurrences of the token value in the file)
  P2 09:57:46 odd_stack_status (mission probe, N3, C4's window)
              -> rc 0, env:{"GF_LOG_LEVEL":"debug","X_DEMO_TOKEN":null}
                 (credential-named value REDACTED to null; 0 occurrences of
                 the value in the whole result)                                       1496.4 ms
  C5 09:57:54 odd_config_set config={"stack_config":{"local":{"GF_LOG_LEVEL":null}}}
              -> rc 0, effective stack_config.local = {} (key gone), NO reset         1190.7 ms
     snapshot: same container 3d74751f3f2a, env untouched (sticky until reset);
               config = {"stack_config":{"local":{}}}
  C6 09:59:25 odd_stack_reset (bare, cleanup + deletion proof)
              -> rc 0, NO env_applied/env_reapplied/env_persisted/env_not_persisted,
                 services_wiped:[oddyssey-mcp, otelcol-contrib]                       6293.5 ms
     snapshot: container 77c1b3556373 (started 09:59:27.958Z), .Config.Env user
               entries = [PROMETHEUS_EXTRA_ARGS=--enable-feature=otlp-deltatocumulative]
               only - no GF_LOG_LEVEL, no X_DEMO_TOKEN
  C7 09:59:35 odd_stack_status                  -> rc 0, all four true,
                 env:{} (clean end-state now visible in the tool result)              2011.7 ms
stderr: 0 bytes on C1-C7 and P1/P2; C0's 522 bytes are npm cache/deprecation
        notices (cold fake-HOME npx cache), not server output
Deviation from the baseline scenario: P1 and P2 only (mission-mandated
        N3 probes; both land extra status traces in the W1/W3 stores,
        accounted for in §2; the final store holds C6+C7 only, so check
        12 is undisturbed)
Not reproducible: none (fixed payloads; X_DEMO_TOKEN's value "fake" is the
        protocol's own placeholder, not a credential; image pinned in the server)
```

Store-scoped query points (traces searchable after ~35–60 s; each store
wiped by the next reset): W1 after C2 (post-C2 store), W2 after C3, W3
after C5 (post-C4 store, holds C4+P2+C5), W4 after C7 (final store,
holds C6+C7).

## 2. Observed behavior

All numbers are one-shot observations (n=1 per call, n=3 for resets)
under the expensive-iteration carve-out — structure and magnitude, never
quantiles.

| Operation | Requests | client (ms) | server root span (ms) | Error % | docker calls per req | Notable |
|---|---|---|---|---|---|---|
| `odd_config_get` (C0) | 1 | 11617.2 (cold npx) | trace lost (store destroyed by C1, by design) | 0 | 0 | isolated defaults returned |
| `odd_stack_down` (C1) | 1 | 3585.6 | trace lost (exported into the dying store, by design) | 0 | rm | running:false |
| `odd_stack_up` creation (C2) | 1 | 5782.3 | 4358.9 — trace `8dcca0ab6d20f50715a14cb5b184a116` | 0 | inspect(exit 1) + run (162.6 ms) | 16 spans; `env_applied:true`, `env_persisted`; **0 exception events** |
| `odd_stack_reset` (C3 bare, C4 env, C6 bare) | 3 | 6001.9 / 6472.1 / 6293.5 | 4840 / 4855 / 4790 — traces `544d699c…`, `5b98711c…`, `a8d66644…` | 0 | 3x inspect + rm + run | identical 22-span shape 3/3, pre-rm phase intact, **0 exception events 3/3** |
| `odd_stack_status` (P1, P2, C7) | 3 | 1916.6 / 1496.4 / 2011.7 | 135.3 (P2 `b834bff4…`) / 126.8 (C7 `790f39dd…`) | 0 | 2x inspect + **image-inspect** (new, #146) | 8 spans (was 5): identity read added; env in result |
| `odd_config_set` null deletion (C5) | 1 | 1190.7 | 24.0 — trace `9d2a5170…` | 0 | 1 inspect (22.7 ms = ~95% of the span) | no reset, config-file-only |
| httpx GET boot-poll (per creation/reset) | 8 | — | 0.7–2.3 each | 8/8 transport-error by design (booting) | — | ERROR status + `error.type=ReadError` kept, **stacktrace events GONE** (N4 fix); each failure now also counted in `oddyssey_stack_probe_failures_total` (A5 fix) |
| httpx GET pre-rm enumeration (per reset) | 3 | — | — | 0 (all 200) | — | present in-trace 3/3 (F3 fix holds) |
| httpx POST `/v1/traces` OTLP-ready (per creation/reset) | 1 | — | — | 415 by design | — | unchanged |

**The 15-check protocol, ruled check by check** (before-values = the
baseline's §7 table):

| Check | Baseline before-value | This run | Verdict |
|---|---|---|---|
| 1. Creation persists env | `env_applied:true`, `env_persisted:["GF_LOG_LEVEL"]` | identical fields, exact (C2 result JSON) | **PASS** |
| 2. Config file holds persisted value | `{"stack_config":{"local":{"GF_LOG_LEVEL":"debug"}}}` | identical (post-C2 snapshot) | **PASS** |
| 3. Bare reset reapplies | `env_reapplied:["GF_LOG_LEVEL"]`; var in .Config.Env; no `env_persisted`/`env_applied` | identical: C3 result + `docker inspect d66e32bf8ccd` → `GF_LOG_LEVEL=debug` | **PASS** |
| 4. Credential exclusion | `env_not_persisted:["X_DEMO_TOKEN"]`; 0 name/value hits in config | identical; container `3d74751f3f2a` carries both vars; config grep: 0 hits | **PASS** |
| 5. Null deletion | `stack_config.local == {}`, no reset (same container id) | identical: same container `3d74751f3f2a`, env sticky, config `{"stack_config":{"local":{}}}` | **PASS** |
| 6. Deletion honored on recreation | no env fields; user env = embedded default only | identical: C6 result has no env fields; `77c1b3556373` carries only `PROMETHEUS_EXTRA_ARGS=…` | **PASS** |
| 7. Reset trace with pre-rm phase | 22 spans: root + inspect x3(0,0,1) + rm + run + 3 pre-rm GET-200 + 8 GET ERR + 4 GET 200 + POST 415, 3/3 | same grouped 22-span structure 3/3 (`544d699c0a7458075e1215d27be0e2c0`, `5b98711c7b4aacde6597f15caef3c35c`, `a8d66644073ce4130d8c05687399a670`); per the check's own caveat the N4 fix removed the 8 stacktrace **events**, not the spans: 0 `exception` events 3/3, ERROR status + `error.type` intact | **PASS** |
| 8. Creation trace lands | "14 spans", root 4385.9 ms, criterion: same structure, root 3–7 s | 16 spans = exactly the baseline's own itemization (root + inspect + run + 8 GET ERR + 4 GET 200 + POST 415 sums to 16; the baseline's "14" contradicts its own list — arithmetic slip in the baseline, structure identical); root 4358.9 ms | **PASS** (with the noted baseline-internal inconsistency) |
| 9. Null-deletion trace | 2 spans (root 25.3 + inspect 23.8 ms), criterion root < 100 ms | 2 spans: root 24.0 ms + inspect 22.7 ms (trace `9d2a517031d76968ce4fee19fbc57778`) | **PASS** |
| 10. No secret in config/results/telemetry | 0/0/0/0 | value `fake`: 0 in isolated config, 0 in all stdout captures except none, 0 in 125 KB of fetched trace JSON (W1+W3+W4), 0 in 42.6 KB series output; name `X_DEMO_TOKEN`: 0 in trace JSON and series. Positive controls: the name appears where contracted — C4's `env_not_persisted` and P2's `env` key (value null) | **PASS** |
| 11. Resource attrs | version = built branch's; env local; no instance id | `service.version=1.8.0` (the branch build's), `deployment.environment.name=local`, no `service.instance.id` — all 6 fetched traces; `target_info` shows `1.8.0` + `1.8.1` (co-resident installed server, anticipated by the mission) | **PASS** |
| 12. Spanmetrics match driven calls | reset=1, status=1, inspect=3, rm=1, run=1, GET ERR=8, GET UNSET=11, POST ERR=1 | final store: reset=1, status=1, **inspect=5, image-inspect=1**, rm=1, run=1, GET ERR=8, GET UNSET=11, POST ERR=1 — sums to exactly C6's 22 + C7's 8 = 30 landed spans, nothing else; the two deltas are the fixes under test (#146 adds 2 docker calls to status, F2 renames the image read) | **PASS** (deltas explained by the fixes) |
| 13. Contamination marker (N2) | polluted: config_set=13, status=4–5, config_get=2 beyond driven calls | still polluted, as expected while N2 is `tracked`: seconds-old final store shows status=3 (C7's 1 + installed 1.8.1's 2), config_get=2 (installed 1.8.1's) — `ps aux` read first (uvx 1.8.1 PID 1964, uvx 1.2.0 PID 60321) and `target_info` versions (1.8.0/1.8.1) interpreted per the protocol; the baseline's 1.7.0 polluter (config_set=13) is gone, so contamination shrank but the mechanism persists; `…_sum{gen_ai_tool_name="odd_stack_reset"}` = 4.7901 s = C6's root span 4790.1 ms to the ms; spanmetrics remain the trustworthy counter | **expected result confirmed** (pollution present; fixed-case criterion not applicable — no N2 fix in this wave, decision `tracked` via #148) |
| 14. Real user config untouched | SHA-256 `f010281d…35c3e` unchanged | identical SHA before and after — and identical to the baseline's recorded value | **PASS** |
| 15. Pipeline sanity | all four true; root 50 ms | all four true; root 126.8 ms — the +77 ms is #146's identity read (2 inspects + image-inspect ≈ 80 ms of docker CLI), status trace now 8 spans (was root + 4 GET) | **PASS** (magnitude delta explained by the fix under test) |

**Metrics evidence (per store):**

- A5 counter: `sum by (error_type)(oddyssey_stack_probe_failures_total)`
  → `{error_type="ReadError"} = 8` on each fresh store (W1 = C2's boot
  polls, W2 = C3's, W3 = C4's, W4 = C6's) — exactly the 8 ERROR boot-poll
  GET spans of the matching trace, cross-confirmed trace↔metric. Empty
  pre-run, so the series is uniquely the branch build's (the installed
  1.8.1 predates #149).
- httpx accounting by version (final store,
  `sum by (service_version, http_response_status_code, server_port)(http_client_request_duration_seconds_count{service_name="oddyssey-mcp"})`):
  `1.8.0`: GET-200 :3000 = 4, POST-415 :4318 = 1; `1.8.1`: GET-200
  :3000 = 8. The 1.8.0 value is **C7's process-lifetime total (4)
  overwriting C6's (7)** — the two branch processes share one cumulative
  series without an instance id, so the counter interleaves
  (last-writer-wins), the concrete same-series collision the 2026-08-22
  report predicted (spec decision #9 / N2 territory). The 1.8.1 series is
  the installed server's session history (2 status calls × 4 probes)
  re-exported into the fresh store. Trace-derived spanmetrics (GET
  UNSET=11, GET ERR=8) carry the true in-window counts.
- `target_info{service_name="oddyssey-mcp"}` → two series,
  `service_version="1.8.0"` (branch processes) and `"1.8.1"` (installed
  live server), both `deployment_environment_name="local"`. The
  co-resident 1.2.0 process exports nothing visible (no series carries
  it).
- Service graph: `traces_service_graph_request_total` →
  `user → oddyssey-mcp` = 2 (`connection_type="virtual_node"`), no
  outbound edges — unchanged, leaf service driving subprocesses.

**Verdict deltas vs baseline (per operation):**

| Item | Baseline | This run | Delta |
|---|---|---|---|
| Lifecycle contract fields (checks 1–6) | 5/5 exact | 5/5 exact | **unchanged — holds on the new branch** |
| Bare/env reset client / root | 6215.6–6301.3 / 4767–4823 ms | 6001.9–6472.1 / 4790–4855 ms (n=3) | unchanged magnitude |
| Creation root span | 4385.9 ms | 4358.9 ms | unchanged |
| status root span | 50 ms | 126.8–135.3 ms (n=2) | +~80 ms, the #146 identity read (2 inspect + image-inspect); absolute cost trivial for a diagnostic tool |
| config_set null-deletion root | 25.3 ms | 24.0 ms | unchanged |
| Boot-poll stacktrace events | 8 per creation/reset trace | **0 per trace, 4/4** | **fixed (N4)** |
| Creation trace JSON size | 64.5 KB | 30.1 KB | **−53%** (mission's expected ~45% gain met) |
| Reset trace JSON size | ~65 KB class | 38.8 KB | shrunk (same mechanism) |
| Probe-failure metric | did not exist (trace-only failures) | `oddyssey_stack_probe_failures_total{error_type}` = 8/boot, all stores | **new (A5 fix)** |
| Image-read span | `oddyssey.docker.image` + container attr, backend-invisible | `oddyssey.docker.image-inspect` + `oddyssey.docker.image` attr, backend-visible in status traces | **fixed (F2)** |
| Status env surfacing | absent (N3 open) | `image`/`created`/`started`/`env` in every status result | **fixed (N3, #146)** |
| Tool-span dedup / instance id absent / stderr silence / env-value hygiene | hold | hold (spanmetrics root=1 per landed call; no id anywhere; 0 bytes ×9; 0 secret hits) | hold |

## 3. Anomalies and probable causes — fate of every baseline finding

| # | Baseline finding | Fate | Confidence | Evidence |
|---|---|---|---|---|
| N1 | #117/#112 lifecycle contract fully correct | **still correct** — re-confirmed 5/5 on the new branch (regression check passed) | confirmed (cross-signal: results + docker inspect + config snapshots + traces) | §2 checks 1–6 |
| N2 | Co-resident servers pollute fresh-store metrics (no instance id) | **open by decision — `tracked`** via issue #148 (ledger row 2026-08-29), not re-ruled per mission. Freshly evidenced anyway: installed 1.8.1 re-exported status=2/config_get=2 into the seconds-old store (check 13), and the run caught the sharper variant — two same-version processes interleaving one cumulative httpx series, C7's 4 overwriting C6's 7 (last-writer-wins) | confirmed | check 13; httpx-by-version decomposition §2 |
| N3 | Sticky container env invisible (applied-but-not-persisted vars dark) | **FIXED** by #146 (in installed 1.8.1 and ancestor of this branch): `odd_stack_status` returns `image`/`created`/`started`/`env`. P1 (after C2): `env:{"GF_LOG_LEVEL":"debug"}`; **P2 (C4's window): `env:{"GF_LOG_LEVEL":"debug","X_DEMO_TOKEN":null}` — the credential-named var visible by name, value redacted to null, 0 occurrences of the value in the result**; C7: `env:{}` proves the clean end-state through the tool surface. The X_DEMO_TOKEN-class dark window is closed | confirmed (tool results ×3 + docker inspect cross-check) | P1/P2/C7 result JSONs, §1 scenario record |
| N4 | Boot-poll exception noise (8 stacktrace events per creation/reset trace, ~30 of 65 KB) | **FIXED** by #149: 0 `exception` events on all 4 creation/reset traces (and all 6 fetched traces); the spans themselves remain — 8 ERROR GETs with `error.type=ReadError` and ERROR status intact per trace, exactly the check-7 caveat; creation trace JSON 64.5 → 30.1 KB (−53%) | confirmed | trace fetches `8dcca0ab…`, `544d699c…`, `5b98711c…`, `a8d66644…`: `exception events total: 0` each |
| N5 | config_set null deletion spends ~94% of its span on one state-inspect | **unchanged, by design** (baseline: negligible, none worth taking) — 22.7 of 24.0 ms (~95%) this run | confirmed | trace `9d2a5170…` |
| N6 | C0/C1 telemetry unobservable-by-construction (wiper's own down-path) | **unchanged, by design** — W1 store held C2's trace only; C0/C1 traces nowhere | confirmed | W1 search: 1 trace |

**Older still-open findings the evidence reaches:**

| Finding (origin) | Fate | Evidence |
|---|---|---|
| F2 (2026-08-26-1003): image-read span named `oddyssey.docker.image` with a container attribute, backend-invisible | **FIXED** by #149, with a relocation the mission's expectation missed: the span is now `oddyssey.docker.image-inspect` carrying `oddyssey.docker.image=sha256:f1e548c2…` (the `.Image` ID the container was created from, per the #83 subtraction design), **no** container attribute, exit_code present — and it is backend-visible, but in **status traces**, not the pre-rm phase of reset traces: since #117 the reset reads env from the persisted config, so `container_user_env()` (the only image-inspect caller, stack.py:383) runs only in `odd_stack_status`. Observed in P2's trace `b834bff401691116c5350ccc3b913c86` and C7's `790f39dd227891c13e5099b893ffafdd`, and in spanmetrics (`traces_spanmetrics_calls_total{span_name="oddyssey.docker.image-inspect"}` = 1 on the final store). Reset traces correctly contain no image-inspect — that is #117's design, not a regression |
| A5 (2026-08-22-2227): connection-level probe failures trace-only, no PromQL-native error series | **FIXED** by #149: `oddyssey.stack.probe.failures` counter, exported exactly as the mission expected — `oddyssey_stack_probe_failures_total{error_type="ReadError"}` = 8 after each boot (4/4 stores), matching the trace's 8 ERROR GETs one-for-one; dimension = exception class name only (bounded cardinality, no URL/host). Probe error rates are now answerable in PromQL without TraceQL |

## 4. Improvement opportunities

1. **Close issue #149** — all three of its items are proven landed
   end-to-end in the backend (A5 counter, F2 span shape, N4 quiet
   boot-polls; §3). Proof queries for the closing PR: this report's §3
   tables; the scenario replays in ~6 minutes via §7.
2. **#146 needs no further action** — N3 is closed by evidence (P1/P2/C7
   results); already shipped in v1.8.1.
3. **N2 stays with issue #148** (maintainer decision `tracked`): this
   run adds the sharpest evidence yet for that issue — the
   same-version cumulative-series interleave (httpx GET-200 `1.8.0` = 4
   where the two branch processes' lifetimes sum to 11), which no
   version-label workaround can separate. Until #148 lands, the
   documented rule holds: on the local stack, trace-derived
   `traces_spanmetrics_*` are the counters; `mcp_server_*`/
   `http_client_*` are advisory. Verification query unchanged from the
   baseline's §7 check 13.
4. **Optional, cosmetic:** the `oddyssey.docker.image` attribute carries
   the sha256 image ID, not the human tag (`grafana/otel-lgtm:0.31.0`).
   Correct by the #83 design (the subtraction targets `.Image`), but a
   reader correlating spans to the pinned tag must resolve the ID. If it
   ever matters, attach both. No expected gain worth a wave on its own;
   recorded so the spec can decide consciously.

## 5. Telemetry gaps — fate of every baseline gap

- **Logs: absent for oddyssey-mcp** — unchanged (spec-scoped out).
  `gcx logs labels -l service_name` → `{"status":"success","data":null}`
  pre-run and on the final store.
- **Profiles: absent for oddyssey-mcp** — unchanged (spec-scoped out).
  `gcx profiles labels -l service_name -d pyroscope` → `["pyroscope"]`
  (stack self-profile only), pre-run and final store.
- **Metric identity gap (N2's driver)** — still open, tracked by #148
  (decision ledger). Fresh discovery evidence: 42.6 KB of
  `gcx metrics series '{service_name="oddyssey-mcp"}'` output contains no
  instance-shaped label; this run proved the gap now bites even between
  same-version processes (httpx interleave, §2), where `target_info`'s
  `service_version` no longer separates them.
- **The wiper's own down-path is dark (N6)** — unchanged by design
  (`stack_down(flush=True)`); W1 held only C2's trace.
- **Grafana debug-level effectiveness not re-probed** — carried again:
  the containers of C2–C5 ran with `GF_LOG_LEVEL=debug` but this run did
  not grep `docker logs` before C6 recreated the container; the
  2026-08-26 baseline's verdict stands unre-tested for the third run.
  (Evidence of absence of the probe, not of the feature.)
- No `otel-instrumentation-expert` handoff needed: N4/F2/A5 — the gaps
  that were instrumentation code — are now closed; everything left is
  design-scoped or tracked by issue.

## 6. Decisions the spec must settle

1. **(carried, now issue-tracked)** Metric attribution on a shared stack:
   with N2 `tracked` via #148, the open design question (bounded-
   cardinality instance identity vs "spanmetrics are the counters")
   lives there; this run's same-version interleave evidence belongs in
   that issue's discussion.
2. **(carried from baseline #3)** Empty `stack_config.local: {}` after
   the last deletion — confirm present-but-empty as the intended public
   contract or prune empty entries. Re-observed verbatim this run (C5).
3. **(new, cosmetic)** `oddyssey.docker.image` attribute value: sha256 ID
   (current, per #83) vs human tag vs both — see §4.4.
4. Baseline decision #4 (boot-poll error semantics) is settled by
   evidence: #149 kept ERROR status + `error.type` and dropped the
   stacktrace events — if the spec wants the remaining ERROR statuses
   demoted too, that is a new decision; the observed shape is coherent
   as-is (expected failures countable via A5's counter, visible but
   lean in traces).

## 7. Measurement protocol for the next run

**Replay:** the §1 scenario record verbatim — C0–C7 with the same driver,
order, isolated-HOME arrangement (ABSENT scratch config), env payloads
(C2 `{"GF_LOG_LEVEL":"debug"}`, C4 `{"X_DEMO_TOKEN":"fake"}` — the
placeholder, not a credential), and per-store query points W1–W4; keep
P1/P2 (status probes after C2 and after C4) now that status carries the
env surface — they are the N3 regression checks. The stack must start
from a present container so C1 exercises the down; ports 3000/4317/4318.
All counts n=1 per call (expensive-iteration carve-out): compare by
structure and magnitude, never value-to-value.

Checks, before-values (this run), pass criteria, validation status:

| Check | Query / method | Before-value (this run) | Pass criterion | Validated |
|---|---|---|---|---|
| 1. Creation persists env | C2 result JSON | `env_applied:true`, `env_persisted:["GF_LOG_LEVEL"]` | identical fields | positive this run |
| 2. Config file holds persisted value | cat isolated config after C2 | `{"stack_config":{"local":{"GF_LOG_LEVEL":"debug"}}}` | identical | positive this run |
| 3. Bare reset reapplies | C3 result + `docker inspect --format '{{json .Config.Env}}'` | `env_reapplied:["GF_LOG_LEVEL"]`; var in .Config.Env | both present, no `env_persisted`/`env_applied` | positive this run |
| 4. Credential exclusion | C4 result + config grep | `env_not_persisted:["X_DEMO_TOKEN"]`; 0 name/value hits in config | identical; 0 hits | positive this run |
| 5. Null deletion | C5 result + config | `stack_config.local == {}`, no reset (same container id) | identical | positive this run |
| 6. Deletion honored on recreation | C6 result + `docker inspect` | no env fields; user env = embedded default only | identical | positive this run |
| 7. Reset trace, pre-rm phase, quiet boot-polls | `gcx traces query '{resource.service.name="oddyssey-mcp" && name="tools/call odd_stack_reset"}'` per store, then get | 22 spans: root + inspect x3(0,0,1) + rm + run + 3 pre-rm GET-200 + 8 GET ERR + 4 GET 200 + POST 415; **0 exception events**; ERROR GETs keep `error.type=ReadError`; 3/3 identical | same grouped structure AND 0 exception events (a regression re-adds them) | positive on 3 stores this run |
| 8. Creation trace lands, quiet | same search for `odd_stack_up` on the post-C2 store | **16 spans** (root + inspect + run + 8 GET ERR + 4 GET 200 + POST 415), root 4358.9 ms, 0 exception events, JSON 30.1 KB | same structure; root 3–7 s; 0 exception events; JSON < 40 KB | positive this run (16 corrects the baseline's mis-summed "14") |
| 9. Null-deletion trace | `gcx traces get <C5-trace>` | 2 spans (root 24.0 + inspect 22.7 ms) | 2 spans, root < 100 ms | positive this run |
| 10. No secret in config/results/telemetry | grep value + name over config, stdout captures, fetched trace JSONs, series output | 0/0/0/0 (name present only in `env_not_persisted` and as a null-valued `env` key — contracted surfaces) | all 0 outside contracted surfaces | positive control this run (name visible where contracted, nowhere else) |
| 11. Resource attrs | trace resource + `target_info` | `service.version=1.8.0`, `deployment.environment.name=local`, no instance id; `target_info` = built version + any live installed versions | version = built branch's; env local; id absent unless spec #9 amended via #148 | positive this run |
| 12. Spanmetrics match driven calls | `traces_spanmetrics_calls_total{service="oddyssey-mcp"}` on final store | reset=1, status=1, inspect=5, **image-inspect=1**, rm=1, run=1, GET ERR=8, GET UNSET=11, POST ERR=1 (= C6's 22 + C7's 8 spans) | equals the store's landed spans | positive this run |
| 13. Shared-store contamination marker (N2/#148) | `ps aux \| grep oddyssey-mcp`, then `sum by (gen_ai_tool_name)(mcp_server_operation_duration_seconds_count)` and `target_info` versions on a seconds-old store | polluted: status +2, config_get +2 beyond driven calls (installed 1.8.1, PID read first); plus same-version httpx interleave (GET-200 `1.8.0` = last writer's 4, not the 11 driven) | after a #148 fix: counts equal driven calls per process; until then: expect pollution whenever an installed server runs | query validated this run (returned the polluter's counts); `not validated` for the fixed case |
| 14. Real user config untouched | `shasum -a 256 ~/.oddyssey/config.json` before/after | `f010281d5bf1…35c3e` unchanged | identical before/after | positive this run |
| 15. Pipeline sanity + identity surface | C7 status result + its trace | all four true; `image`/`created`/`started` present; `env:{}` on a clean container; root 126.8 ms; trace = 8 spans (root + 4 GET-200 + 2 inspect + image-inspect) | lands, all true, identity fields present, root < 500 ms | positive this run |
| 16. (new) Probe-failure counter (A5 regression check) | `sum by (error_type)(oddyssey_stack_probe_failures_total)` on each fresh store, ~15 s after the creating call | `{error_type="ReadError"} = 8` per boot, 4/4 stores, = the trace's ERROR GET count | series present, value = the matching trace's ERROR GET count, only bounded `error_type` values | positive on 4 stores this run |
| 17. (new) Status env surface (N3 regression check) | P1/P2 result JSONs | P1 `env:{"GF_LOG_LEVEL":"debug"}`; P2 adds `"X_DEMO_TOKEN": null`; C7 `env:{}` | names of applied vars always listed; credential-named values null; clean container → `{}` | positive this run |
| 18. (new) image-inspect span (F2 regression check) | `gcx traces get <any status trace>`; `traces_spanmetrics_calls_total{span_name="oddyssey.docker.image-inspect"}` | 1 per status call, attr `oddyssey.docker.image=<sha256 .Image id>`, no container attr | span present in status traces with the image attribute | positive this run (2 traces + spanmetrics) |

**Backend/env record for replay:** C2 `odd_stack_up` env
`{"GF_LOG_LEVEL": "debug"}`; C4 `odd_stack_reset` env
`{"X_DEMO_TOKEN": "fake"}` (placeholder, not a credential); C3/C6 bare.
A replay must reproduce these payloads or checks 1–6 are meaningless.

**Environment left as found and ready:** `oddyssey-lgtm` =
`77c1b3556373`, Up (healthy), image `grafana/otel-lgtm:0.31.0`, default
ports 3000/4317/4318, embedded defaults only — no leftover scenario env
(proven by check 6 and C7's `env:{}`). `gcx config check` ✔ online after
the run (Grafana 13.1.3). **The stack stays UP for the main agent's next
measurement.** Final store contents = exactly C6's reset trace + C7's
status trace and their metrics (plus the installed servers' background
export, per N2/#148). The user's real `~/.oddyssey/config.json` is
byte-identical (check 14). The scratch fakehome, capture files, and
analysis script are ephemeral under the session scratchpad. The repo was
switched from `main` to `fix/check-odd-status` for the run and left
there (the mission's stated working copy).
