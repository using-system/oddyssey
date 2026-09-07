# Running a k6 test and reading its output

Official docs: https://grafana.com/docs/k6/latest/get-started/running-k6/,
https://grafana.com/docs/k6/latest/results-output/

## Running

**A stored benchmark is replayed by this skill's own script, never by a
hand-built command:**

```bash
python3 <this skill's directory>/scripts/replay_benchmark.py <benchmark dir> --run-slug <slug>
```

It reads the benchmark's manifest, resolves every base URL the manifest
declares a default for, passes the run slug through the variable the
manifest names, runs the script **unmodified**, and prints the record:
the benchmark and its own git revision, whether its directory is clean,
the command verbatim, the UTC window, the exit status, and where the
summary landed. `--json` for the same as one object, `--dry-run` to see
the command without sending anything.

**A benchmark that outlasts a tool call is `--detach`, not a wrapper.**
Most are: a two-minute scenario does not fit in one call, and wrapping
the command in a shell script of your own puts the flags back in your
hands — which is what this script exists to prevent.

```bash
python3 <...>/replay_benchmark.py <benchmark dir> --run-slug <slug> --detach <dir>
python3 <...>/replay_benchmark.py --status <dir>     # poll until it says finished
```

`--detach` starts k6 in its own session and returns at once, writing
`replay-record.json`, `k6-stdout.log` and `k6-stderr.log` into `<dir>`;
`--status` answers "still running" or the finished record with its UTC
window and exit status — the same record the foreground form prints. The
whole flag surface is those two plus `--run-slug`, `-e KEY=value`,
`--summary`, `--send-traceparent`, `--otel`, `--dry-run` and `--json`:
there is nothing else, so `--help` has nothing to add and the file has
nothing to read.

It **refuses** `--vus`, `--iterations`, `--duration`, `--stage`, `--rps`,
`--execution-segment`, `--no-thresholds`, `--no-setup`/`--no-teardown` —
each replaces the script's own `options.scenarios` or its criteria, and
two runs that differ there stop comparing. A benchmark that needs one to
finish is a reported failure and a re-authoring, never a flag added at
run time.

What the caller still decides: the run slug (always — without it every
replay sends the same User-Agent and the runs merge), any `-e KEY=value`
the manifest left to run time, and `--send-traceparent`, which belongs to
a **remote** drive only: locally the launched process already carries
`service.instance.id`, and a synthetic parent would cost the run its
trace roots for nothing.

### The flags themselves


`k6 run <script.js>` - single VU, once, by default. Flags (verified
2026-08 against k6 v2.2.0):

| Flag | Meaning |
| --- | --- |
| `-u`, `--vus <int>` | number of virtual users (default 1) |
| `-d`, `--duration <duration>` | test duration limit (e.g. `30s`, `5m`) |
| `-i`, `--iterations <int>` | total iteration limit across all VUs |
| `-s`, `--stage <dur>:<target>` | add one load stage - repeat the flag for multiple stages, or use `options.stages` in the script (see scripting.md) |
| `-o`, `--out <output>` | where to send results - `json=<file>` (newline-delimited JSON), `opentelemetry` (see below), and others |
| `--summary-export <file>` | write the end-of-test summary (per-metric values, threshold results, checks) as JSON to `<file>` - k6's own execution evidence for a run record (verified 2026-09 against k6 v2.2.0) - how to read it without inverting its booleans: "Reading k6's own evidence" below. Its schema is the legacy one unless `--new-machine-readable-summary` is also passed, which switches the export to the new shape - never assume a fixed schema across the two |
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
run, not a validation.

## Exit codes

**Verified live** (this machine, 2026-08-31, k6 v2.2.0):

- **`0`** - every threshold passed (or no thresholds declared).
- **`99`** - a declared threshold was crossed. Stderr carries
  `level=error msg="thresholds on metrics '<name>' have been crossed"`.
  This is **not** the pass/fail signal `/odd-observe`/`/odd-verify` use
  (that's telemetry-only, per the design) - it is k6's own execution
  evidence, recorded alongside the telemetry-derived numbers by
  the run record, alongside the telemetry-derived numbers.
- Other non-zero codes cover setup/script errors - always read stderr,
  don't infer the failure kind from the code alone (this repo's own
  convention with other CLIs' exit codes, e.g. `az`'s).

## Reading k6's own evidence - the `--summary-export` file

