---
services: [oddyssey-mcp]
stack: local
environment: local
mode: drive
depth: quick
window: 2026-09-04T10:38:33Z/2026-09-04T10:39:10Z
run_name: status-quick-check
date: 2026-09-04
revision: 8564f17
tree_anchor: {.agents: "00fec2a0d71f459a5b1291f21b2ae50d0331b94e", .apm: "42f6aa7045f03dfb5e56f59952bf341fc53b4ad8", .claude-plugin: "03d248c6c1ef292dcdcb7697bf24fdd63a2b1573", .claude: "423cffd027ba21e2cb9b6fe396194b277cab58d2", .gitattributes: "14c97432b1cd8a40d995aba505e3ebe3529ad709", .github: "cc8f80ee7b472165287378f96cd5072f80b4feb7", .gitignore: "7db740346f04814b7feb089f85aea8a663db1dd3", .odd: "3a99421241d45bc243bf8f991f336038ee93be80", AGENTS.md: "19b71d6d48085b59f930b377f8d589c0dd615219", CHANGELOG.md: "f7b8d0a5f80556ed75664a717e4714d2eb4df3a7", CLAUDE.md: "43c994c2d3617f947bcb5adf1933e21dabe46bb5", CODE_OF_CONDUCT.md: "948ced506f78d19ccac65a19d19b4f84f618dcf3", CONTRIBUTING.md: "6e901effed8ecb618160ffe6e84d5ac93063905a", LICENSE: "2bcbad39118126520a36068a3dea6775700a3404", README.md: "f8c783b9480e194b47d442a1ab4e879fd09fd06e", SECURITY.md: "4909276e2d2f1a91ecb7274a3090bf81faa549bd", apm.yml: "6040682ac04d8d63f2b126269cdee6deea133307", assets: "175f6c7aee93b5616cdbfd5c82b12e15e1d600a1", cliff.toml: "62e26cbf98f96473424692b0de6afe43d35df649", docs: "a1cd62294258cf964a33fb87e7dc51040e6bab7f", integration-tests: "6f1c20ca315c3ccd399b777a8ef9be27a7cb1d25", marketplace: "2c33443cb5c6521730b0ad9b9a2e218698d2cd4a", scripts: "286472375d7ef5894d3a77b1333a9cb3f10cf8fd", src: "ccdf5688c0fa897cb66c962d7afde1e90ff46637", tests: "a302b40ef143ee1f10841ee96dc9e72b36bdffcc"}
instance: {oddyssey-mcp: "service.instance.id=odd-281-1038 on every driven one-shot process (35 processes, one run slug, opt-in via OTEL_RESOURCE_ATTRIBUTES through the MCP Inspector's -e flag). Co-resident exporters on the same stack: two installed uvx oddyssey-mcp==1.10.3 servers (this Claude Code session's, no instance id, fold into one no-id series)"}
process_restarted: true
---

# Observation report: status-quick-check (quick depth)

Backend: the local oddyssey stack (`grafana/otel-lgtm:0.31.0` — Tempo,
Prometheus, Loki, Pyroscope behind Grafana 13.1.3), queried through
**gcx 1.2.0** on the `setup-local-stack` isolated context, piloted
through the oddyssey MCP tools. Depth **quick**: the one question is
"does `odd_stack_status` answer on the local stack, and with what
server-side latency" — the same question the recalled baseline asked,
re-measured on the same server code from a fresh store.

## 1. Mission and run record

- **Service:** `oddyssey-mcp` — the MCP server at
  `src/mcp-server/.venv/bin/oddyssey-mcp` (editable install of the
  working tree at `8564f17`; the server source is byte-identical to
  the baseline's `c89223f` except the release bump `1.10.2 → 1.10.3`
  in `pyproject.toml` / `uv.lock`), driven one-shot over stdio through
  the MCP Inspector CLI 2.3.0, `HOME` = a fresh fake home under the
  scratchpad (isolated config absent = defaults, ports
  3000/4317/4318/4040), run slug `odd-281-1038` as
  `service.instance.id`.
