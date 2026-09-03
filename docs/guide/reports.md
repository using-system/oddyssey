# The `.odd/` reports

Every mission ends in a committed report — the ODD loop's memory, and
its only durable artifact: the raw telemetry behind an observation
lives in a volume-less container that the next `odd_stack_reset`
destroys, but the report survives in the repository, versioned by git
and reviewable in PRs. This page explains what you are looking at when
you open one: the filename conventions, every frontmatter field with
its possible values, and the body structure each report kind carries.

This guide **documents** the contracts — it never redefines them. The
authoritative sources are the skills that persist the reports
([create-observe-run-report](../../.apm/skills/create-observe-run-report/SKILL.md),
[create-otel-instrumentation-report](../../.apm/skills/create-otel-instrumentation-report/SKILL.md))
and the agents that produce their bodies
([observe-run](../../.apm/agents/observe-run.agent.md),
[otel-instrumentation-expert](../../.apm/agents/otel-instrumentation-expert.agent.md)).
On any divergence, those sources win and this page is the bug.

## Observation reports — `.odd/observe-run-reports/`

Produced by `/odd-observe` and `/odd-verify` (through the
`observe-run` agent), one file per run.

### Filenames

```text
YYYY-MM-DD-HHmm-<run_name>.md            # an observation
YYYY-MM-DD-HHmm-verify-<run_name>.md     # a verification replaying a stored protocol
YYYY-MM-DD-HHmm-remeasure-<run_name>.md  # a protocol replay testing no fix
```

- `YYYY-MM-DD-HHmm` is the run's own **UTC** start time, to the minute
  — a plain directory listing sorts chronologically, and verify or
  re-measure reports interleave in the timeline instead of clustering.
- `<run_name>` is a short kebab-case slug naming what the run analyzed
  (`checkout-latency-sweep`), never the date. Verification and
  re-measure runs reuse the replayed report's `run_name` unchanged.
- The prefixes make two questions answerable by glob alone: **"has
  this run been verified?"** is `*-verify-<run_name>.md` on later
  timestamps — and only that: a re-measure never matches it, because
  it ruled on no fix. **"Has this protocol been replayed without a
  fix?"** is `*-remeasure-<run_name>.md`. The filename is the readable
  convention; the `verifies` frontmatter field is the machine
  contract.

### Frontmatter

```yaml
---
services: [checkout, payment]
stack: local
environment: local
mode: drive
window: 2026-08-22T10:04:12Z/2026-08-22T10:05:03Z
run_name: checkout-latency-sweep
date: 2026-08-22
revision: 2299d4c
workload: repo-under-analysis
instance: {checkout: af6070c1}
process_restarted: true
---
```

