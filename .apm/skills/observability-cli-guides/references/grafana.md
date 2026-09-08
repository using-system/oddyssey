# Grafana — gcx

Official docs: https://github.com/grafana/gcx (source, README, `docs/`) and
https://grafana.com/docs/grafana-cloud/as-code/observability-as-code/grafana-cli/gcx/
(published site).
`raw.githubusercontent.com/grafana/gcx/main/...` links return raw markdown;
`grafana.com/docs/...` and `github.com/.../blob/...` links are HTML-rendered
only. The CLI command reference (`docs/reference/cli/*.md`) exists only in
the repo — it is not mirrored on the published site.

gcx works against **any Grafana 12+**: Grafana Cloud, Enterprise, and OSS,
including the local oddyssey stack. It authenticates over the Grafana REST
API, so on-prem and Cloud differ only in the stack entry you configure
(`org-id` for on-prem vs `stack-id`/OAuth for Cloud) — every query below is
identical either way.

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
| Local oddyssey stack | the `setup-local-stack` skill (ships with the oddyssey package) | Carries a ready-made isolated `GCX_CONFIG` context (`admin`/`admin` against the configured `grafana_url` — default `http://localhost:3000`, never assumed — datasource UIDs `prometheus`/`loki`/`tempo`/`pyroscope`). Use it instead of re-deriving context setup for the local stack; `gcx` is the mandatory query CLI. |

## Remote missions — targeting without touching the user's config

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-context.py [--stack <context name>] [--json]
```

Whole surface: `--stack` (default: the user's current context), `--json`.
Prints the `export GCX_CONFIG=…` line to put in front of every later
call, the context, and the four datasource UIDs (marked when a UID is
not a context default: gcx then resolves it from the stack). Exit 0 =
proved with [`config check --context`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_config_check.md); exit 1 =
the message names the fix, which is the user's, never the mission's.

- Target is the user's current context (the usual case): the user's
  file is used in place, nothing copied, nothing written — a
  keychain-bound credential answers only from the file it was bound to,
  and no default is needed (verified 2026-09-08 on Cloud: four signals
  answered with `loki` and `prometheus` the only defaults set). Fix on
  exit 1: `gcx login <stack>`.
- Target is another context: the user's file is copied to a session path
  (one per stack and session), the copy gets that context and the
  default UID per signal from [`datasources list`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_datasources_list.md).
  Fix on exit 1 ("the keychain reference does not match this config
  source", verified 1.2.0): `gcx login <stack> --config <the session path>`.
- No other fallback: the scripts take no `-d`; a mission with no proved
  context stops. Never copy a credential, never write into the user's
  file. On Cloud, `datasources list` returns `"type": ""` (observed
  2026-08): UIDs are mapped by type, then by the `…-prom` / `-traces` /
  `-logs` / `-profiles` naming.

## Query by signal

The four signals are read with the scripts this skill ships in
`scripts/` — never with gcx commands composed by hand: service names and a
window fix every query, and the scripts carry, in code, every trap of gcx
1.2.0 this file used to spell out as prose (the `{"class":"hint"}` line on
either stream, the multi-line JSON, the `gcx.spill_reference` a large
answer turns into, the `gcx.error` object, the envelope that differs per
command, the search `--limit` that silently defaults to 20 and caps at
1 000 on Cloud, Loki's 5 000-line server cap, the unpadded 31-hex trace
ids, the base64 ids inside `traces get`, the flamegraph quadruples, the
export lag on cumulative metrics, a counter reset, the trace-versus-span
duration confusion). Each invocation below is copy-pasteable and states
the script's **whole** flag surface: `--help` has nothing to add and the
files have nothing to read. **A run that writes its own query runner or
its own envelope parser is rebuilding one of these** — invoke the script
instead, and when it lacks a shape of the work, that is a defect to
record in the run record, not a wrapper to write.

Common to every script: it reads `GCX_CONFIG` (the preflight handoff's
`context:` line, or `grafana-context.py`'s export) and the datasource
defaults of that context; a **window** is `--from <RFC3339 UTC> --to
<RFC3339 UTC>` or `--since <duration>` (a lookback ending now), on every
subcommand that takes one — `instant`, `get` and `types` take none;
`--json` prints the same result parseable (the text form is the default
and is what a run reads: the JSON form is four times larger, for a
consumer that parses it); exit 0 means every query ran (an empty answer
is a result), exit 1 that gcx errored — **and then the only line printed
is the error**, never a zero dressed as data; a usage error exits 2 with
the message. **Every subcommand ends by printing the gcx commands it
ran** — `queries run (record these):` — and those lines, with the script
invocation above them, are what the report records as the query; the
`odd-memory` skill's report reference says so — repeats are folded
losslessly in the text form (three quantiles, three services: one line
with `{a|b|c}` at the token that differs, the call count stated; `--json`
carries the verbatim list). Each subsection below links the gcx command
reference behind the calls its script runs. The scripts run their gcx
calls **concurrently** against one context — verified safe on 1.2.0 (six
discoveries in 0.33 s against 1.56 s serial, 32 `traces get` at once with
no failure) — so one call for three services costs one call. `<Skills>`
is the `skills` line the preflight handoff carries (the `package-layout`
skill's `scripts/layout.py`).

### First, in one call: what the window holds

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-discover.py <svc> [<svc> ...] --from <start> --to <end>
```

