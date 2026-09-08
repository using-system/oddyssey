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

A remote mission runs on the user's own gcx context and must never write
into it. Datasource defaults live in the context file
(`contexts.<name>.datasources.<kind>`), so a mission without its own file
pays `-d <uid>` on every call. This skill ships the remote mirror of the
local pattern:

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-context.py --stack <context name>
```

That is the whole surface — `--stack <name>` (the gcx context to target;
default the user's current one) and `--json`. It copies the user's config
to a per-session path, reads that context's `gcx datasources list`, writes
the default datasource UID per signal into the copy, proves the copy with
`gcx config check --context <name>`, and prints the `export GCX_CONFIG=…`
line to put in front of every later call plus the four UIDs. The user's
file is never touched and the copy dies with the session. On Grafana
Cloud `datasources list` returns `"type": ""` for every datasource
(observed 2026-08), so the script maps by type first and then by the
stock `…-prom` / `-traces` / `-logs` / `-profiles` UID naming — the same
rule a hand-written mapping used.

Exit 1 is the copy being rejected, and the message says so: keychain-backed
credentials (OAuth sign-in, `gcx login`-stored tokens) are bound to the
config file's path — "the keychain reference does not match this config
source" (verified 1.2.0). The fix is the user's, never the mission's:
`gcx login <stack> --config <the session path the script printed>`, then
the script again. If they decline, stay on the user's config and pass
`-d <uid>` per call. Never copy a credential out of the keychain or the
user's file, and never write into the user's config to "just add" the
defaults.

## Query by signal

The four signals are read with the scripts this skill ships in
`scripts/` — never with gcx commands composed by hand: service names and a
window fix every query, and the scripts carry, in code, every trap of gcx
1.2.0 this file used to spell out as prose (the `{"class":"hint"}` line on
stderr, the multi-line JSON, the `gcx.spill_reference` a large answer
turns into, the `gcx.error` object, the envelope that differs per
command, the search `--limit` that silently defaults to 20 and caps at
1 000 on Cloud, the unpadded 31-hex trace ids, the base64 ids inside
`traces get`, the flamegraph quadruples, the export lag on cumulative
metrics, the trace-versus-span duration confusion). Each invocation below
is copy-pasteable and states the script's **whole** flag surface: `--help`
has nothing to add and the files have nothing to read. **A run that
writes its own query runner or its own envelope parser is rebuilding one
of these** — invoke the script instead, and when it lacks a shape of the
work, that is a defect to record, not a wrapper to write.

Common to every script: it reads `GCX_CONFIG` (the preflight handoff's
`context:` line, or `grafana-context.py`'s export); a window is
`--from <RFC3339 UTC> --to <RFC3339 UTC>` or `--since <duration>`; `--json`
prints the same result parseable; exit 0 means every query ran (an empty
answer is a result), 1 that gcx errored (the message is in the output), 2
for `grafana-discover.py` when a probe failed outright. The scripts run
their gcx calls **concurrently** against one context — verified safe on
1.2.0 (six discoveries in 0.33 s against 1.56 s serial, 32 `traces get`
at once with no failure) — so one call for three services costs one call.
`<Skills>` is the `skills` line the preflight handoff carries (the
`package-layout` skill's `scripts/layout.py`).

### First, in one call: what the window holds

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-discover.py <svc> [<svc> ...] --from <start> --to <end>
```

Per service: the metric names the store carries, the root operations its
traces name with their counts, its log line count and severities, and
whether a CPU profile exists — presence and absence with the same weight.
Surface: service names (positional), a window, `--json`. Nothing else.
This is the observation-time counterpart of the `setup-local-stack`
skill's `probe_services.py` (which answers the preflight's "is this
service emitting at all, under which identity" over a lookback); this one
is per window and per signal, on any Grafana.

