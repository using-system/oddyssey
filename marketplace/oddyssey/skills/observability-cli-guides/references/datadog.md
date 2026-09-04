# Datadog — Pup CLI

Official docs: https://docs.datadoghq.com/cli/ and https://github.com/DataDog/pup
(official `DataDog` GitHub org, not archived). Appending `.md` to any
`docs.datadoghq.com` page (e.g. `docs.datadoghq.com/cli.md`) and any
`raw.githubusercontent.com/DataDog/pup/main/...` URL returns raw markdown;
the plain `docs.datadoghq.com/...` and `github.com/.../blob/...` pages are
HTML/JS-rendered only.

**Resolved CLI story (verified 2026-08):** the query-capable Datadog CLI is
**Pup** (`github.com/DataDog/pup`) — a Rust CLI, distinct from the historical
Pup dashboard. It supports `metrics`, `logs`, and `traces`/`apm` query
commands directly from the terminal. The older **dogshell**/`dog` (from
`datadogpy`) is explicitly marked deprecated by Datadog's own docs, in favor
of Pup. **`datadog-ci`** is a real, current, actively maintained tool, but it
is **write-only** — it uploads CI/CD artifacts (test results, sourcemaps,
deployment markers, coverage) to Datadog and has no command to query metrics,
logs, or traces. For any signal, the raw HTTP API (`DD-API-KEY` /
`DD-APPLICATION-KEY` headers) is the underlying surface Pup wraps,
including from environments where Pup isn't installed.

## CLI binary

- **Binary**: `pup`
- **Detect**: `command -v pup`
- **Install**: `brew tap datadog-labs/pack && brew install
  datadog-labs/pack/pup`, a prebuilt release binary, or `cargo build
  --release` from source — see the Install row below (pup README link).

## Setup

