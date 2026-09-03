---
services: [oddyssey-mcp]
stack: local
environment: local
mode: re-measure
window: 2026-09-03T17:56:27Z/2026-09-03T17:57:41Z
run_name: mcp-read-tools
verifies: 2026-09-03-1710-mcp-read-tools.md
date: 2026-09-03
revision: edcd69f
tree_anchor: {.agents: "00fec2a0d71f459a5b1291f21b2ae50d0331b94e", .apm: "b52bf19a75968de473fef2a4be5093d060c52df9", .claude-plugin: "08b5b693ba92e7353eb1e5b31c58763421b18a22", .claude: "423cffd027ba21e2cb9b6fe396194b277cab58d2", .gitattributes: "14c97432b1cd8a40d995aba505e3ebe3529ad709", .github: "4c3b66e80c0b42e5b0706315f83f251dc09d692a", .gitignore: "7db740346f04814b7feb089f85aea8a663db1dd3", .odd: "6f5ececf49894ed84bc5d3a7ea0d239efc1d1221", AGENTS.md: "3055b320789dc62a79cbaf2a27bb74fb5ef3051a", CHANGELOG.md: "54deefa5a96ad44c96958dbdb93a6e9a326dfe29", CLAUDE.md: "43c994c2d3617f947bcb5adf1933e21dabe46bb5", CODE_OF_CONDUCT.md: "948ced506f78d19ccac65a19d19b4f84f618dcf3", CONTRIBUTING.md: "a23efce39f5e2b6f302c3e671d4c5cc6fcd45813", LICENSE: "2bcbad39118126520a36068a3dea6775700a3404", README.md: "c1af66c39bb116720ecc9105c8a96db4c7cbae94", SECURITY.md: "4909276e2d2f1a91ecb7274a3090bf81faa549bd", apm.yml: "484dbcf28b6906bcb50aff48928b62672fcda897", assets: "175f6c7aee93b5616cdbfd5c82b12e15e1d600a1", cliff.toml: "62e26cbf98f96473424692b0de6afe43d35df649", docs: "0cfe93936b30fa2ee75be46dc6ae0b0246511223", integration-tests: "6f1c20ca315c3ccd399b777a8ef9be27a7cb1d25", marketplace: "089becc00a4dfd2dc266ec875764910f3525f688", scripts: "286472375d7ef5894d3a77b1333a9cb3f10cf8fd", src: "2497e5d426ed15bb340a078af754a488b10ea43d", tests: "a35653b9078d49bf97c2cfa5d3efb7705046460a"}
instance: {oddyssey-mcp: "service.instance.id=odd-264-1755 on every driven one-shot process (70 processes, one run slug, opt-in via OTEL_RESOURCE_ATTRIBUTES through the MCP Inspector's -e flag). Co-resident exporter on the same stack: the installed uvx oddyssey-mcp==1.10.1 (this Claude Code session's server, no instance id)"}
process_restarted: true
---

# Observation report — oddyssey-mcp read tools, re-measure of 2026-09-03-1710

Re-measure of `2026-09-03-1710-mcp-read-tools.md`: the same scenario,
replayed verbatim on unchanged service code (`src` tree hash
`2497e5d4…` identical between the two revisions), to measure drift and
to exercise the #264 contract — the backend reference read by section
after a preflight handoff, the baseline read by section, the
persistence skill's return value carried back in the reply.

## 1. Mission and run record

- **Service:** `oddyssey-mcp`, binary `src/mcp-server/.venv/bin/oddyssey-mcp`
  (1.10.2, `telemetry.sdk.version=1.44.0`), driven through the MCP
  Inspector CLI 2.3.0 in `--cli` mode, one stdio server process per call.
- **Stack / backend:** local (Grafana LGTM, `grafana/otel-lgtm:0.31.0`,
  Grafana 13.1.3; Tempo, Prometheus, Loki, Pyroscope behind the
  datasource proxy on `http://localhost:3000`, OTLP gRPC `:4317`, OTLP
  HTTP `:4318`, Pyroscope `:4040`), `stack_config.local =
  {GF_LOG_LEVEL: debug}`. Backend CLI: gcx 1.2.0 through the
  `setup-local-stack` isolated context handed over by the preflight
  (reused as-is; `gcx config check` re-run once after the reset:
  online, Grafana 13.1.3). The preflight handoff itself is
  conversation-scope and not restated.
- **Mode:** drive (the replayed report's execution mode), recorded as
  `mode: re-measure`. **Benchmark:** none. **Window:** the scenario's
  own Started/Ended. **Focus:** replay the baseline's scenario verbatim
  and rule on every item it recorded — its section 7 checks, section 3
  anomalies, section 5 gaps. **Expectations:** the baseline's section 7
  before-values.
- **Defaults applied:** none beyond the contract's (window = scenario,
  one query point, one clean-base reset).
- **Deployment environment: `local`** — forced by construction on the
  local stack, and what the telemetry reports. Pre-reset detection (one
  bounded query per signal, before any reset):
  `gcx traces labels --scope resource -l deployment.environment.name -q '{resource.service.name="oddyssey-mcp"}'`
  → `["local"]`;
  `gcx metrics labels -l deployment_environment_name --match 'target_info{service_name="oddyssey-mcp"}'`
  → `["local"]`. Post-run on the slug: both queries with
  `service.instance.id="odd-264-1755"` → `["local"]`. Definite, not
  provisional. Baseline environment `local` = detected `local`: carry on.
- **Recalled baseline:** named by the mission —
  `.odd/observe-run-reports/2026-09-03-1710-mcp-read-tools.md`
  (revision `d0622d1`, drive, environment `local`, same service and
  stack). `tree_anchor` against `git ls-tree HEAD` (`edcd69f`): `.apm`,
  `docs` and `.odd` differ, every other entry — `src`, `tests`,
  `integration-tests` included — is byte-identical; the working tree is
  clean; no benchmark is named. No fix under test → **re-measure**, not
  verify. The diff below compares this run's numbers against that
  report's, and rules on each of its findings, gaps and checks.

