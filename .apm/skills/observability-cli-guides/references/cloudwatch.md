# AWS CloudWatch (+ X-Ray) — `aws`

CloudWatch is queried from the terminal with `aws`: the Logs Insights
query language against a log group (`aws logs start-query` /
`get-query-results` - the log records, and the raw Embedded Metric
Format records the metrics arrive through), `filter-log-events` for the
simple case, the extracted metrics through `aws cloudwatch`, and the
traces through `aws xray` (`get-trace-summaries`, `batch-get-traces`,
`get-service-graph`). This skill ships, in its `scripts/`, the scripts a
run invokes so that it composes no `aws` command and no CWLI query by
hand; the preflight and the switch read the four configuration sections,
the agents the rest. Official docs:
[cloudwatch](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/),
[logs](https://docs.aws.amazon.com/cli/latest/reference/logs/),
[xray](https://docs.aws.amazon.com/cli/latest/reference/xray/). Every
`docs.aws.amazon.com` page is HTML-only - no raw-markdown query
parameter, no source mirror; fetch and convert, never guess at raw links.

Verified live 2026-09-11, aws-cli 2.36.37 (Python 3.14.7, macOS), against an account carrying real data - one service (orders-api, an OTel resource driven continuously by an instrumented load generator that roots every trace, about 1 100 traces per 10 minutes with 404s, 500s and 502s), an OpenTelemetry Collector writing the log records as JSON bodies to the application group and EMF records (namespace with histogram statistic sets, delta counters, a gauge) to the metrics group, X-Ray segments with two remote subsegments, no CodeGuru profiling group; every script invocation below run from the repository root over 10-to-15-minute windows between 12:12 and 12:40 UTC; unverified where a bullet says so (a User-Agent-rooted identity, an X-Ray group other than Default, an expired SSO token, a Transaction Search account, EMF records carrying resource fields).

## CLI binary

- **Binary**: `aws`
- **Detect**: `command -v aws`
- **Install**: `brew install awscli` (macOS) or the official AWS CLI v2
  installer per platform:
  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

## Setup

| Topic | Link | What to do with it |
| --- | --- | --- |
| Credentials & config precedence | [Configuring settings for the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html) | `aws configure` writes `~/.aws/credentials` and `~/.aws/config`; `aws configure --profile <name>` writes a named profile. Precedence (highest first): CLI flags → env vars → assume-role config → web identity → IAM Identity Center (SSO) config → credentials file → external credential process → config file → container/EC2 instance-profile credentials. |
| Authentication overview | [Authentication and access credentials](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-authentication.html) | Every credential source (static keys, SSO, assume-role, env vars, external process, instance/container roles) - pick the mechanism for the environment (laptop vs CI vs EC2/ECS). |
| Environment variables | [Configuring environment variables](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html) | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_REGION`, `AWS_PROFILE` - for containers/CI where a shared credentials file is not wanted. Referred to by name, never a value. |
| Current context & connection probe | [aws sts get-caller-identity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html) | `aws configure list --profile <profile>` displays the effective profile, region and the source of each; `aws sts get-caller-identity --profile <profile>` proves the credentials work (returns account and ARN, needs no permission) - run through `scripts/cloudwatch-context.py check` (below). |
| IAM Identity Center (SSO) login | [Configuring IAM Identity Center authentication](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html) | `aws configure sso` writes a `[profile ...]` + `[sso-session ...]` block; `aws sso login --profile <name>` opens a browser and caches short-lived credentials. `aws sso login --profile <name>` is also the fix for an *expired* cached session (`Token has expired and refresh failed`) - the profile works, only its token lapsed. A `NoCredentials` error suggesting `aws login` is routinely a missing `default` profile, not a missing login: `aws configure list-profiles` first. Never run the login for the user. |
| `aws cloudwatch` reference | [cloudwatch](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/index.html) | Metrics: `list-metrics`, `get-metric-data`, `get-metric-statistics`. |
| `aws logs` reference | [logs](https://docs.aws.amazon.com/cli/latest/reference/logs/index.html) | Log groups and streams, `filter-log-events`, the Logs Insights trio `start-query` / `get-query-results` / `stop-query`. |
| `aws xray` reference | [xray](https://docs.aws.amazon.com/cli/latest/reference/xray/index.html) | `get-trace-summaries`, `batch-get-traces`, `get-service-graph`, `get-groups`. |

## Query by signal

The signals are read with the scripts this skill ships in `scripts/` -
never with `aws` commands or CWLI queries composed by hand. The shared
module `scripts/cloudwatch_aws.py` carries, in code, every transport
trap verified 2026-09-11: `--profile`/`--region` on every call (an SSO
setup routinely has no default profile), `--output json` captured whole
and filtered client-side (never `--query` with `--output text` on a
paginated command - the filter re-applies per page and yields a
multi-line string; never `--no-paginate` beside `--max-items` - refused;
never `TracesProcessedCount` as a population - it is per page); the time
units per command (`filter-log-events` in epoch milliseconds,
`start-query` and X-Ray in epoch seconds - the scripts speak RFC 3339
UTC or `--since`); the X-Ray range refused at 24 h before the service
refuses it; the local-offset timestamps X-Ray and `get-metric-data`
render converted to UTC; the Logs Insights `start-query` →
`get-query-results` poll inside and bounded (every second, 120 s at most,
then `stop-query`; a terminal status other than `Complete` is the
answer, never a partial page), the `[{field, value}]` rows turned into
dicts with the numbers coerced; the `get-metric-data` queries written to
a JSON file (the `Name=,Value=` shorthand dies on a `{param}` in a route
value); and the errors classified off stderr - the expired SSO token
(`identity-expired`), a profile the CLI cannot find (`no-profile`), no
credentials at all (`no-credentials`), a `MalformedQueryException` with
its message (`malformed-query`), an X-Ray `InvalidRequestException`
(`invalid-request`), a `ResourceNotFoundException` on a log group
(`not-found`, the account id it embeds scrubbed), a missing right
(`rights`), a throttle (`throttled`), a command the CLI refuses with
exit 252 (`usage`). Each invocation below is copy-pasteable - `<Skills>` is
the `skills` line the preflight handoff carries (the `package-layout`
skill's `scripts/layout.py`) - and states the script's **whole** flag
surface: `--help` has nothing to add and the files have nothing to read.
A run that lacks a shape of the work records it in its report's `## 8.
Stack friction`, never a wrapper.

Common to every script: the targeting values come from
`stack_config.cloudwatch` and are passed as flags - `--profile
<profile> --region <region>` on every script, `--log-group <log_group>`
(the application logs group), `--metrics-log-group <metrics_log_group>`
(the EMF group), `--xray-group <xray>` (an X-Ray group name, where the
service graph takes one), `--namespace <namespace>` where a metrics shape
needs one (the EMF namespace - discovered, not persisted); a **window**
is `--from <RFC3339 UTC> --to <RFC3339 UTC>` or `--since <duration>`
(`30m`, `2h`), and every X-Ray range stays under 24 h; a **service** is
`--service <name>` (repeatable, none = every service: the
`resource.service.name` of the log records, the segment name in X-Ray);
`--json` prints the same result as one object carrying the keys the
`Output` line names plus `commands` and `failed`; exit 0 means every
call ran (an empty answer is a result), 1 that a call failed - **the
failure is in the output**, under `FAILED` with its classification -, 2
a usage error, 3 (context only) a persisted value that does not resolve.
**Every subcommand ends by printing the `aws` commands it ran** -
`queries run (record these):` - with the targeting values **replaced by
their field names in angle brackets** (`--profile <profile> --region
<region>`, `--log-group-name <log_group>`, `--group-name <xray>`, the
queries file as `file://<queries.json>`), so the lines go into a
committed report as printed. The scripts run their independent calls
**concurrently** against one SSO profile - verified 2026-09-11,
seventeen Logs Insights queries side by side in 5.1 s, all complete, and
the `aws` calls of a discovery beside them. The commands behind the
scripts are
[start-query](https://docs.aws.amazon.com/cli/latest/reference/logs/start-query.html),
[get-query-results](https://docs.aws.amazon.com/cli/latest/reference/logs/get-query-results.html),
[stop-query](https://docs.aws.amazon.com/cli/latest/reference/logs/stop-query.html),
[filter-log-events](https://docs.aws.amazon.com/cli/latest/reference/logs/filter-log-events.html),
[describe-log-groups](https://docs.aws.amazon.com/cli/latest/reference/logs/describe-log-groups.html),
[list-metrics](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/list-metrics.html),
[get-metric-data](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/get-metric-data.html),
[get-trace-summaries](https://docs.aws.amazon.com/cli/latest/reference/xray/get-trace-summaries.html),
[batch-get-traces](https://docs.aws.amazon.com/cli/latest/reference/xray/batch-get-traces.html),
[get-service-graph](https://docs.aws.amazon.com/cli/latest/reference/xray/get-service-graph.html),
[list-profiling-groups](https://docs.aws.amazon.com/cli/latest/reference/codeguruprofiler/list-profiling-groups.html)
and [sts get-caller-identity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html);
the queries in them are the
[CloudWatch Logs Insights query syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html)
(`stats`, `parse`, `filter`, `bin`, `ispresent`, `earliest`/`latest`),
the [Embedded Metric Format specification](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html)
and the [X-Ray segment documents](https://docs.aws.amazon.com/xray/latest/devguide/xray-api-segmentdocuments.html).

### First, in one call: what the window holds - and where the environment is read from

```bash
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-discover.py --profile <profile> --region <region> --log-group <log_group> --metrics-log-group <metrics_log_group> --since 30m
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-discover.py --profile <profile> --region <region> --log-group <log_group> --metrics-log-group <metrics_log_group> --service <svc> --namespace <namespace> --from <start> --to <end> --json
```

Whole surface: `--profile`, `--region`, `--log-group`,
`--metrics-log-group` (all four required), `--service`, `--namespace`
(repeatable; none = every namespace the EMF records declare in the
window), `--xray-group`, a window, `--json`. **This is the first read
of a window**: it carries the deployment-environment detection, so a
run composes nothing for it. Output: `logs` - the group resolved
(retention, stored bytes), `freshness` (newest and oldest record,
count - the `max(@timestamp)` probe, never a stream's
`lastEventTimestamp`), `by_service_severity` (rows per
`resource.service.name` and `severity_number` with the OTel severity
range), `environment` (one row per service, `deployment.environment.name`
falling back to `deployment.environment`, `service.version`,
`service.instance.id`); `metrics` - the group resolved, `namespaces`
(from the records' `_aws.CloudWatchMetrics.0.Namespace`, with count and
newest), `resource_fields` (how many EMF records carry
`resource.service.name` / `resource.service.instance.id` - the guard the
edge diff needs, with the note saying what it implies), `by_namespace`
(per metric name: the series count, the number of dimension-set
variants, the `full_dimension_set` - one CloudWatch series per variant,
the fan-out counted); `traces` - the X-Ray service graph nodes with
`type` (`client` = the load generator's own root span, `remote` = an
upstream), `requests`, `error_rate`, `fault_rate`, `throttle_rate`,
`mean_response_s`, `edges_to`, the `--service` ones marked and the
absent ones listed under `missing`; `profiles` - the CodeGuru profiling
groups, `gap: true` and the note when there are none; `failed` (exit 1
when non-empty). Verified 2026-09-11: the environment came back `dev`
from `deployment.environment.name`, the EMF records carried no resource
field (0 of 420), one namespace with seven metric names, nine graph
nodes; the `deployment.environment` fallback and an account with a
profiling group are unverified 2026-09-11 (no record carries the old
key, no group exists). Runs its five queries and four calls side by side.

### Traces

A trace in X-Ray is a set of **segments** (one per service, the load
generator's own span among them, named by the HTTP method) with nested
**subsegments** (a remote call: `namespace: remote`, `peer.service` in
its metadata, the upstream inferred as a segment of its own); a summary
is one row per trace, its `Duration` the root segment's. Percentiles
are computed client-side over the summaries: EMF statistic sets cannot
yield them (below).

```bash
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-traces.py operations --profile <profile> --region <region> --service <svc> --since 30m
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-traces.py operations --profile <profile> --region <region> --user-agent odd-observe/<slug> --slow 3 --failed 3 --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-traces.py trace <trace_id> [<trace_id> ...] --profile <profile> --region <region>
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-traces.py graph --profile <profile> --region <region> --service <svc> --since 30m
```

Whole surface: every subcommand takes `--profile`, `--region`, `--json`;
`operations` and `graph` take a window under 24 h. `operations`:
`--service` (the summaries whose `ServiceIds` carry the name),
`--user-agent` (the run's identity as read on `Http.UserAgent`; its
`-warmup` variant folded into the identity table and excluded from the
operations), `--top` (operations printed, default 20), `--slow N`
(default 3), `--failed N` (default 3). `trace`: the trace ids, any
number (`batch-get-traces` takes five per call - a sixth is refused -
and the calls run concurrently). `graph`: `--service` (the nodes of
that name and the edges touching them), `--xray-group` (passed as
`--group-name`; omitted, the default group). Output of `operations`:
`traces` (the population: `len(TraceSummaries)` of **one unfiltered
call** over the window, split client-side - never a second, filtered
call), `identities` (per `Http.UserAgent` base: `traces`,
`warmup_traces`, `t0` = the first trace *without* the `-warmup` suffix,
`last`), `operations` (method + the URL's path with numeric or
UUID-like segments folded to `{id}` - a client-side stand-in, the true
`http.route` is on the server segment's metadata: `n`, `errors`,
`faults`, `throttles`, `p50_s`/`p95_s`/`p99_s`/`max_s` over `Duration`,
`rt_p95_s` over `ResponseTime`, `statuses`), `statuses` overall,
`partial` (summaries with `IsPartial` or no `Http` block - a root not
yet indexed - counted apart), `exemplars.slowest` and
`exemplars.failed` (ids with start, operation, status, duration,
flags), the three notes on whose span `Duration` is. Output of `trace`:
per id `duration_s`, `segments`, `tree` - each node `name`, `kind`
(`segment`, `subsegment`, `inferred`), `start`, `ms`, `method`, `url`,
`status`, `error`/`fault`/`throttle`, `metadata` (the flat dotted
`metadata.default` keys that matter: `http.route`, `error.type`,
`peer.service`, `otel.resource.service.name`,
`otel.resource.service.instance.id`,
`otel.resource.deployment.environment.name`), `metadata_keys` (all of
them - the literal key is `"otel.resource.service.name"`, one string,
never a path), `exceptions` (from `cause`), `children`; the text form is
the indented tree with `E`/`F`/`T` flags. Output of `graph`: `nodes`
(name, type, state, counts, `error_rate`, `fault_rate`, `mean_s`,
`p50`/`p95`/`p99` read off the node's `ResponseTimeHistogram` - the
server's view, every operation folded -, `buckets`) and `edges` (`from`
→ `to`, the same off the edge's histogram - the client's view of that
hop). Verified 2026-09-11: `operations` over 15 minutes - 1 684
summaries in 0.6 s, five operations, 4 partial, every `Http.UserAgent`
null (the account's load generator roots the traces: the identity table
shows one null identity, and the `--user-agent` path was exercised on
it - 0 traces of the identity - **but a User-Agent-rooted account, where
the run's `odd-observe/<slug>` lands on every summary, is unverified
2026-09-11**); `trace` on six ids in two calls, the faulted traces
rendering `payment-upstream` / `storage-upstream` under the server
segment with their `error.type` and exception; `graph` with
`--xray-group Default` (the only group the account has - another group
name is unverified 2026-09-11); a 25 h range refused at exit 2 before
any call.

### Metrics

Metrics arrive through the EMF group: the collector writes each push as
one JSON record carrying an `_aws.CloudWatchMetrics` block (namespace,
dimension sets, metric names) and the values - a histogram as a
**statistic set** (`Min`/`Max`/`Sum`/`Count` under the metric's name:
the fields `<metric>.Count` and `<metric>.Sum`), a counter or a gauge
as a scalar - and CloudWatch extracts one series per dimension-set
variant. A window's count is read off the **raw records**, never off
the extracted roll-up: on a cumulative pipeline every push carries the
total since process start, and a `get-metric-data` `SampleCount` per
period is a snapshot, not a count.

```bash
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-metrics.py list --profile <profile> --region <region> --namespace <namespace>
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-metrics.py probe http.server.request.duration --profile <profile> --region <region> --metrics-log-group <metrics_log_group> --namespace <namespace> --since 30m
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-metrics.py window http.server.request.duration --profile <profile> --region <region> --metrics-log-group <metrics_log_group> --namespace <namespace> --since 30m
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-metrics.py window orders.created --profile <profile> --region <region> --metrics-log-group <metrics_log_group> --by product.id --by OTelLib --since 30m
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-metrics.py window http.server.active_requests --profile <profile> --region <region> --metrics-log-group <metrics_log_group> --namespace <namespace> --as gauge --since 30m
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-metrics.py series http.server.request.duration --profile <profile> --region <region> --namespace <namespace> --dimension http.request.method=GET --dimension 'http.route=/orders/{order_id}' --dimension http.response.status_code=200 --dimension OTelLib=<lib> --dimension url.scheme=http --dimension network.protocol.version=1.1 --since 30m
```

Whole surface - `list`: `--profile`, `--region`, `--namespace`
(required), `--metric` (repeatable), `--json`. `probe <metric>` and
`window <metric>`: `--profile`, `--region`, `--metrics-log-group`
(required), `--by` (repeatable: the dimension fields) **or**
`--namespace` (the full dimension set is then read off `list-metrics`:
every dimension name the metric declares - a grouping coarser than the
full set folds distinct series together and yields garbage, routinely
negative, deltas), a window, `--json`; `window` adds `--as
auto|cumulative|delta|gauge` (default `auto`) and `--top` (rows,
default 40). `series <metric>`: `--profile`, `--region`, `--namespace`
(required), `--dimension Name=Value` (repeatable: the whole dimension
set of one series - a `{param}` in a route value is fine, the queries go
through a JSON file), `--stat` (repeatable; default `SampleCount`,
`Sum`, `Average`, `Minimum`, `Maximum`), `--period` (seconds, a
multiple of 60, default 60), `--show` (points per stat, the newest,
default 10), a window, `--json`. Output of `list`: per metric name the
`series` count, the `full_dimension_set`, the `dimension_sets` with
their series counts. Output of `probe`: `shape` (`statset` or `scalar`,
with the record counts), `dimensions`, `qualified_by_instance` (the
`ispresent()` guard: whether the records carry
`resource.service.instance.id` - when they do not, the output says a
restart shows as `reset_suspected` only), and per series (the full
dimension set, plus the instance id when carried) and per field
(`.Count` and `.Sum` for a statistic set) `pushes`, `min`, `earliest`,
`latest`, `max`, `sum`, `temporality` - `cumulative` when `min ==
earliest`, `max == latest` and the level at the window's start is at
least the window's increment (the magnitude), `delta` when the pushes
fell inside the window, `ambiguous` when monotonic but the level too
low (a process started inside the window, or a delta series that
happened to rise - both readings printed), `flat` when unchanged -,
`edge_diff`, `reset_suspected` (a cumulative series whose `max - min`
differs from `latest - earliest` decreased inside the window: a
restart). Output of `window`: one row per full dimension set with
`temporality`, `pushes` and, for a statistic set, `count` (the edge
diff of `.Count` on a cumulative series, its sum on a delta one), `sum`
(seconds, the same way) and `mean`; for a scalar, `value` (the edge
diff, the sum, a gauge's `min`/`max`/`mean` of the pushes, or both
readings when ambiguous); the notes say what each temporality means
and that percentiles are not computable from a statistic set. Output
of `series`: per stat the `status`, `datapoints`, the newest `points`
as `(UTC timestamp, value)`, a note when empty (not extracted yet, no
series of exactly these dimensions, or a percentile on a statistic set
- empty by design), and `metric_data_queries` (the exact payload, for
the record). Verified 2026-09-11: `list` (35 series of the histogram
across 10 dimension-set variants), `probe` and `window` on the
histogram (eight series `cumulative`, edge diffs of 5 to 775 over 15
minutes, means of 1 ms to 0.57 s - the checkout route), on the two
counters (`delta`: `sum()` per `product.id`), on the gauge with `--as
gauge` (0 on every push), `series` on the histogram with a braced route
(15 datapoints per stat; `p95` empty). The `ambiguous`, `flat` and
`reset_suspected` readings and `qualified_by_instance: true` are
unverified 2026-09-11 (no series of the window took those shapes; the
records carry no resource field).

### Logs

The records are the OTel log records the collector writes as JSON
bodies (stream `otel-collector`): Logs Insights exposes their keys as
fields - `trace_id`, `span_id`, `severity_number`, `severity_text`,
`body`, `resource.service.name`, `scope.name` (a dotted name is
backquoted in a query) - so a log line correlates with its trace with
no `parse`.

```bash
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-logs.py count --profile <profile> --region <region> --log-group <log_group> --service <svc> --since 30m
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-logs.py sample --profile <profile> --region <region> --log-group <log_group> --min-severity 13 --show 20 --since 30m
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-logs.py sample --profile <profile> --region <region> --log-group <log_group> --trace-id <trace_id> --since 1h
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-logs.py filter --profile <profile> --region <region> --log-group <log_group> --pattern '{ $.severity_number >= 13 }' --limit 20 --since 30m
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-logs.py routes --profile <profile> --region <region> --log-group <log_group> --service <svc> --since 30m
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-logs.py query --profile <profile> --region <region> --log-group <log_group> 'stats count() as n by `scope.name`, severity_text' --since 30m
```

Whole surface - every subcommand takes `--profile`, `--region`,
`--log-group`, a window, `--json`. `count`: `--service`, `--bin
<duration>` (one row per bucket and severity, newest first - no `sort`
on a `bin()`). `sample`: `--service`, `--min-severity` (an OTel
`severity_number`: 1 TRACE, 5 DEBUG, 9 INFO, 13 WARN, 17 ERROR, 21
FATAL; default 1), `--contains` (a substring of `body`), `--trace-id`,
`--show` (the newest, default 20). `filter`: `--pattern` (a CloudWatch
Logs filter pattern, through `filter-log-events` in epoch milliseconds
- the simple case, one page capped by `--limit`, default 50, the output
saying when more exist), `--stream-prefix`. `routes`: `--service`,
`--field` (the field holding the access line, default `body`), `--bin`
- the chained `parse` ready as the reference states it: the line into
`method`, `path`, `status`, then the path into `route` (the first
segment) and `tail` (a trailing segment after a folded id:
`/orders/{n}/checkout` reads as route `/orders`, tail `/checkout`),
then `stats count() by method, route, tail, status`. `query`: the CWLI
string, `--log-group` repeatable and `--metrics-log-group` (optional:
the EMF group joins the query, masked by its own field name), `--show`
(rows printed, default 50), `--cap` (the poll's bound, seconds, default
120) - the one escape hatch, through the same transport (the window
converted, the poll bounded, a `MalformedQueryException` classified
with its message). Output: `count` - rows with `resource.service.name`,
`severity_number`, `severity` (the OTel range), `n`, `last`, and
`total`; `sample` - `records` with `@timestamp`, service, severity,
`body`, `trace_id`, `span_id`, `scope.name`; `filter` - `events`
(`timestamp`, `stream`, `message`), `truncated`; `routes` - `rows` by
`method`, `route`, `tail`, `status`, `n`, and `not_access_lines` (the
records with no method parsed - the application's own lines); `query` -
`status`, `rows` (every field the query returned; `@ptr` dropped),
`rows_total`, `statistics` (records scanned and matched, bytes).
Verified 2026-09-11: `count` (1 698 records: INFO and WARN), `count
--bin 5m`, `sample --min-severity 13` (the `storage flake` and `payment
upstream unavailable` warnings with their trace ids), `sample
--trace-id` (the access line and the warning of one trace), `filter`
with a JSON filter pattern, `routes` (eight rows, 15 non-access
records) and `routes --bin 5m`, `query` on one group and on both, and a
malformed query classified (`sort bin(5m)`: `unexpected symbol found (
at line 1 and position 115`, exit 1). Runs one query per subcommand.

### The landing of a driven run

```bash
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-context.py landing --profile <profile> --region <region> --log-group <log_group> --metrics-log-group <metrics_log_group> --until <run end, RFC3339 UTC> --service <svc>
```

Whole surface: `--profile`, `--region`, `--log-group` (required),
`--metrics-log-group` (optional), `--until` (the instant the newest
log record must reach), `--service`, `--lookback` (how far back the
probe reads, default `15m`), `--every` (seconds between polls, default
10), `--cap` (the bound, default `3m`), `--json`. The proof is the
Logs Insights `max(@timestamp)` probe polled until it reaches `--until`
- **for the log records only**: the same probe on the EMF group is a
lower bound (an EMF record landed does not mean the metric is
extracted: the metric read itself - `window` or `series` answering
datapoints - is the proof), and **traces have no landing proof on this
backend** - a summary count read once is an observation, not a proven
landing; the output states all three. Exit 0 landed, 1 the cap was
reached (the last `newest` is in the output), 3 the group does not
resolve. Verified 2026-09-11: landed on the first poll for an `--until`
two minutes back (the EMF group at `--until` too), and not landed at
exit 1 for an `--until` ten minutes ahead with an 8 s cap. No
ingest-latency figure is documented for any of the three signals
(Planning notes): the poll is the only wait.

### Profiles

Not served by `aws cloudwatch`, `aws logs` or `aws xray`: continuous
profiling is Amazon CodeGuru Profiler, a separate service
([what it is](https://docs.aws.amazon.com/codeguru/latest/profiler-ug/what-is-codeguru-profiler.html),
[list-profiling-groups](https://docs.aws.amazon.com/cli/latest/reference/codeguruprofiler/list-profiling-groups.html),
[get-profile](https://docs.aws.amazon.com/cli/latest/reference/codeguruprofiler/get-profile.html))
with its own agent in the application, JVM and Python runtimes only.
`cloudwatch-discover.py` lists the profiling groups and states
their absence as the gap it is (verified 2026-09-11: none on the
account); the read of a profile is not shipped (unverified 2026-09-11,
no group to read) - an account with one records the gap in the
report's stack-friction section.

### Residual traps, for a call still composed by hand

- Logs Insights `min()`/`max()` print rounded to four decimals while
  `earliest()`/`latest()` print at full precision (verified 2026-09-11:
  `19.2677` against `19.267682323999793` on the same field): compare
  with a tolerance, never for equality - the module does.
- A regex literal is valid in `parse` and in `filter … like /…/` only;
  `replace()` takes plain strings (`MalformedQueryException: token
  recognition error at: '\'`).
- `sort` takes no `bin()`; a by-bin result is already ordered newest
  first.
- A `parse`-created field must not be re-listed in a downstream
  `fields` (`MalformedQueryException: Ephemeral field is already
  defined`).
- Grouping by an absent field errors nowhere: every record lands in one
  null group - `ispresent()` first (the scripts do).
- `@log` in a result carries the account id as its prefix: never copied
  into a report.
- A Logs Insights query is bounded by its own poll, never by an external
  `timeout` wrapper (`timeout(1)` is absent on macOS).
- `-o` is not accepted as the short form of `--output`; `--extended-statistics`
  and a `p<N>` stat return empty on an EMF statistic set, exit 0.
- X-Ray's `--filter-expression` vocabulary is a fixed set (`http.status
  = 404`, `service("name")`, `annotation[key]`, `error`/`fault`/
  `throttle`, `duration`, …), never an OTel attribute name: an invented
  field fails with `InvalidRequestException … Invalid input symbol`
  pointing at a position, nothing saying "unknown field"
  ([filter syntax](https://docs.aws.amazon.com/xray/latest/devguide/xray-console-filters.html)).
- `describe-log-streams`' `lastEventTimestamp` is eventually consistent
  and lags minutes behind: never a freshness signal.
- `batch-get-traces` does not work once Transaction Search is enabled
  on the account (unverified 2026-09-11: the account has it off).

## Planning notes

- **Whose span `Duration` is.** A summary's `Duration` is the root
  segment's: with an instrumented client (a load generator tracing
  itself) the root is the client's own span - named by the method,
  `Type: client` in the graph, `Http.UserAgent` null on every summary -
  and `Duration` its view, never shorter than the server segment's
  (verified 2026-09-11 on a faulted checkout: root 334.9 ms, server
  333.4 ms, remote 332.4 ms). Server-side percentiles are `graph`'s
  per-node histogram (every operation folded) or the server segments of
  `trace` (sampled). With stock k6 and no client span, the server's own
  segment roots the trace and `Http.UserAgent` carries the run's
  User-Agent - the preferred selector then (unverified here: the
  account's generator is instrumented).
- **A run's t0** is its first request without the `-warmup` suffix:
  `operations` takes it that way per identity. Taking it over the whole
  identity puts t0 on the warmup and every stage boundary shifts.
- **Summary volume scales with the request rate**: one summary per
  trace, about 1 100 per 10 minutes here in 0.5 s (a 10-minute window
  at 200 req/s came back as 60 547 summaries, 102 MB, about 40 s on an
  earlier campaign). One unfiltered call per window, split client-side.
- **EMF temporality.** The histogram statistic sets are cumulative on
  this pipeline (every push the total since process start: the window's
  count is the edge diff), the `orders.*` counters are per-push deltas
  (`sum()`), the gauge is unexplained: `probe` decides per series and
  `window` reads accordingly. A `get-metric-data` roll-up of a
  cumulative series is a snapshot with no operational meaning - no
  error, no warning.
- **An EMF gauge's `Max` is not the window's peak** (0 on every push
  here while requests were in flight, as an earlier run measured 0-8
  against about 150 concurrent): what the exporter samples was not
  ruled - stated as unexplained in a report, never quoted as
  concurrency.
- **The EMF records carry no resource fields** on this pipeline (0 of
  420): an edge diff cannot be qualified by instance; attribute a series
  through the log records' `service.instance.id` (discover's
  environment table) and read `reset_suspected`. The metrics group's
  streams are the exporter's `otel-stream-<uuid>`, never a service
  instance.
- **No documented ingest-latency figure** for logs, metrics or traces
  (checked 2026-09-06 on
  [What is CloudWatch Logs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/WhatIsCloudWatchLogs.html),
  [Analyzing log data](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html),
  [Getting data from X-Ray](https://docs.aws.amazon.com/xray/latest/devguide/xray-api-gettingdata.html),
  [EMF alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Alarms.html)):
  logs are waited on through `landing`, metrics through the read
  itself, traces not proven - `list-metrics` warns a newly created
  metric can take up to 15 minutes to appear.
- **Aggregations are zero-safe**: over a window where nothing matches
  a `stats` answers a row holding `0` (or no row for a `fields` query),
  so a protocol's zero branch validates as a measured `0`.
- **Partial summaries** (`IsPartial`, empty `Http`) are traces whose
  root is not indexed yet - 3 to 4 per 15 minutes here; `operations`
  counts them apart.
- **The `error.type` dimension** appears in the histogram's full
  dimension set on failures only: on the successful series it groups as
  `-` (absent), which is right - it distinguishes the series.
- **The EMF dimension sets fan out**: 35 series for one histogram name
  across 10 variants here; `list` counts them, `window` reads the raw
  records once per full set.
- **Timestamps**: Logs Insights prints UTC without an offset
  (`2026-09-11 12:27:11.555`); X-Ray and `get-metric-data` print the
  machine's local offset - the scripts convert, a hand call must.
- Auth scope: SSO credentials are short-lived; automation prefers a
  static IAM user, an assumed role or an instance/container role over
  an interactive `aws sso login` a human refreshes.

## Configuration display

### Display

Two sources, labelled per line - the CLI's effective credentials and
the persisted targeting values.

**If `stack_config.cloudwatch.profile` is persisted, run every
command below (display and connection proof alike) with `--profile
<profile>`** - a bare call answers for whatever profile happens to
resolve without a flag, which on an SSO setup with no `default` is
routinely none at all, reporting a degradation on an account that is
configured and working.

From the `aws` CLI:

- `aws sts get-caller-identity --profile <profile>` - the account id
  and the caller ARN (which identity the queries run as); through
  `scripts/cloudwatch-context.py check` the text form shows the
  principal's type and the account's last four digits only (the full
  values under `--json`), so a pasted line carries no identifier.
- `aws configure list --profile <profile>` - the effective profile,
  region, and where each came from (env, config file, IAM role). Show
  the source column: a region coming from an env var is the usual
  explanation for queries hitting the wrong one.

On an SSO profile whose cached token has expired, `aws configure list
--profile <name>` itself errors (`Error when retrieving token from sso:
Token has expired and refresh failed`, exit 255) while still printing a
partial table - the same auth failure the connection proof diagnoses,
one step earlier. Carry on to the proof's expired-token guidance.

From `stack_config.cloudwatch` (per `odd_config_get`):

- `region` - the region the mission queries, when pinned separately
  from the CLI's effective one.
- `profile` - the named `aws` CLI profile the mission runs under, when
  no `default` profile resolves on its own (the SSO norm).
- `log_group` - the CloudWatch Logs group the mission reads for
  application logs.
- `metrics_log_group` - the CloudWatch Logs group metrics arrive
  through as Embedded Metric Format, when the account exports them that
  way rather than writing directly to the CloudWatch metrics API. May
  equal `log_group`, may not - display both, never assume one covers
  the other.
- `xray` - the X-Ray group name the service graph reads (`--xray-group`),
  when persisted; the default group otherwise.

Every field the user did not persist is listed as "not persisted - the
mission will ask", and a present-but-empty `stack_config.cloudwatch`
(`{}`) means exactly that for all of them: a valid state, not an error.
Call out a persisted `region` that differs from the CLI's effective one
- the query targets the persisted value.

Add any `invalid_ignored` dotted names as degradations: the stored
value was invalid and was dropped. `stack_config` has no defaults behind
it, so a dropped value reads as not persisted - nothing silently took
its place.

Never echo: an access key, a session token, the SSO cache.

### Connection proof

```bash
python3 <Skills>/observability-cli-guides/scripts/cloudwatch-context.py check --profile <profile> --region <region> --log-group <log_group> --metrics-log-group <metrics_log_group>
```

Whole surface: `--profile`, `--region` (required), `--log-group`,
`--metrics-log-group` (each optional: given, proved to resolve;
omitted, skipped and said so), `--json`. Two parts: **identity** - `aws
sts get-caller-identity --profile <profile>` (needs no permission: a
success proves the credentials resolve and work); **targeting** -
`describe-log-groups` with each group as the prefix, the name matched
exactly. Output: `identity` (`ok`, `principal_type`, `account`, `arn`),
`targeting.<field>` (`ok`, retention and stored bytes, or `kind`,
`error`, `diagnosis`), `connected`. Exit 0 connected; 1 an identity
failure or a rights/network error, with the diagnosis saying what is
the user's to do - **the expired SSO token** (`identity-expired`: run
`aws sso login --profile <profile>`, a browser flow, displayed and never
run on the user's behalf), **a profile the CLI cannot find**
(`no-profile`: `aws configure list-profiles` enumerates what exists -
route to the switch), **no credentials at all** (`no-credentials`: an
SSO setup routinely has no `default` profile; persist the named one
rather than running the `aws login` the error suggests); 3 a persisted
group that does not resolve (a wrong value, not a connection problem:
route to the switch); 2 the CLI refused the command. Verified
2026-09-11: connected (an assumed-role principal, both groups); a
missing group at exit 3; a missing profile at exit 1 with its
diagnosis. The expired-token and no-credentials shapes are classified
from the CLI's documented messages and **unverified 2026-09-11** (the
session was valid throughout). Same rule as everything else here:
display the login command, never run it for the user, never echo an
access key.

### Change-request phrasing

- "persist log group <name> for cloudwatch"
- "clear the log group for cloudwatch"
- "use profile <name> for cloudwatch"
- "persist metrics log group <name> for cloudwatch"
- "use X-Ray group <name> for cloudwatch"
- "change backend to cloudwatch"

## What to persist

### What stack_config holds

`aws` is a **general-purpose** CLI. A profile says which credentials and
which region - it never says which log group holds the service's logs,
which log group its metrics arrive through, or which X-Ray group the
missions read. So `stack_config.cloudwatch` holds the targeting
information:

- `region` - the region the missions query, pinned separately from
  whatever the CLI's effective region happens to be.
- `profile` - the named `aws` CLI profile the missions run every command
  under (`--profile <name>` / `AWS_PROFILE`). SSO setups routinely have
  **no `default` profile at all** - without this, `aws sts
  get-caller-identity` fails with `NoCredentials` even though the CLI is
  configured and working under its named profile. Skip the field only
  when a `default` profile truly resolves on its own.
- `log_group` - the CloudWatch Logs group the missions read for
  **application logs**. When the services follow a convention rather
  than one fixed group, store the **naming pattern** instead
  (`/aws/ecs/<service>`, `/aws/lambda/<function>`) - a pattern the
  mission can expand beats a single group that only covers one service.
- `metrics_log_group` - the CloudWatch Logs group **metrics arrive
  through**, when the account exports metrics as Embedded Metric Format
  (EMF) log records (an OTel Collector's `awsemf`-style exporter is the
  common source) rather than writing directly to the CloudWatch metrics
  API. Keep it separate from `log_group` even though the two **may hold
  the same value** for a team that does not split them - persist
  whatever the account does. Omit entirely when metrics do not arrive
  via a log group.
- `xray` - the X-Ray group name the missions read the service graph
  under, when X-Ray is part of the picture and a group other than the
  default one is wanted. Omit it entirely otherwise.

Region names, profile names, group names, and patterns - all
identifiers, none of them a secret. Access keys, session tokens, and SSO
sessions stay where the `aws` CLI keeps them and are never copied into
the configuration.

### Where each value comes from

- `region` - `aws configure list --profile <profile>` prints the
  effective profile, region, and the **source** of each (env var, config
  file, IAM role). Take the region from there when it is the one the
  missions want; the source column also explains a surprising value.
- `profile` - `aws configure list-profiles` enumerates every named
  profile the identity has locally; `aws configure list` (or `--profile
  <name>` beside `aws sts get-caller-identity`) shows which one, if any,
  resolves without an explicit flag. Persist it whenever more than one
  profile exists or a bare call shows nothing set - never assume a
  `default` profile exists.
- `log_group` - `aws logs describe-log-groups --profile <profile>
  --region <region> --output json` lists what the identity can see
  (`logGroups[].logGroupName`); pick the group (or read the convention
  off the list) with the user.
- `metrics_log_group` - same listing; ask the user which group (if any)
  the account's metrics exporter writes EMF records to, distinctly from
  the application-logs group. A raw EMF record has an
  `_aws.CloudWatchMetrics` key at the top level - `cloudwatch-logs.py
  filter --log-group <candidate> --pattern '{ $._aws.CloudWatchMetrics[0].Namespace = "*" }'
  --limit 1 --since 15m` on a candidate confirms it is the metrics
  source (verified 2026-09-11: one event on the EMF group, none on the
  application group; the group given to `--log-group` prints as
  `<log_group>` whichever it is).
- `xray` - `aws xray get-groups --profile <profile> --region <region>
  --output json` lists the groups (`Groups[].GroupName`; `Default`
  always exists - verified 2026-09-11 as the only one on the account).
  Skip the field unless the user says traces come from X-Ray under a
  group of their own.

`aws sts get-caller-identity` is the identity check, not a source of
targeting values - it belongs to the connection proof above.

### What to ask the user

Ask for whatever `aws configure list` and the list commands above do not
settle, in one question:

> Which region and profile should the runs use? Which log group (or
> log-group naming pattern) holds application logs - and is there a
> separate one metrics arrive through as Embedded Metric Format? Is
> X-Ray part of it, and if so under which group?

Persist only what the user confirms. An unpersisted field reads "not
persisted, the mission will ask", which is a valid state - never guess a
log group from a service name, never assume `log_group` and
`metrics_log_group` are the same value without checking, and never
persist a region (or a profile) simply because it is what the CLI
defaults to today when the user has not said it is the right one.
