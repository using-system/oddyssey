---
name: create-observe-run-report
description: Persist an observation report into the observed repository at .odd/observe-run-reports/ with a structured frontmatter, and recall previous reports for the same service - the file contract that turns single observation runs into the ODD loop's memory. Use when storing the report an observation run produced, or when loading past reports to establish a baseline before a new run.
---

# Create an Observe-Run Report

An observation run that cannot see the previous ones starts blind every
time. This skill defines the file contract that gives the ODD loop its
memory: reports live **in the observed repository**, so git versions
them, PRs review them, and every user of the repo shares them — no
side-channel storage, nothing opaque.

The report is also the loop's **only durable artifact**: the raw
telemetry behind it lives in a volume-less container that any
`odd_stack_reset` — from this project or another on the same machine —
destroys irreversibly. A question that only occurs at verify time is
unanswerable unless its numbers were recorded at observe time: when in
doubt, record the number.

## Where reports live

```text
<observed-repo-root>/.odd/observe-run-reports/YYYY-MM-DD-HHmm-<run_name>.md
```

- `YYYY-MM-DD-HHmm` is the run's **UTC** start time — timestamped to the
  minute so two same-day runs never collide, and so a plain directory
  listing sorts chronologically.
- `<run_name>` is a short kebab-case slug derived from what the run
  analyzed (e.g. `checkout-latency-sweep`, `orders-post-hoc-errors`).
  Name the content, not the date — the date is already in front.
- A **verification run** — a run that replays a stored report's
  measurement protocol — names its file
  `YYYY-MM-DD-HHmm-verify-<run_name>.md`: its **own** UTC timestamp,
  then `verify-`, then the verified report's `run_name` unchanged (the
  baseline's timestamp is not repeated). Chronological sorting is
  preserved — verify reports interleave in the timeline instead of
  clustering — and "has this run been verified?" becomes a filename
  glob (`*-verify-<run_name>.md`). Re-verifications share the suffix
  and differ by their own timestamp. `verify-` always references the
  report **whose protocol is replayed**: re-verifying replays the
  original observation's protocol again, so the new report references
  the original observation — never a previous verification.
- Create the directory if it does not exist. The files are meant to be
  **committed**: leave them tracked, never add them to `.gitignore`.

## The file format

A YAML frontmatter, then the complete report:

```markdown
---
services: [checkout, payment]
environment: local            # local | the remote backend name (grafana, datadog, ...)
mode: drive                   # drive | observe | post-hoc | verify
window: 2026-08-22T10:04:12Z/2026-08-22T10:05:03Z
run_name: checkout-latency-sweep
date: 2026-08-22
revision: 2299d4c             # optional: commit of the observed repo at run time
workload: repo-under-analysis # optional: the input that shaped this run
instance: {checkout: af6070c1}   # optional: per service, the identity the numbers belong to
process_restarted: true       # optional: restarted before the window (or per-service map)
---

<the observation report, verbatim and complete>
```

A verification run (stored as
`2026-08-25-0930-verify-checkout-latency-sweep.md`) differs only in
these fields:

```yaml
mode: verify
run_name: checkout-latency-sweep                     # the baseline's, unchanged
verifies: 2026-08-20-1012-checkout-latency-sweep.md  # exact filename of the replayed baseline
```

- The frontmatter exists so future runs can filter reports **without
  parsing prose**: every field mirrors the run as it actually executed —
  mission parameters and execution environment alike (defaults applied,
  not as requested). One exception: a verification run records
  `mode: verify` even though it executes in the baseline's mode — the
  replayed execution mode stays reachable through `verifies`.
- `window` is the observed interval as `start/end` in UTC; in drive mode
  it is the scenario's own start and end.
- A verification run sets `mode: verify` and `verifies: <exact filename
  of the replayed baseline report>`, and takes its `run_name` from that
  baseline. Observation reports never carry `verifies` and record their
  execution mode — the mode a verification replayed is the baseline's,
  reachable through `verifies`, so it is not repeated. The exact
  filename (not just the run_name) is what disambiguates two baselines
  sharing a run_name and survives an accidental rename; the field is
  the machine contract, the `verify-` filename the readable convention.
