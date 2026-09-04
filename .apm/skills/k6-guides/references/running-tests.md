# Running a k6 test and reading its output

Official docs: https://grafana.com/docs/k6/latest/get-started/running-k6/,
https://grafana.com/docs/k6/latest/results-output/

## Running

`k6 run <script.js>` - single VU, once, by default. Flags (verified
2026-08 against k6 v2.2.0):

| Flag | Meaning |
| --- | --- |
| `-u`, `--vus <int>` | number of virtual users (default 1) |
| `-d`, `--duration <duration>` | test duration limit (e.g. `30s`, `5m`) |
| `-i`, `--iterations <int>` | total iteration limit across all VUs |
| `-s`, `--stage <dur>:<target>` | add one load stage - repeat the flag for multiple stages, or use `options.stages` in the script (see scripting.md) |
| `-o`, `--out <output>` | where to send results - `json=<file>` (newline-delimited JSON), `opentelemetry` (see below), and others |
| `--summary-export <file>` | write the end-of-test summary (per-metric values, threshold results, checks) as JSON to `<file>` - what `run-scenario`'s stored-benchmark step reads for k6's own evidence (verified 2026-09 against k6 v2.2.0). Its schema is the legacy one unless `--new-machine-readable-summary` is also passed, which switches the export to the new shape - never assume a fixed schema across the two |
| `-e KEY=value` | set an environment variable for the script (`__ENV.KEY`) - how a mission-time base URL or a named secret reaches the script without editing it |
| `--no-setup` / `--no-teardown` | skip the script's `setup()`/`teardown()` |

## Validating without running - `k6 inspect` and the one-iteration smoke

Two checks sit between "written" and "run", both verified live on this
machine (2026-09-02, k6 v2.2.0):

- **`k6 inspect <script>`** - loads the script, runs its init context,
  resolves the options, prints them as JSON. Parse and schema errors
  fail here with the exact message: `constant-arrival-rate` with
  `rate: 1.5` exits **104** - `parsing options from script got error
  ... json: cannot unmarshal number 1.5 into Go struct field
  Options.scenarios.rate of type int64`. **Zero network I/O**: a script
  whose requests target an unresolvable host inspects with exit 0 - no
  request is ever sent, no target is contacted. Equally, it catches
  nothing that only happens at runtime - a `discardResponseBodies` /
  `res.json()` contradiction (scripting.md, "Response bodies") inspects
  clean. Official docs carry no dedicated page for the command; `k6
  inspect --help` is the reference.
- **The one-iteration smoke** - `k6 run --vus 1 --iterations 1
  --no-thresholds <script>`. When the script defines
  `options.scenarios`, these CLI flags **replace the scenarios
  entirely** - k6 logs `"cli" level configuration overrode scenarios
  configuration entirely` - so exactly one VU runs the default function
  exactly once (verified: a `constant-arrival-rate` script at 5 req/s
  for 20 s ran 1 iteration, 1 request, in 0.17 s). `--no-thresholds`
  keeps a one-sample latency from crossing a p95 threshold and turning
  a clean smoke into exit 99. **The exit code is not the smoke's
  verdict.** With `--no-thresholds`, a smoke whose single iteration
  threw on `res.json()` still exits **0**, its summary reading
  `http_req_failed 0.00% 0 out of 1` and `1 complete and 0 interrupted
  iterations` (verified live, 2026-09-02, k6 v2.2.0) - the only trace
  of the defect is one `level=error msg="GoError: ..." hint="script
  exception"` line on stderr. So does a fully refused request (exit 0,
  `http_req_failed 100.00%`). Grep stderr for `level=error` / `GoError`
  and read `http_req_failed` and the checks; a clean exit proves
  nothing. Three limits to state when relying on it: the override runs
  the **default** function only, so a scenario naming another function
  through `exec` is not exercised; a script whose scenarios all use
  `exec` and that exports no default function does not start at all -
  exit **104**, `executor default: function 'default' not found in
  exports` (verified live; `k6 inspect` passes it) - and is recorded as
  not applicable rather than patched with a default function; and the
  iteration's requests are real, with real side effects on the target -
  the smoke is authorized like any traffic at that target, never
  assumed.

