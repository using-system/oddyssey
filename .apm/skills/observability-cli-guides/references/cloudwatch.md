# AWS CloudWatch (+ X-Ray) — `aws`

Official docs: https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/,
https://docs.aws.amazon.com/cli/latest/reference/logs/,
https://docs.aws.amazon.com/cli/latest/reference/xray/
All `docs.aws.amazon.com` pages (CLI reference and user/developer guides
alike) are HTML-only — no raw-markdown query parameter or GitHub source
mirror was found; fetch and convert, don't guess at raw links.

## CLI binary

- **Binary**: `aws`
- **Detect**: `command -v aws`
- **Install**: `brew install awscli` (macOS) or the official AWS CLI v2
  installer per platform:
  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

## Setup

| Topic | Link | What to do with it |
| --- | --- | --- |
| Credentials & config precedence | [Configuring settings for the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html) | `aws configure` writes `~/.aws/credentials` and `~/.aws/config`; `aws configure --profile <name>` writes a named profile. Precedence (highest first): CLI flags → env vars → assume-role config → assume-role-with-web-identity → IAM Identity Center (SSO) config → credentials file → external credential process → config file → container/EC2 instance-profile credentials. |
| Authentication overview | [Authentication and access credentials for the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-authentication.html) | Landing page for every credential source (static keys, SSO, assume-role, env vars, external process, instance/container roles) — use it to pick the right mechanism for a given environment (laptop vs CI vs EC2/ECS). |
| Environment variables | [Configuring environment variables for the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html) | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_REGION`, `AWS_PROFILE` — use for containers/CI where a shared credentials file isn't wanted. |
| Current context & connection probe | [aws sts get-caller-identity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html) | `aws configure list` displays the effective profile, region, and credential source — the preflight's context display; `aws sts get-caller-identity` proves the credentials actually work (returns account and ARN, requires no permissions) — the cheapest connection probe. |
| IAM Identity Center (SSO) login | [Configuring IAM Identity Center authentication](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html) | `aws configure sso` (interactive wizard: start URL, SSO region, account, role, profile name) writes a `[profile ...]` + `[sso-session ...]` block to `~/.aws/config`; then `aws sso login --profile <name>` (or `--sso-session <name>`) opens a browser and caches short-lived credentials under `~/.aws/sso/cache`. `aws sso logout` clears cached sessions. PKCE is the default flow since CLI 2.22.0; add `--use-device-code` for the older device-code flow. A separate top-level `aws login` subcommand also exists on newer CLI builds (2.36.34), distinct from `aws sso login` — it's what a `NoCredentials` error suggests running, but check `aws configure list-profiles` for an already-working named profile first (the `backend-configuration`'s `## Check` skill's connection-proof section owns this failure mode): the everyday cause is a missing `default` profile, not a missing login. `aws sso login --profile <name>` is also the fix for an *expired* cached session (`Error when retrieving token from sso: Token has expired and refresh failed`), not only a missing one — that error means the profile itself works and only its short-lived token lapsed, and re-running the login refreshes it. |
| `aws cloudwatch` command reference | [cloudwatch — AWS CLI reference](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/index.html) | Metrics and metric-alarm operations: `list-metrics`, `get-metric-data`, `get-metric-statistics`, `put-metric-alarm`, etc. Start here for anything metric-shaped. |
| `aws logs` command reference | [logs — AWS CLI reference](https://docs.aws.amazon.com/cli/latest/reference/logs/index.html) | CloudWatch Logs operations: log group/stream discovery, `filter-log-events`, and the Logs Insights query trio `start-query` / `get-query-results` / `stop-query`. |
| `aws xray` command reference | [xray — AWS CLI reference](https://docs.aws.amazon.com/cli/latest/reference/xray/index.html) | X-Ray trace search (`get-trace-summaries`), full trace retrieval (`batch-get-traces`), and service map (`get-service-graph`). |

## Reading aws output

Verified live (`aws-cli/2.36.34`, 2026-08; the next three against
`aws-cli/2.36.36`, 2026-09; the last two against `aws-cli/2.36.37`,
2026-09-04) — traps that cost real missions retries:

- **`-o` is not accepted as a short form of `--output`** on this build —
  `aws logs describe-log-groups ... -o table` fails with `Unknown
  options: -o, table`; use the long `--output json|text|table|yaml`
  flag.
- **Auto-pagination re-applies `--query`/`--output text` (or `table`) to
  EACH page**, not once to the aggregated result. Every listing/search
  command in the table below (`list-metrics`, `describe-log-groups`,
  `filter-log-events`, `get-trace-summaries`, ...) paginates by default.
  A scripted `VAR=$(aws ... --query 'X[0].Id' --output text)` against a
  multi-page result silently returns a **multi-line string** — one line
  per page, with the literal word `None` on any page where the filtered
  path doesn't resolve. Verified: this broke a follow-up `batch-get-traces
  --trace-ids "$VAR"` call with an opaque `ValidationException` about the
  trace ID's length constraint, nothing pointing back at pagination as
  the cause. Add `--no-paginate` (or capture full `--output json` and
  filter client-side) whenever a script captures a `--query`-filtered
  scalar this way.
- **`--no-paginate` is incompatible with every pagination argument,
  `--max-items` included** — `aws logs filter-log-events ... --max-items
  3 --no-paginate` fails with `ParamValidation: Cannot specify
  --no-paginate along with pagination arguments: --max-items`. So the
  `--no-paginate` fix above can't be combined with `--max-items`: drop
  `--max-items` and cap with the command's own limit flag instead
  (`filter-log-events --limit`, which composes with `--no-paginate`
  fine); for commands without a native limit flag (`list-metrics`,
  `get-trace-summaries`, ...), capture the full `--output json` and
  truncate client-side, per the previous bullet.
- **The `--dimensions Name=,Value=` shorthand can't parse `{}` in a
  value** — OTel's `http.route` convention routinely carries `{param}`
  placeholders (`/orders/{order_id}`), and the shorthand parser dies on
  the brace: `ParamValidation: Error parsing parameter '--dimensions':
  Expected: ',', received: '}'`. Working form: `--dimensions
  file://dims.json` with a JSON array of `{"Name": ..., "Value": ...}`
  objects — the same braces value then queries fine.
- **`--extended-statistics` (percentiles) silently returns empty on
  EMF-ingested metrics.** OTel-Collector-style EMF exporters write
  histogram metrics as pre-aggregated `StatisticSet` values
  (`Min`/`Max`/`Sum`/`SampleCount`), and CloudWatch cannot compute
  percentiles from a statistic set — it needs raw, unsummarized
  datapoints (which EMF can also carry, just not for these) — so
  `get-metric-statistics ... --extended-statistics p95` returns
  `"Datapoints": []` with exit 0, indistinguishable from a wrong time
  window or missing permissions. For EMF-derived metrics this is the
  common case, not an edge case: before concluding "no data",
  cross-check with a plain `--statistics` call on the same
  series/window — data there plus an empty extended result means the
  storage format, not the query, is the limit. The percentiles then
  come from X-Ray, not CloudWatch metrics (verified 2026-09-04): every
  `get-trace-summaries` summary carries `Duration` (seconds, 1 ms
  resolution) — compute p50/p95/p99 client-side over the summaries of
  the window and filter; and `get-service-graph` returns a
  `ResponseTimeHistogram` per client→server edge (bucketed, enough for
  a distribution check). Neither needs the raw datapoints EMF does
  not carry.
- **[`describe-log-streams`](https://docs.aws.amazon.com/cli/latest/reference/logs/describe-log-streams.html)
  `lastEventTimestamp` is not a freshness signal** — it is eventually
  consistent (the command reference says so)
  and lags the newest record by minutes (verified 2026-09-04: 12
  minutes behind on a stream written every second), so read alone it
  says "the pipeline stopped" on a pipeline that is writing. For "is
  telemetry still arriving", run a Logs Insights `stats
  max(@timestamp)` over the group (or `filter-log-events` on the last
  minute), never the stream listing.

## Query by signal

| Signal | How | Link | Notes |
| --- | --- | --- | --- |
| Metrics (discovery) | `aws cloudwatch list-metrics --namespace "AWS/EC2"` | [list-metrics](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/list-metrics.html) | `--namespace`/`--metric-name`/`--dimensions` are exact-match filters, up to 500 results per call (paginate with `--starting-token`). A metric with no data in the last two weeks won't be listed; a newly-created metric can take up to 15 minutes to appear. Metrics commonly arrive here via Embedded Metric Format (EMF) log records rather than a direct metrics-API write — see Planning notes. |
| Metrics (multi-metric / math) | `aws cloudwatch get-metric-data --metric-data-queries file://query.json --start-time 2024-09-29T22:10:00Z --end-time 2024-09-29T22:15:00Z` | [get-metric-data](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/get-metric-data.html) | Preferred over `get-metric-statistics` for anything beyond a single series: up to 500 `MetricDataQuery` entries per call, each a metric fetch, a Metrics Insights SQL-like query, or a math expression combining other queries in the same call. |
| Metrics (single series, simple) | `aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUUtilization --dimensions Name=InstanceId,Value=i-abcdef --start-time 2014-04-08T23:18:00Z --end-time 2014-04-09T23:18:00Z --period 3600 --statistics Maximum` | [get-metric-statistics](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/get-metric-statistics.html) | `--period` must be a multiple of 60s; `--statistics` (`SampleCount, Average, Sum, Minimum, Maximum`, max 5) is mutually exclusive with `--extended-statistics` (percentiles). Max 1,440 datapoints per call — narrow the window or widen `--period` if you hit the limit. |
| Logs (discovery) | `aws logs describe-log-groups --log-group-name-prefix <prefix>` | [describe-log-groups](https://docs.aws.amazon.com/cli/latest/reference/logs/describe-log-groups.html) | Lists log groups (name, ARN, retention, stored bytes), ASCII-sorted by name. `--log-group-name-prefix` and `--log-group-name-pattern` are mutually exclusive. |
| Logs (simple filter) | `aws logs filter-log-events --log-group-name <name> --filter-pattern "<pattern>" --start-time <epoch-ms> --end-time <epoch-ms>` | [filter-log-events](https://docs.aws.amazon.com/cli/latest/reference/logs/filter-log-events.html) | Pattern-based search across streams in one log group, no aggregation — reach for Logs Insights below for anything needing `stats`/`parse`/joins. Paginated, up to 1&nbsp;MB or 10,000 events per page; `--start-time`/`--end-time` are epoch **milliseconds**, not seconds. An OTel Collector's log exporter commonly writes the whole OTel log record as one JSON body per event (`trace_id`, `span_id`, `resource.service.name`, ...) rather than plain text — see Planning notes for a Logs Insights `parse` example. |
| Logs (CloudWatch Logs Insights, query language) | `aws logs start-query --log-group-name <name> --start-time <epoch-s> --end-time <epoch-s> --query-string '<CWLI query>'` → poll `aws logs get-query-results --query-id <id>` | [start-query](https://docs.aws.amazon.com/cli/latest/reference/logs/start-query.html), [get-query-results](https://docs.aws.amazon.com/cli/latest/reference/logs/get-query-results.html), [query syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html) | Async: `start-query` returns a `queryId` immediately (`--start-time`/`--end-time` here are epoch **seconds**, unlike `filter-log-events`); poll `get-query-results` until `status` is `Complete` (also: `Scheduled, Running, Failed, Cancelled, Timeout, Unknown`) — a `Running`/`Scheduled` poll returns partial results. Queries auto-timeout after 60 minutes; up to 100 concurrent queries per account. `--query-language` defaults to `CWLI` (pipe-separated commands: `fields`, `filter`, `stats`, `sort`, `limit`, `parse`, `dedup`, `stats ... by bin()`, …) but also accepts `SQL` and `PPL`. |
| Traces (search) | `aws xray get-trace-summaries --start-time <epoch-s> --end-time <epoch-s> --filter-expression 'service("api.example.com")'` | [get-trace-summaries](https://docs.aws.amazon.com/cli/latest/reference/xray/get-trace-summaries.html) | Returns trace IDs + annotation summaries matching the filter, not full trace bodies — feed the IDs to `batch-get-traces` for detail. `--time-range-type` can key the search on `TraceId` (default), `Event`, or `Service`. The filter-expression vocabulary is a fixed set of reserved fields and functions — `http.status`, `http.method`, `http.url`, `responsetime`, `error`/`fault`/`throttle`, `annotation[<key>]` for custom annotations (the square brackets are mandatory when the key contains dots — which OTel-derived keys routinely do), `service("name")`, `duration`, ... ([full syntax](https://docs.aws.amazon.com/xray/latest/devguide/xray-console-filters.html)) — not OTel semconv attribute names: an invented-by-analogy name (`responsecode("404")`) fails with `InvalidRequestException ... Invalid input symbol` pointing at a byte offset, nothing saying "unknown field". Verified working form for status filtering: `http.status = 404`. `StartTime`/`ApproximateTime` render in the machine's **local offset** (`2026-09-04T22:24:49+02:00`), not UTC, while every log timestamp is UTC — convert with `date -u` or a timezone-aware parser before bucketing, never by string prefix; `MatchedEventTime` is `null` unless the search runs with `--time-range-type Event` (verified 2026-09-04). |
| Traces (full detail) | `aws xray batch-get-traces --trace-ids <id1> ... <id5>` (at most **5** IDs per call — a sixth fails with `InvalidRequestException: Exceeding maximum query size: 5`, verified 2026-09-04; batch and loop) | [batch-get-traces](https://docs.aws.amazon.com/cli/latest/reference/xray/batch-get-traces.html) | Returns full segment/subsegment JSON per trace ID (duration, resources, exceptions, annotations). Does not work if the account has Transaction Search enabled — traces then aren't indexed in classic X-Ray and must be queried differently. |
| Traces (service map) | `aws xray get-service-graph --start-time <epoch-s> --end-time <epoch-s>` | [get-service-graph](https://docs.aws.amazon.com/cli/latest/reference/xray/get-service-graph.html) | The node/edge graph backing the X-Ray console's Service Map — use for a topology view rather than individual trace inspection. |
| Profiles | Not a CloudWatch signal — profiling lives in the separate Amazon CodeGuru Profiler service: `aws codeguruprofiler list-profiling-groups --include-description` then `aws codeguruprofiler get-profile --profiling-group-name <name> --period P1D --accept application/json <outfile>` | [codeguruprofiler CLI reference](https://docs.aws.amazon.com/cli/latest/reference/codeguruprofiler/index.html), [get-profile](https://docs.aws.amazon.com/cli/latest/reference/codeguruprofiler/get-profile.html), [list-profiling-groups](https://docs.aws.amazon.com/cli/latest/reference/codeguruprofiler/list-profiling-groups.html), [What is CodeGuru Profiler](https://docs.aws.amazon.com/codeguru/latest/profiler-ug/what-is-codeguru-profiler.html) | `get-profile` writes the aggregated profile to a positional `<outfile>`; pick the window with 1 or 2 of `--start-time`/`--end-time`/`--period` (ISO 8601, e.g. `P1DT1H1M1S`), max range **7 days**. `--accept` defaults to `application/x-amzn-ion` — pass `application/json` for a readable profile. `--max-depth` (1–10000) caps stack depth. Requires the CodeGuru Profiler agent in the application and a profiling group; supported runtimes are JVM languages and Python 3.6+. No `aws cloudwatch`/`aws logs`/`aws xray` command returns profiles. |

`aws logs`, `aws cloudwatch` and `aws xray` read commands are **safe to
run concurrently against one profile**: backgrounded in one shell
call, they share the SSO credential cache without contention — a
`describe-log-groups`, two `filter-log-events`, a `list-metrics`, a
`get-trace-summaries` and a `get-service-graph` all exited 0 with
their data in 11.0 s against 13.0 s serial, the slowest call
(`get-trace-summaries` over six hours, ~40 K summaries) bounding both
(verified 2026-09-04, aws-cli 2.36.37, an account carrying real logs,
metrics and traces).

## Planning notes

- A trace/span in X-Ray is a **segment** (one service's work in the request)
  with nested **subsegments** (instrumented sub-calls: SDK, HTTP, SQL
  clients); a trace ID groups all segments for one end-to-end request. This
  is the AWS analogue of the request/dependency correlation Application
  Insights does via `operation_Id` (per the fetched X-Ray console-traces
  page, verified 2026-08).
- `get-metric-data` is the documented preference over `get-metric-statistics`
  for anything beyond one metric/no math — higher throughput per call (500
  queries vs. 1,440 datapoints) and native math-expression support; treat
  `get-metric-statistics` as the simple/legacy path.
- **Metrics commonly arrive via a CloudWatch Logs log group, not a direct
  metrics-API write.** An OTel Collector's `awsemf`-style exporter (or any
  Embedded Metric Format producer) writes metrics as JSON log records —
  each carrying an `_aws.CloudWatchMetrics` block naming the namespace,
  dimension sets, and metric definitions — into a log group; CloudWatch
  auto-extracts them into `aws cloudwatch list-metrics`/`get-metric-data`
  from there (verified: the raw EMF JSON in the log group and the
  extracted namespace metrics agree). Reading the raw log group directly
  (via Logs Insights) is a valid, sometimes-earlier path to the same data
  — useful when extraction lags or the exact dimension sets a service
  emits need inspecting.
- **EMF dimension sets fan out into many CloudWatch metrics.** Each EMF
  record's `Dimensions` array can declare several dimension-set variants
  for the same metric name, and CloudWatch materializes one metric series
  per variant — `list-metrics --namespace <ns>` can return many entries
  for what is conceptually one metric, each with a different dimension
  combination. A real cardinality/cost consideration when a service emits
  high-cardinality attributes (status codes, routes, ...) as EMF
  dimensions.
- **Cumulative-temporality metrics make statistics roll-ups silently
  meaningless for rate/count questions.** OTel's default metric
  temporality is cumulative, and when the export pipeline forwards
  those values unchanged, each EMF push carries the total count/sum
  **since process start**, not a delta for that push interval. Not
  every pipeline does — some convert to deltas before writing EMF — so
  detect before trusting either path: read a few consecutive raw EMF
  records for one series and check whether the value grows
  monotonically across pushes and whether its magnitude exceeds any
  plausible per-interval count (verified: `Count` rose 311129 → 313221
  over 30 consecutive pushes on a cumulative pipeline — hundreds of
  thousands, for a series receiving ~1 request/second). On cumulative
  pushes, `get-metric-statistics`/`get-metric-data` roll-ups spanning
  more than one push interval sum already-cumulative snapshots into a
  number with no operational meaning — no error, no warning, a
  normal-looking result shape (verified: a service running at ~1.8
  req/s showed a `SampleCount` of ~2.4 million per 5-minute `--period
  300` bucket). For a rate or count over a window, query the raw EMF
  records via Logs Insights and diff the cumulative values across the
  window's edges instead — verified working form (per-dimension deltas
  from two independent exporters of the same traffic, client and
  server side, agreed within 0.5%):
  ``stats latest(`http.server.request.duration.Count`) -
  earliest(`http.server.request.duration.Count`) as delta by
  `http.request.method`, `http.response.status_code`, `http.route` ``
  — grouped by
  **every dimension field the series carries** — a grouping coarser than
  the full dimension set folds distinct series together and yields
  garbage, routinely *negative*, deltas (verified: omitting `http.route`
  folded two routes into one group and returned -165k for a positive
  count). A mid-window process restart resets the cumulative counter to
  zero, which an edge diff reads as a traffic drop — also qualify the
  grouping by the emitting process, and **probe the field first**: an
  EMF pipeline may carry no resource fields at all (verified
  2026-09-04: `` stats sum(ispresent(`resource.service.name`)),
  sum(ispresent(`resource.service.instance.id`)), count() `` → `0 /
  0 of 10080` on the metrics group, while the log group's records all
  carried the instance id), and grouping by an absent field does not
  error — every record lands in one null group, the delta computes,
  and nothing says the guard did nothing. So: `ispresent()` on the
  resource fields as the first step; qualify by
  `resource.service.instance.id` when present, else by the log stream
  when instances map to streams, else attribute the series through the
  log records' instance id and check monotonicity across consecutive
  pushes as the restart guard; then sum the per-epoch deltas to recover
  the window total (verified: per-route counts attributed through the
  logs' instance id agreed with X-Ray trace counts within 0.5 %).
- CloudWatch Logs Insights (`start-query`/`get-query-results`) and
  `filter-log-events` use **different time units** for the same-named flags
  — `filter-log-events` wants epoch milliseconds, `start-query` wants epoch
  seconds. Easy to get wrong when scripting both against the same window.
- **JSON-bodied log records are auto-discovered as top-level fields.**
  When an OTel Collector exporter writes the whole log record as one
  JSON body, CloudWatch Logs Insights already exposes `trace_id`,
  `span_id`, `resource.service.name`, etc. as queryable fields — no
  `parse` needed: `fields @timestamp, trace_id, span_id,
  resource.service.name | filter ispresent(trace_id)` correlates a log
  line to its trace directly, the AWS analogue of Application Insights'
  `operation_Id` join. Reach for `parse @message '"trace_id":"*"' as
  trace_id` only for a shape CWLI doesn't already auto-expose — and
  never re-list a `parse`-created field in a downstream `fields`
  (renaming the alias doesn't help): `MalformedQueryException: Ephemeral
  field is already defined`.
- **Logs Insights regex literals are valid in `parse` and `filter …
  like /…/` only** — `replace()` takes plain strings, and
  `fields replace(path, /\/orders\/[0-9]+/, "/orders/{id}") as route`
  fails with `MalformedQueryException: token recognition error at:
  '\'`, an error that points at a byte, not at the rule (verified
  2026-09-04). Route normalization — the query every per-route
  analysis needs here, since `http.route` is not indexed in X-Ray
  annotations and the access-log body carries the raw path — goes
  through a chained `parse` with named groups, then `stats … by` the
  groups: `parse path /^(?<route>\/[a-z]+)(\/[0-9]+)?(?<tail>\/[a-z]+)?$/
  | stats count() as n by method, route, tail, status`.
- `batch-get-traces` explicitly does not work once Transaction Search is
  enabled on the account (traces stop being indexed in classic X-Ray) — a
  quirk worth checking for before assuming this path works in a given
  account.
- Profiles are not part of CloudWatch or X-Ray: continuous profiling is
  Amazon CodeGuru Profiler, a separate service with its own `aws
  codeguruprofiler` command group, its own agent in the application, its
  own profiling groups, and JVM/Python-only runtime support. If the account
  has no profiling group, profiles are a genuine telemetry gap on this
  backend — say so rather than substituting CPU metrics for them.
- Auth scope: SSO/Identity Center credentials are short-lived and cached
  per `sso-session`; automation (CI, long-running agents) should prefer a
  static IAM user, assumed role, or instance/container role over an
  interactive `aws sso login` flow that a human must periodically refresh.

## Configuration display

### Display

Two sources, labelled per line — the CLI's effective credentials and
the persisted targeting values.

**If `stack_config.cloudwatch.profile` is persisted, run every command
below (display and connection proof alike) with `--profile <profile>`**
— a bare call answers for whatever profile happens to resolve without a
flag, which on an SSO setup with no `default` is routinely none at all,
reporting a degradation on an account that is actually configured and
working.

From the `aws` CLI:

- `aws sts get-caller-identity` — the account id and the caller ARN
  (which identity the queries run as).
- `aws configure list` — the effective profile, region, and where each
  came from (env, config file, IAM role). Show the source column: a
  region coming from an env var is the usual explanation for queries
  hitting the wrong one.

On an SSO profile whose cached token has expired, `aws configure list
--profile <name>` itself errors (`Error when retrieving token from sso:
Token has expired and refresh failed`, exit 255) while still printing a
partial table — the display step failing this way is not a separate
problem, it is the same auth failure the connection proof below
diagnoses, surfacing one step earlier. Carry on to the connection
proof's expired-token guidance rather than treating the display as
broken.

From `stack_config.cloudwatch` (per `odd_config_get`):

- `region` — the region the mission queries, when pinned separately
  from the CLI's effective one.
- `profile` — the named `aws` CLI profile the mission runs under, when
  no `default` profile resolves on its own (the SSO norm).
- `log_group` — the CloudWatch Logs group the mission reads for
  application logs.
- `metrics_log_group` — the CloudWatch Logs group metrics arrive
  through as Embedded Metric Format, when the account exports them that
  way rather than writing directly to the CloudWatch metrics API. May
  equal `log_group`, may not — display both, never assume one covers
  the other.
- `xray` — the X-Ray context values the mission needs (group or
  sampling target), when persisted.

Every field the user did not persist is listed as "not persisted — the
mission will ask", and a present-but-empty `stack_config.cloudwatch`
(`{}`) means exactly that for all of them: a valid state, not an error.
Call out a persisted `region` that differs from the CLI's effective
one — the query targets the persisted value.

Add any `invalid_ignored` dotted names as degradations: the stored
value was invalid and was dropped. `stack_config` has no defaults behind
it, so a dropped value reads as not persisted — nothing silently took
its place.

### Connection proof

`aws sts get-caller-identity --profile <profile>` when
`stack_config.cloudwatch.profile` is persisted (see Display above),
plain `aws sts get-caller-identity` otherwise. It needs no permissions
and returns the account and ARN, so a success is proof the credentials
resolve and work.

On failure, check the single most likely real-world cause **first**: no
`default` profile resolves, even though a named one is fully configured
and working. `aws configure list-profiles` enumerates what exists
locally; retry the identity check with `--profile <name>` (or `export
AWS_PROFILE=<name>`) before concluding nothing is configured — an
error naming `NoCredentials` and suggesting `aws login` reads like "not
set up at all" but is routinely just "no default among the profiles
that do exist," even when there's only the one. Only after that comes
up empty is it a genuine stop-and-guide (profile creation, SSO login,
env vars) — never run the login for the user, never echo an access key.

A second, distinct failure family: the profile is correctly persisted
and correctly configured, but its cached SSO token has expired. The
error reads `Error when retrieving token from sso: Token has expired
and refresh failed` — not `NoCredentials` — and the fix is different
too: guide the user to run `aws sso login --profile <name>` (an
interactive browser flow) — not the retry-with-`--profile` step above
(the flag is already applied here), and not the `aws login` subcommand
a `NoCredentials` error suggests. Same
rule as everything else here: display the command, never run the login
on the user's behalf.

### Change-request phrasing

- "persist log group <name> for cloudwatch"
- "clear the log group for cloudwatch"
- "use profile <name> for cloudwatch"
- "persist metrics log group <name> for cloudwatch"
- "change backend to cloudwatch"

## What to persist

### What stack_config holds

Same rationale as Azure Monitor: `aws` is a **general-purpose** CLI. A
profile says which credentials and which region — it never says which
log group holds the service's logs, which log group its metrics arrive
through, or which X-Ray group the missions read. So `stack_config.cloudwatch`
holds the targeting information:

- `region` — the region the missions query, pinned separately from
  whatever the CLI's effective region happens to be.
- `profile` — the named `aws` CLI profile the missions run every command
  under (`--profile <name>` / `AWS_PROFILE`). SSO setups routinely have
  **no `default` profile at all** — without this, `aws sts
  get-caller-identity` fails with `NoCredentials` even though the CLI is
  genuinely configured and working under its named profile. Skip the
  field only when a `default` profile truly resolves on its own.
- `log_group` — the CloudWatch Logs group the missions read for
  **application logs**. When the services follow a convention rather
  than one fixed group, store the **naming pattern** instead
  (`/aws/ecs/<service>`, `/aws/lambda/<function>`) — a pattern the
  mission can expand beats a single group that only covers one service.
- `metrics_log_group` — the CloudWatch Logs group **metrics arrive
  through**, when the account exports metrics as Embedded Metric Format
  (EMF) log records (an OTel Collector's `awsemf`-style exporter is the
  common source) rather than writing directly to the CloudWatch metrics
  API. Good practice keeps this separate from `log_group` even though
  the two **may hold the same value** for a team that doesn't split
  them — persist whatever the account actually does, don't assume one
  group serves both. Omit entirely when metrics don't arrive via a log
  group (i.e. nothing to extract, `list-metrics` is already the whole
  story).
- `xray` — the X-Ray group or context the missions use, when X-Ray is
  part of the picture. Omit it entirely when it is not.

Region names, profile names, group names, and patterns — all
identifiers, none of them a secret. Access keys, session tokens, and SSO
sessions stay where the `aws` CLI keeps them and are never copied into
the configuration.

### Where each value comes from

- `region` — `aws configure list` prints the effective profile, region,
  and the **source** of each (env var, config file, IAM role). Take the
  region from there when it is the one the missions want; the source
  column is also what explains a surprising value.
- `profile` — `aws configure list-profiles` enumerates every named
  profile the identity has locally; `aws configure list` (or `--profile
  <name>` beside `aws sts get-caller-identity`) shows which one, if any,
  currently resolves without an explicit flag. Persist it whenever more
  than one profile exists or `aws configure list` shows nothing set for
  a bare (no-flag) call — never assume a `default` profile exists.
- `log_group` — `aws logs describe-log-groups --query
  'logGroups[].logGroupName'` lists what the identity can actually see;
  pick the group (or read the convention off the list) with the user.
- `metrics_log_group` — same listing command as `log_group`; ask the
  user which group (if any) the account's metrics exporter writes EMF
  records to, distinctly from the application-logs group. A raw EMF
  record has an `_aws.CloudWatchMetrics` key at the top level — grep a
  sample event for it to confirm a candidate group is actually the
  metrics source, don't guess from the name alone.
- `xray` — take the group-listing command from `aws xray help`, never
  from memory. Skip the field entirely unless the user says traces come
  from X-Ray.

`aws sts get-caller-identity` is the identity check, not a source of
targeting values — it belongs to the connection proof in
`backend-configuration`'s `## Check`.

### What to ask the user

Ask for whatever `aws configure list` and the list commands above do not
settle, in one question:

> Which region and profile should the runs use? Which log group (or
> log-group naming pattern) holds application logs — and is there a
> separate one metrics arrive through as Embedded Metric Format? Is
> X-Ray part of it, and if so which group?

Persist only what the user confirms. An unpersisted field reads "not
persisted, the mission will ask", which is a valid state — never guess a
log group from a service name, never assume `log_group` and
`metrics_log_group` are the same value without checking, and never
persist a region (or a profile) simply because it is what the CLI
defaults to today when the user has not said it is the right one.
