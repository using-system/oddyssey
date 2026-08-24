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
- Create the directory if it does not exist. The files are meant to be
  **committed**: leave them tracked, never add them to `.gitignore`.

## The file format

A YAML frontmatter, then the complete report:

```markdown
---
services: [checkout, payment]
environment: local            # local | the remote backend name (grafana, datadog, ...)
mode: drive                   # drive | observe | post-hoc
window: 2026-08-22T10:04:12Z/2026-08-22T10:05:03Z
run_name: checkout-latency-sweep
date: 2026-08-22
---

<the observation report, verbatim and complete>
```

- The frontmatter exists so future runs can filter reports **without
  parsing prose**: every field mirrors the mission the run actually
  executed (defaults applied, not as requested).
- `window` is the observed interval as `start/end` in UTC; in drive mode
  it is the scenario's own start and end.
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
   and its `environment` is the mission's.
3. The first match is the baseline: read that one report in full — its
   per-operation numbers, findings, and measurement protocol are the
   before-values the new run compares against. What the comparison must
   report belongs to the calling agent's contract, not to this skill.
4. Older matches are history: only when a trend matters (a number
   degrading run after run), read at most the few most recent matches,
   and only the numbers in question — never the full files.

## Rules

- **Never write secrets into a report**: no tokens, credentials, cookies,
  or connection strings — these files are made to be committed and
  shared. Refer to access material by variable or secret name only.
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
  `git commit -m "docs(odd): observation report <run_name>"` — never
  stage anything else; a dirty working tree stays untouched otherwise.
  If committing is impossible (not a git repository, or the caller said
  not to), state the path and leave the commit to the caller.
- Either way, state the stored path in the reply.
