# Grafana — gcx

Official docs: https://github.com/grafana/gcx (source, README, `docs/`) and
https://grafana.com/docs/grafana-cloud/as-code/observability-as-code/grafana-cli/gcx/
(published site)
`raw.githubusercontent.com/grafana/gcx/main/...` links return raw markdown;
`grafana.com/docs/...` and `github.com/.../blob/...` links are HTML-rendered
only. The CLI command reference (`docs/reference/cli/*.md`) exists only in
the repo — it is not mirrored on the published site.

gcx works against **any Grafana 12+**: Grafana Cloud, Enterprise, and OSS,
including the local oddyssey stack. It authenticates over the Grafana REST
API, so on-prem and Cloud differ only in the stack entry you configure
(`org-id` for on-prem vs `stack-id`/OAuth for Cloud) — every query command
below is identical either way.

## CLI binary

- **Binary**: `gcx`
- **Detect**: `command -v gcx` (non-empty path = installed; `which -a gcx`
  flags duplicate installs)
- **Install**: `brew install gcx`, or the official install script /
  prebuilt binaries — see the Install row below (installation.md link).

## Setup

| Topic | Link | What to do with it |
| --- | --- | --- |
| Install | [installation.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/sources/installation.md) | Quick-install script (`curl \| sh`), Homebrew (`brew install gcx`, or the `grafana/grafana/gcx` tap to build from source), prebuilt binaries, `go install github.com/grafana/gcx/cmd/gcx@latest`. Pick one method only — running two leaves two binaries on `PATH`; use `which -a gcx` to find duplicates. Homebrew installs avoid the macOS Gatekeeper `killed: 9` issue that manually downloaded binaries hit. |
| Configure / contexts | [configuration.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/sources/configuration.md) | How `gcx` layers config (system → user `$HOME/.config/gcx/config.yaml` → repo `.gcx.yaml`), the four auth methods (OAuth, service-account token, basic auth, mTLS), and `gcx config set/check/view/list-contexts/use-context`. Use this to define a named context per Grafana instance (`stacks.<name>.grafana.server`, `.org-id` for on-prem, `.token`/`.user`+`.password`) and switch with `gcx config use-context`. Run `gcx config check` (optionally `--context <name>`) as a connectivity/auth gate. |
| Configuration file schema | [reference/configuration](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/configuration/index.md) | Full annotated YAML schema: `stacks`, `cloud`, `contexts`, `contexts.<name>.datasources.<kind>` (default datasource UID per signal), `diagnostics`. Consult when hand-editing a config/`.gcx.yaml` file instead of using `gcx config set`, or to see exactly which fields a given auth method needs. |
| Environment variables | [reference/environment-variables](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/environment-variables/index.md) | `GRAFANA_SERVER`, `GRAFANA_ORG_ID`, `GRAFANA_STACK_ID`, `GRAFANA_TOKEN`, `GRAFANA_USER`/`GRAFANA_PASSWORD`, `GRAFANA_TLS_*`, `GRAFANA_CLOUD_TOKEN`, `GCX_TELEMETRY`, `GCX_AUTO_APPROVE`. Use for CI/non-interactive runs — env vars override the selected context in memory and are never persisted. Minimum for a working call: `GRAFANA_SERVER` + `GRAFANA_ORG_ID` (on-prem) plus one credential var. |
| `gcx login` | [gcx_login.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_login.md) | Interactive/non-interactive auth: `--oauth` (Cloud, browser-based, works in agent mode), `--token` (service-account token, Cloud or on-prem), `--cloud-token` (Cloud platform API), `--yes` to skip prompts. `gcx login prod --server https://<stack>.grafana.net` for Cloud; `gcx login local --server http://localhost:3000 --token <token>` for self-hosted/on-prem. |
| Migrate configuration | [migrate-configuration.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/sources/migrate-configuration.md) | Steps to move an older `gcx` config file to the current schema version. Run only if `gcx config check` reports a legacy/unversioned config. |
| `gcx help-tree` | [gcx_help-tree.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_help-tree.md) | Prints a compact command tree (with inline args/flags/agent hints) for agent context injection; take a subtree with positional args (`gcx help-tree metrics`) or cap depth with `--depth`. Run this first when unsure what a command area supports — it is the token-cheap way to discover the full command surface without paging through individual `--help` output. |
| `gcx commands` | [gcx_commands.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_commands.md) | Full JSON catalog of every command with flags, args, token-cost estimates, and known Grafana resource types; `--validate` checks it against a live instance. Use for programmatic/agent discovery of the entire CLI surface, or `--flat` for a single-list view. |
| Local oddyssey stack | the `setup-local-stack` skill (ships with the oddyssey package) | Carries a ready-made isolated `GCX_CONFIG` context (`admin`/`admin` against the configured `grafana_url` — default `http://localhost:3000`, never assumed — datasource UIDs `prometheus`/`loki`/`tempo`/`pyroscope`). Use it instead of re-deriving context setup for the local stack; `gcx` is the mandatory query CLI (recorded proof queries may be raw datasource-proxy HTTP — that skill says when each form is right). |