Neither is the benchmark: the first sends nothing, the second sends one
iteration. Anything beyond - a `--duration`, a second iteration - is a
run, and belongs to the execution side (`run-scenario`).

## Exit codes

**Verified live** (this machine, 2026-08-31, k6 v2.2.0):

- **`0`** - every threshold passed (or no thresholds declared).
- **`99`** - a declared threshold was crossed. Stderr carries
  `level=error msg="thresholds on metrics '<name>' have been crossed"`.
  This is **not** the pass/fail signal `/odd-observe`/`/odd-verify` use
  (that's telemetry-only, per the design) - it is k6's own execution
  evidence, recorded alongside the telemetry-derived numbers by
  `run-scenario`'s stored-benchmark step (its `benchmark-replay.md` reference).
- Other non-zero codes cover setup/script errors - always read stderr,
  don't infer the failure kind from the code alone (this repo's own
  convention with other CLIs' exit codes, e.g. `az`'s).

## Output surface

- **Default (stdout)**: a human-readable summary - per-threshold
  pass/fail, then `HTTP`/`EXECUTION`/`NETWORK` sections with
  avg/min/med/max/p90/p95 for each metric.
- **`--out json=<file>`** - newline-delimited JSON, verified live: one
  `{"type":"Metric",...}` line per metric definition (name, type,
  thresholds, submetrics), then `{"type":"Point","metric":...,"data":{...}}`
  lines per sample, tagged with `scenario`, `status`, `method`, `url`,
  `expected_response`, `group`.
- **`-o opentelemetry`** - pushes metrics to an OTLP endpoint instead of
  writing a local file. Configuration is entirely via `K6_OTEL_*`
  environment variables (no CLI flags for this beyond `-o opentelemetry`
  itself), verified against `results-output/real-time/opentelemetry.md`:

  | Variable | Default | Notes |
  | --- | --- | --- |
  | `K6_OTEL_SERVICE_NAME` | `k6` | the OTel `service.name` k6's own metrics carry - **verified live: lands as `service_name="k6"`, `job="k6"` in Prometheus** when exported to oddyssey's local stack. Distinguishable from the target service's own labels, never mistake one for the other. |
  | `K6_OTEL_GRPC_EXPORTER_ENDPOINT` | `localhost:4317` | **matches oddyssey's local stack's default OTLP gRPC port exactly** - verified live: `K6_OTEL_GRPC_EXPORTER_INSECURE=true k6 run -o opentelemetry script.js` against a running local stack needs no endpoint override at all. |
  | `K6_OTEL_GRPC_EXPORTER_INSECURE` | (unset = TLS required) | set `true` for the local stack (no TLS) - without it the exporter fails to connect. |
  | `K6_OTEL_HTTP_EXPORTER_ENDPOINT` | `localhost:4318` | for `K6_OTEL_EXPORTER_PROTOCOL=http/protobuf` instead of the grpc default |
  | `K6_OTEL_METRIC_PREFIX` | (empty) | prefix every exported metric name |
  | `K6_OTEL_EXPORT_INTERVAL` | `10s` | how often metrics flush to the collector |

  Verified live metric names landing in Prometheus:
  `http_reqs_total`, `http_req_duration_milliseconds_{sum,count,bucket}`,
  `http_req_blocked_milliseconds_{sum,count,bucket}` - the `_bucket`
  suffix confirms k6's Trend metrics (like `http_req_duration`) export
  as OTel histograms, queryable with standard PromQL histogram functions
  (`histogram_quantile`).

  **This is a local-stack reality, not a general one - never treat it as
  required.** It works with zero extra config against oddyssey's own
  local stack only because the endpoint default happens to match. Most
  remote backends (`cloudwatch`, `azure-monitor`, `datadog`, `dynatrace`)
  have no bare OTLP-push endpoint the machine running k6 can
  reach at all - they take telemetry through their own SDK/agent, not a
  plain gRPC/HTTP OTLP target, and even where one exists the load
  generator's network path to it is frequently blocked (firewalls, VPNs,
  auth the load generator doesn't carry). Treat k6's own OpenTelemetry
  output as an **opportunistic bonus signal, used when reachable, never
  assumed** - the service's own telemetry (what every backend already
  guarantees `/odd-observe` can reach, or nothing about this project
  works at all) is what a benchmark's verdict can always depend on.