### Metrics

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py histogram <base> --by <label,label> --selector '<matchers>' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py counter <name> --by <label> --selector '<matchers>' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py names --match '{<selector>}' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py instant '<PromQL>' --at <instant>
python3 <Skills>/observability-cli-guides/scripts/grafana-metrics.py range '<PromQL>' --from <start> --to <end> --step 30s
```

Five subcommands, the whole surface: `histogram` takes the metric's base
name (without `_bucket`), `--by` (comma list of grouping labels),
`--selector` (label matchers without the braces), `--quantiles` (default
`0.5,0.95,0.99`), `--from`/`--to`, `--settle` — and prints p50/p95/p99,
count, sum and mean per group. `counter` takes the metric name, `--by`,
`--selector`, `--from`/`--to`, `--settle` — and prints the raw cumulative
value at the window's start, at its end, and after it settled, plus the
`increase()` over the window: on a store where the counter was born inside
the window the settled raw value is the run's total and `increase()` is an
extrapolated estimate of it (386 against 426 real requests, measured
2026-09-05). `--settle` (default `90s`, both subcommands) is the export
lag: an SDK exports every 60 s, so the sample carrying a run's last
requests lands after the window closes — read exactly at `--to`, a
counter of 817 orders answered 471 (measured 2026-09-08); both subcommands
evaluate at `--to` + settle and print the instant they used. `names`
lists the distinct metric names behind one or more `--match` selectors
(`metrics metadata` is empty for every OTLP-written metric, measured
2026-09-06 — names come from the series, and an empty metadata answer is
not evidence of an absent metric). `instant` and `range` take a raw PromQL
expression for anything the first three do not shape; `instant` takes
`--at`, `range` takes `--from`/`--to`/`--step`. An empty result on a
window shorter than two export intervals is a window problem before it is
an absence: widen it before ruling anything absent.

### Traces

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-traces.py ops --service <svc> [--service <svc>] --from <start> --to <end> --fetch <dir>
python3 <Skills>/observability-cli-guides/scripts/grafana-traces.py get <trace id> [<trace id> ...] [--spans] [--out <dir>]
python3 <Skills>/observability-cli-guides/scripts/grafana-traces.py count '<TraceQL>' --from <start> --to <end> --bin 30s
python3 <Skills>/observability-cli-guides/scripts/grafana-traces.py search '<TraceQL>' --from <start> --to <end> --limit 1000
```

Four subcommands, the whole surface. `ops` (`--service` repeatable,
`--name` repeatable to add operations the window's roots do not show,
`--limit` default 1000, `--fetch <dir>`, a window) prints, per root
operation of each service, **two latency readings that are not the same
number**: the span-level p50/p95/p99 and call count from the store's span
metrics (`traces_spanmetrics_latency_bucket`, exact, present on the local
stack and on Cloud when the metrics generator is on — the output says
when it is absent), and the trace-level p50/p95/max over the traces
*rooted* at the operation (integer milliseconds — a sub-millisecond
operation reads 0 there); plus the worst trace *containing* the operation,
which is where a fan-out shows. `--fetch` also retrieves each operation's
p50, worst-rooted and worst-containing exemplar and prints its summary:
root, duration, span count, per-`(service, name)` counts with the longest
span, error spans, GenAI token totals. `get` takes trace ids in either form
gcx prints (padded or not) and prints that summary; `--spans` prints every
span with its parent, kind, duration and attributes instead; `--out <dir>`
keeps the raw documents. `count` counts the traces a TraceQL selector
matches over a window in `--bin` slices (default `30s`), deduplicated on
trace id — a trace overlapping two bins is listed in both — and says when
a bin hit the 1 000 ceiling (narrow the bin or split the selector).
`search` runs a raw TraceQL expression and lists what it matched, ids
padded. Compose a TraceQL filter inside one pair of braces —
`{ resource.service.name = "svc" && span.http.status_code >= 500 }` —
never as two brace groups joined by `&&` (a parse error).