## Remote missions — targeting without touching the user's config

The local stack has its sanctioned isolated setup (the
`setup-local-stack` skill's per-session `GCX_CONFIG`); a remote
mission runs on the user's own gcx context and must never write into
it. Datasource defaults live in the context file
(`contexts.<name>.datasources.<kind>`), so a mission without its own
file pays `-d <uid>` on every call. The remote mirror of the local
pattern, in order of preference:

- **Session copy** — copy the user's config to a per-session path,
  point `GCX_CONFIG` at the copy, and add the datasource defaults
  there: the user's file is never touched and the copy dies with the
  session. **Gate it with `gcx config check` immediately** — on the
  mission's context (`--context <name>`) when the user's active one
  is not the target stack: keychain-backed credentials (OAuth
  sign-in, `gcx login`-stored tokens) are bound to the config file's
  path and are rejected in the copy — "the keychain reference does
  not match this config source" (verified 1.2.0) — so the copy alone
  only works for inline-credential or env-var contexts.
- **When the check rejects the copy** — the rejection message itself
  names the fix: the user re-authenticates once into the session file
  (`gcx login <stack> --config "$GCX_CONFIG"` — their action, never
  the mission's), then re-run the check to prove the session file
  works. If they decline, stay on the user's config and pass
  `-d <uid>` per call — verbose, but deterministic with the UID
  conventions below.
- Never work around a rejection by copying credential values out of
  the keychain or the user's file, and never write into the user's
  config to "just add" the datasource defaults.

**Grafana Cloud datasource discovery**: `gcx datasources list -o
agents` returns `"type": ""` for every datasource on Cloud (observed
2026-08), so the signal-kind mapping cannot be read from the type
field. Map by the stock naming and proxy URLs instead: the
provisioned datasources follow the `grafanacloud-…-prom` /
`-traces` / `-logs` / `-profiles` naming (observed 2026-08 as UIDs
`grafanacloud-prom`, `grafanacloud-traces`, `grafanacloud-logs`,
`grafanacloud-profiles`; display names may prefix the stack slug) —
take each one's **`uid` field from the `datasources list` output**
and set it as the matching `datasources.<kind>` default
(`prometheus`, `tempo`, `loki`, `pyroscope`) in the session copy.

## Query by signal

| Signal | How | Link | Notes |
| --- | --- | --- | --- |
| Metrics | `gcx metrics labels` | [gcx_metrics_labels.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_labels.md) | List all labels, or values for one label (`-l/--label`); scope with `--metric` and/or repeatable `--match` selectors. |
| Metrics | `gcx metrics series` | [gcx_metrics_series.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_series.md) | Prometheus `/api/v1/series` — list time series for one or more selectors; unbounded time range unless `--since`/`--from`/`--to` is given. |
| Metrics | `gcx metrics metadata` | [gcx_metrics_metadata.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_metadata.md) | Type and help text for metrics; filter with `-m/--metric`. |
| Metrics | `gcx metrics query [PROMQL]` | [gcx_metrics_query.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_query.md) | Instant query by default; add `--from/--to/--step` (or `--since`) for a range query, or `--time` for an instant query at a specific timestamp. `--share-link`/`--open` produce a Grafana Explore URL. |
| Traces | `gcx traces labels` | [gcx_traces_labels.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_labels.md) | List all trace labels, or values for one (`-l`); `--scope` filters to `resource`/`span`/`event`/`link`/`instrumentation`; `-q` scopes by a TraceQL filter. **No time flags**: `--since` and `--from`/`--to` are rejected (`Unknown flag`) — for a time-bounded attribute-value check, run a TraceQL query with `--since` instead. Experimental `--llm` requests an LLM-friendly value format. |
| Traces | `gcx traces query [TRACEQL]` | [gcx_traces_query.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_query.md) | Search for traces with a TraceQL expression, e.g. `{ span.http.status_code >= 500 }`; `--limit` defaults to 20. **`--limit 0` is documented as unlimited but silently returns the backend default of 20** (verified 1.2.0: a query matching 434 traces returned 20) — never use it for counting; pass an explicit large limit (`--limit 1000`) instead. |
| Traces | `gcx traces get TRACE_ID` | [gcx_traces_get.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_get.md) | Fetch one trace by hex trace ID. Experimental `--llm` returns an LLM-friendly shape; default `-o json` is raw OTLP-shaped **inside an envelope**: `{"trace": {"resourceSpans": [...]}, "metrics": {"inspectedBytes": ...}}` (verified 2026-09-02, gcx 1.2.0). A `--jq` path must start at `.trace.resourceSpans` — `.resourceSpans` at the top level yields `null` silently, indistinguishable from "no data"; only an expression that iterates it fails, with `jq: cannot iterate over: null` and a field hint naming `trace.resourceSpans`. |
| Logs | `gcx logs labels` | [gcx_logs_labels.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_logs_labels.md) | List all labels, or values for one (`-l/--label`). |
| Logs | `gcx logs series` | [gcx_logs_series.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_logs_series.md) | List log streams; requires at least one `-M/--match` LogQL stream selector (repeatable, OR logic). |
| Logs | `gcx logs query [LOGQL]` | [gcx_logs_query.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_logs_query.md) | Default `-o table`; use `-o raw` for bare line bodies or `-o json` for the full response. `--limit` defaults to 50 (0 = documented unlimited — unverified; after the traces `--limit 0` finding, prefer an explicit large limit). |
| Profiles | `gcx profiles list-profile-types` | [gcx_profiles_list-profile-types.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_list-profile-types.md) | Lists available profile type IDs (e.g. `process_cpu:cpu:nanoseconds:cpu:nanoseconds`) — required input to `profiles query`. |
| Profiles | `gcx profiles labels` | [gcx_profiles_labels.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_labels.md) | List all labels, or values for one (`-l`, e.g. `service_name`). Pyroscope's underlying `querier.v1.QuerierService/LabelValues` endpoint **requires a time range in epoch milliseconds** — without start/end it fails with "missing time range in the query", a message that names neither the parameter nor the unit. Through gcx, the range is optional: `--since 1h`, or `--from`/`--to` (RFC3339, **Unix seconds**, or relative like `now-1h`), or nothing at all — gcx answers without one (verified 2026-09-02, gcx 1.2.0: no flags and `--since 1h` both answer), but the window it then covers is documented neither in `--help` nor in the CLI reference, so pass an explicit range whenever the window matters. gcx's "Unix timestamp" is seconds, not the raw endpoint's milliseconds: a millisecond value is read as seconds, a one-hour window becomes ~1000h, and the query fails with `the query time range exceeds the limit (max_query_length, actual: 1000h0m0s, limit: 1d)`. Supply `start`/`end` in ms yourself only when replaying the raw endpoint. SDK-pushed profiles carry no `service.instance.id`: a pyroscope-io profile's labels are `service_name`, `deployment_environment`, `otel.scope.*`, `process.runtime.*` (verified 2026-09-03, gcx 1.2.0, local stack). Qualify a run's profiles by a per-run tag the service pushes (`service_instance_id=<run slug>`, mirroring the OTel resource attribute); without one, two emitters sharing a `service_name` (a server and its healthcheck, two instances) are separable only by `process.runtime.version` and by the frames themselves. **Scope**: without `-l` the listing is store-wide — the label *names* present across every service, Pyroscope's own self-profile included (`hostname`, `pyroscope_spy`, `service_git_ref`, `service_repository`, `target`) — and there is no selector flag (`-q` is rejected), so never attribute that list to one service; a service's real label set is one exemplar's: `gcx profiles exemplars profile '{service_name="<svc>"}' --profile-type <type> --since 24h --jq '.exemplars[0].labels'`. `-l <name>` on an unknown or misspelled label name answers `{"names":null}` with exit 0 — the twin to validate a suspect selector against (verified 2026-09-03, gcx 1.2.0, local stack). |
| Profiles | `gcx profiles query [SELECTOR]` | [gcx_profiles_query.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_query.md) | Requires `--profile-type`; can drill into specific `--profile-id`s (from `profiles exemplars`), restrict by `--span-id`/`--trace-id`, or filter the flamegraph with repeatable `--stacktrace-selector`. **Selector**: SDK-pushed profiles carry dotted label names (`process.runtime.version`, `otel.scope.name`) that must be **quoted** inside the braces — `'{service_name="orders-api", "process.runtime.version"="3.12.14"}'`; unquoted, the selector fails to parse (`unexpected character inside braces: '.'`). An unknown or misspelled label **name** (`process_runtime_version`) or a wrong **value** matches nothing and answers a zero flamegraph (`.flamegraph.total` `"0"`) with exit 0 — indistinguishable from "no data in the window", so validate any zero against a known-positive twin (drop the suspect label, or list its values with `profiles labels -l <name>` first) before ruling anything absent. The JSON envelope, the per-frame computation and the frame-naming rule are in `### Reading profile output` below. |

Every query command resolves its datasource from `-d/--datasource <UID>` or
falls back to `datasources.<kind>` in the active context (`prometheus`,
`tempo`, `loki`, `pyroscope`) — set the defaults once per context instead of
passing `-d` on every call. Time flags differ per signal family:
`traces query` takes `--since` or `--from`/`--to`, `traces labels` takes
none, `logs labels` rejects `--since` too (`Unknown flag`),
`profiles labels` takes `--since`, `--from`/`--to`, or nothing — the raw
Pyroscope endpoint behind it is what requires a range; through gcx the
call answers without one, over an unspecified window (see its row, and
its seconds-not-milliseconds trap).

gcx query commands are **safe to run concurrently against one
context**: backgrounded in one shell call sharing one `GCX_CONFIG`,
they neither lock the config file nor contend for the credential —
six discoveries (`metrics labels`, `metrics metadata`, `traces
labels`, `logs labels`, `profiles list-profile-types`, a `traces
query`) all exited 0 in 0.33 s against 1.56 s serial, eight `traces
get` in 0.62 s against 2.1 s serial with every output parsing, and 32
`traces get` at once with no failure (verified 2026-09-04, gcx 1.2.0,
local stack). Redirect **stdout and stderr to separate files**: gcx
prints its `{"class":"hint",...}` line on stderr, and a `2>&1`
capture puts it in front of the JSON (`Extra data: line 2` on
parsing).

### Reading gcx output

All verified against gcx 1.2.0 — five traps that each cost real missions
several retries:

- **`-o agents` and `--jq` are mutually exclusive** ("--jq requires JSON
  output"): reshaping needs `-o json --jq '<expr>'`. `--json <fields>` is
  not a boolean flag (`--json list` — or `?` — discovers the fields, a
  bare `--json` fails with "Flag needs an argument"), and `--jq`/`--json`
  are mutually exclusive with each other too.
- **JSON output is pretty-printed multi-line with no compact flag** —
  `--jq '[…]' | tail -1` silently yields `]`, indistinguishable from an
  empty result. Force one line with `--jq '<expr> | tostring'` (or
  `-o raw` for bare log bodies).
- **A `{"class":"hint",…}` preamble line precedes the payload** — on
  stderr on the current build, on stdout on earlier ones — so merged or
  older-build output must never be parsed naively. Stable either way:
  `-o json --jq '<expr> | tostring' 2>&1 | tail -1`. On errors the last
  line is the single-line `gcx.error` JSON — a non-parsing result is an
  error, not empty data.
- **The response envelope differs per command, and `--jq` runs over the
  whole envelope**: `metrics query` → `.data.result[]`, `metrics series`
  → `.data[]`, `traces query` → `.traces[]`, `traces get` →
  `.trace.resourceSpans[]`, `logs query` → `.data.result[]`.
- **Anchor every aggregation on the data field, never on the envelope**:
  `metrics series '…' --jq 'length'` returns 2 — the `{status, data}`
  envelope's key count — even when the real series count is 0. The
  correct form is `--jq '.data | length'`. An envelope-level count is a
  silently wrong number, not an error.

### Loki over OTLP

On an OTLP-fed Loki (the local otel-lgtm stack and Grafana Cloud behave
identically), idiomatic scrape-era LogQL returns empty results:

- **The only stream labels are `service_name`, `service_instance_id`,
  and `deployment_environment_name`.** `trace_id` and the level are
  **structured metadata** — not labels, not in the line body: label
  matchers (`detected_level=~"warn|error"`) and body matches
  (`|= "<trace-id>"`) come back empty. Use pipeline filters instead:
  `| severity_text =~ "WARN.*|ERROR"` and `| trace_id = "<id>"`.
- **Metric-style LogQL through `gcx logs query` needs an explicit
  range** (`--since`, or `--from`/`--to`; it returns `null` without
  one), has no instant mode, and its matrix samples are
  `{line: "<value>", timestamp}` objects — not the Prometheus
  `[ts, "value"]` pairs.
- **Counting lines over a finished window: the exact total is the raw
  line count, never a metric-style sample.**
  `gcx logs query '<selector>' --from <start> --to <end> --limit <large>`
  and count `.data.result[].values` (`--jq '[.data.result[].values[]] |
  length'`; the default `--limit` is 50). The count is exact only below
  the limit you pass: when it comes back equal to `--limit`, it is
  truncated, not the total — raise the limit (Loki caps it server-side)
  or split the window. A metric-style count is an estimate: its samples
  sit on a grid aligned to the step, the first one **before** `--from`
  and the last one **after** `--to` (a 6-minute window at `[6m]` came
  back as 8 samples at 60 s, from 9 s before `start` to 51 s after
  `end`), so every sample straddles the edges — a range vector
  evaluated at the window start reaches back before it and pulls in
  whatever preceded the window (a service's startup lines, an earlier
  run). When a metric form must be used: query `--from`/`--to`, never
  `--since`, for a finished window — `--since` ends at now, so its last
  sample is a sliding partial that under-counts (32 against 35 true
  lines) — bound the range to the step (`[1m]`, `--step 1m`) and sum
  only the samples whose timestamp falls in `(start, end]`. A sample's
  `timestamp` is in **nanoseconds** (19 digits), hence the `/1e9`;
  `<start>` and `<end>` are the Unix seconds passed to `--from`/`--to`:

  ```text
  --jq '[.data.result[].values[]
         | select((.timestamp|tonumber/1e9) > <start>
                  and (.timestamp|tonumber/1e9) <= <end>)
         | .line | tonumber] | add'
  ```

  (35, matching the raw count; the unfiltered sum read 47). The `max`
  of a `[<window>]` matrix over-counted by one here (36) and its last
  sample happened to match the raw count (35) — both straddle the
  edges like every other sample, the error is whatever the edge
  samples pull in, so neither is a total or a correction. Verified
  2026-09-03, gcx 1.2.0, local stack, on a steady healthcheck stream;
  the single-point `--since` result issue #256 reported was not
  reproduced (8 samples here). A "correlated lines = lines" check
  therefore compares two **raw** counts over the same window and
  stream selector, one of them carrying the trace-id filter
  (`'{...} | trace_id != ""'` against `'{...}'`), with the startup and
  excluded-URL lines that legitimately carry no trace id excluded
  explicitly, or enumerated with `-o raw` and classified.
- **An un-aggregated range vector hits a misleading series-limit
  error**: `count_over_time({service_name="..."}[20m])` fails with
  `maximum number of series (500) reached for a single query` — read as
  a cardinality problem, but the query is just unbounded in shape (one
  series per label combination), not actually near a real cardinality
  limit. Wrap it in `sum()` (or another aggregator) —
  `sum(count_over_time(...))` — to fix it.

### Reading profile output

`gcx profiles query -o json` returns one top-level key, `flamegraph`,
holding `names` (frame names, index 0 = `total`), `levels` (one entry
per depth, each `values` a flat list of quadruples
`[offset, total, self, nameIndex]` — **all strings**, so the index
needs `tonumber`: `$names[(.[$i+3]|tonumber)]`), `total` and `maxSelf`
(strings, in the profile type's unit); there is no top-level `total`,
and `--json list` exposes only those five fields. Per-frame self or
total is computed from the quadruples — sum `self` per `nameIndex`
across levels for a top-N by CPU — the JSON carries no ready-made
per-frame arrays. `-o pprof --pprof-path <file>` writes a gzip pprof
for `go tool pprof` and the like (default path
`profile-<timestamp>.pb.gz` in the working directory). Verified
2026-09-03, gcx 1.2.0, local stack, on a pyroscope-io service.

**Frame names** are the profiler's own. pyroscope-io emits
`Class.method` or a bare function name — observed:
`OpenerDirector.add_handler`, `HTTPConnection.request`, `urlopen`,
`getaddrinfo`, `_verbose_message`, and the module-level frame
`<module>` — never a module path. A stored check that greps
`.flamegraph.names` therefore uses **anchored** names read off the
emitting process's own flamegraph, never a module-path regex: on a
FastAPI/uvicorn service, `uvicorn|app\.main` matched nothing while
`^(Server\.serve|RequestResponseCycle\.run_asgi)$` did, and an
unanchored `urlopen` false-positived on a healthy server because
urllib3's `HTTPConnectionPool.urlopen`, called by the OTLP HTTP
exporter, shares the name with the standard library's function
(observed in issue #265's mission, not re-verified here).

## Planning notes

- Verified 2026-08-30 (the `profiles labels` and `traces get` rows
  re-verified 2026-09-02) against gcx 1.2.0 (Homebrew build 2026-08-25) on a
  live local stack — flag surface, output framing, envelope shapes, and
  the `--limit 0` truncation were each exercised, not read from docs.
  gcx labels itself "generally available" (README badge) and requires
  Grafana 12+ — older self-hosted instances are out of scope.
- The flag surface moves between builds sharing a version string:
  `metrics labels --match` was rejected by an earlier 1.2.0 build and
  works on the current one. When a documented flag comes back
  `Unknown flag`, suspect the installed build before this file — and
  fall back to an equivalent (`gcx metrics series '{selector}'` + jq
  over `__name__` replaces `--match` scoping).
- Query commands are read-only and identical across on-prem, Enterprise, and
  Cloud; the only differences are auth (`org-id` for on-prem vs
  `stack-id`/OAuth for Cloud) and which datasource UIDs exist on the stack.
- OAuth sign-in (`gcx login --oauth`) needs the Grafana user to hold the
  **gcx User** role (permission `grafana-assistant-app.tokens.gcx:access`),
  granted automatically to Viewer-or-above on instances with the Grafana
  Assistant application; service-account tokens have no such extra
  requirement and are the documented recommendation for CI.
- `gcx traces`/`gcx metrics`/`gcx logs`/`gcx profiles` also carry `adaptive`
  subtrees (Adaptive Metrics/Logs/Traces cost-control resources) not covered
  here — this file is scoped to reading the four signals, not managing
  sampling/retention policy.

## Configuration display

### Display

`grafana` is a **remote** Grafana; the gcx context is what says which
instance, so the display is the context, not an invented value.

- `gcx config list-contexts` — every configured context, with the
  active one marked.
- `gcx config view` — the active context's `grafana.server` (the
  instance the queries will hit) and its `org-id` when set. Show the
  server URL and org; never echo a token, password, or any other
  credential field the view prints.

`stack_config.grafana` is expected **empty** — the gcx context already
names the instance, and duplicating it in the global configuration only
creates a second truth to drift. Present-and-empty (`{}`) or missing
both display as "nothing persisted — the gcx context is the source".
If values are stored there anyway, show them as-is and say the gcx
context still wins for targeting.

List any `invalid_ignored` dotted names `odd_config_get` returned as
degradations: the stored value was invalid and was dropped.
`stack_config` has no defaults behind it, so a dropped value reads as
not persisted — nothing silently took its place.

### Connection proof

`gcx config check` (add `--context <name>` when proving a context other
than the active one). Success on the active context = connected. No
context configured for a remote instance is not automatically an
authentication problem: offer `odd_config_set {"stack": "local"}` first
if the user meant the local stack.

### Change-request phrasing

- "switch gcx to context <name>"
- "change backend to local"

## What to persist

### What stack_config holds

**Nothing.** `stack_config.grafana` is expected to stay empty, and an
empty entry is the correct final state of a switch to `grafana`, not an
unfinished one.

The reason is that gcx is a **context-bearing** CLI: the active context
already names the instance (`grafana.server`), the org (`org-id`) or
Cloud stack, and the default datasource UID per signal. Copying any of
that into the global configuration creates a second truth that drifts
the first time the user runs `gcx config use-context` — and the gcx
context wins for targeting regardless, so the copy would be wrong
without being consulted.

`grafana` always means a **remote** Grafana. The local stack is the
separate `local` value, with its own reference.

### Where each value comes from

From the gcx context, read at use time and never mirrored here:

- `gcx config list-contexts` — the configured contexts, active one
  marked.
- `gcx config view` — the active context's server URL, org, and
  datasource defaults.

Whichever credential the context uses (a service-account token, basic
auth, OAuth, mTLS) lives in gcx's own configuration. It is referred to
by name in any display and never written into `stack_config`.

### What to ask the user

**Nothing about targeting.** Do not ask for the instance URL, the org,
the stack id, or the datasource UIDs — asking implies they should be
stored, and they should not be.

The one thing worth raising, and only when the user has more than one
context or none active, is which gcx context the runs should use — and
the fix for that lives in gcx (`gcx config use-context <name>`), not in
this configuration. If no context points at a remote instance at all,
offer the alternative before anything else: the user may have meant the
local stack, and that is `odd_config_set {"stack": "local"}`.

Leave `stack_config.grafana` alone. If values are already stored there
from an earlier run, do not add to them and say plainly that the gcx
context is what the missions will target.