| Field | Required | Description | Possible values |
|---|---|---|---|
| `services` | yes | The observed services, as their telemetry names them | list of service names |
| `stack` | yes | The backend the run queried | `local`, or a remote backend name (`grafana`, `datadog`, ...) |
| `environment` | yes | The deployment environment, **detected** from the `deployment.environment.name` resource attribute — never asked | any detected value (`prod`, `uat`, ...); `local` forced on the local stack; `unknown` when the service emits no attribute (stated, never guessed — and recorded as a telemetry gap) |
| `mode` | yes | How the run executed — or, for `verify` and `re-measure`, what kind of replay it was (the replayed execution mode stays reachable through `verifies`) | `drive` (the run generated the traffic), `observe` (someone else drove, the run watched live), `post-hoc` (analysis of a past window), `verify` (protocol replay ruling on a fix), `re-measure` (protocol replay testing no fix — drift or stability) |
| `window` | yes | The observed interval, `start/end` in UTC; in drive mode, the scenario's own start and end | ISO 8601 interval |
| `run_name` | yes | The slug the filename carries; a verification or re-measure takes the replayed report's | kebab-case slug |
| `date` | yes | The run's UTC date | `YYYY-MM-DD` |
| `verifies` | only on `verify` / `re-measure` | The exact filename of the report **whose protocol was actually replayed** — exact so two baselines sharing a `run_name` stay distinct and an accidental rename is survivable | a sibling filename; a repo-relative `.odd/otel-instrumentation-reports/<filename>` path when the baseline is an instrumentation report (the value's shape says which directory); a verification report only when its own §7 protocol — not the original's — was the one replayed |
| `revision` | optional | The observed repo's commit at run time (`git rev-parse --short HEAD`) — what makes a before/after honest | short SHA |
| `tree_anchor` | optional | Full top-level entry map of `git ls-tree <revision>` — the squash-proof content anchor a fresh clone can compare (consumers ignore `.odd` — its hash moves with every report — and every entry that cannot change the service's runtime behavior: documentation, CI configuration, generated artifacts, release metadata; they test `.odd/benchmarks/` separately, by path, as living source) | map of entry name to object hash |
| `workload` | optional | The input that shaped the run, when the runtime profile depends on what was processed, not only on the service — runs with different workloads are incomparable | free-form; omitted when the service alone defines the profile |
| `instance` | optional | Per service, the process identity the numbers belong to — `service.instance.id`, or the backend equivalent when absent | map of service to identity |
| `process_restarted` | optional | Whether the process restarted before the window | boolean, or a per-service map when only some restarted |

Plain observation reports (`drive`, `observe`, `post-hoc`) never carry
`verifies`. Reports predating a field simply lack it — a pre-convention
report stays valid; its chain just is not machine-readable, which is a
fact `/odd-status` states rather than an error.

### Body — seven sections

The body is the `observe-run` agent's report, stored verbatim and
complete (a summary cannot feed a diff):

1. **Mission and run record** — the mission as understood, every
   default applied, the detected environment with the query that found
   it, the recalled baseline (or "no previous report"); in drive mode,
   the verbatim scenario record (exact commands, counts, UTC
   start/end, and the query points (each beyond the first with its
   reason) — for a stored k6 benchmark, its name and git revision,
   the `k6 run` command, k6's exit status and summary including its
   script-error count, and the stage boundaries) so the run replays
   identically; in observe mode with a benchmark, its name and
   revision stand in for the commands the agent did not run.
2. **Observed behavior** — the per-operation summary table (requests,
   rate, p50/p95/p99, error %, downstream calls), followed, with a
   benchmark, by the threshold table (manifest threshold, measurement
   with its query, pass/fail — or `void` on every row when the run
   record's k6 line carries script errors above zero, the defect then
   being section 3's first finding), then the narrative,
   every number carrying the query that produced it and a sample;
   with a baseline, the per-operation deltas and the fate of its
   findings; the service graph closes the section.
3. **Anomalies and probable causes** — the ranked findings table
   (severity, confidence `confirmed`/`suspected`, evidence, expected
   gain), then the detail per row.
4. **Improvement opportunities** — each with a measurable expected
   gain and the query that will prove it landed.
5. **Telemetry gaps** — what the service should emit but does not,
   each gap carrying the discovery query that came back empty.
6. **Decisions the spec must settle** — the open questions telemetry
   cannot answer.
7. **Measurement protocol for the fix** — how the next run must
   observe: the exact scenario to replay (for a stored benchmark, the
   same benchmark at the same revision; otherwise window and
   conditions),
   then every verification check with its before-value, pass
   criterion, and how the query was validated (or `not validated`).

A verification's body carries the same sections plus its verdicts:
each §7 check of the baseline ruled pass/fail with before and after
values, each anomaly ruled fixed / still present / worse, each gap
ruled filled / still missing. A re-measure replays the same protocol
but rules on no fix — its numbers extend the run's measurement
history, comparable by construction with the report its `verifies`
names.

## Instrumentation reports — `.odd/otel-instrumentation-reports/`

Produced by `/odd-instrument-otel` (through the
`otel-instrumentation-expert` agent), one file per investigation.

### Filenames

```text
YYYY-MM-DD-HHmm-<run_name>.md
```

Same timestamp rules; `<run_name>` names what was investigated
(`mcp-server-python`, `checkout-monorepo-full`). There is no verify or
re-measure variant here: verifying an instrumentation plan produces an
**observation** report whose `verifies` carries this report's
repo-relative path.

### Frontmatter

```yaml
---
project: oddyssey/src/mcp-server
stack: local
run_name: mcp-server-python
date: 2026-08-23
revision: 2299d4c
---
```

| Field | Required | Description | Possible values |
|---|---|---|---|
| `project` | yes | What was investigated | repo, or repo/path for a scoped investigation |
| `stack` | yes | The export stack the recommendations were derived for | `local`, or a remote backend name |
| `run_name` | yes | The slug the filename carries | kebab-case slug |
| `date` | yes | The investigation's UTC date | `YYYY-MM-DD` |
| `revision` | optional | Which code the findings hold for | short SHA |
| `tree_anchor` | optional | Full top-level entry map of `git ls-tree <revision>` — the squash-proof content anchor a fresh clone can compare | map of entry name to object hash |

No `services`, `mode`, or `environment` by design: the services live
in the body's per-service plan, and the investigation reads code,
never telemetry — there is no mission mode to record and nothing to
detect an environment from.

### Body — five sections

1. **Stack inventory** — per service: language and version,
   frameworks, entry point, how it starts, where it runs, existing
   telemetry; evidence as file paths; opens with the recalled baseline.
2. **Summary table** — the whole plan at a glance, one row per service
   (approach, signals, pinned packages, OTLP endpoint, effort, risk
   flags), followed by the recommended implementation order.
3. **Decisions made, with rationale — per service** — the approach
   (zero-code / libraries / manual), exact packages and setup steps
   sourced from the official docs, and the `OTEL_*` configuration
   block.
4. **Decisions the spec must settle** — sampling, Collector topology,
   migration vs coexistence, propagation, log correlation, naming,
   what not to instrument.
5. **Verification protocol** — one replayable check per planned item
   (spans searchable, metrics present, logs carrying trace IDs,
   resource attributes set), each with its discovery query and
   expected outcome, so a later `/odd-verify` run rules **closed /
   still missing** without interpreting prose.

## How the reports chain

The loop's history is machine-readable from frontmatters and filenames
alone — `/odd-status` renders it without parsing prose. An observation
records before-values at a `revision`; a fix lands; a verification
replays the protocol and rules on everything the observation recorded;
a re-measure replays it when nothing changed. `verifies` always names
the report whose protocol was actually replayed, one hop away —
re-verifying replays the original's protocol and references the
original; only a run that explicitly replays a verification's own §7
protocol references that verification.

## What a reviewer can hold a report to

The rules the persistence skills enforce — and a PR review should too:

- **One run, one file.** A report is never edited after the fact: a
  diff that modifies a stored report "to update it" violates the
  contract — a new run writes a new file, and the diff lives in the
  new report.
- **Committed alone.** Each report lands in its own commit, staging
  nothing else: `docs(odd): observation report <run_name>`,
  `docs(odd): verification report <run_name>`,
  `docs(odd): re-measure report <run_name>`, or
  `docs(odd): instrumentation investigation <run_name>`.
- **No secrets, ever.** No tokens, credentials, cookies, or connection
  strings — access material appears by variable or secret name only.
  These files are made to be committed and shared.

These rules — immutability first among them — cover the report stores
this guide documents: `.odd/observe-run-reports/`,
`.odd/otel-instrumentation-reports/`, and `.odd/decisions.md`.
`.odd/benchmarks/` is out of scope here: a benchmark is living source
updated in place through reviewed diffs, not a run record, and
[benchmarks.md](benchmarks.md) documents it.
