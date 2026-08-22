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
| Local oddyssey stack | the `setup-local-stack` skill (ships with the oddyssey package) | Carries a ready-made isolated `GCX_CONFIG` context (`admin`/`admin` against `http://localhost:3000`, datasource UIDs `prometheus`/`loki`/`tempo`/`pyroscope`). Use it instead of re-deriving context setup for the local stack; `gcx` is the mandatory query CLI. |

## Query by signal

| Signal | How | Link | Notes |
| --- | --- | --- | --- |
| Metrics | `gcx metrics labels` | [gcx_metrics_labels.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_labels.md) | List all labels, or values for one label (`-l/--label`); scope with `--metric` and/or repeatable `--match` selectors. |
| Metrics | `gcx metrics series` | [gcx_metrics_series.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_series.md) | Prometheus `/api/v1/series` — list time series for one or more selectors; unbounded time range unless `--since`/`--from`/`--to` is given. |
| Metrics | `gcx metrics metadata` | [gcx_metrics_metadata.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_metadata.md) | Type and help text for metrics; filter with `-m/--metric`. |
| Metrics | `gcx metrics query [PROMQL]` | [gcx_metrics_query.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_query.md) | Instant query by default; add `--from/--to/--step` (or `--since`) for a range query, or `--time` for an instant query at a specific timestamp. `--share-link`/`--open` produce a Grafana Explore URL. |
| Traces | `gcx traces labels` | [gcx_traces_labels.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_labels.md) | List all trace labels, or values for one (`-l`); `--scope` filters to `resource`/`span`/`event`/`link`/`instrumentation`; `-q` scopes by a TraceQL filter. Experimental `--llm` requests an LLM-friendly value format. |
| Traces | `gcx traces query [TRACEQL]` | [gcx_traces_query.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_query.md) | Search for traces with a TraceQL expression, e.g. `{ span.http.status_code >= 500 }`; `--limit` defaults to 20 (0 = unlimited). |
| Traces | `gcx traces get TRACE_ID` | [gcx_traces_get.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_get.md) | Fetch one trace by hex trace ID. Experimental `--llm` returns an LLM-friendly shape; default `-o json` is raw OTLP-shaped. |
| Logs | `gcx logs labels` | [gcx_logs_labels.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_logs_labels.md) | List all labels, or values for one (`-l/--label`). |
| Logs | `gcx logs series` | [gcx_logs_series.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_logs_series.md) | List log streams; requires at least one `-M/--match` LogQL stream selector (repeatable, OR logic). |
| Logs | `gcx logs query [LOGQL]` | [gcx_logs_query.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_logs_query.md) | Default `-o table`; use `-o raw` for bare line bodies or `-o json` for the full response. `--limit` defaults to 50 (0 = unlimited). |
| Profiles | `gcx profiles list-profile-types` | [gcx_profiles_list-profile-types.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_list-profile-types.md) | Lists available profile type IDs (e.g. `process_cpu:cpu:nanoseconds:cpu:nanoseconds`) — required input to `profiles query`. |
| Profiles | `gcx profiles labels` | [gcx_profiles_labels.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_labels.md) | List all labels, or values for one (`-l`, e.g. `service_name`). |
| Profiles | `gcx profiles query [SELECTOR]` | [gcx_profiles_query.md](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_query.md) | Requires `--profile-type`; can drill into specific `--profile-id`s (from `profiles exemplars`), restrict by `--span-id`/`--trace-id`, or filter the flamegraph with repeatable `--stacktrace-selector`. `-o pprof` writes a pprof binary. |

Every query command resolves its datasource from `-d/--datasource <UID>` or
falls back to `datasources.<kind>` in the active context (`prometheus`,
`tempo`, `loki`, `pyroscope`) — set the defaults once per context instead of
passing `-d` on every call. All four accept `-o agents` for compact
agent-oriented output and `--jq`/`--json` for reshaping JSON results.

## Planning notes

- Verified 2026-08 against `grafana/gcx` on the `main` branch. gcx labels
  itself "generally available" (README badge) and requires Grafana 12+ —
  older self-hosted instances are out of scope.
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