The exported JSON is what a run's record quotes. Two of its conventions
read backwards, and a third number - one a threshold names - is simply
absent. Verified live (this machine, 2026-09-06, k6 v2.2.0, `k6 run
--vus 1 --iterations 1 --summary-export summary.json` against a trivial
local HTTP target, four thresholds declared, all met, exit 0 - the
default, legacy export shape, which `--new-machine-readable-summary`
replaces):

- **A threshold's boolean answers "crossed?", not "passed?".** Stdout
  printed `✓ 'p(95)<900'`, `✓ 'p(99)<200'`, `✓ 'rate<0.01'` and
  `✓ 'rate==1.00'`; the export wrote every one of them as `false`:

  ```text
  "http_req_duration": { ...the six trend stats..., "p(95)": 0.7,
                         "thresholds": {"p(95)<900": false, "p(99)<200": false} }
  "http_req_failed":   {"passes": 0, "fails": 1,
                        "thresholds": {"rate<0.01": false}, "value": 0}
  ```

  (two entries of the export's `metrics` object, the `http_req_duration`
  one abridged - `p(95)` is in milliseconds, that run's single request)

  `false` is the passing value. The run's verdict is the exit code
  (above), never the booleans read as plain English.
- **A `Rate` metric's `passes`/`fails` count samples, and on
  `http_req_failed` the polarity is inverted.** `passes` is the number
  of samples worth 1 and `fails` the number worth 0 - so the clean run
  above exported `http_req_failed: {"passes": 0, "fails": 1,
  "value": 0}` for its one successful request, while `checks` exported
  `{"passes": 1, "fails": 0, "value": 1}`. **Read `value`**: it is the
  rate itself (`0` = nothing failed, `1` = every check passed). Never
  quote a `Rate`'s `fails` as a count of failed requests.
- **A `p(99)` threshold has no value in the export.** The default trend
  stats are `avg,min,med,max,p(90),p(95)` (`summaryTrendStats`, option
  reference fetched 2026-09-06), so the run above - which declares
  `p(99)<200` - exported `http_req_duration` with those six stats, the
  threshold boolean, and no `p(99)` key at all. A record that must
  quote a percentile outside the six sets
  `summaryTrendStats: ['avg','min','med','max','p(95)','p(99)']` in the
  script's options (or `--summary-trend-stats`); otherwise the number
  comes from the telemetry, not from k6.

**The per-scenario progress glyph is not a verdict.** Observed during
the 2026-09-06 benchmark campaign (k6 v2.2.0): a run that exited 0 with
every threshold met still ended its progress line with
`<scenario> ✗ [ 100% ]`, where the one-iteration run above ended
`default ✓ [ 100% ]`. No k6 page found documents the glyph, so read it
as an observation and nothing more. k6's own verdict is the exit code
(above); `dropped_iterations` and its threshold say what was dropped.

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
  as OTel histograms, readable with the standard PromQL histogram
  functions (`histogram_quantile`) - for shape; see below on why a
  percentile taken that way is not the percentile k6 reports.

  Three things about reading those series back, recorded during the
  2026-09-06 benchmark campaign (k6 v2.2.0, this output read from a
  Prometheus-compatible store):

  - **Select on `service_name="k6"`, never on a name prefix.** The
    names above are the whole convention - `K6_OTEL_METRIC_PREFIX` is
    empty by default - so a query written `{__name__=~"k6_.*"}`
    returns an empty result, which reads exactly like "k6 exported
    nothing".
  - **A store-side quantile over those buckets is shape, not k6's
    percentile.** `histogram_quantile(0.95, ...)` over
    `http_req_duration_milliseconds_bucket` returned **950 ms** for a
    run whose own summary reported **p(95) = 779.46 ms** - the output's
    default millisecond bucket boundaries (..., 750, 1000, ...) put the
    true value inside one 250 ms-wide bucket. Use the exported
    histogram to compare shape across runs; take the percentile a
    threshold is read against from k6's own summary.
  - **An empty result is not a measured zero.** On one run that dropped
    no iteration, `dropped_iterations` had no series at all in the
    store - so that run's `dropped_iterations` threshold could not be
    cross-confirmed here. Whether this generalises to every counter at
    zero was not established; read the metric from the summary export
    and the exit code either way.

  A run ending with one `level=info msg="... failed to upload metrics:
  context canceled"` line was also recorded: k6's own shutdown cancelled
  the exporter's last flush, and every row had already landed (the
  store's counts matched the summary's exactly). It is an `info` line
  about the exporter, not the sign of a partial run.

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
