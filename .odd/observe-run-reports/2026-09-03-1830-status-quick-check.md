---
services: [oddyssey-mcp]
stack: local
environment: local
mode: drive
depth: quick
window: 2026-09-03T18:30:47Z/2026-09-03T18:31:25Z
run_name: status-quick-check
date: 2026-09-03
revision: c89223f
tree_anchor: {.agents: "00fec2a0d71f459a5b1291f21b2ae50d0331b94e", .apm: "b584bb96f3631c61a7d259f088565e68d50c28f7", .claude-plugin: "08b5b693ba92e7353eb1e5b31c58763421b18a22", .claude: "423cffd027ba21e2cb9b6fe396194b277cab58d2", .gitattributes: "14c97432b1cd8a40d995aba505e3ebe3529ad709", .github: "4c3b66e80c0b42e5b0706315f83f251dc09d692a", .gitignore: "7db740346f04814b7feb089f85aea8a663db1dd3", .odd: "1dc9ac15f9e4eab6d347fdd41aa05625abb94bf5", AGENTS.md: "3055b320789dc62a79cbaf2a27bb74fb5ef3051a", CHANGELOG.md: "54deefa5a96ad44c96958dbdb93a6e9a326dfe29", CLAUDE.md: "43c994c2d3617f947bcb5adf1933e21dabe46bb5", CODE_OF_CONDUCT.md: "948ced506f78d19ccac65a19d19b4f84f618dcf3", CONTRIBUTING.md: "a23efce39f5e2b6f302c3e671d4c5cc6fcd45813", LICENSE: "2bcbad39118126520a36068a3dea6775700a3404", README.md: "c1af66c39bb116720ecc9105c8a96db4c7cbae94", SECURITY.md: "4909276e2d2f1a91ecb7274a3090bf81faa549bd", apm.yml: "484dbcf28b6906bcb50aff48928b62672fcda897", assets: "175f6c7aee93b5616cdbfd5c82b12e15e1d600a1", cliff.toml: "62e26cbf98f96473424692b0de6afe43d35df649", docs: "22a1c315a3906991c2b2dc6c190fee8ef7ba061a", integration-tests: "6f1c20ca315c3ccd399b777a8ef9be27a7cb1d25", marketplace: "089becc00a4dfd2dc266ec875764910f3525f688", scripts: "286472375d7ef5894d3a77b1333a9cb3f10cf8fd", src: "2497e5d426ed15bb340a078af754a488b10ea43d", tests: "a35653b9078d49bf97c2cfa5d3efb7705046460a"}
instance: {oddyssey-mcp: "service.instance.id=odd-262-1830 on every driven one-shot process (35 processes, one run slug, opt-in via OTEL_RESOURCE_ATTRIBUTES through the MCP Inspector's -e flag). Co-resident exporter on the same stack: the installed uvx oddyssey-mcp==1.10.1 (this Claude Code session's server, no instance id)"}
process_restarted: true
---

# Observation report: status-quick-check (quick depth)

**Answer to the question:** `odd_stack_status` answers on the local
stack — 30/30 load calls (and 5/5 warmup) returned rc 0, `isError:
false`, one byte-identical body (`running: true`, all four signals
ready) — with a server-side root of **p50 118 ms / p95 125 ms / max
127 ms** (n=30) inside a ~1.24 s one-shot client wall.

## 1. Mission and run record

- **Service:** `oddyssey-mcp`, binary `src/mcp-server/.venv/bin/oddyssey-mcp`
  (1.10.2, `telemetry.sdk.version=1.44.0`), driven through the MCP
  Inspector CLI 2.3.0 in `--cli` mode, one stdio server process per call.
- **Stack / backend:** local (Grafana LGTM, `grafana/otel-lgtm:0.31.0`,
  Grafana 13.1.3; Tempo, Prometheus, Loki, Pyroscope behind the
  datasource proxy on `http://localhost:3000`, OTLP gRPC `:4317`, OTLP
  HTTP `:4318`, Pyroscope `:4040`), `stack_config.local =
  {GF_LOG_LEVEL: debug}`. Backend CLI: gcx 1.2.0 through the
  `setup-local-stack` isolated context the preflight handed over
  (reused as-is; `gcx config check` re-run once after the reset:
  Connectivity online, Grafana 13.1.3). The preflight handoff itself is
  conversation-scope and not restated.
