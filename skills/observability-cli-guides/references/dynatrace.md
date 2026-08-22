# Dynatrace — `dtctl` (+ Monaco, `dtcli`)

Official docs: https://docs.dynatrace.com/, https://developer.dynatrace.com/,
https://github.com/dynatrace-oss/dtctl
`docs.dynatrace.com` and `developer.dynatrace.com` pages are HTML-only (no
raw-markdown mirror found); the `dtctl` docs live as plain `.md` files in
its GitHub repo and are fetchable raw via
`raw.githubusercontent.com/dynatrace-oss/dtctl/main/docs/<file>.md`.

The user-mentioned name **`dtctl` is real** — it is an open-source,
kubectl-styled CLI published by Dynatrace itself under the `dynatrace-oss`
GitHub org, distinct from two older, narrower tools: `dt-cli` (PyPI package
`dt-cli`, Python module name `dtcli`) for signing/building/uploading
Extensions Framework 2.0 packages, and Monaco, a separate configuration-as-code
tool. There is no CLI that runs "raw DQL" other than `dtctl query`; absent
that, DQL is executed over the Grail Query REST API with `curl`.

## Setup

| Topic | Link | What to do with it |
| --- | --- | --- |
| `dtctl` install | [dtctl INSTALLATION.md](https://github.com/dynatrace-oss/dtctl/blob/main/docs/INSTALLATION.md) | `brew install dynatrace-oss/tap/dtctl`, or `curl -fsSL https://raw.githubusercontent.com/dynatrace-oss/dtctl/main/install.sh \| sh` (macOS/Linux), or download a release binary. Requires Go 1.24+ only if building from source. |
| `dtctl` auth & first query | [dtctl QUICK_START.md](https://github.com/dynatrace-oss/dtctl/blob/main/docs/QUICK_START.md) | OAuth (recommended): `dtctl auth login --context my-env --environment "https://<envid>.apps.dynatrace.com"`. Token-based: `dtctl config set-context ...` + `dtctl config set-credentials my-token --token "dt0s16.…"`. Verify with `dtctl auth whoami`. |
| `dtctl` required scopes | [dtctl TOKEN_SCOPES.md](https://github.com/dynatrace-oss/dtctl/blob/main/docs/TOKEN_SCOPES.md) | Per-operation scope list — `storage:logs:read`, `storage:metrics:read`, `storage:spans:read`, `storage:events:read`, plus `automation:workflows:*`, `document:documents:*`, `settings:*` for non-telemetry resources. Use to scope a token/OAuth client to least privilege. |
| Dynatrace Hub listing | [dtctl on Dynatrace Hub](https://www.dynatrace.com/hub/detail/dtctl/) | Dynatrace's own catalog entry for `dtctl`, plus the [launch blog post](https://www.dynatrace.com/news/blog/dtctl-the-dynatrace-observability-cli-thats-built-for-ai-agents-and-humans/) — use as corroboration that this is a Dynatrace-endorsed OSS tool, not a third-party guess. |
| API tokens vs. OAuth clients vs. platform tokens | [Dynatrace API — Tokens and authentication](https://docs.dynatrace.com/docs/dynatrace-api/basics/dynatrace-api-authentication) | Three credential kinds share a `dt0sNN.<public>.<secret>` shape: `dt0s01` classic API tokens (`Authorization: Api-Token …`), `dt0s02` OAuth2 clients, `dt0s16` platform tokens. Classic Environment APIs (e.g. Metrics API v2) take an API token; Grail/DQL and most platform APIs take an OAuth bearer token instead. |
| Create/manage an OAuth client | [OAuth clients](https://docs.dynatrace.com/docs/manage/identity-access-management/access-tokens-and-oauth-clients/oauth-clients) | Create a client in the account management UI, pick scopes up front (a minted token can only request a subset of them later) — needed before the client-credentials curl flow below will work. |
| Get an OAuth bearer token from the CLI (curl) | [Access platform APIs from outside](https://developer.dynatrace.com/develop/guides/access-platform-apis-from-outside/) | `curl --request POST 'https://sso.dynatrace.com/sso/oauth2/token' --data-urlencode 'grant_type=client_credentials' --data-urlencode 'client_id=…' --data-urlencode 'client_secret=…' --data-urlencode 'scope=storage:logs:read storage:metrics:read storage:spans:read'` → `access_token` (valid 300s), sent as `Authorization: Bearer …` on subsequent calls. |
| Extensions packaging CLI (`dt-cli`/`dtcli`) | [dynatrace-oss/dt-cli](https://github.com/dynatrace-oss/dt-cli) | For building/signing/uploading Extension Framework 2.0 packages only — not a query tool. Installed via `pip install dt-cli`. |
| Configuration as code (Monaco) | [Configuration as Code via Monaco](https://docs.dynatrace.com/docs/deliver/configuration-as-code/monaco), [Monaco CLI commands](https://docs.dynatrace.com/docs/deliver/configuration-as-code/monaco/monaco-cli-commands) | `monaco deploy`/`download`/`delete` manage dashboards, Settings 2.0 objects, workflows, etc. as YAML — it "can only manage configuration"; it has no command to query logs, metrics, or traces. |

## Query by signal

| Signal | How | Link | Notes |
| --- | --- | --- | --- |
| Logs | `dtctl query 'fetch logs \| filter status=="ERROR" \| limit 100'` | [dtctl QUICK_START.md](https://github.com/dynatrace-oss/dtctl/blob/main/docs/QUICK_START.md), [DQL data source commands](https://docs.dynatrace.com/docs/platform/grail/dynatrace-query-language/commands/data-source-commands) | `-o table\|json\|yaml\|csv`; pipe a `.dql` file with `-f queries/errors.dql`. Needs `storage:logs:read` (+ `storage:buckets:read`). No `dtctl` → curl POST to `/platform/storage/query/v1/query:execute` with the same DQL string as `{"query": "..."}`, `Authorization: Bearer <oauth token>`. |
| Metrics (DQL/Grail) | `dtctl query 'timeseries avg(builtin:host.cpu.usage), by:{dt.entity.host}'` | [DQL metric commands](https://docs.dynatrace.com/docs/platform/grail/dynatrace-query-language/commands/metric-commands), [DQL timeseries examples](https://docs.dynatrace.com/docs/analyze-explore-automate/metrics/dql-examples) | Metrics use the `timeseries` command, **not** `fetch metrics` — DQL's `fetch` covers logs/spans/bizevents/entities/events/problems but metrics are a dedicated command. Needs `storage:metrics:read`. |
| Metrics (classic Environment API, no OAuth needed) | `curl -H 'Authorization: Api-Token dt0s01.…' 'https://<envid>.live.dynatrace.com/api/v2/metrics/query?metricSelector=builtin:host.cpu.usage:avg&from=now-1h'` | [Metrics API v2](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/metric-v2), [GET data points](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/metric-v2/get-data-points) | Older, non-Grail API that predates DQL; simpler auth (plain API token, no OAuth dance) if a full DQL/Grail setup isn't wanted. `dtctl` does not wrap this API — it only speaks DQL. |
| Traces / spans | `dtctl query 'fetch spans \| filter dt.entity.service=="SERVICE-XYZ" \| limit 50'` | [DQL data source commands](https://docs.dynatrace.com/docs/platform/grail/dynatrace-query-language/commands/data-source-commands), [Advanced Tracing Analytics powered by Grail](https://docs.dynatrace.com/docs/observe/application-observability/distributed-tracing/advanced-tracing-analytics) | `fetch spans` exposes every span attribute stored in Grail (same DQL surface as logs). Needs `storage:spans:read`. No CLI/API exists to download a single trace's full waterfall outside the web UI — DQL span queries are the terminal-accessible path. |
| Raw DQL (curl, no `dtctl`) | `curl -X POST 'https://<envid>.apps.dynatrace.com/platform/storage/query/v1/query:execute' -H 'Authorization: Bearer …' -H 'Content-Type: application/json' -d '{"query":"fetch logs \| limit 10"}'` then poll `GET .../query:poll?request-token=…` | [Grail service](https://developer.dynatrace.com/develop/platform-services/services/grail-service/), [Query Grail data](https://docs.dynatrace.com/docs/platform/grail/dynatrace-grail/query-data) | Execution is async: `query:execute` returns a `request-token`; poll `query:poll` with it until the query finishes. Final results are only guaranteed available for **one minute** after completion — poll faster than that. This is the documented API alternative for any signal when `dtctl` isn't installed. |

## Planning notes

- `dtctl` is real, Dynatrace-published OSS (`dynatrace-oss/dtctl`, listed on
  Dynatrace Hub) but its own README describes it as under "active
  development" with possible bugs, and `dtctl serve http` is explicitly
  experimental (verified 2026-08). Treat it as a supported convenience
  layer over the platform API, not a versioned GA product with an SLA.
- Two auth mechanisms don't mix: the classic Environment API (Metrics API
  v2) takes a plain `Api-Token` (`dt0s01…`) header; Grail/DQL access
  (`dtctl query`, `query:execute`) requires an OAuth bearer token
  (`dt0s02` client-credentials or `dt0s16` platform token) with
  `storage:*:read` scopes plus bucket/table permissions on the target data.
  A token minted for one won't work for the other.
- Coverage gap: there is no dedicated CLI or API to pull one trace's full
  waterfall/JSON outside the web UI — `fetch spans` via DQL is the closest
  terminal-accessible substitute, returning individual span rows rather
  than an assembled trace tree.
- Monaco and `dt-cli`/`dtcli` are easy to confuse with `dtctl` by name but
  solve different problems: Monaco only pushes/pulls *configuration*
  (dashboards, settings, workflows) and cannot query telemetry at all;
  `dt-cli` only packages/signs *extensions* — neither touches logs,
  metrics, or traces.