| Topic | Link | What to do with it |
| --- | --- | --- |
| Pup CLI overview | [docs.datadoghq.com/cli.md](https://docs.datadoghq.com/cli.md) | What Pup is, install methods, usage examples, agent mode, global flags, env vars. Start here — it is Datadog's own page for the CLI (not a third-party tool). Cross-links to the fuller [README](https://raw.githubusercontent.com/DataDog/pup/main/README.md) and [command reference](https://raw.githubusercontent.com/DataDog/pup/main/docs/COMMANDS.md) in the repo. |
| Install (Homebrew / source / binary) | [pup README — Installation](https://raw.githubusercontent.com/DataDog/pup/main/README.md#installation) | `brew tap datadog-labs/pack && brew install datadog-labs/pack/pup`; `cargo build --release` from a git clone; or a prebuilt binary from [the latest GitHub release](https://github.com/DataDog/pup/releases/latest). Homebrew is the fastest path; source build needs Rust/Cargo. |
| Authentication | [pup README — Authentication](https://raw.githubusercontent.com/DataDog/pup/main/README.md#authentication) | Three methods, checked in this priority order: `DD_ACCESS_TOKEN` (bearer, highest priority) → OAuth2 tokens from `pup auth login` → `DD_API_KEY`+`DD_APP_KEY`. OAuth2 needs Dynamic Client Registration enabled on the site; falls back to API keys if not. Run `pup auth login` interactively (opens a browser) for day-to-day use; set `DD_API_KEY`/`DD_APP_KEY` for CI/non-interactive use. `pup auth status` / `pup auth test` verify the active credential — by their **output**, never their exit code: pup exits 0 even unauthenticated (`"authenticated": false` / `not set` in the report). |
| API and application keys | [API and application keys](https://docs.datadoghq.com/account_management/api-app-keys.md) | How to create `DD_API_KEY` (write access) and `DD_APP_KEY` (read access, required for query operations) in the Datadog UI. Needed before `pup auth login` can fall back to API-key auth, and before any raw curl call to a read endpoint. |
| Site / multi-org sessions | [pup README — Multiple sites and orgs](https://raw.githubusercontent.com/DataDog/pup/main/README.md#multiple-sites-and-orgs) | `DD_SITE` (default `datadoghq.com`; also `datadoghq.eu`, `us3`/`us5.datadoghq.com`, `ap1`/`ap2.datadoghq.com`, `ddog-gov.com`, or a vanity SSO host). Pup persists one session per named `--org`/`DD_ORG` and recalls its site automatically. Set `DD_SITE` (or `--site` at `pup auth login`) to the org's actual region before querying — reads silently target the wrong region otherwise. Use `pup auth list` to see every stored session's site/org/expiry. |
| Command reference | [docs/COMMANDS.md](https://raw.githubusercontent.com/DataDog/pup/main/docs/COMMANDS.md) | Full command index by domain, global flags (`--config`, `--site`, `--output`, `--jq`, `--read-only`), `--jq` filtering semantics. Explicitly notes it "may lag the source" — the live truth is `pup --help` or `pup agent schema`. Use for discovering flags per command; treat it as a starting point, not gospel — verify against `pup <domain> <action> --help` when a flag doesn't behave as documented (see Planning notes). |
| Dogshell/`dog` (deprecated) | [docs.datadoghq.com/extend/guide/dogshell.md](https://docs.datadoghq.com/extend/guide/dogshell.md) | Datadog's own page states: *"Dogshell is deprecated and has been replaced by Pup CLI, a comprehensive, AI-agent-ready CLI for interacting with Datadog APIs."* Do not use it for new work; it also only posts/manages resources (metrics post, events, monitors, downtimes) — it never had a metrics/logs/traces query surface. |
| `datadog-ci` (write-only, not a query tool) | [github.com/DataDog/datadog-ci](https://github.com/DataDog/datadog-ci), [CI Visibility getting started](https://docs.datadoghq.com/getting_started/ci_visibility.md) | Real and current, but out of scope here: it uploads JUnit/coverage/sourcemaps/deployment markers *to* Datadog from a pipeline. It has no subcommand that reads metrics, logs, or traces back out — don't reach for it when the task is "query production data." |

## Query by signal

| Signal | How | Link | Notes |
| --- | --- | --- | --- |
| Metrics | `pup metrics query --query=<v2-metric-query> --from=<t> --to=<t>` | [pup README examples](https://raw.githubusercontent.com/DataDog/pup/main/README.md) | v2 timeseries query, e.g. `avg:system.cpu.user{*}`, `sum:app.requests{env:prod} by {service}`. `--from`/`--to` accept `1h`/`30m`/`7d`, RFC3339, Unix ms, or `now`. |
| Metrics | `pup metrics search --query=<v1-metric-query> --from=<t> --to=<t>` | same | v1 query API; kept for compatibility (the underlying REST "Search metrics" op is marked deprecated in the [API reference](https://docs.datadoghq.com/api/latest/metrics.md#search-metrics) — prefer `metrics query`). |
| Metrics | `pup metrics list [--filter=<pattern>] [--tag-filter=<tags>]`, `pup metrics metadata get <name>`, `pup metrics tags list <name>` | same | Discovery commands: list active metric names, get type/unit/description metadata, list a metric's tags. |
| Metrics | REST API (what Pup wraps) | [Query timeseries points (v1)](https://docs.datadoghq.com/api/latest/metrics.md#query-timeseries-points), [Query across multiple products (v2)](https://docs.datadoghq.com/api/latest/metrics.md#query-timeseries-data-across-multiple-products) | `GET https://api.<site>/api/v1/query?query=...` with `DD-API-KEY`/`DD-APPLICATION-KEY` headers; the API behind `pup metrics`. |
| Traces / APM | `pup traces search --query=<span-query> [--from=<t>] [--to=<t>] [--limit=1..1000] [--sort=timestamp\|-timestamp] [--live] [--cursor=<c>]` | [pup source: TracesActions::Search](https://raw.githubusercontent.com/DataDog/pup/main/src/main.rs) (doc comment; not yet in a rendered doc page) | Searches individual spans (service, resource, duration, tags, trace IDs). `--live` pins the window end to now, hitting Datadog's live unsampled trace buffer instead of the indexed store — page backwards through it with `--cursor`. Requires OAuth2 `apm_read` scope, or API+APP keys. |
| Traces / APM | `pup traces aggregate --query=<span-query> --compute=<fn> [--group-by=<facet>] [--from=<t>] [--to=<t>]` | same | Statistical buckets, not individual spans: `count`, `avg(@duration)`, `percentile(@duration, 99)`, etc., optionally grouped by a facet like `service` or `resource_name`. |
| Traces / APM | `pup apm services list/stats/operations/resources`, `pup apm entities list`, `pup apm dependencies list`, `pup apm flow-map` | [docs/EXAMPLES.md](https://raw.githubusercontent.com/DataDog/pup/main/docs/EXAMPLES.md) | Service-level APM views (throughput/latency/error-rate stats, dependency graph) rather than raw span search — use alongside `traces search`/`traces aggregate`. |
| Traces / APM | REST API (what Pup wraps) | [Search spans](https://docs.datadoghq.com/api/latest/spans.md#search-spans), [Aggregate spans](https://docs.datadoghq.com/api/latest/spans.md#aggregate-spans) | `POST https://api.<site>/api/v2/spans/events/search`; same header auth as metrics. |
| Logs | `pup logs search --query=<q> [--from=<t>] [--to=<t>] [--limit=1..1000] [--index=<idx,...>] [--storage=auto\|indexes\|online-archives\|flex]` | [docs/COMMANDS.md](https://raw.githubusercontent.com/DataDog/pup/main/docs/COMMANDS.md) | v1 log search. Long lookback windows may need `--storage=flex` or `online-archives` for full retention. |
| Logs | `pup logs query --query=<q> [--from=<t>] [--to=<t>] [--limit] [--cursor] [--sort] [--storage] [--index] [--timezone]`, `pup logs list [--query=*] ...` | same | v2 search/list — `query` requires an explicit query, `list` defaults to `*`. |
| Logs | `pup logs aggregate --query=<q> --compute=<fn,...> [--group-by=<f,...>] [--interval=<dur>]` | same | Bucketed stats over logs (`count`, `avg(@duration)`, `percentile(@duration, 95)`, comma-separated for multiple computes); pass `--interval` (e.g. `5m`) to get a timeseries instead of scalar groups. |
| Logs | `pup logs patterns --query=<q> --pattern-field=<field> [--from] [--to] [--group-by]` | same | Clusters similar log messages by a field (e.g. `message`) — useful for triage before a targeted search. |
| Logs | REST API (what Pup wraps) | [Search logs (POST)](https://docs.datadoghq.com/api/latest/logs.md#search-logs-post) | `POST https://api.<site>/api/v2/logs/events/search`; same header auth. |

Concurrency — **not verified**: read commands issued concurrently
from one shell are the expected shape, and
`pup` read commands are stateless API calls sharing one credential,
so nothing in their design objects to it — but no Datadog account was
available to prove it (2026-09-04). Until a live check lands here,
treat a concurrent failure as a possible CLI limit before a backend
fault: rerun the failed commands serially once, and record which
shape answered.

## Planning notes

- Pup is young and fast-moving (README documents changes through v0.64.x as
  of this snapshot); its own docs warn `docs/COMMANDS.md` "may lag the
  source." Confirmed firsthand: `COMMANDS.md`'s command index omits `traces
  search`/`traces aggregate` even though the README's coverage table and the
  actual source (`src/commands/traces.rs`, `src/main.rs`) both implement
  them — when a documented command misbehaves, verify with `pup <domain>
  <action> --help` or `pup agent schema` before assuming the doc is right.
- Dogshell/`dog` is explicitly deprecated by Datadog (see the Setup table);
  do not recommend it for new query workflows even though it still ships in
  `datadogpy` — it also never had a metrics/logs/traces *query* surface, only
  posting/management commands.
- Profiling has no Pup command yet (`pup profiling` is an empty placeholder
  in the source). Datadog's own docs redirect profiling requests to the
  [Datadog MCP server](https://docs.datadoghq.com/mcp_server.md) instead —
  there is no CLI or simple curl one-liner documented for it here.
- `pup traces search`/`pup traces aggregate` explicitly require the OAuth2
  `apm_read` scope (or API+APP keys); `pup logs *` and `pup metrics *`
  commands only need default OAuth2 scopes or API+APP keys, with no extra
  scope called out in the docs — request `apm_read` up front if traces will
  be queried in an OAuth2 session.

## Configuration display

### Display

The Pup CLI's own session is the context: which site and org the
queries will hit.

- `pup auth list` — every stored session with its site, org, and
  expiry; the one the mission will use is the org/site pair the run
  targets (`--org`/`DD_ORG`, `--site`/`DD_SITE`).
- The credential **by name only**: which of `DD_ACCESS_TOKEN`, an
  OAuth2 session from `pup auth login`, or `DD_API_KEY` +
  `DD_APP_KEY` is set — never the value of any of them, never a
  partial or masked value. See the setup section earlier in this file
  for the priority order between the three and for the site list.

`stack_config.datadog` is expected **empty** — the CLI session already
names the site and org. Present-and-empty (`{}`) or missing both
display as "nothing persisted — the Pup session is the source".

Add any `invalid_ignored` dotted names as degradations: the stored
value was invalid and was dropped. `stack_config` has no defaults behind
it, so a dropped value reads as not persisted — nothing silently took
its place.

### Connection proof

`pup auth status` — the cheapest call that verifies the active
credential, per the setup section earlier in this file. But **the exit
code is not the signal**: pup exits 0 authenticated or not (verified on
pup 1.14.0 — `pup auth status` prints
`{"authenticated": false, "org": null, ...}` and exits 0;
`pup auth test` exits 0 while reporting
`API Key: not set`). Unlike the other backends' probes (`aws sts
get-caller-identity` exits 253, `dtctl auth whoami` exits 1), a shell
exit-code check on pup proves nothing. The proof is the **output**:
connected means the status JSON carries `"authenticated": true` —
that boolean is the sole authority. `pup auth test`'s `not set` lines
corroborate a missing API-key pair, but an OAuth or bearer session
leaves those keys unset while authenticated — never rule a failed
proof on `not set` alone. `"authenticated": false` is the failed
proof: stop and guide `pup auth login` or the API/app key setup;
never authenticate on the user's behalf.

Site mismatch is silent here: a read against the wrong region returns
empty rather than failing, so show the site even when the probe passes.

### Change-request phrasing

- "change backend to datadog"

## What to persist

### What stack_config holds

**Nothing.** `stack_config.datadog` is expected to stay empty, and an
empty entry is the correct final state of a switch to `datadog`.

The Pup CLI carries its own session, and that session is what names the
**site** (`datadoghq.com`, `datadoghq.eu`, `us3`, `us5`, `ap1`, …) and
the **org** the queries hit. Persisting a site or org here would
duplicate the session and diverge from it the moment the user logs in
elsewhere — while the CLI's own session is still what the query
actually uses.

### Where each value comes from

From the Pup session, read at use time:

- `pup auth list` — every stored session with its site, org, and
  expiry; the org/site pair a run targets is the one selected via
  `--org`/`DD_ORG` and `--site`/`DD_SITE`.

The credential is whichever of the documented mechanisms is in play — an
OAuth2 session from `pup auth login`, or the environment-variable
credentials the CLI reads. Refer to it **by name only** (which variable
is set, which login was used); never read, echo, mask, or persist a
value. The setup section earlier in this file owns the priority
order between them.

### What to ask the user

**Nothing about targeting.** Do not ask for the site, the org, the API
key, or the application key — the first two belong to the session and
the last two are secrets that never enter this configuration.

One thing is worth saying out loud after the switch, because it fails
quietly: a session pointed at the wrong site returns **empty results
rather than an error**. So confirm with the user that the session's site
is the region their data lives in, and let
`backend-configuration`'s `## Check` display it. That is a confirmation, not a
value to store.

Leave `stack_config.datadog` alone.
