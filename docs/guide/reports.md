# The `.odd/` reports

Every mission ends in a committed report — the ODD loop's memory, and
its only durable artifact: the telemetry behind an observation dies
with the next `odd_stack_reset`, the report survives in the repository.
This page tells you what you are looking at when you open one. The
contracts themselves belong to the `odd-memory` skill's references
([observe-run-report.md](../../.apm/skills/odd-memory/references/observe-run-report.md),
[otel-instrumentation-report.md](../../.apm/skills/odd-memory/references/otel-instrumentation-report.md))
and the agents that write their bodies
([observe-run](../../.apm/agents/observe-run.agent.md),
[otel-instrumentation-expert](../../.apm/agents/otel-instrumentation-expert.agent.md));
on any divergence, they win.

## Observation reports — `.odd/observe-run-reports/`

Written by `/odd-observe` and `/odd-verify`, one file per run.

### Filenames

```text
YYYY-MM-DD-HHmm-<run_name>.md                   # an observation
YYYY-MM-DD-HHmm-<name>-observe-<stack>.md       # a run someone else drove, as one observer saw it
YYYY-MM-DD-HHmm-verify-<run_name>.md            # a verification replaying a stored protocol
YYYY-MM-DD-HHmm-remeasure-<run_name>.md         # a protocol replay testing no fix
```

The timestamp is the run's own UTC start, so a directory listing reads
as a timeline. `<run_name>` names what the run analyzed
(`checkout-latency-sweep`); a verification or re-measure reuses the
replayed report's. "Has this run been verified?" is the glob
`*-verify-<run_name>.md`; a re-measure never matches it.

A run one mission drives and others watch — the same benchmark seen
from two backends, say — writes one report per mission, never a shared
file: an observer's names the run and the backend it watched from, the
driver's sits beside it under the same timestamp, and each says in
section 1 which mission drove the run.

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
| `window` | yes | The observed interval, UTC — the run's own span, not the time a mission spent waiting for it | `start/end` |
| `run_name` | yes | The filename's slug | kebab-case |
| `date` | yes | The run's UTC date | `YYYY-MM-DD` |
| `verifies` | verify, re-measure | The report whose protocol was replayed | its exact filename; the repo-relative path for an instrumentation report |
| `revision` | optional | The observed repo's commit at run time | short SHA |
| `tree_anchor` | optional | The top-level tree hashes at `revision`, so "code unchanged since" survives squash merges and fresh clones | entry name to hash |
| `repository` | optional | The repository `revision` was taken from, so a report moved to a central store still says where its code lives | the `origin` remote as host then path (`github.com/org/repo`); service to repository when the run spans several |
| `workload` | optional | The input that shaped the run, when the service alone does not | free-form |
| `instance` | optional | Which process the numbers belong to | service to identity |
| `process_restarted` | optional | Whether the process restarted before the window | boolean, or per service |
| `stack_friction` | custom stack | How many points of friction with the custom stack the run met, counted from section 8 | integer; present only when the stack is a custom one |

A report predating a field simply lacks it; `/odd-status` says so
rather than guessing.

### Body — seven sections, eight on a custom stack

A title line, then one paragraph — the headline, how the run went in
one sentence — then the seven numbered sections, an eighth on a custom
stack; the skill's script refuses to persist a report missing any of
the three.

1. **Mission and run record** — the mission as understood and, in
   drive mode, the scenario record that replays it verbatim.
2. **Observed behavior** — the per-operation table (requests, rate,
   p50/p95/p99, errors), every number with the query that produced it —
   for a query run through a backend's shipped script, the script
   invocation plus the backend commands it printed;
   the deltas against the previous report; the service graph.
3. **Anomalies and probable causes** — the ranked findings, each
   `confirmed` or `suspected`, with evidence and expected gain.
4. **Improvement opportunities** — each with a measurable gain and the
   query that will prove it landed.
5. **Telemetry gaps** — what the service should emit but does not:
   the `not queried` line first when the run has one, then one bullet
   per gap carrying its fate (`filled`, `still missing`, `new`,
   `not ruled (quick)`) and the discovery query that came back empty.
6. **Decisions the spec must settle** — what telemetry cannot answer.
7. **Measurement protocol for the fix** — the scenario to replay and
   every check with its before-value, its pass criterion, and how its
   query was validated — on today's data only, or on the shape the
   pass criterion expects too — or `not validated`.