- **Mode:** drive. **Depth: `quick`** — resolved by the caller from the
  user's phrasing ("quick check"), not asked. **Benchmark:** none.
  **Window:** the scenario's own Started/Ended. **Focus:** the
  `odd_stack_status` operation — does it answer, and how fast.
  **Expectations:** none from the caller; the recalled baseline below.
- **Defaults applied:** window = scenario, one query point, one
  clean-base reset; everything else the mission named.
- **Quick depth, as applied:** signals queried = traces and the metrics
  (Tempo's span-derived `traces_spanmetrics_*` / `traces_service_graph_*`
  as the per-operation table's source, plus the SDK's own histograms
  for attribution); **not queried (quick): logs, profiles** — each
  probed once for the environment only. One exemplar (the
  worst-duration `odd_stack_status` trace). Cross-confirmation only
  for the findings reported `confirmed`. Only `odd_stack_status` was
  driven — `odd_config_get` was not, so nothing is ruled on it.
- **Deployment environment: `local`** — forced by construction on the
  local stack, and what the telemetry reports on every signal that
  carries the service. Pre-reset detection (before any reset, one
  bounded query per signal):
  `gcx traces labels --scope resource -l deployment.environment.name -q '{resource.service.name="oddyssey-mcp"}'`
  → `["local"]`;
  `gcx metrics labels -l deployment_environment_name --match 'target_info{service_name="oddyssey-mcp"}'`
  → `["local"]`; `gcx logs labels -l service_name` → `["orders-api"]`
  and `gcx profiles labels -l service_name -d pyroscope --since 1h` →
  `["orders-api","pyroscope"]` (the service is on neither — another
  project's leftover only). Post-run on the slug: traces
  `-q '{resource.service.instance.id="odd-262-1830"}'` → `["local"]`;
  metrics `--match 'target_info{service_instance_id="odd-262-1830"}'`
  → `["local"]`. Definite, not provisional.
- **Recalled baseline:** per the persistence skill's recall (a quick
  mission takes the newest match of either depth):
  `.odd/observe-run-reports/2026-09-03-1756-remeasure-mcp-read-tools.md`
  (re-measure of `2026-09-03-1710-mcp-read-tools.md`, revision
  `edcd69f`, `full` protocol — no `depth` field, written before it;
  same service, stack and environment). Read by section: frontmatter,
  section 1's record block and replay notes, sections 2, 3 and 7 —
  never whole. `tree_anchor` against `git ls-tree HEAD` (`c89223f`):
  `src`, `tests`, `integration-tests` byte-identical to the baseline's;
  `.apm`, `docs`, `.odd`, `README.md` differ (the #262 contract change
  and documentation — nothing that changes the observed server's
  runtime). The deltas below compare against its numbers, on the one
  operation this run drove.

### Replay notes

- **Clean base:** the driven processes are one-shot (each inspector
  call spawns its own server process), so "restart the observed process
  first" holds by construction; then **one** bare `odd_stack_reset`
  before the scenario — the only reset of the mission. Pre-wipe store
  inventory (the wipe is machine-wide, on the mission's explicit
  order): Tempo `service.name` = `[oddyssey-mcp]`; `target_info`
  `service_name` = `[oddyssey-mcp, orders-api, otelcol-contrib]`; Loki
  `service_name` = `[orders-api]`; Pyroscope `service_name` =
  `[orders-api, pyroscope]`. Reset result: `env_reapplied:
  [GF_LOG_LEVEL]`, `services_wiped: [oddyssey-mcp, orders-api,
  otelcol-contrib]`. Container created 18:30:13Z (from the driven
  `odd_stack_status` bodies).