### Logs

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-logs.py severity '{<selector>}' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-logs.py sample '{<selector>}' --contains '<text>' --severity 'WARN.*|ERROR' --from <start> --to <end> --show 20
python3 <Skills>/observability-cli-guides/scripts/grafana-logs.py correlate '{<selector>}' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-logs.py count '{<selector>}' --from <start> --to <end>
```

Four subcommands, the whole surface: each takes a LogQL stream selector,
a window, `--limit` (default 5 000) and `--json`; `sample` adds
`--contains` (a line-body filter), `--severity` (a regular expression on
the level) and `--show` (lines printed, default 20). `severity` counts the
window's lines by level with samples of the non-informational ones;
`correlate` compares the raw line count against the lines carrying a trace
id and lists the orphans (startup and health-check lines legitimately
carry none — classify them before calling this a gap); `count` is the
exact raw count per stream. Every count is exact only below `--limit`,
and the output says when it was reached: raise it or split the window —
never take a metric-style LogQL sample for a total, its grid straddles
the window's edges (35 true lines read 47 that way, measured 2026-09-03).
On an OTLP-fed Loki (the local stack and Cloud alike) the level and the
trace id are **structured metadata** — not labels, not in the line body —
so `detected_level=~"warn"` as a matcher and `|= "<trace id>"` as a body
match both return nothing; the scripts read `severity_text` and `trace_id`
where they live. The only stream labels are `service_name`,
`service_instance_id` and `deployment_environment_name`.

### Profiles

```bash
python3 <Skills>/observability-cli-guides/scripts/grafana-profiles.py top '{service_name="<svc>"}' --from <start> --to <end> -n 15
python3 <Skills>/observability-cli-guides/scripts/grafana-profiles.py check '{service_name="<svc>", "<label>"="<value>"}' --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-profiles.py labels --label <name> --from <start> --to <end>
python3 <Skills>/observability-cli-guides/scripts/grafana-profiles.py types
```

Four subcommands, the whole surface: `top` (a selector, `--type` default
`process_cpu:cpu:nanoseconds:cpu:nanoseconds`, a window, `-n` default 15)
prints the process total and the top frames by **self** time and by
**total** time, with percentages — both, because a percentage quoted
against the wrong one is a different number (the same frame read 88.4 %
as self and 79.0 % as largest total on one profile, and a report quotes
self). `check` runs a selector and then the same selector with each label
dropped in turn, so a zero that is a misspelt label name or a wrong value
is told apart from a window that holds no data — a zero flamegraph
answers with exit 0 in every one of those cases. `labels` lists a label's
values with `--label`, the store-wide label *names* without it (every
service's, Pyroscope's own included — a service's own labels are on one
exemplar). `types` lists the profile types the store holds. Dotted label
names are quoted inside the braces (`"process.runtime.version"="3.12"`).
SDK-pushed profiles carry no `service.instance.id`: profiles are
attributed by `service_name` and the window, and two emitters sharing a
name are separable only by the frames themselves. A memory profile type
answers a zero total for a Python service (the SDK pushes CPU only).

### When a gcx call is still composed by hand

The `instant`, `range`, `search` and `sample` subcommands take a raw
expression, so the case is rare. For anyone who must run `gcx` directly:
`-o json` with `--jq '<expr> | tostring'` and `2>&1 | tail -1` is the one
stable framing (`-o agents` and `--jq` are mutually exclusive, a bare
`--json` needs an argument, the JSON is pretty-printed over many lines);
anchor every `--jq` on the data field, never on the envelope
(`metrics query` → `.data.result[]?`, `metrics series` → `.data[]`,
`traces query` → `.traces[]`, `traces get` → `.trace.resourceSpans[]`,
`logs query` → `.data.result[]`, `datasources list` → `.datasources[]`);
pass an explicit `--limit` (`0` silently returns 20); `traces labels`
takes no time flag, `logs labels` and `logs series` neither, `profiles
labels` takes an optional one; a `--trace-id` must be the padded 32 hex;
and a TraceQL **metrics** query through `traces query` is silently run as
a search — `gcx traces metrics` is the command, and its
`quantile_over_time` snaps a small span set to power-of-two bucket edges
(a "p99" of 8.589934592 s = 2³³ ns over a true maximum of 6.35 s, measured
2026-09-08): quote small-N latency from `traces get`, never from it.

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