8. **Stack friction** — on a custom stack only: one bullet per point
   of friction with the stack as shipped (a script that failed as
   written, an output shape the guide did not state, a flag it lacked,
   a query composed by hand), each with the invocation, what it
   answered and what the run did instead — or one `none` bullet, which
   states that every backend call went through a shipped invocation. The
   run never edits the stack; `/odd-instrument-stack from report
   <path>` fixes it from this section
   ([custom-backends.md](custom-backends.md)).

A `quick` report keeps the seven headings with sections 1, 2 and 7
complete and 3 to 6 reduced to their essentials — section 8, on a
custom stack, complete at both depths; section 5 names the signals
the run did not query. A verification adds its verdicts:
section 3 opens with one row per finding of the baseline — its id as
the baseline wrote it (`1`, `F4`), then `fixed`, `still present`,
`worse`, or `not ruled (quick)` — before the findings the run names
itself; each check passed or failed; each gap filled or still missing.
That id is how `/odd-status` burns a finding down, so a ruling written
under a renumbered id, or only in prose, leaves the finding open in
the status and says so under "Judgment needed". A re-measure replays
the same protocol and writes the same rows, but rules on no fix: its
numbers extend the run's measurement history, and only a
verification's rows close a finding.

A service that calls a model adds a **GenAI** subsection to section 2:
the per-model table — calls, tokens in and out, p50/p99, error rate,
and cost only when you handed the run a price per model — and the
agent-loop reading (spans per conversation, tool-call chains,
iteration counts). Its telemetry gaps sit in section 5 with the others.

## Instrumentation reports — `.odd/otel-instrumentation-reports/`

Written by `/odd-instrument-otel`, one file per investigation - the
`odd-memory` skill's report script names the file and writes the
frontmatter and the five headings (`new --kind instrumentation`),
refuses to persist a report that breaks the rules below, and renders
the closing synthesis (`show`).

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
| `repository` | optional | The repository `revision` was taken from | the `origin` remote as host then path (`github.com/org/repo`) |

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
   signal, as a table (`Check | Query | Expected outcome | Attribution
   evidence`) or a four-part bullet, with the identity that ties it to
   the process under test, so `/odd-verify` can rule closed, present
   but unattributed, or still missing. A check that projects a
   credential is refused before the report is persisted.

A service whose dependencies name a model SDK adds a **GenAI
approach** to section 3 under its own `### GenAI approach` heading —
prose, never a table row: the instrumentation library the plan adopts,
and what stays hand-coded — and two decisions to section 4: prompt and
completion content capture (off unless you turn it on, named as the
library's own switch) and cost attribution.

## How the reports chain

An observation records before-values at a `revision`; a fix lands; a
verification replays the protocol and rules on everything the
observation recorded; a re-measure replays it when nothing changed -
which of the two a replay is comes from the code state, never from
how the request was phrased. `verifies` always names the report
whose protocol was actually replayed, and `/odd-status` reads the
whole chain from filenames and frontmatters alone.

## What a reviewer can hold a report to

- **One run, one file.** A stored report is never edited: a new run
  writes a new file, and the diff lives there.
- **Committed alone.** Each report lands in its own commit
  (`docs(odd): observation report <run_name>`, and the verification,
  re-measure, and instrumentation variants).
- **Written by the skill's script.** A report's filename, frontmatter
  and headings - of both kinds - come from the `odd-memory` skill's
  report script, which also refuses to persist a report that breaks
  these rules; only the sections' content is the agent's.
- **No secrets, ever.** No tokens, credentials, connection strings, or
  real tenant, workspace, or account identifiers, nor a value persisted
  under a remote stack's `stack_config`, regions excepted (a log group,
  a profile name: the field's name in angle brackets instead) —
  placeholders and variable names only. A verification check whose
  query would return
  one on replay counts as a secret in the report.

These rules cover the report stores and the two ruling ledgers,
`.odd/decisions.md` and `.odd/entry-classifications.md`; the
[`odd-memory`](../../.apm/skills/odd-memory/SKILL.md) skill is the
contract they come from. `.odd/benchmarks/` is living source, updated
through reviewed diffs — see [benchmarks.md](benchmarks.md).