Per service: the metric names the store carries, how many traces carry a
span of it and how many are **rooted** at it (with the root operations and
their counts — an operation rooted elsewhere is not attributed to it), its
exact log line count and severities, and whether a CPU profile exists —
presence and absence with the same weight. Surface: service names
(positional), a window, `--label-key` (the label a service is named by on
metrics, logs and profiles — default `service_name`, the OTel resource
convention; a scrape-based Prometheus names it `job`; traces are always
selected on `resource.service.name`), `--json`. Nothing else. Behind it:
[`metrics series`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_series.md), [`traces query`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_query.md), [`logs query`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_logs_query.md),
[`profiles query`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_query.md) and [`profiles labels`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_labels.md). This is the
observation-time counterpart of the `setup-local-stack` skill's
`probe_services.py` (which answers the preflight's "is this service
emitting at all, under which identity" over a lookback); this one is per
window and per signal, on any Grafana.

### Metrics

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py histogram <base> --by <label,label> --selector '<matchers>' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py counter <name> --by <label> --selector '<matchers>' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py names --match '{<selector>}' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py labels --match '{<selector>}' [--label <name>] --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py instant '<PromQL with a selector or an aggregation>' --at <instant>
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py range '<PromQL>' --from <start> --to <end> --step 30s
```

Six subcommands, the whole surface: `histogram` takes the metric's base
name (without `_bucket`), `--by` (comma list of grouping labels),
`--selector` (label matchers without the braces), `--quantiles` (default
`0.5,0.95,0.99`), a window, `--settle` — and prints p50/p95/p99 per group
next to the raw `_count` and `_sum` read at the window's start and after
settling (their difference is the run's own count and sum, whole numbers,
and the mean comes from those), with the `increase()` over the window as
a separate, extrapolated figure. `counter` takes the metric name, `--by`,
`--selector`, a window, `--settle` — and prints the raw cumulative value
at the window's start, at its end and after it settled, the delta (the
run's own count) and the `increase()`: on a store where the counter was
born inside the window the settled raw value is the run's total and
`increase()` is an estimate of it (386 against 426 real requests, measured
2026-09-05). **A raw value that fell inside the window** (a counter reset,
an instance change) is flagged `RESET` and the run's own figures are
withheld — `counter`'s delta, `histogram`'s count, sum and mean — take
the increase then, never a negative count; a row so flagged is ranked by
its increase. `--settle` (default `90s`) is
the export lag: an SDK exports every 60 s, so the sample carrying a run's
last requests lands after the window closes — read exactly at `--to`, a
counter of 817 orders answered 471 (measured 2026-09-08); both subcommands
evaluate at `--to` + settle and print the instant they used. `names`
lists the distinct metric names behind one or more `--match` selectors
(`metrics metadata` is empty for every OTLP-written metric, measured
2026-09-06 — names come from the series, and an empty metadata answer is
not evidence of an absent metric). `labels` takes one `--match` selector
and a window: with `--label <name>` it lists that label's values across
the series the selector matches in the window (each with its series
count), without it the label *names* those series carry. `instant` and
`range` take a raw PromQL expression for anything the first four do not
shape — always with a selector or an aggregation, since a bare metric
name lists every series it has; `instant` takes `--at` (default now),
`range` takes a window and `--step`. An empty result on a window shorter
than two export intervals is a window problem before it is an absence:
widen it before ruling anything absent. Behind the six:
[`metrics query`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_query.md) (an instant query, or a range one)
and [`metrics series`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_series.md).

### Traces

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-traces.py ops --service <svc> [--service <svc> ...] [--name <operation> ...] --from <start> --to <end> [--fetch <dir>] [--limit 1000] [--settle 90s] [--top 15] [--json]
python3 <Skills>/observability-cli-guides/scripts/grafana-traces.py get <trace id> [<trace id> ...] [--spans] [--out <dir>] [--json]
python3 <Skills>/observability-cli-guides/scripts/grafana-traces.py count '<TraceQL>' --from <start> --to <end> [--bin 30s] [--json]
python3 <Skills>/observability-cli-guides/scripts/grafana-traces.py search '<TraceQL>' --from <start> --to <end> [--limit 1000] [--json]
```

Four subcommands, the whole surface above (`--since <duration>` replaces
`--from/--to` everywhere). Behind them: [`traces query`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_query.md),
[`traces get`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_get.md) and, for the span metrics,
[`metrics query`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_query.md).

- `ops` — per operation of each service: rooted and containing trace
  counts, span-level p50/p95/p99 and calls (span metrics, settled,
  bucket-interpolated; `RESET` and calls withheld when the counter fell
  inside the window; absence said), trace-level p50/p95/max over the
  rooted traces (integer ms), the worst containing trace. `--fetch` adds
  each operation's p50, worst-rooted and worst-containing exemplar with
  its summary. `--name` adds an operation the roots do not show.
- `ops` on a service never rooted in the window (its callers are
  instrumented, or nothing carries it): the output says which, with the
  callers named; its operations are its `--top` busiest span-metric names
  (capped is said), its rooted columns stay empty, the median containing
  trace is its p50 exemplar (verified 2026-09-08 on Cloud: seven
  operations, zero rooted).
- `get` — several ids in one call, either form gcx prints; one summary
  each, `--spans` every span with parent, kind, duration and attributes,
  `--out` keeps the raw documents; no window.
- `count` — traces matching a TraceQL selector per `--bin`, deduplicated
  on trace id (a trace overlapping two bins is listed in both); says when
  a bin hit the 1 000 ceiling (narrow the bin or split the selector).
- `search` — a raw TraceQL expression, ids padded. One pair of braces:
  `{ resource.service.name = "svc" && span.http.status_code >= 500 }` —
  two brace groups joined by `&&` is a parse error.

### Logs

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-logs.py severity '{<selector>}' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-logs.py sample '{<selector>}' --contains '<text>' --severity 'WARN.*|ERROR' --pipeline '<raw LogQL>' --from <start> --to <end> --show 20
python3 <Skills>/observability-cli-guides/scripts/grafana-logs.py correlate '{<selector>}' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-logs.py count '{<selector>}' --from <start> --to <end>
```

Four subcommands, the whole surface: each takes a LogQL stream selector, a
window and `--json`; `sample` adds `--contains` (a line-body filter, any
text — it is quoted for you), `--severity` (a regular expression on the
level), `--pipeline` (raw LogQL appended after the selector and those two
filters, for any other structured-metadata filter — e.g. `| trace_id =
"<32 hex>"`, `| service_instance_id != ""`) and `--show` (lines printed,
default 20). `severity` counts the
window's lines by level with samples of the non-informational ones;
`correlate` compares the raw line count against the lines carrying a
trace id and lists the orphans (startup and health-check lines
legitimately carry none — classify them before calling this a gap);
`count` is the exact raw count per stream. Loki answers at most **5 000
lines per query, server-side** — a larger limit is refused — so a window
holding more is read in pieces, split in halves until each fits, lines
deduplicated: the counts are exact, and when a piece still saturates
after six splits the output says `PARTIAL` and `correlate` reports no
ratio at all (narrow the window). Never take a metric-style LogQL sample
for a total: its grid straddles the window's edges (35 true lines read 47
that way, measured 2026-09-03). On an OTLP-fed Loki (the local stack and
Cloud alike) the level and the trace id are **structured metadata** — not
labels, not in the line body — so `detected_level=~"warn"` as a matcher
and `|= "<trace id>"` as a body match both return nothing; the working
forms are the pipeline filters `| severity_text =~ "WARN.*|ERROR"` and
`| trace_id = "<32 hex>"`, which `--severity` composes for you and
`--pipeline` takes verbatim. The only stream labels are `service_name`,
`service_instance_id` and `deployment_environment_name`. Behind the
four: [`logs query`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_logs_query.md).

### Profiles

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-profiles.py top '{service_name="<svc>"}' --from <start> --to <end> -n 15
python3 <Skills>/observability-cli-guides/scripts/grafana-profiles.py top '{service_name="<svc>"}' --from <start> --to <end> --trace-id <trace id>
python3 <Skills>/observability-cli-guides/scripts/grafana-profiles.py check '{service_name="<svc>", "<label>"="<value>"}' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-profiles.py labels --label <name> --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-profiles.py types
```

Four subcommands, the whole surface: `top` (a selector in braces,
`--type` default `process_cpu:cpu:nanoseconds:cpu:nanoseconds`, a window,
`-n` default 15, `--trace-id` / `--span-id` to restrict the flamegraph to
the samples linked to one trace or span — a trace id is padded to 32 hex
for you, the width gcx validates) prints the process total and the top
frames by **self** time and by **total** time, with percentages — both,
because a percentage quoted against the wrong one is a different number
(the same frame read 88.4 % as self and 79.0 % as largest total on one
profile, and a report quotes self). `check` (a selector, `--type`, a
window) runs the selector and then the same selector with each label
dropped in turn, so a zero that is a misspelt label name or a wrong value
is told apart from a window that holds no data — a zero flamegraph
answers with exit 0 in every one of those cases, a trace with no linked
samples included. `labels` lists a label's values with `--label`, the
store-wide label *names* without it (every service's, the store's own
self-profile included — never attribute that list to one service; a
suspect label name or value is validated with `check`, not with the
listing). `types` lists the profile types the store holds. Dotted label names are quoted
inside the braces (`"process.runtime.version"="3.12"`). SDK-pushed
profiles carry no `service.instance.id`: profiles are attributed by
`service_name` and the window, and two emitters sharing a name are
separable only by the frames themselves. A memory profile type answers a
zero total for a Python service (the SDK pushes CPU only). Frame names
are the profiler's own — `Class.method`, a bare function name,
`<module>` — never a module path: a stored check that greps them uses
**anchored** names read off `top`'s output (`^(Server\.serve|RequestResponseCycle\.run_asgi)$`
matched a FastAPI service where `uvicorn|app\.main` matched nothing, and
an unanchored `urlopen` false-positived on a healthy server — issue #265).
Behind the four: [`profiles query`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_query.md), [`profiles labels`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_labels.md) and
[`profiles list-profile-types`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_list-profile-types.md).

### When a gcx call is still composed by hand

The `instant`, `range` and `search` subcommands take a raw expression
(PromQL, TraceQL) and `sample --pipeline` a raw LogQL pipeline, so the
case is rare, and every trap below that a script could absorb, it does.
For a `gcx` call run directly (its command reference is linked at each
mention; [`gcx help-tree`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_help-tree.md) prints a command area's
surface):

- `-o json` with `--jq '<expr> | tostring'` and `2>&1 | tail -1` is the
  one stable framing: `-o agents` and `--jq` are mutually exclusive, a
  bare `--json` needs an argument, the JSON is pretty-printed over many
  lines, and the hint line lands on stderr (stdout on older builds).
- Anchor every `--jq` on the data field, never on the envelope
  (`metrics query` → `.data.result[]?`, `metrics series` → `.data[]`,
  `traces query` → `.traces[]`, `traces get` → `.trace.resourceSpans[]`,
  `logs query` → `.data.result[]`, `datasources list` → `.datasources[]`);
  inside `--jq` the pipe binds looser than the comma — parenthesise each
  element of a list — and `sort_by(.le|tonumber)` aborts on a histogram's
  `+Inf` bucket.
- Pass an explicit `--limit` (`0` silently returns 20; 1 000 is the
  ceiling on Cloud; Loki refuses more than 5 000).
- [`traces labels`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_labels.md) takes no time flag, [`logs labels`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_logs_labels.md) and
  [`logs series`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_logs_series.md) neither, [`profiles labels`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_profiles_labels.md) an optional one;
  [`metrics labels`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_metrics_labels.md) takes `--metric` and repeatable `--match`
  (verified on the current 1.2.0 build, rejected by an earlier one — the
  scripts' `labels` subcommands answer the same questions from queries
  every build serves); a `--trace-id` must be the padded 32 hex.
- **A trace-attribute listing is never exhaustive**: `traces labels -l
  user_agent.original --scope span` answered one value, and `[]` once
  scoped to the run, while a bounded search found 360 traces carrying it
  (verified 2026-09-05). A presence ruling made from a listing is a false
  "absent" — prove presence with `grafana-traces.py search` on the
  attribute, or `get` on a trace.
- A TraceQL **metrics** query through [`traces query`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_query.md) is silently
  run as a search — [`traces metrics`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_traces_metrics.md) is the command, its output
  reached 552 KB
  on one service (redirect it to a file), and its `quantile_over_time`
  snaps a small span set to power-of-two bucket edges (a "p99" of
  8.589934592 s = 2³³ ns over a true maximum of 6.35 s, measured
  2026-09-08): quote small-N latency from `get`, never from it.
- An un-aggregated LogQL range vector fails with `maximum number of series
  (500) reached` — a shape problem, not a cardinality one: wrap it in
  `sum()`.
- [`gcx help-tree <group>`](https://raw.githubusercontent.com/grafana/gcx/main/docs/reference/cli/gcx_help-tree.md) is the token-cheap way to
  see a command area's surface when a flag comes back `Unknown flag`.

## Planning notes

- The scripts above were each exercised live on 2026-09-08 against gcx
  1.2.0 (Homebrew build 2026-08-25) and the local stack, on a window
  holding a two-minute k6 run: envelope shapes, the spill reference, the
  settled counter, the two latency readings and the zero-check were read
  off real answers, not documentation. The measurements the prose quotes
  date from 2026-08-30 to 2026-09-08 on the local stack and Grafana Cloud.
  gcx labels itself "generally available" and requires Grafana 12+ —
  older self-hosted instances are out of scope.
- The flag surface moves between builds sharing a version string: when a
  documented flag comes back `Unknown flag`, suspect the installed build
  before this file, and read the script's error rather than retrying the
  flag.
- Query commands are read-only and identical across on-prem, Enterprise,
  and Cloud; the only differences are auth (`org-id` vs `stack-id`/OAuth)
  and which datasource UIDs exist on the stack.
- OAuth sign-in (`gcx login --oauth`) needs the Grafana user to hold the
  **gcx User** role (permission `grafana-assistant-app.tokens.gcx:access`),
  granted automatically to Viewer-or-above on instances with the Grafana
  Assistant application; service-account tokens have no such extra
  requirement and are the documented recommendation for CI.
- `gcx traces`/`metrics`/`logs`/`profiles` also carry `adaptive` subtrees
  (cost-control resources) not covered here — this file is scoped to
  reading the four signals.
- **Size a rate window to at least two exports, and read the export
  interval first.** At the OTel SDK's default 60 s interval a `[1m]`
  `increase()` answered `result: []` with exit 0 where `[2m]` answered
  (verified 2026-09-05, Cloud): the scripts' windows are the mission's
  own window plus the settle lag, and an empty answer on a short window
  is a window problem first. One query per metric: `increase()` strips
  `__name__`, so a regex over two metrics either fails on a colliding
  labelset or silently merges them into one series.
- **A live instant `rate()` can answer stale** on Mimir (`1.97` in flight,
  `138.5` re-read afterwards, verified 2026-09-06, Cloud): never conclude
  "the run has ended" from an instant metric rate; decide that on the
  traces.

### Adaptive Metrics on Grafana Cloud

On Grafana Cloud an Adaptive Metrics rule may drop a label from a metric
before it is stored, and the metric then answers in three shapes, none of
which says "a rule did this" (verified 2026-09-06, gcx 1.2.0, Cloud): the
unaggregated selector errors with `Can't query aggregated metric … the
following label is aggregated: <label>`; the wrong aggregator (`max`)
answers `result: []` with exit 0 where `sum` answers; grouping by an
aggregated label returns the literal value `<aggregated>`. A label
missing from a Cloud metric is a cost-control rule before it is an
instrumentation gap; the series carrying one are
`grafana-metrics.py names --match '{job="<job>", __aggregation__!=""}'`.

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