- `revision` (`git rev-parse --short HEAD` in the observed repo) is what
  makes a before/after honest: a report is a before-value for a fix
  wave, and the fix is a diff against some revision.
- `workload` names the input that shaped the run when the runtime
  profile depends on what was processed, not only on the service (an
  analysis service run against two different repositories produces
  incomparable numbers). Free-form, omit when the service alone defines
  the profile — and if the workload changes mid-mission, that is a new
  run, not a note.
- `instance` and `process_restarted` pin which process the numbers
  belong to (run-scenario step 0). `instance` maps each observed service
  to its identity: `service.instance.id` when the SDK emits one, or the
  backend equivalent when it is absent — the process start time, a
  `target_info` label, a container id. `process_restarted`
  is one boolean when it holds for every listed service, a per-service
  map when only some were restarted. Cumulative-metric
  queries in the measurement protocol must be qualified by the recorded
  identity — a number that cannot be attributed to a process is not a
  before-value.
- The body is the producing agent's report **as-is** — the report
  contract (sections, tables, evidence rules) belongs to the agent, not
  to this skill. Store the whole thing: a summary cannot feed a diff.

## Recall: reading the memory

Before a new run, load the baseline:

1. List `.odd/observe-run-reports/` in the observed repo (missing or
   empty directory = first run, no baseline — say so, do not fail).
2. Walk the listing newest first (filenames sort chronologically),
   reading **frontmatter blocks only** — never whole files at this
   stage. A report matches when its `services` intersect the mission's
   and its `environment` is the mission's. When a match's `workload`
   differs from the mission's (or only one side has one), keep it but
   **warn**: its numbers were shaped by a different input, and diffing
   across workloads violates the one-changed-variable rule.
3. The first match is the baseline: read that one report in full — its
   per-operation numbers, findings, and measurement protocol are the
   before-values the new run compares against. What the comparison must
   report belongs to the calling agent's contract, not to this skill.
4. Older matches are history: only when a trend matters (a number
   degrading run after run), read at most the few most recent matches,
   and only the numbers in question — never the full files.
5. The observed → verified chain is machine-readable — never parse
   prose for it. Whether a report has been verified is the glob
   `*-verify-<run_name>.md` on later timestamps, confirmed by the
   candidate's `verifies` field naming that report's exact filename
   (the field is authoritative; the filename is convention). A
   verification report is itself a full report — when it is the newest
   match, it is the baseline, and its `verifies` field says whose
   findings its verdicts re-measured. Pre-convention reports (free-form
   slug, no `verifies`) stay valid matches: their chain simply is not
   machine-readable, which is a fact to state, not an error.

## Rules

- **Never write secrets into a report**: no tokens, credentials, cookies,
  or connection strings — these files are made to be committed and
  shared. Refer to access material by variable or secret name only.
- **A recorded query is a contract only once shown to work**: a check is
  authored against *broken* data, so "returns NaN/empty" and "the query
  is wrong" are indistinguishable at authoring time (measured: `rate()`
  over a single burst makes every `histogram_quantile` NaN by
  construction on any window sampled after the burst, whatever the fix
  did). Each verification check states how its query was validated —
  run against a healthy or adjacent series, or a synthetic one — or
  carries `not validated`, which tells the verify run to suspect the
  query before the fix.
- **Record how the backend was started** when it needed configuration:
  the `env` passed to `odd_stack_up` / `odd_stack_reset` belongs in the
  measurement protocol (key names and values — secrets by name only). A
  replayed reset recreates the container bare; only a recorded env lets
  the verify run pass the same one.
- One run, one file: never edit a previous report to "update" it — a new
  run writes a new file, the diff lives in the new report.
- Write the file exactly where the contract says: the report belongs to
  the **observed** repository, not to the oddyssey package, a home
  directory, or a temp path.
- **After writing, commit the report file on its own**:
  `git add <report file>` then
  `git commit -m "docs(odd): observation report <run_name>"` (for a
  verification run, `docs(odd): verification report <run_name>`) — never
  stage anything else; a dirty working tree stays untouched otherwise.
  If committing is impossible (not a git repository, or the caller said
  not to), state the path and leave the commit to the caller.
- Either way, state the stored path in the reply.
