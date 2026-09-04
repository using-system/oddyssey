# The `.odd/` reports

Every mission ends in a committed report — the ODD loop's memory, and
its only durable artifact: the telemetry behind an observation dies
with the next `odd_stack_reset`, the report survives in the repository.
This page tells you what you are looking at when you open one. The
contracts themselves belong to the skills that persist the reports
([create-observe-run-report](../../.apm/skills/create-observe-run-report/SKILL.md),
[create-otel-instrumentation-report](../../.apm/skills/create-otel-instrumentation-report/SKILL.md))
and the agents that write their bodies
([observe-run](../../.apm/agents/observe-run.agent.md),
[otel-instrumentation-expert](../../.apm/agents/otel-instrumentation-expert.agent.md));
on any divergence, they win.

## Observation reports — `.odd/observe-run-reports/`

Written by `/odd-observe` and `/odd-verify`, one file per run.

### Filenames

```text
YYYY-MM-DD-HHmm-<run_name>.md            # an observation
YYYY-MM-DD-HHmm-verify-<run_name>.md     # a verification replaying a stored protocol
YYYY-MM-DD-HHmm-remeasure-<run_name>.md  # a protocol replay testing no fix
```

The timestamp is the run's own UTC start, so a directory listing reads
as a timeline. `<run_name>` names what the run analyzed
(`checkout-latency-sweep`); a verification or re-measure reuses the
replayed report's. "Has this run been verified?" is the glob
`*-verify-<run_name>.md`; a re-measure never matches it.

### Frontmatter

```yaml
---
services: [checkout, payment]
stack: local
environment: local
mode: drive
depth: full
window: 2026-08-22T10:04:12Z/2026-08-22T10:05:03Z
run_name: checkout-latency-sweep
date: 2026-08-22
revision: 2299d4c
workload: repo-under-analysis
instance: {checkout: af6070c1}
process_restarted: true
---
```

| Field | Required | What it says | Values |
|---|---|---|---|
| `services` | yes | The observed services, as their telemetry names them | service names |
| `stack` | yes | The backend the run queried | `local`, or a remote backend name |
| `environment` | yes | The deployment environment, detected from the telemetry, never asked | the detected value; `local` on the local stack; `unknown` when the service emits none |
| `mode` | yes | How the run executed, or what kind of replay it was | `drive`, `observe`, `post-hoc`, `verify`, `re-measure` |
| `depth` | new reports | How far the mission went | `quick` (the signals the question touches, a collapsed report), `full`; absent on older reports, which ran full — `/odd-verify` replays such a baseline at `quick` unless you say `full verify` |
| `window` | yes | The observed interval, UTC | `start/end` |
| `run_name` | yes | The filename's slug | kebab-case |
| `date` | yes | The run's UTC date | `YYYY-MM-DD` |
| `verifies` | verify, re-measure | The report whose protocol was replayed | its exact filename; the repo-relative path for an instrumentation report |
| `revision` | optional | The observed repo's commit at run time | short SHA |
| `tree_anchor` | optional | The top-level tree hashes at `revision`, so "code unchanged since" survives squash merges and fresh clones | entry name to hash |
| `workload` | optional | The input that shaped the run, when the service alone does not | free-form |
| `instance` | optional | Which process the numbers belong to | service to identity |
| `process_restarted` | optional | Whether the process restarted before the window | boolean, or per service |

A report predating a field simply lacks it; `/odd-status` says so
rather than guessing.

### Body — seven sections

1. **Mission and run record** — the mission as understood and, in
   drive mode, the scenario record that replays it verbatim.
2. **Observed behavior** — the per-operation table (requests, rate,
   p50/p95/p99, errors), every number with the query that produced it;
   the deltas against the previous report; the service graph.
3. **Anomalies and probable causes** — the ranked findings, each
   `confirmed` or `suspected`, with evidence and expected gain.
4. **Improvement opportunities** — each with a measurable gain and the
   query that will prove it landed.
5. **Telemetry gaps** — what the service should emit but does not.
6. **Decisions the spec must settle** — what telemetry cannot answer.
7. **Measurement protocol for the fix** — the scenario to replay and
   every check with its before-value, its pass criterion, and how its
   query was validated, or `not validated`.

A `quick` report keeps the seven headings with sections 1, 2 and 7
complete and 3 to 6 reduced to their essentials; section 5 names the
signals the run did not query. A verification adds its verdicts: each
check passed or failed, each anomaly fixed or still present, each gap
filled or still missing. A re-measure replays the same protocol and
rules on no fix: its numbers extend the run's measurement history.

## Instrumentation reports — `.odd/otel-instrumentation-reports/`

Written by `/odd-instrument-otel`, one file per investigation.

```text
YYYY-MM-DD-HHmm-<run_name>.md
```

Same timestamp rule, `<run_name>` naming what was investigated; no
verify variant — verifying a plan writes an observation report whose
`verifies` points here.

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

| Field | Required | What it says | Values |
|---|---|---|---|
| `project` | yes | What was investigated | repo, or repo/path |
| `stack` | yes | The export stack the plan targets | `local`, or a remote backend name |
| `run_name` | yes | The filename's slug | kebab-case |
| `date` | yes | The investigation's UTC date | `YYYY-MM-DD` |
| `revision` | optional | Which code the findings hold for | short SHA |
| `tree_anchor` | optional | The top-level tree hashes at `revision` | entry name to hash |

No `services`, `mode`, or `environment`: the services live in the
plan, and an investigation reads code, not telemetry — beyond
checking that a protocol's query runs.

### Body — five sections

1. **Stack inventory** — per service: language, frameworks, entry
   point, existing telemetry, with file paths as evidence.
2. **Summary table** — the plan at a glance, one row per service, and
   the implementation order.
3. **Decisions made, with rationale** — per service: the approach,
   the packages, the `OTEL_*` configuration, sourced from the
   official docs.
4. **Decisions the spec must settle** — sampling, Collector topology,
   migration, propagation, naming.
5. **Verification protocol** — one replayable check per planned
   signal, with the identity that ties it to the process under test,
   so `/odd-verify` can rule closed, present but unattributed, or
   still missing.

## How the reports chain

An observation records before-values at a `revision`; a fix lands; a
verification replays the protocol and rules on everything the
observation recorded; a re-measure replays it when nothing changed.
`verifies` always names the report whose protocol was actually
replayed, and `/odd-status` reads the whole chain from filenames and
frontmatters alone.

## What a reviewer can hold a report to

- **One run, one file.** A stored report is never edited: a new run
  writes a new file, and the diff lives there.
- **Committed alone.** Each report lands in its own commit
  (`docs(odd): observation report <run_name>`, and the verification,
  re-measure, and instrumentation variants).
- **No secrets, ever.** No tokens, credentials, connection strings, or
  real tenant, workspace, or account identifiers — placeholders and
  variable names only. A verification check whose query would return
  one on replay counts as a secret in the report.

These rules cover the report stores and `.odd/decisions.md`.
`.odd/benchmarks/` is living source, updated through reviewed diffs —
see [benchmarks.md](benchmarks.md).