- **Co-resident server (`ps` filtered on `oddyssey-mcp`):** the
  installed `uvx oddyssey-mcp==1.10.1` (this Claude Code session's
  server, no instance id). It served this mission's clean-base reset
  and re-exported its lifetime totals into the fresh store
  (status=7, config_get=4, reset=3 — grown since the baseline's 5/3/2
  by this session's own calls); separable from the driven processes by
  the slug (section 2).
- **Config isolation:** every driven process ran with `HOME` pointed at
  a **fresh** scratch `fakehome` (the previous one moved aside, so the
  npx cache was cold again — warmup call 1: 11459 ms wall; the
  baseline's 12538 ms). The isolated config is absent = defaults, ports
  3000/4317/4318/4040; no real identifier in any driven result.
- **Service preflight (queried signals only, post-scenario store):**
  traces present
  (`gcx traces query '{resource.service.instance.id="odd-262-1830" && name="tools/call odd_stack_status"}' --since 1h --limit 1000`
  → 35 traces = 5 warmup + 30 load, exact; service-wide
  `'{resource.service.name="oddyssey-mcp"}'` → 36, the extra being the
  co-resident's reset trace); metrics present
  (`gcx metrics series '{service_instance_id="odd-262-1830"}' --since 1h`
  → 33 series: `mcp_server_operation_duration_seconds_*`,
  `http_client_request_duration_seconds_*`, `target_info`). Logs and
  profiles: not preflighted (quick); the environment probes above show
  neither carries the service, which section 5's line records without
  ruling.
- **Driver detail that binds every replay:** the inspector's stdio
  client passes only a whitelisted environment to the spawned server —
  `OTEL_RESOURCE_ATTRIBUTES` must go through the inspector's own `-e`
  flag, placed **after** the server command. Proven again: all 35
  traces carry `service.instance.id=odd-262-1830`
  (`gcx traces labels --scope resource -l service.instance.id -q '{resource.service.name="oddyssey-mcp"}'`
  → `["odd-262-1830"]`, the only value in the store).
- **Deviation from the record, stated:** the post-reset `gcx config
  check`, the warmup loop and the load loop ran chained in one shell
  command (`check && warmup && load`), so the three are strictly
  sequential by construction; the load loop is still one blocking
  foreground `drive.py` invocation, as the record demands.

### Scenario record (verbatim)

```text
Scenario: status-quick-check — 5 warmup then 30 x odd_stack_status, sequential, one
          blocking foreground loop, each call its own stdio server process
          (MCP Inspector CLI 2.3.0), cwd = repo root
Server:   src/mcp-server/.venv/bin/oddyssey-mcp (branch feat/observe-quick-depth c89223f,
          oddyssey-mcp 1.10.2, telemetry default-on, HOME=<scratchpad>/fakehome (fresh):
          isolated config ABSENT = defaults, ports 3000/4317/4318/4040)
Base URL: n/a (stdio); the server's own probes hit http://localhost:3000, OTLP to :4317
Backend:  odd_stack_reset (bare) once, before the scenario — env reapplied from
          stack_config.local: {"GF_LOG_LEVEL": "debug"}; container created 18:30:13Z
Instance: service.instance.id=odd-262-1830 on every driven process (35 one-shot
          processes; restart-by-construction, then the single reset)
Identity: -e "OTEL_RESOURCE_ATTRIBUTES=service.instance.id=odd-262-1830" AFTER the
          server command (shell-env export does not reach the spawned server)
Driver:   HOME=<scratchpad>/fakehome npx -y @modelcontextprotocol/inspector@2.3.0
          --cli src/mcp-server/.venv/bin/oddyssey-mcp
          -e "OTEL_RESOURCE_ATTRIBUTES=service.instance.id=odd-262-1830"
          --method tools/call --tool-name odd_stack_status
          (wrapped by <scratchpad>/drive.py, unchanged from the baseline: one Python
          loop, subprocess.run per call, wall time per call captured,
          stdout/stderr saved per call)
Warmup:   5 x odd_stack_status (18:30:30Z–18:30:47Z; first call 11459 ms cold npx
          cache, then 1229–1333 ms) — discarded from every quoted number
Load:     30 x odd_stack_status (18:30:47Z–18:31:25Z), sequential, client-paced
          (no concurrency)
Started (UTC): 2026-09-03T18:30:47Z
Ended   (UTC): 2026-09-03T18:31:25Z
Query points: 1 (after Ended)
Commands:
  python3 <scratchpad>/drive.py odd_stack_status 5  warmup-status-262 odd-262-1830
  python3 <scratchpad>/drive.py odd_stack_status 30 load-status-262   odd-262-1830
  # each drive.py iteration = the Driver line above, verbatim
Results:  30/30 rc 0, 30/30 isError:false, 0 stderr bytes on all 30 load calls,
          1 distinct stdout body across the 30 calls (byte-identical results);
          warmup: 5/5 rc 0, 522 stderr bytes on warmup call 1 only (npm's
          notices while populating the cold cache)
Not reproducible: none (fixed payload: the tool takes no arguments)
```

### Timeline (UTC)

```text
Timeline (UTC):
  18:29:15Z  mission start — contract reads by section (agent file, run-scenario,
             create-observe-run-report, the routed reference sections, the baseline partial read)
  18:29:48Z  pre-reset environment detection on all four signals + store inventory + co-resident
             census (one turn, 4 parallel calls: odd_stack_status, odd_config_get, gcx probes, ps)
  18:30:03Z  reset issued        (bare odd_stack_reset — the single clean-base reset; container
             created 18:30:13Z; the server's own root span 4863 ms, trace 54de411e…)
  18:30:30Z  gcx config check    (the single post-reset probe: Connectivity online, Grafana 13.1.3)
  18:30:30Z  warmup start        (5 x status, discarded)
  18:30:47Z  warmup end
  18:30:47Z  scenario Started    (load loop: 30 x odd_stack_status, one blocking command)
  18:31:25Z  scenario Ended      (last call returned)
  18:31:31Z  flush wait start    (ONE wait, 60 s — traces are the slowest signal read;
             foreground python3 time.sleep(60); the driver-output hygiene check ran in parallel)
  18:32:31Z  flush wait end
  18:32:59Z  discovery + query turn (4 parallel calls: traces list/errors/identity/environment;
             metrics series/environment/spanmetrics/service graph; logs + profiles environment
             probes; SDK-histogram attribution) — every number of sections 2 and 3 comes from it
  18:33:29Z  exemplar search     (one p99 predicate → empty; fallback = the limit-1000 list)
  18:33:33Z  exemplar fetch      (1 trace, 60d7f9f4…, 13 KB)
  18:36:11Z  report persisted (this file written)
Ended → persisted: 4.8 min — target < 5 min: held.
Quick shape: signals queried = traces, metrics (span-derived + SDK); not queried (quick) = logs,
             profiles (one environment probe each); exemplars fetched = 1; anomalies = 4 confirmed
             (F1's cause suspected), 0 suspected-only; section lines as written: 3 = 6 (table: header, separator, 4 rows),
             4 = 1, 5 = 1, 6 = 1.
```

## 2. Observed behavior

| Operation | Requests | Rate | p50 | p95 | p99 | Error % | DB/downstream calls per req | Notable |
|---|---|---|---|---|---|---|---|---|
| `tools/call odd_stack_status` | 30 (+5 warmup discarded) | 0.79 calls/s (30 in 38 s, client-paced sequential) | 118 ms | 125 ms | n=30 — not quoted (max 127 ms) | 0 | 3 docker CLI subprocesses (2 x `inspect` + 1 x `image-inspect`, sequential) + 4 HTTP GET readiness probes to `:3000` (sequential) | server root = 9.5 % of the 1242 ms client wall p50; ~28 ms of every root uninstrumented (F1) |

Sources. Requests and root durations: the limit-1000 list
`gcx traces query '{resource.service.instance.id="odd-262-1830" && name="tools/call odd_stack_status"}' --since 1h --limit 1000`
(35 traces, split warmup/load by `startTimeUnixNano` against the
record's load start; load roots, integer ms, in call order: 118 121 120
120 **127** 105 121 120 125 119 118 105 117 118 116 122 118 116 119 123
102 116 119 118 119 117 121 116 106 116 → min 102, p50 118, p95 125,
max 127, mean 117.3; warmup 140 119 113 117 120). Rate: the loop's
first-call → last-return stamps. Error %:
`gcx traces query '{resource.service.instance.id="odd-262-1830" && status=error}' --since 1h --limit 1000`
→ 0 traces (positive control: the service-wide search returned exactly
one error trace, `54de411ee501e83a751a89a1e46cf1de`, the co-resident's
reset, root 4863 ms). Downstream calls: the exemplar's span tree (8
spans) and the span-derived counts below.

**Cross-confirmation by Tempo's span-derived metrics** (pinned
`--time 1788460305` = 18:31:45Z, Ended + 20 s;
`sum by (span_name, span_kind, status_code) (traces_spanmetrics_calls_total{service="oddyssey-mcp"})`):
`tools/call odd_stack_status` = 35 (= 30 load + 5 warmup),
`oddyssey.docker.inspect` = 73 (= 35 x 2 + the reset's 3),
`oddyssey.docker.image-inspect` = 35 (1 per status call), `GET` UNSET =
147 (= 35 x 4 + the reset's 7), `GET` ERROR = 8 and `POST` ERROR = 1
(both the reset trace's), `tools/call odd_stack_reset` = 1, `docker.rm`
= 1, `docker.run` = 1 — every count identical to the baseline's.
Span-derived latency
(`histogram_quantile(q, sum by (le, span_name) (traces_spanmetrics_latency_bucket{service="oddyssey-mcp"}))`,
n=35 incl. warmup, bucket-interpolated): status p50 96.9 ms / p95 126.6
ms / p99 211.2 ms, mean 118.4 ms (`_sum/_count`; baseline 99 / 181 /
241, mean 122.8 — the baseline's p95 carried its 165 ms outlier, absent
here); `docker.inspect` p50 24.0 ms, mean 21.8 ms; `image-inspect` p50
45.9 ms, mean 35.5 ms; `GET` p50 1.46 ms, mean 2.25 ms. Interpolated
quantiles bracket the trace-list values; the trace list is the quoted
source. Service graph:
`sum by (client, server) (traces_service_graph_request_total)` → `user
→ oddyssey-mcp` = 36 (35 driven + the reset; baseline 71 for 70 + 1);
server-side p50
(`histogram_quantile(0.5, sum by (le, server) (traces_service_graph_request_server_seconds_bucket))`)
151 ms (a 36-sample interpolation the reset's 4.9 s skews; the trace
list is the number).

**The one exemplar — worst load trace `60d7f9f4091bc39b75e67e95a4e851bf`**
(127.82 ms, call 5; offsets from root start): `docker.inspect` +0.1 →
22.32 ms; `docker.inspect` +22.6 → 21.36 ms; `docker.image-inspect`
+44.2 → 38.39 ms (docker phase ends at +82.6 ms = 64 % of the root);
**no span from +82.6 to +110.8 ms (28.2 ms)**; then GET
`/api/datasources/proxy/uid/prometheus/-/ready` 3.83 ms, tempo 1.70,
loki 4.74, pyroscope 4.53 (all 200; probes end at +127.5). 8 spans, 0
events, 0 error statuses, `oddyssey.docker.exit_code=0` on all docker
spans, resource `service.instance.id=odd-262-1830`,
`service.version=1.10.2`, `deployment.environment.name=local`. The
worst-duration search with the span-derived p99
(`… && duration > 211ms`) returned `[]`; the fallback limit-1000 list
(explicit limit, 35 returned) gave this trace. At 127 ms the "worst"
sits 9 ms above p50: the run has no outlier (the baseline's worst was
165 ms, one docker-jitter sample).

**Client wall time (driver CSV, informational — the driver is not the
service):** load n=30 min 1220 / p50 1242 / p95 1268 / max 1592 / mean
1245 ms (one 1592 ms call, the driver side's own; its server root is
in the 102–127 band like the others). Wall − server root ≈ 1124 ms:
the per-call process-lifecycle cost (F3).

**Attribution (pinned `--time 1788460305`):**
`sum by (gen_ai_tool_name, service_instance_id, service_version) (mcp_server_operation_duration_seconds_count{service_name="oddyssey-mcp"})`
→ `{odd-262-1830, 1.10.2}`: status=1 (last writer — cumulative
temporality, 35 one-shot processes writing the same series;
`_sum{odd-262-1830}` = 0.11632 s = the 30th load call's root, 116 ms
in the list); `{no id, 1.10.1}`: status=7, config_get=4, reset=3 — the
co-resident's lifetime totals. `http_client_request_duration_seconds_count{service_instance_id="odd-262-1830"}`
= 4 (`{200, :3000}`, the last process's 4 probes).
`target_info{service_name="oddyssey-mcp"}` pinned → two identities
exactly. No driven call landed without the slug; no foreign call
carries it (F4 holds).

**Deltas against the recalled baseline (2026-09-03-1756, n=30 there
and here, same server code):** status root p50 121 → 118 ms, p95 126 →
125 ms, mean 122.2 → 117.3 ms: **unchanged** (−3 ms p50, inside the
spread both runs recorded); max 165 → 127 ms: **improved by one
sample** (the baseline's O1 docker-jitter sample did not recur; 30/30
calls lie in 102–127 ms); min 103 → 102 ms: unchanged; client wall p50
1237 → 1242 ms: **unchanged**; span shape 8 spans (root + 2 inspect +
image-inspect + 4 GET-200): **unchanged** (1/1); gap 28.5 ms (p50
trace) → 28.2 ms (worst trace): **unchanged**; span-derived counts per
status call (2 inspect, 1 image-inspect, 4 GET): **unchanged**; SDK
histogram count 1 per tool, `_sum` = last root: **unchanged**; slug
attribution two identities, no leak: **unchanged**. `odd_config_get`:
not driven, not ruled.

**Service graph:** `user → oddyssey-mcp` (36 requests); `oddyssey-mcp →
localhost:3000` (Grafana datasource proxy: 4 GETs per status call, 140
in the load+warmup); `oddyssey-mcp → docker CLI` (3 subprocesses per
status call, 105). No other node.

## 3. Anomalies and probable causes

| # | Finding | Severity | Confidence | Evidence | Expected gain |
|---|---|---|---|---|---|
| F1 | ~28 ms of every `odd_stack_status` root (22 % at p50) is uninstrumented, between `image-inspect`'s end and the first readiness GET — unchanged from the baseline | low | confirmed as a gap, cross-signal (exemplar 28.2 ms; spanmetrics means: root 118.4 − 2 x 21.8 − 35.5 − 4 x 2.25 ≈ 30 ms per call, the reset's spans slightly contaminating the children's means); **suspected** as to cause (the baseline's httpx-client-construction probe was not re-run) | `60d7f9f4…` +82.6 → +110.8 ms with no span | −20 to −28 ms per status call (root ~118 → ~90 ms) |
| F2 | The docker CLI phase is 64–68 % of a status call: 3 sequential subprocesses (2 x `docker inspect` ~22 ms + `docker image inspect` ~38 ms = ~82 ms) — unchanged | low | confirmed, cross-signal (span tree; spanmetrics inspect=73 = 2 per status call + 3, image-inspect=35; means 21.8 / 35.5 ms) | `60d7f9f4…`: 22.32 + 21.36 + 38.39 ms sequential | −20 to −25 ms per call (one inspect feeding both identity and env) |
| F3 | ~1.12 s per one-shot call is process lifecycle invisible to the telemetry: client wall p50 1242 ms vs server root 118 ms — unchanged | informational | confirmed as a number (driver CSV n=30 vs 35 traces); split unknown — no startup or shutdown span exists | wall − root = 1124 ms | none on the request path; a startup/shutdown span would make the split measurable |
| F4 | SDK cumulative histograms under one shared run slug are last-writer-wins: `_count` = 1 across the whole window, `_sum` = the last process's root — unchanged | medium for metric-based checks; by construction | confirmed, cross-signal (metrics count=1 vs spanmetrics 35 vs 35 traces) | `_sum{odd-262-1830}` = 0.11632 s = last root 116 ms | protocol: spanmetrics + trace list are the counters (section 7) |

## 4. Improvement opportunities

Unchanged from the baseline and not re-derived at quick depth: instrument the 28 ms gap (F1, verify with check 2 below) and collapse the two `docker inspect` calls into one (F2, verify with check 3) — together ~−45 ms on a ~118 ms root.

## 5. Telemetry gaps

Not queried (quick): logs, profiles — the environment probes showed neither carries `oddyssey-mcp` (`gcx logs labels -l service_name` → `["orders-api"]`; `gcx profiles labels -l service_name -d pyroscope --since 1h` → `["orders-api","pyroscope"]`), recorded without ruling; on the queried signals, the baseline's gaps stand as observed: the uninstrumented ~28 ms (F1, `60d7f9f4…`) and no process startup/shutdown span (F3).

## 6. Decisions the spec must settle

Unchanged from the baseline (its section 6 was not read at quick depth): whether the one-shot process lifecycle (F3) is in scope for the request path, and the form of the p50 band a verify run rules on (the baseline's decision 4).

## 7. Measurement protocol for the fix

Replay the scenario record of section 1 verbatim through the
`run-scenario` skill — same driver line, same `HOME=<fresh fakehome>`,
a new run slug (`odd-<issue>-<HHMM>`), 5 warmup discarded, 30
sequential `odd_stack_status`, one bare `odd_stack_reset` before,
**one** 60 s flush wait after `Ended`, then every query; the stack must
be `grafana/otel-lgtm:0.31.0` with `stack_config.local = {GF_LOG_LEVEL:
debug}` (the bare reset reapplies it; nothing credential-named was
passed). n=30: p50/p95 quotable, p99 not. Pin every instant metric
query with `--time <Unix seconds within 5 min of Ended>` or use a range
query. A verify at `quick` depth replays this at quick; a `full` replay
rules these same checks and says the baseline's coverage was quick.
**Only the checks this run measured are carried** — the baseline's
check 6 (`odd_config_get` root), 9 (lookback guard) and 10 (reset trace
census) were not measured here and are not part of this protocol.

| Check | Query | Before-value (this run) | Pass criterion | Validation |
|---|---|---|---|---|
| 1. status root p50 (trace list; baseline check 1) | `gcx traces query '{resource.service.instance.id="<slug>" && name="tools/call odd_stack_status"}' --since 1h --limit 1000 -o json --jq '[.traces[] \| {traceID, durationMs, startTimeUnixNano}] \| tostring'`, load-only by start time, p50 of `durationMs` | p50 118 ms, p95 125 ms, range 102–127 (n=30); baseline p50 121 / p95 126 / range 103–165 | F1 fix: p50 ≤ 95 ms; F1+F2: ≤ 75 ms; unchanged code: p50 106–135 ms and p95 ≤ 135 ms | validated this run (35 traces returned; warmup split by timestamp) |
| 2. Uninstrumented gap in a status trace (baseline check 2) | `gcx traces get <worst trace>` → `first GET startTime − image-inspect endTime` | 28.2 ms (`60d7f9f4…`, n=1 exemplar at quick depth; baseline 28.5 / 28.5 / 28.0 / 43.6 on 4) | ≤ 5 ms, or a span covering it whose duration equals the former gap | validated this run (1 fetch) |
| 3. docker inspect count per status call (baseline check 3) | `sum by (span_name) (traces_spanmetrics_calls_total{service="oddyssey-mcp"})` (pinned) | inspect=73 for 35 status calls + 1 reset (= 2/call + 3), image-inspect=35 | F2 fix: inspect = 1 x status calls (+3 per reset in store) | validated this run (values equal the driven counts exactly) |
| 4. Error % (baseline check 4) | `gcx traces query '{resource.service.instance.id="<slug>" && status=error}' --since 1h --limit 1000 --jq '.traces \| length'` | 0 (positive control: service-wide search → 1, the co-resident's reset) | 0 | validated this run (positive control returned the reset trace) |
| 5. Attribution by slug (baseline check 5) | `sum by (gen_ai_tool_name, service_instance_id, service_version) (mcp_server_operation_duration_seconds_count{service_name="oddyssey-mcp"})` with `--time` pinned ≤ Ended + 5 min | `{slug}` status=1 (last writer); no-id remainder = the co-resident's totals (7 / 4 / 3) | slug series carry only driven tools; no driven call lands without the slug; a slug-filtered count > 1 means the SDK's temporality changed | validated this run (pinned query returned both identities) |
| 6. Hygiene (baseline check 7) | driver CSV + saved stdout/stderr; distinct bodies by hash | 0 stderr bytes / 30 load calls; 1 distinct stdout body; `isError: false` on 30/30 | identical | validated this run |
| 7. Client wall p50 (driver, informational; baseline check 8) | driver CSV `wall_ms` p50 | 1242 ms (n=30); baseline 1237 | same magnitude (±20 %); a fix on the request path moves it by at most its own gain (~50 ms) | validated this run (n=30) |

The local stack is left **running** (container created 18:30:13Z,
`GF_LOG_LEVEL=debug`, all four signals ready) — the main agent measures
next. No git command that changes state was run by this mission; the
report file is left for the main conversation to commit.