### Contract reads (#264 evidence)

Reference and skill text read under the new contract, by section, with
`sed -n` line ranges — never a whole file:

| File | Sections read | Lines | Deliberately not read |
|---|---|---|---|
| `.apm/skills/observability-cli-guides/references/local.md` (157 lines) | `## Query by signal` (85–94) | 10 | `## CLI binary`, `## Setup`, `## Configuration display`, `## What to persist` (the preflight's) |
| `.apm/skills/observability-cli-guides/references/grafana.md` (278 lines) | `## Query by signal` incl. `### Reading gcx output`, `### Loki over OTLP` (82–164); `## Planning notes` (165–191) | 83 + 27 = 110 | `## CLI binary`, `## Setup`, `## Remote missions`, `## Configuration display`, `## What to persist` |
| `.apm/skills/setup-local-stack/SKILL.md` (154 lines) | `## Datasources` (109–142); `## This stack is push-based` (143–154) | 34 + 12 = 46 | `## Configure an isolated context` (the context exists, per the handoff) and everything before line 109 |

Baseline read (`2026-09-03-1710-mcp-read-tools.md`, 449 lines):

```text
Baseline read:
  1–13      frontmatter                                              13 lines
  71–190    section 1: replay notes (clean base, co-resident, config
            isolation, preflight, driver detail) + scenario record
            block (112–149) + timeline block and its closing note     120 lines
  191–327   section 2 (per-operation numbers, deltas)                137 lines
  328–346   section 3 (findings ruled on)                             19 lines
  372–399   section 5 (gaps ruled on)                                 28 lines
  421–449   section 7 (checks, before-values)                         29 lines
  total     346 of 449 lines (77 %); not read: 14–70 (section 1's
            mission restatement and recalled-baseline line, 57 lines),
            347–371 (section 4, 25 lines), 400–420 (section 6, 21 lines)
  locating  one grep over 29–190 for the bold sub-header lines (12
            header fragments, to place the record block) and one grep
            for the `## ` headings and the `Scenario:`/`Not
            reproducible:` anchors — lookups, not prose reads
  outside   nothing needed for any ruling was outside that set: no
            exception read was taken
```

`Contract reads:` 512 lines in total (reference sections 120 +
setup-local-stack sections 46 + baseline partial read 346), against a
whole-file read of 1025 lines (local.md 147 + setup-local-stack 151 +
grafana.md 278 + baseline 449 as the mission counts them; 1038 by
today's `wc -l`) — 50 % of the whole-file volume.

### Replay notes

- **Clean base:** the driven processes are one-shot (each inspector
  call spawns its own server process), so "restart the observed process
  first" holds by construction; then **one** bare `odd_stack_reset`
  before the scenario — the only reset of the mission. Pre-wipe store
  inventory (the wipe is machine-wide): Tempo `service.name` =
  `[oddyssey-mcp]` (the baseline run's 74 traces); `target_info`
  `service_name` = `[oddyssey-mcp, orders-api, otelcol-contrib]`; Loki
  `service_name` = `[orders-api]`; Pyroscope `service_name` =
  `[orders-api, pyroscope]`. Reset result: `env_reapplied:
  [GF_LOG_LEVEL]`, `services_wiped: [oddyssey-mcp, orders-api,
  otelcol-contrib]` (`orders-api` is another project's leftover, wiped
  on the mission's explicit order; it kept exporting after the wipe —
  a live process elsewhere on the machine — and is back in
  Loki/Pyroscope/`target_info` post-run, never in this run's queries).
  Container created 17:55:40Z (from the driven `odd_stack_status`
  bodies).
- **Co-resident server, read first (`ps` filtered on `oddyssey-mcp`):**
  the installed `uvx oddyssey-mcp==1.10.1` (this Claude Code session's
  server, started 16:51Z, no instance id). It served this mission's
  clean-base reset and re-exported its lifetime totals into the fresh
  store (status=5, config_get=3, reset=2 — grown by this session's own
  calls since the baseline's status=2 / config_get=2 / reset=1);
  separable from the driven processes by the slug (section 2).
- **Config isolation:** every driven process ran with `HOME` pointed at
  a **fresh** scratch `fakehome` (the baseline's was moved aside, so
  the npx cache was cold again — warmup call 1: 12538 ms, the
  baseline's 11964 ms): every `odd_config_get` result read
  `stack: local`, ports 3000/4317/4318/4040, `stack_config: {}` — no
  real identifier in any driven result.
- **Preflight (all four signals, post-scenario store):** traces present
  (`gcx traces query '{resource.service.instance.id="odd-264-1755"}' --since 1h --limit 1000`
  → 70 traces = 10 warmup + 60 load, exact; service-wide → 71, the
  extra being the co-resident's reset trace); metrics present (48
  series carry the slug: `mcp_server_operation_duration_seconds_*`,
  `http_client_request_duration_seconds_*`, `target_info`); logs absent
  (`gcx logs labels -l service_name` → `["orders-api"]`); profiles
  absent (`gcx profiles labels -l service_name -d pyroscope --since 1h`
  → `["orders-api","pyroscope"]`). Gaps in section 5.
- **Driver detail that binds every replay:** the inspector's stdio
  client passes only a whitelisted environment to the spawned server —
  `OTEL_RESOURCE_ATTRIBUTES` must go through the inspector's own `-e`
  flag, placed **after** the server command. Proven again: all 70
  traces carry `service.instance.id=odd-264-1755`
  (`gcx traces labels --scope resource -l service.instance.id -q '{resource.service.name="oddyssey-mcp"}'`
  → `["odd-264-1755"]`, the only value in the store).
- **Deviation from the record, stated:** the two load loops and the
  warmup were issued as three tool calls in one turn (the host ran them
  back-to-back: loop 1 17:56:27–17:57:05Z, loop 2 17:57:06–17:57:41Z,
  no interleaving — the per-call start stamps in the driver CSVs are
  strictly sequential). Each loop is still one blocking foreground
  command, as the record demands.

### Scenario record (verbatim)

```text
Scenario: mcp-read-tools — 5+5 warmup then 30 x odd_stack_status, 30 x odd_config_get,
          sequential, one blocking foreground loop per tool, each call its own
          stdio server process (MCP Inspector CLI 2.3.0), cwd = repo root
Server:   src/mcp-server/.venv/bin/oddyssey-mcp (branch feat/observe-preflight-recall-trim
          edcd69f, oddyssey-mcp 1.10.2, telemetry default-on, HOME=<scratchpad>/fakehome (fresh):
          isolated config ABSENT = defaults, ports 3000/4317/4318/4040)
Base URL: n/a (stdio); the server's own probes hit http://localhost:3000, OTLP to :4317
Backend:  odd_stack_reset (bare) once, before the scenario — env reapplied from
          stack_config.local: {"GF_LOG_LEVEL": "debug"}; container created 17:55:40Z
Instance: service.instance.id=odd-264-1755 on every driven process (70 one-shot
          processes; restart-by-construction, then the single reset)
Identity: -e "OTEL_RESOURCE_ATTRIBUTES=service.instance.id=odd-264-1755" AFTER the
          server command (shell-env export does not reach the spawned server)
Driver:   HOME=<scratchpad>/fakehome npx -y @modelcontextprotocol/inspector@2.3.0
          --cli src/mcp-server/.venv/bin/oddyssey-mcp
          -e "OTEL_RESOURCE_ATTRIBUTES=service.instance.id=odd-264-1755"
          --method tools/call --tool-name <tool>
          (wrapped by <scratchpad>/drive.py, unchanged from the baseline: one Python
          loop per tool, subprocess.run per call, wall time per call captured,
          stdout/stderr saved per call)
Warmup:   5 x odd_stack_status (17:56:02Z–17:56:20Z; first call 12538 ms cold npx
          cache, then 1245–1311 ms) + 5 x odd_config_get (17:56:20Z–17:56:26Z,
          1124–1216 ms) — discarded from every quoted number
Load:     30 x odd_stack_status (17:56:27Z–17:57:05Z) then 30 x odd_config_get
          (17:57:06Z–17:57:41Z), sequential, client-paced (no concurrency)
Started (UTC): 2026-09-03T17:56:27Z
Ended   (UTC): 2026-09-03T17:57:41Z
Query points: 1 (after Ended)
Commands:
  python3 <scratchpad>/drive.py odd_stack_status 5  warmup-status odd-264-1755
  python3 <scratchpad>/drive.py odd_config_get   5  warmup-config odd-264-1755
  python3 <scratchpad>/drive.py odd_stack_status 30 load-status   odd-264-1755
  python3 <scratchpad>/drive.py odd_config_get   30 load-config   odd-264-1755
  # each drive.py iteration = the Driver line above, verbatim
Results:  60/60 rc 0, 60/60 isError:false, 0 stderr bytes on all 60 load calls,
          1 distinct stdout body per tool across its 30 calls (byte-identical results);
          warmup: 10/10 rc 0, 522 stderr bytes on warmup-status call 1 only (npm's
          deprecation/update notices while populating the cold cache)
Not reproducible: none (fixed payloads: both tools take no arguments)
```

### Timeline (UTC)

Executed under the #264 contract (branch working tree). One line per
step; phase boundaries include the agent's own reasoning between turns.

```text
Timeline (UTC):
  17:53:53Z  mission start — contract reads by section (agent file, run-scenario, create-observe-run-report,
             the routed reference sections, the baseline partial read); pre-reset environment detection
  17:55:38Z  reset issued        (bare odd_stack_reset — the mission's single clean-base reset; container created 17:55:40Z)
  17:56:02Z  reset returned      (the server's own root span: 4900.65 ms, trace 4f7b9a09…; harness wall ~24 s,
             the call shared its turn with the pre-wipe inventory queries)
  17:56:02Z  gcx config check    (the single post-reset probe: Connectivity online, Grafana 13.1.3)
  17:56:02Z  warmup start        (5 x status, 5 x config_get, discarded)
  17:56:26Z  warmup end
  17:56:27Z  scenario Started    (load loop 1: 30 x odd_stack_status, one blocking command)
  17:57:05Z  load loop 1 end
  17:57:06Z  load loop 2 start   (30 x odd_config_get, one blocking command)
  17:57:41Z  scenario Ended      (last call returned)
  17:57:41Z  flush window start  (ONE wait, sized 60 s after Ended — traces are the slowest signal read;
             the blocking foreground sleep ran 17:58:16Z–17:58:45Z, the driver-output hygiene check
             in between reads no store)
  17:58:45Z  flush window end
  17:59:13Z  discovery turn start — 5 parallel tool calls issued in ONE turn (metrics, span-derived
             metrics, traces, logs, profiles; 27 gcx invocations in total; service preflight and the
             post-run environment re-check folded in)
  17:59:37Z  discovery turn end   (the host executed the 5 calls back-to-back: starts 17:59:13 /
             :21 / :30 / :34 / :37, each call 1–3 s — one turn, not concurrent execution)
  18:00:16Z  per-signal query phase start (3 parallel calls in one turn: per-trace durations from the
             saved limit-1000 lists, SDK histogram + attribution + HTTP-client series (pinned),
             exemplar p99-predicate searches)
  18:00:39Z  per-signal query phase end — includes the exemplar search phase (18:00:38Z–18:00:39Z:
             2 ops x 1 p99-predicate search; the discovery turn's limit-1000 lists are the fallback)
  18:01:09Z  exemplar fetch batch start   — 7 fetches issued in ONE turn (4 status traces, 2 config_get,
             1 co-resident reset), ~98 KB of OTLP JSON
  18:01:30Z  exemplar fetch batch end     (host ran them back-to-back, 2–5 s apart, each < 1 s)
  18:02:50Z  lookback guard (check 9)     — the one query that must wait for Ended + 5 min
  18:07:15Z  report persisted (.odd/observe-run-reports/2026-09-03-1756-remeasure-mcp-read-tools.md)
```

`Contract reads:` 512 lines (reference sections 120 + setup-local-stack
sections 46 + baseline partial read 346) versus 1025 for the whole-file
read.

**Ended → persisted: 9.6 min** (17:57:41Z → 18:07:15Z). The
baseline's was 13.3 min; of this run's delay, 64 s was the single flush
window, 0 s further resets, ~24 s the discovery turn, ~21 s the fetch
batch, ~70 s the wait for the lookback guard's 5-minute mark (overlapped
with the fetch batch and report drafting).

## 2. Observed behavior

| Operation | Requests | Rate | p50 | p95 | p99 | Error % | DB/downstream calls per req | Notable |
|---|---|---|---|---|---|---|---|---|
| `tools/call odd_stack_status` | 30 (+5 warmup discarded) | 0.79 calls/s (30 in 38 s, client-paced sequential) | 121 ms | 126 ms | n=30 — not quoted (max 165 ms, one outlier; second-highest 126 ms) | 0 | 3 docker CLI subprocesses (2 x `inspect` + 1 x `image-inspect`, sequential) + 4 HTTP GET readiness probes to `:3000` (sequential) | server root = 9.8 % of the 1237 ms client wall p50; ~28 ms of every root uninstrumented (F1, unchanged) |
| `tools/call odd_config_get` | 30 (+5 warmup discarded) | 0.86 calls/s (30 in 35 s) | < 1 ms (fetched: 102 µs, 95 µs; all 35 roots read 0 ms at search resolution) | < 1 ms | n=30 — not quoted | 0 | 0 | server root ≈ 0.01 % of the 1117 ms client wall p50 — the call is all process lifecycle (F3, unchanged) |

Sources per column. Requests and per-trace root durations: the limit-1000
list `gcx traces query '{resource.service.instance.id="odd-264-1755" && name="tools/call <op>"}' --since 1h --limit 1000`
(35 traces per op, split warmup/load by `startTimeUnixNano` against the
record's loop starts; load-only status roots, integer ms, in call order:
126 119 124 118 121 123 103 122 118 118 122 121 118 126 **165** 119 122
120 121 123 124 123 121 108 122 125 121 121 126 125 → min 103, p50 121,
p95 126, max 165, mean 122.2; warmup 139 123 109 129 117). Rate: the
loops' first-call → last-return stamps. Error %:
`gcx traces query '{resource.service.instance.id="odd-264-1755" && status=error}' --since 1h --limit 1000`
→ 0 traces (positive control: the service-wide search returned exactly
one error trace, `4f7b9a0952748f23e859333b6913dc29`, the co-resident's
reset, root 4900 ms). Downstream calls: the fetched span trees (4/4
status traces have the same 8-span shape; 2/2 config_get traces have a
single span).

**Cross-confirmation by Tempo's span-derived metrics** (pinned
`--time 1788458281` = 17:58:01Z, Ended + 20 s;
`sum by (span_name, span_kind, status_code) (traces_spanmetrics_calls_total{service="oddyssey-mcp"})`):
`tools/call odd_stack_status` = 35, `tools/call odd_config_get` = 35 (=
30 load + 5 warmup each), `oddyssey.docker.inspect` = 73 (= 35 x 2 + the
reset's 3), `oddyssey.docker.image-inspect` = 35 (1 per status call),
`GET` UNSET = 147 (= 35 x 4 + the reset's 7), `GET` ERROR = 8 and `POST`
ERROR = 1 (both entirely the reset trace's), `tools/call
odd_stack_reset` = 1, `docker.rm` = 1, `docker.run` = 1 — **every count
identical to the baseline's.** Span-derived latency
(`histogram_quantile(q, sum by (le, span_name) (traces_spanmetrics_latency_bucket{service="oddyssey-mcp"}))`,
n=35 incl. warmup, bucket-interpolated): status p50 99 ms / p95 181 ms
/ p99 241 ms, mean 122.8 ms (`_sum/_count`; baseline 97 / 127 / 211,
mean 119.7 — the p95 jump is the 165 ms outlier landing in the 0.1–0.25
s bucket, an interpolation artifact at n=35); `docker.inspect` p50 24.0
ms, mean 23.1 ms (baseline 24.1 / 22.4); `image-inspect` p50 47.0 ms,
mean 36.9 ms (baseline 47.0 / 35.5); `GET` p50 1.46 ms, mean 2.37 ms
(baseline 1.5 / 2.4); config_get mean 0.107 ms (baseline 0.106; its
quantiles sit in the smallest bucket — unusable, the mean is the
number). Interpolated quantiles bracket the trace-list values; the trace
list is the quoted source. Service graph:
`sum by (client, server) (traces_service_graph_request_total)` →
`user → oddyssey-mcp` = 71 (70 driven + the reset; baseline 71);
server-side p50
(`histogram_quantile(0.5, sum by (le, server) (traces_service_graph_request_server_seconds_bucket))`)
101.4 ms (baseline 101 ms).

**Where a status call spends its time** (p50-representative trace
`5112c5e071e20f699f3336ca85c5ea1a`, root 121.74 ms; offsets from root
start): `docker.inspect` +0.0 → 24.06 ms; `docker.inspect` +24.5 → 21.21
ms; `docker.image-inspect` +46.0 → 37.03 ms (docker phase ends at +83.0
ms = 68 % of the root); **no span from +83.0 to +111.5 ms (28.5 ms)**;
then GET `/api/datasources/proxy/uid/prometheus/-/ready` 3.86 ms, tempo
1.57, loki 1.59, pyroscope 1.73 (all 200; probes end at +121.4). Worst
load trace `d65efff3b524ded64ec1be248d5b5dc5` (165.07 ms, call 15):
27.56 / 21.57 / **75.77** ms docker, gap 28.5 ms, GETs 3.48 / 1.65 /
1.86 / 2.14 — the +43 ms over p50 is +38.7 ms in `image-inspect` alone
(2x its p50) and +3.5 ms in the first `inspect`; gap and probes are at
p50. Fastest `1c3470d7458817c92345609921157aaf` (103.05 ms): 18.51 /
17.57 / 29.05 ms docker, gap 28.0 ms, GETs 3.35 / 1.57 / 1.51 / 1.54.
Cold warmup #1 `eb94636f824e23c7d3a16d814b800` (139.49 ms): 26.97 /
21.67 / 35.15 ms docker, gap **43.6 ms**, GETs 4.42 / 1.90 / 1.68 / 2.06
— the cold penalty is in the gap, not in docker (baseline: 42.8 ms).
Exemplar diff: p50 → worst differs by +43 ms, of it 39 ms in one docker
`image-inspect` subprocess (single-signal: no docker-daemon telemetry
exists to say why that one call took 76 ms); p50 → fastest by −19 ms
spread over the three docker calls (−5.6 / −3.6 / −8.0); the gap is a
constant 28.0–28.5 ms warm. All four: 0 events, 0 error statuses,
`oddyssey.docker.exit_code=0` on all docker spans, resource
`service.instance.id=odd-264-1755`, `service.version=1.10.2`,
`telemetry.sdk.version=1.44.0`, `deployment.environment.name=local`.

**config_get exemplars** — `690b3ddf259971dbc87a8dbb678625a0` (first
load call): single span `tools/call odd_config_get` 102.0 µs, attributes
`mcp.method.name=tools/call`, `gen_ai.tool.name=odd_config_get`,
`network.transport=pipe`, `jsonrpc.protocol.version=2.0`; last load call
`bf9b9bf95c64d4e46a03b3b785ac0ff4`: 95.0 µs. The worst-duration search
`… && duration > 1.98ms` (span-derived p99, n=35, same value as the
baseline's) returned `[]`; the fallback limit-1000 list reads 0 ms for
all 35, so "worst" is undecidable at search resolution — recorded, the
two fetches bound the operation at ~0.1 ms. The status worst-duration
search `… && duration > 241ms` (span-derived p99) returned `[]` too; the
limit-1000 list (explicit limit, 35 returned) gave the 165 ms trace.

**Client wall time (driver CSVs, informational — the driver is not the
service):** status load n=30 min 1213 / p50 1237 / p95 1287 / max 1336 /
mean 1242 ms; config_get load n=30 min 1098 / p50 1117 / p95 1222 / max
1913 / mean 1148 ms (one 1913 ms call, the driver side's own outlier —
its server root reads 0 ms like the other 34). Wall − server root ≈ 1116
ms (status) and ≈ 1117 ms (config_get): the per-call process-lifecycle
cost is invariant across the two tools (F3, unchanged).

**The SDK's own metrics under a shared run slug (F4).**
`mcp_server_operation_duration_seconds_count{service_instance_id="odd-264-1755"}`
reads **1** per tool at every sample: range query `--from 1788458187
--to 1788458281 --step 15s` → status `1 1 1 1 1 1 1 1`, config_get `1 1
1 1 1 1 1`; pinned instants at 17:56:30Z, 17:57:15Z, 17:58:01Z → 1 / 1 /
1 for both. Cumulative temporality per process, 35 one-shot processes
writing the same series, last writer wins: `_sum{odd_stack_status}` =
0.12513 s = the 30th load call's root (125 ms in the list) to the 0.1
ms; `_sum{odd_config_get}` = 0.1765 ms (the last config_get process; its
handler span is 95 µs — the histogram's operation covers ~80 µs more
than the span, suspected framing/serialization outside the handler,
single-signal; baseline 250 µs vs 128 µs). `histogram_quantile(0.5, …)`
on it returns 0.175 s for status (baseline 0.175 s) — a one-sample
bucket interpolation, not a latency. Same on
`http_client_request_duration_seconds_count{service_instance_id="odd-264-1755"}`
= 4 (`{200, :3000}` — the last status process's 4 probes; p50 2.5 ms).
**For a one-shot-process run under one slug, the SDK histograms neither
count nor quantile the run; the counters and quantiles are Tempo's
spanmetrics and the trace list** — unchanged.

**Attribution (check 5), pinned inside Prometheus's lookback
(`--time 1788458281` = 17:58:01Z):**
`sum by (gen_ai_tool_name, service_instance_id, service_version) (mcp_server_operation_duration_seconds_count{service_name="oddyssey-mcp"})`
→ `{odd-264-1755, 1.10.2}`: status=1, config_get=1 (last writer, above);
`{no id, 1.10.1}`: status=5, config_get=3, reset=2 — the co-resident's
lifetime totals, cross-consistent with its no-id
`http_client…{200, :3000}` = 34 (= 5 status x 4 probes + 2 resets x 7
pre-rm GETs), `{415, :4318}` = 2 (one OTLP-ready POST per reset) and
`oddyssey_stack_probe_failures_total{error_type="ReadError"}` = 16 (2
resets x 8 boot polls). `target_info{service_name="oddyssey-mcp"}`
pinned → two identities exactly (`odd-264-1755`/1.10.2 and
no-id/1.10.1). No driven call landed without the slug; no foreign call
carries it.

**Lookback (F5, check 9):** at 18:02:50Z (Ended + 5 min 9 s) the
unpinned instant
`mcp_server_operation_duration_seconds_count{service_instance_id="odd-264-1755"}`
returned **0 series**; the same query `--time 1788458281` → 2 series.
Every instant metric query in this report is `--time`-pinned or a range
query.

**Deltas against the recalled baseline (2026-09-03-1710, n=30 there and
here, same code):** status root p50 119 → 121 ms, p95 126 → 126 ms, mean
119.1 → 122.2 ms: **unchanged** (+2 ms p50, inside the 106–127 spread
the baseline recorded); status max 127 → 165 ms: **drifted by one
sample** (call 15, 76 ms in a single `docker image inspect`; 29/30
calls lie in 103–126 ms); status min 106 → 103 ms: unchanged; status
client wall p50 1242 → 1237 ms: **unchanged**; config_get client wall
p50 1118 → 1117 ms: **unchanged**; config_get server root 109/128 µs →
102/95 µs: **unchanged**; status span shape 8 spans (root + 2 inspect +
image-inspect + 4 GET-200) → identical 4/4: **unchanged**; gap
27.9–29.1 ms warm / 42.8 cold → 28.0–28.5 / 43.6: **unchanged**;
span-derived counts (35/35/73/35/147/8/1/1/1/1) → identical:
**unchanged**; service graph 71 → 71: **unchanged**; SDK histogram
count 1 per tool, `_sum` = last root: **unchanged** (F4 holds); slug
attribution two identities, no leak either way: **unchanged** (N2 stays
fixed); reset trace census 22 spans / 0 events / 8 `ReadError` / 1 POST
415 / root 4912.5 → 4900.65 ms: **unchanged** (N4 holds on 1.10.1, n=1,
not driven). Nothing new appeared, nothing disappeared.

**Service graph:** `user → oddyssey-mcp` (71 requests); `oddyssey-mcp →
localhost:3000` (Grafana datasource proxy: 4 GETs per status call, 140
in the load+warmup; 0 for config_get); `oddyssey-mcp → docker CLI`
(3 subprocesses per status call, 105). No other node.

## 3. Anomalies and probable causes

Re-measure ruling on every finding of the baseline's section 3
(unchanged / drifted), then the one new observation.

| # | Finding | Severity | Confidence | Evidence | Expected gain |
|---|---|---|---|---|---|
| F1 | ~28 ms of every `odd_stack_status` root (23 % at p50) is uninstrumented, between `image-inspect`'s end and the first readiness GET; 43.6 ms on the cold first call — **unchanged** | low | confirmed as a gap (4/4 fetched traces: 28.5 / 28.5 / 28.0 / 43.6 ms; baseline 27.9 / 29.1 / 28.0 / 42.8); **suspected** as to cause (the baseline's httpx-client-construction probe was not re-run: same code, same numbers) — single-signal (traces) | `5112c5e0…` +83.0 → +111.5 ms with no span; `d65efff3…`, `1c3470d7…`, `eb94636f…` same | −20 to −28 ms per status call (root ~121 → ~93 ms), as the baseline stated |
| F2 | The docker CLI phase is 68 % of a status call: 3 sequential subprocesses (2 x `docker inspect` ~18–28 ms + `docker image inspect` ~29–37 ms = ~82 ms at p50) — **unchanged** | low | confirmed, cross-signal (span trees 4/4; spanmetrics inspect=73 = 2 per status call + 3, image-inspect=35; means 23.1 / 36.9 ms) | `5112c5e0…`: 24.06 + 21.21 + 37.03 ms sequential | −20 to −25 ms per call (one inspect feeding both identity and env) |
| F3 | ~1.12 s per one-shot call is process lifecycle invisible to the telemetry: client wall p50 1237 / 1117 ms vs server root 121 ms / 0.10 ms, invariant across the two tools — **unchanged** | informational | confirmed as a number (driver CSV n=60 vs 70 traces); split still unknown — no startup or shutdown span exists | wall − root = 1116 ms (status) / 1117 ms (config_get) | none on the request path; a startup/shutdown span would make the split measurable (section 5) |
| F4 | SDK cumulative histograms under one shared run slug are last-writer-wins: `_count` = 1 per tool across the whole window, `_sum` = the last process's root — **unchanged** | medium for the loop's metric-based checks; by construction of cumulative temporality | confirmed, cross-signal (metrics count=1 at 15 range samples and 3 pinned instants vs spanmetrics 35 vs 35 traces) | section 2 "SDK's own metrics"; `_sum{status}` = 0.12513 s = last root 125 ms | protocol: spanmetrics + trace list are the counters (section 7); decision in section 6 |
| F5 | Slug series vanish from unpinned instant queries 5 min after the run's last export (Prometheus lookback) — **unchanged** | low (protocol) | confirmed | unpinned instant at 18:02:50Z → 0 series; `--time 1788458281` → 2 series; range query over the window → 8 + 7 samples | protocol: pin `--time` or use range queries (section 7) |
| O1 | One status call (load call 15, `d65efff3…`) took 165 ms: `docker image inspect` ran 75.77 ms, 2x its 37 ms p50, everything else at p50 — a docker-daemon jitter sample, not a code behavior | informational (1/30; p50 and p95 unmoved) | confirmed as a number (trace + span-derived p95 moved 127 → 181 ms on that one sample); **suspected** as to cause — single-signal (no docker-daemon telemetry) | `d65efff3…` image-inspect 75.77 ms vs 37.03 / 29.05 / 35.15 ms on the other three fetched traces | none; it is the kind of sample the protocol's min–max band must tolerate (section 7, check 1 note) |

Not findings, recorded: the co-resident 1.10.1's re-export (status=5,
config_get=3, reset=2, no id) is separable by the slug — N2 stays fixed;
the store's only error trace (`4f7b9a09…`, 22 spans, root 4900.65 ms,
8 x GET `error.type=ReadError` boot polls at +821 ms and +2843 ms + 1 x
POST 415 to `:4318/v1/traces`, 0 exception events) is this mission's
own reset served by that server, not a driven call — its shape and
event count equal the baseline's (N4 holds on 1.10.1, n=1). Both driven
tools: 0 errors, 0 events, 0 stderr bytes, byte-identical results
across 30 calls each. The service emits
`deployment.environment.name=local` — no resource-attribute
discrepancy.

## 4. Improvement opportunities

Re-derived from this run's telemetry (the baseline's section 4 was not
read, per the recall contract); the numbers are this run's.

- **I1 — build the HTTP client once per process, or make its SSL-context
  cost a span (F1).** Expected gain −20 to −28 ms per status call (root
  p50 121 → ~93 ms, gap 28 → ≤ 5 ms). Verification: check 2 (gap
  between `image-inspect` end and the first GET start on the p50 trace,
  before-value 28.5 ms) and check 1 (root p50, before-value 121 ms).
- **I2 — one `docker inspect` feeding both the container identity and
  the user env (F2).** Expected gain −20 to −25 ms per status call
  (removes one of the two ~21–24 ms inspects). Verification: check 3
  (`oddyssey.docker.inspect` calls_total = 1 x status calls (+3 per
  reset), before-value 73 for 35 calls + 1 reset).
- **I3 — skip or cache `docker image inspect` when the container has no
  user env, or run it concurrently with the readiness probes.** Expected
  gain −29 to −37 ms per call at p50 (up to −76 ms on a jittery sample,
  O1). Verification: `image-inspect` calls_total per status call
  (before-value 1 per call, 35) and the root p50.
- **I4 — issue the four readiness GETs concurrently.** Expected gain ~5
  ms per call (the four sequential probes span 3.86 + 1.57 + 1.59 + 1.73
  ≈ 8.8 ms plus inter-probe gaps, +111.5 → +121.4 = 9.9 ms on the p50
  trace; concurrent they would take ~the slowest, ~4 ms). Verification:
  first GET start → last GET end on the p50 trace, before-value 9.9 ms.
- **I5 — a startup/shutdown span or a process-lifetime metric (F3).** No
  request-path gain; it makes the 1.12 s split measurable. Verification:
  a span or metric named for the lifecycle appears under the slug (any
  name — the discovery query `gcx traces labels --scope span -q
  '{resource.service.instance.id="<slug>"}'` lists it).

Combined I1 + I2 (the baseline's I1+I2 criterion): root p50 ≤ 75 ms.

## 5. Telemetry gaps

Re-measure ruling on every gap of the baseline's section 5 (filled /
still missing):

- **No logs for `oddyssey-mcp`** — **still missing**: `gcx logs labels -l service_name`
  → `["orders-api"]`; `gcx logs labels -l service_instance_id` → one
  `orders-api` UUID; `gcx logs query '{service_name="oddyssey-mcp"}' --since 1h --limit 1000`
  → `[]`. stdout is the JSON-RPC wire by design, but OTLP log export is
  absent too.
- **No profiles for `oddyssey-mcp`** — **still missing**:
  `gcx profiles labels -l service_name -d pyroscope --since 1h` →
  `["orders-api","pyroscope"]`; profile types exist on the stack (11,
  `gcx profiles list-profile-types -d pyroscope`) but none for the
  service.
- **No span around HTTP client construction** (F1) — **still missing**:
  the 28 ms hole is in 4/4 fetched status traces.
- **No startup / shutdown span** (F3) — **still missing**: ~1.12 s of
  every one-shot call has no telemetry at all; the span-attribute
  discovery on the slug lists only the request-path attributes
  (`gen_ai.tool.name`, `http.*`, `jsonrpc.*`, `mcp.method.name`,
  `network.*`, `oddyssey.docker.*`, `server.*`, `url.full`).
- **No metric metadata** — **still missing**: `gcx metrics metadata`
  filtered to `mcp_*` → `[]` (`target_info` present).
- **SDK histograms non-aggregable under a shared slug** (F4) — **still
  present**, by construction; the trace-derived metrics fill it.
  A decision, not a fix (section 6).
- Gaps do not dominate: traces and span-derived metrics carry the whole
  picture. No handoff to `otel-instrumentation-expert` needed for this
  run.

## 6. Decisions the spec must settle

Re-derived (the baseline's section 6 was not read):

1. **Metric temporality for one-shot processes** — keep cumulative
   temporality and treat Tempo's spanmetrics as the run's counters (the
   protocol's current stance), or switch the SDK to delta temporality /
   a per-process instance id so `mcp_server_*` can count a run of 35
   processes. Telemetry cannot decide; it only shows the current
   histograms count 1.
2. **Whether `odd_stack_status` must probe all four datasources on every
   call**, or may answer from the container identity alone and probe
   lazily: it decides whether I3/I4 are behavior changes or
   optimizations.
3. **Whether `docker image inspect` belongs on the status path at all**
   (it exists to read the image's user env): a cached or on-demand read
   changes the tool's contract for a freshly recreated container.
4. **The protocol's "unchanged code" band for check 1** — a min–max band
   from n=30 (106–135 ms) is violated by a single docker-jitter sample
   (O1: 165 ms) on identical code; the maintainers must say whether the
   band is on p50/p95 (this run: 121 / 126, inside) or on the extremes.

## 7. Measurement protocol for the fix

Replay the scenario record of section 1 verbatim through the
`run-scenario` skill — same driver line, same `HOME=<fresh fakehome>`,
a new run slug (`odd-<issue>-<HHMM>`), 5+5 warmup discarded, 30+30
sequential, one bare `odd_stack_reset` before, **one** 60 s flush wait
after `Ended`, then every query; the stack must be `grafana/otel-lgtm:0.31.0`
with `stack_config.local = {GF_LOG_LEVEL: debug}` (the bare reset
reapplies it; nothing credential-named was passed). All counts n=30 per
tool: p50/p95 quotable, p99 not. Pin every instant metric query with
`--time <Unix seconds within 5 min of Ended>` or use a range query (F5).
The before-values below are this run's; the baseline's are quoted where
they differ, so a verify run can diff against either.

| Check | Query | Before-value (this run) | Pass criterion | Validation |
|---|---|---|---|---|
| 1. status root p50 (trace list) | `gcx traces query '{resource.service.instance.id="<slug>" && name="tools/call odd_stack_status"}' --since 1h --limit 1000 -o json --jq '[.traces[] \| {traceID, durationMs, startTimeUnixNano}] \| tostring'`, load-only by start time, p50 of `durationMs` | p50 121 ms, p95 126 ms, range 103–165 (n=30; 29/30 in 103–126); baseline p50 119 / p95 126 / range 106–127 | I1: p50 ≤ 95 ms; I1+I2: ≤ 75 ms; unchanged code: p50 106–135 ms and p95 ≤ 135 ms (the min–max form of the baseline's band is violated by one docker-jitter sample on identical code — decision 4) | validated this run (35 traces returned; warmup split by timestamp); **ruled on the baseline's band: p50 121 in 106–135 → pass; max 165 outside → 1/30 sample, O1** |
| 2. Uninstrumented gap in a status trace | `gcx traces get <p50 trace>` → `first GET startTime − image-inspect endTime` | 28.5 ms (`5112c5e0…`), 28.5 / 28.0 / 43.6 ms on the other three; baseline 27.9 / 29.1 / 28.0 / 42.8 | ≤ 5 ms, or a span covering it whose duration equals the former gap | validated this run (4 fetches); **ruled: unchanged (a fix criterion, not expected to pass on unchanged code)** |
| 3. docker inspect count per status call | `sum by (span_name) (traces_spanmetrics_calls_total{service="oddyssey-mcp"})` (pinned) | inspect=73 for 35 status calls + 1 reset (= 2/call + 3), image-inspect=35; baseline identical | I2: inspect = 1 x status calls (+3 per reset in store) | validated this run (values equal the driven counts exactly); **ruled: unchanged** |
| 4. Error % on both tools | `gcx traces query '{resource.service.instance.id="<slug>" && status=error}' --since 1h --limit 1000 --jq '.traces \| length'` | 0 (positive control: service-wide search → 1, the co-resident's reset); baseline identical | 0 | validated this run (positive control returned the reset trace); **ruled: pass** |
| 5. Attribution by slug (N2 regression) | `sum by (gen_ai_tool_name, service_instance_id, service_version) (mcp_server_operation_duration_seconds_count{service_name="oddyssey-mcp"})` with `--time` pinned ≤ Ended + 5 min | `{slug}` status=1, config_get=1 (last writer); no-id remainder = the co-resident's totals (5 / 3 / 2; baseline 2 / 2 / 1) | slug series carry only driven tools; no driven call lands without the slug; a slug-filtered count > 1 per tool means the SDK's temporality changed (decision 1) | validated this run (pinned query returned both identities); **ruled: pass** |
| 6. config_get root | `gcx traces get` of the first and last load config_get traces | 102.0 µs / 95.0 µs, single span; all 35 read 0 ms at search resolution; baseline 109.0 / 128.0 µs | < 1 ms, single span | validated this run (2 fetches); **ruled: pass** |
| 7. Hygiene | driver CSVs + saved stdout/stderr; distinct bodies by hash | 0 stderr bytes / 60 load calls; 1 distinct stdout body per tool; `stack_config: {}` in every config_get result; baseline identical | identical | validated this run; **ruled: pass** |
| 8. Client wall p50 (driver, informational) | driver CSV `wall_ms` p50 per tool | status 1237 ms, config_get 1117 ms (n=30); baseline 1242 / 1118 | same magnitude (±20 %); a fix on the request path moves it by at most its own gain (~50 ms) | validated this run (n=30 each); **ruled: pass (−0.4 % / −0.1 %)** |
| 9. Lookback guard | unpinned `mcp_server_operation_duration_seconds_count{service_instance_id="<slug>"}` > 5 min after Ended | 0 series at 18:02:50Z (Ended 17:57:41Z); pinned → 2; baseline 0 at Ended + 6.9 min | expected 0 — proves the pin is required, never a finding | validated this run; **ruled: pass (as expected)** |
| 10. Reset trace census (N4, observed only) | `gcx traces get` of the store's `tools/call odd_stack_reset` trace | 22 spans, 0 exception events, 8 GET `ReadError`, 1 POST 415, root 4900.65 ms (1.10.1, n=1); baseline root 4912.5 ms | same census, 0 events; root 3–7 s | validated this run (n=1; not a driven call — the mission's own reset); **ruled: pass** |

Re-measure verdict: 9 of 10 checks pass on their own criteria; check 2
is a fix criterion (unchanged, as expected on unchanged code); check 1
passes on p50 and shows one 165 ms sample outside the baseline's min–max
band (O1, docker jitter) — the band's form is decision 4. Every finding
of the baseline is unchanged; every gap is still missing; nothing
drifted beyond one sample.

The local stack is left **running** (container created 17:55:40Z,
`GF_LOG_LEVEL=debug`, all four signals ready) — the main agent measures
next. No git command that changes state was run by this mission; the
report file is left for the main conversation to commit.