- **Stack:** local; backend = the local stack, gcx context = the
  handoff's file (reused; `gcx config check` re-run once after the
  reset: Connectivity online, Grafana 13.1.3 at 10:38:17Z — an earlier
  informational run at 10:36:47Z, before the reset, also passed).
- **Mode:** drive. **Depth:** quick (mission-set). **Focus:** the
  `odd_stack_status` operation — availability and server-side latency.
- **Window:** the scenario's own: `2026-09-04T10:38:33Z` →
  `2026-09-04T10:39:10Z` (load loop; warmup 10:38:18Z–10:38:33Z
  discarded). **Benchmark:** none. **Expectations:** none from the
  caller — the recalled baseline's numbers and protocol.
- **Deployment environment: `local`** — by construction on the local
  stack, and detected as such on every signal before the reset:
  traces `gcx traces labels -d tempo -l resource.deployment.environment.name`
  → `["local"]`; metrics
  `gcx metrics series 'target_info{service_name="oddyssey-mcp"}' --since 24h`
  → `deployment_environment_name=local` on all three identities
  present; logs `gcx logs labels -d loki -l deployment_environment_name`
  → `["local"]` (the stream is another service's — the MCP server
  emits no logs, section 5). Re-confirmed post-run on the driven
  traces:
  `gcx traces labels -d tempo --scope resource -l deployment.environment.name -q '{resource.service.name="oddyssey-mcp"}'`
  → `["local"]`. Definite, one value.
- **Recalled baseline:** `.odd/observe-run-reports/2026-09-03-1830-status-quick-check.md`
  (newest match on services, stack, environment; `depth: quick`, taken
  as a quick mission takes either depth). Read by section: frontmatter,
  section 1's scenario record and replay notes, sections 2, 3 and 7.
  Its driver script was reused **unchanged** apart from its scratchpad
  path constant (relocated to this session's scratchpad; the rest
  diffed identical).
- **Every default applied:** none beyond those listed — the mission
  block set every field; the window is drive mode's own.

### Replay notes

