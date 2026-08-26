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
| IAM Identity Center (SSO) login | [Configuring IAM Identity Center authentication](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html) | `aws configure sso` (interactive wizard: start URL, SSO region, account, role, profile name) writes a `[profile ...]` + `[sso-session ...]` block to `~/.aws/config`; then `aws sso login --profile <name>` (or `--sso-session <name>`) opens a browser and caches short-lived credentials under `~/.aws/sso/cache`. `aws sso logout` clears cached sessions. PKCE is the default flow since CLI 2.22.0; add `--use-device-code` for the older device-code flow. |
| `aws cloudwatch` command reference | [cloudwatch — AWS CLI reference](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/index.html) | Metrics and metric-alarm operations: `list-metrics`, `get-metric-data`, `get-metric-statistics`, `put-metric-alarm`, etc. Start here for anything metric-shaped. |
| `aws logs` command reference | [logs — AWS CLI reference](https://docs.aws.amazon.com/cli/latest/reference/logs/index.html) | CloudWatch Logs operations: log group/stream discovery, `filter-log-events`, and the Logs Insights query trio `start-query` / `get-query-results` / `stop-query`. |
| `aws xray` command reference | [xray — AWS CLI reference](https://docs.aws.amazon.com/cli/latest/reference/xray/index.html) | X-Ray trace search (`get-trace-summaries`), full trace retrieval (`batch-get-traces`), and service map (`get-service-graph`). |

## Query by signal

| Signal | How | Link | Notes |
| --- | --- | --- | --- |
| Metrics (discovery) | `aws cloudwatch list-metrics --namespace "AWS/EC2"` | [list-metrics](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/list-metrics.html) | `--namespace`/`--metric-name`/`--dimensions` are exact-match filters, up to 500 results per call (paginate with `--starting-token`). A metric with no data in the last two weeks won't be listed; a newly-created metric can take up to 15 minutes to appear. |
| Metrics (multi-metric / math) | `aws cloudwatch get-metric-data --metric-data-queries file://query.json --start-time 2024-09-29T22:10:00Z --end-time 2024-09-29T22:15:00Z` | [get-metric-data](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/get-metric-data.html) | Preferred over `get-metric-statistics` for anything beyond a single series: up to 500 `MetricDataQuery` entries per call, each a metric fetch, a Metrics Insights SQL-like query, or a math expression combining other queries in the same call. |
| Metrics (single series, simple) | `aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUUtilization --dimensions Name=InstanceId,Value=i-abcdef --start-time 2014-04-08T23:18:00Z --end-time 2014-04-09T23:18:00Z --period 3600 --statistics Maximum` | [get-metric-statistics](https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/get-metric-statistics.html) | `--period` must be a multiple of 60s; `--statistics` (`SampleCount, Average, Sum, Minimum, Maximum`, max 5) is mutually exclusive with `--extended-statistics` (percentiles). Max 1,440 datapoints per call — narrow the window or widen `--period` if you hit the limit. |
| Logs (discovery) | `aws logs describe-log-groups --log-group-name-prefix <prefix>` | [describe-log-groups](https://docs.aws.amazon.com/cli/latest/reference/logs/describe-log-groups.html) | Lists log groups (name, ARN, retention, stored bytes), ASCII-sorted by name. `--log-group-name-prefix` and `--log-group-name-pattern` are mutually exclusive. |
| Logs (simple filter) | `aws logs filter-log-events --log-group-name <name> --filter-pattern "<pattern>" --start-time <epoch-ms> --end-time <epoch-ms>` | [filter-log-events](https://docs.aws.amazon.com/cli/latest/reference/logs/filter-log-events.html) | Pattern-based search across streams in one log group, no aggregation — reach for Logs Insights below for anything needing `stats`/`parse`/joins. Paginated, up to 1&nbsp;MB or 10,000 events per page; `--start-time`/`--end-time` are epoch **milliseconds**, not seconds. |
| Logs (CloudWatch Logs Insights, query language) | `aws logs start-query --log-group-name <name> --start-time <epoch-s> --end-time <epoch-s> --query-string '<CWLI query>'` → poll `aws logs get-query-results --query-id <id>` | [start-query](https://docs.aws.amazon.com/cli/latest/reference/logs/start-query.html), [get-query-results](https://docs.aws.amazon.com/cli/latest/reference/logs/get-query-results.html), [query syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html) | Async: `start-query` returns a `queryId` immediately (`--start-time`/`--end-time` here are epoch **seconds**, unlike `filter-log-events`); poll `get-query-results` until `status` is `Complete` (also: `Scheduled, Running, Failed, Cancelled, Timeout, Unknown`) — a `Running`/`Scheduled` poll returns partial results. Queries auto-timeout after 60 minutes; up to 100 concurrent queries per account. `--query-language` defaults to `CWLI` (pipe-separated commands: `fields`, `filter`, `stats`, `sort`, `limit`, `parse`, `dedup`, `stats ... by bin()`, …) but also accepts `SQL` and `PPL`. |
| Traces (search) | `aws xray get-trace-summaries --start-time <epoch-s> --end-time <epoch-s> --filter-expression 'service("api.example.com")'` | [get-trace-summaries](https://docs.aws.amazon.com/cli/latest/reference/xray/get-trace-summaries.html) | Returns trace IDs + annotation summaries matching the filter, not full trace bodies — feed the IDs to `batch-get-traces` for detail. `--time-range-type` can key the search on `TraceId` (default), `Event`, or `Service`. |
| Traces (full detail) | `aws xray batch-get-traces --trace-ids <id1> <id2> ...` | [batch-get-traces](https://docs.aws.amazon.com/cli/latest/reference/xray/batch-get-traces.html) | Returns full segment/subsegment JSON per trace ID (duration, resources, exceptions, annotations). Does not work if the account has Transaction Search enabled — traces then aren't indexed in classic X-Ray and must be queried differently. |
| Traces (service map) | `aws xray get-service-graph --start-time <epoch-s> --end-time <epoch-s>` | [get-service-graph](https://docs.aws.amazon.com/cli/latest/reference/xray/get-service-graph.html) | The node/edge graph backing the X-Ray console's Service Map — use for a topology view rather than individual trace inspection. |
| Profiles | Not a CloudWatch signal — profiling lives in the separate Amazon CodeGuru Profiler service: `aws codeguruprofiler list-profiling-groups --include-description` then `aws codeguruprofiler get-profile --profiling-group-name <name> --period P1D --accept application/json <outfile>` | [codeguruprofiler CLI reference](https://docs.aws.amazon.com/cli/latest/reference/codeguruprofiler/index.html), [get-profile](https://docs.aws.amazon.com/cli/latest/reference/codeguruprofiler/get-profile.html), [list-profiling-groups](https://docs.aws.amazon.com/cli/latest/reference/codeguruprofiler/list-profiling-groups.html), [What is CodeGuru Profiler](https://docs.aws.amazon.com/codeguru/latest/profiler-ug/what-is-codeguru-profiler.html) | `get-profile` writes the aggregated profile to a positional `<outfile>`; pick the window with 1 or 2 of `--start-time`/`--end-time`/`--period` (ISO 8601, e.g. `P1DT1H1M1S`), max range **7 days**. `--accept` defaults to `application/x-amzn-ion` — pass `application/json` for a readable profile. `--max-depth` (1–10000) caps stack depth. Requires the CodeGuru Profiler agent in the application and a profiling group; supported runtimes are JVM languages and Python 3.6+. No `aws cloudwatch`/`aws logs`/`aws xray` command returns profiles. |

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
- CloudWatch Logs Insights (`start-query`/`get-query-results`) and
  `filter-log-events` use **different time units** for the same-named flags
  — `filter-log-events` wants epoch milliseconds, `start-query` wants epoch
  seconds. Easy to get wrong when scripting both against the same window.
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