- **Clean base:** the driven processes are one-shot (each Inspector
  call spawns its own server process), so "restart the observed process
  first" holds by construction; then **one** bare `odd_stack_reset`
  before the scenario, issued 10:37:55Z — the only reset of the
  mission. Pre-wipe store inventory (the wipe is machine-wide, on the
  mission's explicit order): Tempo `service.name` = `[oddyssey-mcp]`;
  `target_info` `service_name` = `[k6, oddyssey-mcp, orders-api,
  otelcol-contrib]`; Loki `service_name` = `[orders-api]`; Pyroscope
  `service_name` = `[orders-api, pyroscope]`. Reset result:
  `env_reapplied: [GF_LOG_LEVEL]`, `services_wiped: [k6, oddyssey-mcp,
  orders-api, otelcol-contrib]`. Container created
  `2026-09-04T10:37:57.70Z` (from the driven `odd_stack_status`
  bodies).
- **Co-resident servers (`ps` filtered on `oddyssey-mcp`):** two
  installed `uvx oddyssey-mcp==1.10.3` processes (this Claude Code
  session's servers, no instance id; one served this mission's reset).
  After the wipe they re-exported their lifetime totals into the fresh
  store as one no-id series: status=2, config_get=2, reset=1 —
  separable from the driven processes by the slug (section 2).
- **Config isolation:** every driven process ran with `HOME` pointed at
  a **fresh** scratch `fakehome` (npx cache cold — warmup call 1:
  10376 ms wall; the baseline's 11459 ms). The isolated config is
  absent = defaults; no real identifier in any driven result.
- **Service preflight (queried signals only, post-scenario store):**
  traces present
  (`gcx traces query '{resource.service.instance.id="odd-281-1038" && name="tools/call odd_stack_status"}' -d tempo --since 1h --limit 1000`
  → 35 traces = 5 warmup + 30 load, exact; service-wide
  `'{resource.service.name="oddyssey-mcp"}'` → 36, the extra being the
  co-resident's reset trace); metrics present
  (`gcx metrics series '{service_instance_id="odd-281-1038"}' --since 1h`
  → 7 metric names: `mcp_server_operation_duration_seconds_{bucket,count,sum}`,
  `http_client_request_duration_seconds_{bucket,count,sum}`,
  `target_info`). Logs and profiles: not preflighted (quick); the
  pre-reset environment probes show neither carries the service, which
  section 5's line records without ruling.
- **Driver detail that binds every replay:** the Inspector's stdio
  client passes only a whitelisted environment to the spawned server —
  `OTEL_RESOURCE_ATTRIBUTES` must go through the Inspector's own `-e`
  flag, placed **after** the server command. Proven again: all 35
  traces carry `service.instance.id=odd-281-1038`
  (`gcx traces labels -d tempo --scope resource -l service.instance.id -q '{resource.service.name="oddyssey-mcp"}'`
  → `["odd-281-1038"]`, the only value in the store).
- **Deviation from the record, stated:** the post-reset `gcx config
  check`, the warmup loop, the load loop **and the single 60 s flush
  wait** ran chained in one shell command
  (`check && warmup && load && sleep 60`), so all four are strictly
  sequential by construction; the load loop is still one blocking
  foreground `drive.py` invocation, as the record demands, and the
  wait was paid once, after `Ended`.

### Scenario record (verbatim)

```text
Scenario: status-quick-check — 5 warmup then 30 x odd_stack_status, sequential, one
          blocking foreground loop, each call its own stdio server process
          (MCP Inspector CLI 2.3.0), cwd = repo root
Server:   src/mcp-server/.venv/bin/oddyssey-mcp (branch perf/observe-run-bounded-setup-reads
          8564f17, editable install; dist-info says 1.10.2, pyproject says 1.10.3 — see F5;
          telemetry default-on, HOME=<scratchpad>/obs/fakehome (fresh): isolated config
          ABSENT = defaults, ports 3000/4317/4318/4040)
Base URL: n/a (stdio); the server's own probes hit http://localhost:3000, OTLP to :4317
Listeners: :4317 served by the stack container (com.docker, *) — the stack itself, not a
          foreign service listener; no service port is bound by the driven process (stdio)
Backend:  odd_stack_reset (bare) once, before the scenario — env reapplied from
          stack_config.local: {"GF_LOG_LEVEL": "debug"}; container created 10:37:57Z
Instance: service.instance.id=odd-281-1038 on every driven process (35 one-shot
          processes; restart-by-construction, then the single reset)
Identity: -e "OTEL_RESOURCE_ATTRIBUTES=service.instance.id=odd-281-1038" AFTER the
          server command (shell-env export does not reach the spawned server)
Driver:   HOME=<scratchpad>/obs/fakehome npx -y @modelcontextprotocol/inspector@2.3.0
          --cli src/mcp-server/.venv/bin/oddyssey-mcp
          -e "OTEL_RESOURCE_ATTRIBUTES=service.instance.id=odd-281-1038"
          --method tools/call --tool-name odd_stack_status
          (wrapped by <scratchpad>/obs/drive.py, the baseline's script unchanged apart
          from its scratchpad path constant: one Python loop, subprocess.run per call,
          wall time per call captured, stdout/stderr saved per call)
Warmup:   5 x odd_stack_status (10:38:18Z–10:38:33Z; first call 10376 ms cold npx
          cache, then 1208–1321 ms) — discarded from every quoted number
Load:     30 x odd_stack_status (10:38:33Z–10:39:10Z), sequential, client-paced
          (no concurrency)
Started (UTC): 2026-09-04T10:38:33Z
Ended   (UTC): 2026-09-04T10:39:10Z
Query points: 1 (after Ended)
Commands:
  python3 <scratchpad>/obs/drive.py odd_stack_status 5  warmup-status-281 odd-281-1038
  python3 <scratchpad>/obs/drive.py odd_stack_status 30 load-status-281   odd-281-1038
  # each drive.py iteration = the Driver line above, verbatim
Results:  30/30 rc 0, 30/30 isError:false, 0 stderr bytes on all 30 load calls,
          1 distinct stdout body across the 30 calls (byte-identical results);
          warmup: 5/5 rc 0, 522 stderr bytes on warmup call 1 only (npm's
          deprecation notices while populating the cold cache)
Not reproducible: none (fixed payload: the tool takes no arguments)
```

### Timeline (UTC)

```text
Timeline (UTC):
  10:33:39Z  caller's preflight proof (handoff: gcx config check online, Grafana 13.1.3)
  10:36:30Z  mission start — contract reads by section (reference routing, run-scenario,
             persistence skill's recall, setup-local-stack; the baseline partial read)
  10:36:47Z  informational gcx config check (pre-reset) + stack status + config
  10:37:10Z  pre-reset environment detection on traces/metrics/logs + store inventory
             + co-resident census (one turn, parallel calls)
  10:37:55Z  reset issued        (bare odd_stack_reset — the single clean-base reset; container
             created 10:37:57Z; the co-resident's root span 4981 ms, trace a3e72c8b…)
  10:38:17Z  gcx config check    (the post-reset probe: Connectivity online, Grafana 13.1.3)
  10:38:18Z  warmup start        (5 x status, discarded)
  10:38:33Z  warmup end
  10:38:33Z  scenario Started    (load loop: 30 x odd_stack_status, one blocking command)
  10:39:10Z  scenario Ended      (last call returned)
  10:39:11Z  flush wait start    (ONE wait, 60 s — traces are the slowest signal read;
             foreground python3 time.sleep(60), chained after the load loop)
  10:40:11Z  flush wait end
  10:40:30Z  discovery + query turn (3 parallel calls: trace list/counts/errors/identity/
             environment/p99 search; spanmetrics/service graph/SDK attribution pinned at
             Ended + 20 s; driver hygiene) — every number of sections 2 and 3 comes from it
  10:41:20Z  exemplar fetch      (1 trace, de8c9ff3…, 13 KB) + venv provenance check
  10:44:30Z  report persisted (this file written)
Ended → persisted: ~5.3 min — target < 5 min: missed by ~20 s (the venv-provenance
             check for F5 and the src diff against the baseline were the extra turns).
Quick shape: signals queried = traces, metrics (span-derived + SDK); not queried (quick) = logs,
             profiles (one environment probe each, pre-reset); exemplars fetched = 1;
             anomalies = 5 confirmed (F1's cause suspected), 0 suspected-only; section
             lines as written: 3 = 7 (table: header, separator, 5 rows), 4 = 1, 5 = 1, 6 = 1.
```

## 2. Observed behavior

| Operation | Requests | Rate | p50 | p95 | p99 | Error % | DB/downstream calls per req | Notable |
|---|---|---|---|---|---|---|---|---|
| `tools/call odd_stack_status` | 30 (+5 warmup discarded) | 0.81 calls/s (30 in 37 s, client-paced sequential) | 122 ms | 126 ms | n=30 — not quoted (max 129 ms) | 0 | 3 docker CLI subprocesses (2 x `inspect` + 1 x `image-inspect`, sequential) + 4 HTTP GET readiness probes to `:3000` (sequential) | server root = 9.8 % of the 1240 ms client wall p50; ~28 ms of every root uninstrumented (F1) |

Sources. Requests and root durations: the limit-1000 list
`gcx traces query '{resource.service.instance.id="odd-281-1038" && name="tools/call odd_stack_status"}' -d tempo --since 1h --limit 1000`
(35 traces, split warmup/load by `startTimeUnixNano` against the
record's load start — the first load trace starts 10:38:34.560Z, ~1 s
after the driver's first load spawn at 10:38:33.557Z; load roots,
integer ms, in call order: 122 115 120 122 123 **129** 124 122 124 122
119 122 123 125 119 115 122 126 119 118 121 119 123 118 116 124 123
120 119 121 → min 115, p50 122, p95 126, max 129, mean 121.2; warmup
125 117 128 104 121). Rate: the loop's first-call → last-return
stamps. Error %:
`gcx traces query '{resource.service.instance.id="odd-281-1038" && status=error}' -d tempo --since 1h --limit 1000`
→ 0 traces (positive control: the service-wide search returned exactly
one error trace, `a3e72c8b410bde406bd41b2f2b903432`, the co-resident's
reset, root 4981 ms). Downstream calls: the exemplar's span tree (8
spans) and the span-derived counts below.

**Cross-confirmation by Tempo's span-derived metrics** (pinned
`--time 1788518370` = 10:39:30Z, Ended + 20 s;
`sum by (span_name, span_kind, status_code) (traces_spanmetrics_calls_total{service="oddyssey-mcp"})`):
`tools/call odd_stack_status` = 35 (= 30 load + 5 warmup),
`oddyssey.docker.inspect` = 73 (= 35 x 2 + the reset's 3),
`oddyssey.docker.image-inspect` = 35 (1 per status call), `GET` UNSET =
147 (= 35 x 4 + the reset's 7), `GET` ERROR = 8 and `POST` ERROR = 1
(both the reset trace's), `tools/call odd_stack_reset` = 1, `docker.rm`
= 1, `docker.run` = 1 — every count identical to the baseline's.
Span-derived latency
(`histogram_quantile(q, sum by (le, span_name) (traces_spanmetrics_latency_bucket{service="oddyssey-mcp", span_name="tools/call odd_stack_status"}))`,
n=35 incl. warmup, bucket-interpolated): status p50 97.9 ms / p95
144.0 ms / p99 233.6 ms, mean 121.4 ms
(`sum(_sum)/sum(_count) by (span_name)`; baseline 96.9 / 126.6 /
211.2, mean 118.4 — the interpolated p95 moved a bucket while the
trace list's p95 moved 1 ms: the coarse buckets, not the service);
`docker.inspect` mean 22.9 ms; `image-inspect` mean 36.0 ms; `GET`
mean 2.43 ms. Interpolated quantiles bracket the trace-list values;
the trace list is the quoted source. Service graph:
`sum by (client, server) (traces_service_graph_request_total)` → `user
→ oddyssey-mcp` = 36 (35 driven + the reset; baseline 36); server-side
p50
(`histogram_quantile(0.5, sum by (le, server) (traces_service_graph_request_server_seconds_bucket))`)
151.4 ms (a 36-sample interpolation the reset's 5.0 s skews; the trace
list is the number).

**The one exemplar — worst load trace `de8c9ff371de3d1653b925dea82e50fb`**
(129.50 ms, call 6; offsets from root start): `docker.inspect` +0.04 →
24.57 ms; `docker.inspect` +24.94 → 22.32 ms; `docker.image-inspect`
+47.53 → 36.13 ms (docker phase ends at +83.7 ms = 65 % of the root);
**no span from +83.7 to +112.0 ms (28.4 ms)**; then GET
`/api/datasources/proxy/uid/prometheus/-/ready` 7.89 ms, tempo 3.50,
loki 1.89, pyroscope 1.82 (all 200; probes end at +129.3). 8 spans, 0
events, 0 error statuses, `oddyssey.docker.exit_code=0` on all docker
spans, resource `service.instance.id=odd-281-1038`,
`service.version=1.10.2`, `deployment.environment.name=local`. The
worst-duration search with a p99 predicate
(`… && duration > 211ms`, the baseline's span-derived p99; this run's
233.6 ms is a subset of it) returned `[]`; the fallback limit-1000 list
(explicit limit, 35 returned) gave this trace. At 129 ms the "worst"
sits 7 ms above p50: the run has no outlier (the baseline's worst was
127).

**Client wall time (driver CSV, informational — the driver is not the
service):** load n=30 min 1225 / p50 1240 / p95 1319 / max 1338 / mean
1248 ms. Wall − server root ≈ 1118 ms: the per-call process-lifecycle
cost (F3).

**Attribution (pinned `--time 1788518370`):**
`sum by (gen_ai_tool_name, service_instance_id, service_version) (mcp_server_operation_duration_seconds_count{service_name="oddyssey-mcp"})`
→ `{odd-281-1038, 1.10.2}`: status=1 (last writer — cumulative
temporality, 35 one-shot processes writing the same series;
`_sum{odd-281-1038}` = 0.121701 s = the 30th load call's root, 121 ms
in the list); `{no id, 1.10.3}`: status=2, config_get=2, reset=1 — the
co-residents' lifetime totals (two processes, one series: the no-id
identity is itself last-writer-wins between them).
`http_client_request_duration_seconds_count{service_instance_id="odd-281-1038"}`
= 4 (`{200, :3000}`, the last process's 4 probes).
`target_info{service_name="oddyssey-mcp"}` pinned → two identities
exactly. No driven call landed without the slug; no foreign call
carries it (F4 holds).

**Deltas against the recalled baseline (2026-09-03-1830, n=30 there
and here, same server code — the src diff is the release bump only):**
status root p50 118 → 122 ms, p95 125 → 126 ms, mean 117.3 → 121.2 ms:
**unchanged** (+4 ms p50, inside the baseline's unchanged-code band of
106–135 ms; p95 ≤ 135 held); max 127 → 129 ms, min 102 → 115 ms:
**unchanged** (30/30 calls in 115–129 ms, a tighter spread than the
baseline's 102–127); client wall p50 1242 → 1240 ms: **unchanged**;
span shape 8 spans (root + 2 inspect + image-inspect + 4 GET-200):
**unchanged** (1/1); gap 28.2 ms → 28.4 ms (worst trace both times):
**unchanged**; span-derived counts per status call (2 inspect, 1
image-inspect, 4 GET): **unchanged**; SDK histogram count 1 per tool,
`_sum` = last root: **unchanged**; slug attribution two identities, no
leak: **unchanged**; error % 0 → 0: **unchanged**; availability 30/30
→ 30/30: **unchanged**. `service.version` reported by the driven
processes 1.10.2 → 1.10.2 while the source moved to 1.10.3: **new**
(F5). Fate of the baseline's findings: F1 still there, F2 still there,
F3 still there, F4 still there (by construction) — none was under fix.
`odd_config_get`: not driven, not ruled.

**Service graph:** `user → oddyssey-mcp` (36 requests); `oddyssey-mcp →
localhost:3000` (Grafana datasource proxy: 4 GETs per status call, 140
in the load+warmup); `oddyssey-mcp → docker CLI` (3 subprocesses per
status call, 105). No other node.

## 3. Anomalies and probable causes

| # | Finding | Severity | Confidence | Evidence | Expected gain |
|---|---|---|---|---|---|
| F1 | ~28 ms of every `odd_stack_status` root (23 % at p50) is uninstrumented, between `image-inspect`'s end and the first readiness GET — unchanged from the baseline | low | confirmed as a gap, cross-signal (exemplar 28.4 ms; spanmetrics means: root 121.4 − 2 x 22.9 − 36.0 − 4 x 2.43 ≈ 30 ms per call, the reset's spans slightly contaminating the children's means); **suspected** as to cause (the baseline's httpx-client-construction probe was not re-run) | `de8c9ff3…` +83.7 → +112.0 ms with no span | −20 to −28 ms per status call (root ~122 → ~94 ms) |
| F2 | The docker CLI phase is 65 % of a status call: 3 sequential subprocesses (2 x `docker inspect` ~23 ms + `docker image inspect` ~36 ms = ~83 ms) — unchanged | low | confirmed, cross-signal (span tree; spanmetrics inspect=73 = 2 per status call + 3, image-inspect=35; means 22.9 / 36.0 ms) | `de8c9ff3…`: 24.57 + 22.32 + 36.13 ms sequential | −20 to −25 ms per call (one inspect feeding both identity and env) |
| F3 | ~1.12 s per one-shot call is process lifecycle invisible to the telemetry: client wall p50 1240 ms vs server root 122 ms — unchanged | informational | confirmed as a number (driver CSV n=30 vs 35 traces); split unknown — no startup or shutdown span exists | wall − root = 1118 ms | none on the request path; a startup/shutdown span would make the split measurable |
| F4 | SDK cumulative histograms under one shared run slug are last-writer-wins: `_count` = 1 across the whole window, `_sum` = the last process's root — unchanged; the no-id co-resident identity now folds two processes the same way | medium for metric-based checks; by construction | confirmed, cross-signal (metrics count=1 vs spanmetrics 35 vs 35 traces; no-id status=2 across two long-lived servers) | `_sum{odd-281-1038}` = 0.121701 s = last root 121 ms | protocol: spanmetrics + trace list are the counters (section 7) |
| F5 | The driven processes report `service.version=1.10.2` while the source they run is 1.10.3: the venv's editable install carries the dist-info written before the release bump, and the SDK reads the version from package metadata — a stale resource attribute, not a code path | low | confirmed, two sources (trace resource attribute on all 35 traces and `target_info{service_instance_id="odd-281-1038"}` → `service_version=1.10.2`; on disk `oddyssey_mcp-1.10.2.dist-info` with `direct_url.json` `editable: true` against `pyproject.toml` `version = "1.10.3"`) | `gcx traces labels -d tempo --scope resource -l service.version -q '{resource.service.name="oddyssey-mcp"}'` → `["1.10.3", "1.10.2"]` (the co-residents' and the driven) | none on latency; re-sync the venv (`uv sync`) before a driven run so `service.version` matches `revision` — otherwise a later reader diffs two reports labeled the same version across a real code change |

## 4. Improvement opportunities

At quick depth, one line: the two request-path gains stay F1 (span the ~28 ms gap or remove it: root p50 122 → ≤ 95 ms, proven by section 7 check 1 and 2) and F2 (one `docker inspect` instead of two + the image inspect: −20 to −25 ms, proven by check 3); F5's hygiene fix (`uv sync` before driving) costs nothing and is proven by the `service.version` label listing above reading `["1.10.3"]` only.

## 5. Telemetry gaps

not queried (quick): logs, profiles — the pre-reset environment probes (`gcx logs labels -d loki -l service_name` → `["orders-api"]`; `gcx profiles labels -d pyroscope -l service_name --since 24h` → `["orders-api", "pyroscope"]`) show neither store carries `oddyssey-mcp`, recorded without ruling (a full run rules whether the server should emit logs and whether a profiler is expected); on the queried signals the gaps are F1's uninstrumented 28 ms (discovery: the exemplar's span tree has no span between +83.7 and +112.0 ms) and F3's absent startup/shutdown spans (the trace has 8 spans, none outside the root) — no `otel-instrumentation-expert` handoff: the gaps do not dominate a 122 ms root that is 77 % instrumented.

## 6. Decisions the spec must settle

None this run: the question was availability and latency of `odd_stack_status`, both answered with evidence (30/30, p50 122 ms); whether F1/F2 are worth fixing at ~50 ms against a 1.1 s process lifecycle (F3) is the same trade-off the baseline left open and this run adds no new fact to it.

## 7. Measurement protocol for the fix

Replay the scenario record of section 1 verbatim through the
`run-scenario` skill — same driver line, same `HOME=<fresh fakehome>`,
a new run slug (`odd-<issue>-<HHMM>`), 5 warmup discarded, 30
sequential `odd_stack_status`, one bare `odd_stack_reset` before,
**one** 60 s flush wait after `Ended`, then every query; the stack must
be `grafana/otel-lgtm:0.31.0` with `stack_config.local = {GF_LOG_LEVEL:
debug}` (the bare reset reapplies it; nothing credential-named was
passed). Re-sync the venv first (F5) so the driven `service.version`
equals the source's. n=30: p50/p95 quotable, p99 not. Pin every
instant metric query with `--time <Unix seconds within 5 min of
Ended>` or use a range query. A verify at `quick` depth replays this at
quick; a `full` replay rules these same checks and says the baseline's
coverage was quick. **Only the checks this run measured are carried**
— the same seven as the recalled baseline's protocol, plus the F5
hygiene check.

| Check | Query | Before-value (this run) | Pass criterion | Validation |
|---|---|---|---|---|
| 1. status root p50 (trace list; baseline check 1) | `gcx traces query '{resource.service.instance.id="<slug>" && name="tools/call odd_stack_status"}' -d tempo --since 1h --limit 1000 -o json --jq '[.traces[] \| {traceID, durationMs, startTimeUnixNano}] \| tostring'`, load-only by start time, p50 of `durationMs` | p50 122 ms, p95 126 ms, range 115–129 (n=30); baseline p50 118 / p95 125 / range 102–127 | F1 fix: p50 ≤ 95 ms; F1+F2: ≤ 75 ms; unchanged code: p50 106–135 ms and p95 ≤ 135 ms | validated this run (35 traces returned; warmup split by timestamp) |
| 2. Uninstrumented gap in a status trace (baseline check 2) | `gcx traces get <worst trace> -d tempo` → `first GET startTime − image-inspect endTime` | 28.4 ms (`de8c9ff3…`, n=1 exemplar at quick depth; baseline 28.2 on 1) | ≤ 5 ms, or a span covering it whose duration equals the former gap | validated this run (1 fetch) |
| 3. docker inspect count per status call (baseline check 3) | `sum by (span_name) (traces_spanmetrics_calls_total{service="oddyssey-mcp"})` (pinned) | inspect=73 for 35 status calls + 1 reset (= 2/call + 3), image-inspect=35 | F2 fix: inspect = 1 x status calls (+3 per reset in store) | validated this run (values equal the driven counts exactly) |
| 4. Error % (baseline check 4) | `gcx traces query '{resource.service.instance.id="<slug>" && status=error}' -d tempo --since 1h --limit 1000 -o json --jq '.traces \| length'` | 0 (positive control: service-wide search → 1, the co-resident's reset) | 0 | validated this run (positive control returned the reset trace) |
| 5. Attribution by slug (baseline check 5) | `sum by (gen_ai_tool_name, service_instance_id, service_version) (mcp_server_operation_duration_seconds_count{service_name="oddyssey-mcp"})` with `--time` pinned ≤ Ended + 5 min | `{slug}` status=1 (last writer); no-id remainder = the co-residents' totals (2 / 2 / 1) | slug series carry only driven tools; no driven call lands without the slug; a slug-filtered count > 1 means the SDK's temporality changed | validated this run (pinned query returned both identities) |
| 6. Hygiene (baseline check 6) | driver CSV + saved stdout/stderr; distinct bodies by hash | 0 stderr bytes / 30 load calls; 1 distinct stdout body; `isError: false` on 30/30 | identical | validated this run |
| 7. Client wall p50 (driver, informational; baseline check 7) | driver CSV `wall_ms` p50 | 1240 ms (n=30); baseline 1242 | same magnitude (±20 %); a fix on the request path moves it by at most its own gain (~50 ms) | validated this run (n=30) |
| 8. `service.version` matches the source (F5, new) | `gcx traces labels -d tempo --scope resource -l service.version -q '{resource.service.instance.id="<slug>"}'` | `["1.10.2"]` against `pyproject.toml` 1.10.3 | the single value equals `pyproject.toml`'s `version` at the run's `revision` | validated this run (the slug-scoped listing returned exactly one value) |

The local stack is left **running** (container created 10:37:57Z,
`GF_LOG_LEVEL=debug`, all four signals ready) — the main agent measures
next. No code was changed; the report file is committed on its own by
the persistence skill, on the mission's branch.
