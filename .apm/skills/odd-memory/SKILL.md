---
name: odd-memory
description: The .odd/ memory - its contract and one reference per kind. The contract states what every kind shares (where the memory lives, the frontmatter and the whole body, append-only reports versus living-source benchmarks, recall by frontmatter then by section, the no-secrets rule, the work branch and the lone commit, the reply that carries a synthesis and never the artifact); each reference says how to persist, recall and show its kind - observation reports, instrumentation reports, benchmarks, the maintainer-ruling ledgers (finding decisions, tree-entry classifications), custom stack files. Read when a report, a benchmark, a custom stack file or a decision is persisted, recalled, shown or inventoried, or when a finding is declined (wontfix) or such a decision reversed, or a tree entry is ruled runtime or non-runtime; never invoked on its own.
---

# The `.odd/` memory contract

The ODD loop's memory is a set of committed files in the observed
repository, under `.odd/`: git versions them, pull requests review them,
every user of the repository shares them — no side-channel storage,
nothing opaque. It has five kinds, each with the reference that owns
its specifics (its paths, its frontmatter fields, its recall matching,
its branch name, its commit subject, what its reply carries, and how a
stored one is shown):

| Kind | Store | Reference |
| --- | --- | --- |
| Observation reports | `.odd/observe-run-reports/` | [references/observe-run-report.md](references/observe-run-report.md) |
| Instrumentation reports | `.odd/otel-instrumentation-reports/` | [references/otel-instrumentation-report.md](references/otel-instrumentation-report.md) |
| Maintainer rulings | `.odd/decisions.md` (findings) and `.odd/entry-classifications.md` (tree entries), written by `scripts/odd_ledger.py` | [references/decisions.md](references/decisions.md) |
| Benchmarks | `.odd/benchmarks/<name>/` | [references/benchmark.md](references/benchmark.md) |
| Custom stacks | `.odd/observability-stacks/<name>.md` | [references/observability-stack.md](references/observability-stack.md) |

This file owns what they share; a reference states only its
specifics. A sixth kind is a new row in this table and a new
reference, never a sixth copy of these rules.

## Reading a reference by section

A reference is read like a stack reference — by the section a step
needs, never whole. To **persist** an artifact, read its naming and
format sections and its `## Rules`; to **recall** the baseline before
a run, its `## Recall`; to **show** a stored artifact at the end of a
mission, its `## Show` and nothing else; to **record** a decision, the
ledger reference's `## Recording a decision` and `## Rules`, and to
record a tree-entry classification, its
`## The entry-classification ledger`. The `## Return value` of a
report reference is what the persistence hands the caller, and what
`## Show` renders from.

## Where the memory lives

- In the **observed** (or investigated) repository, exactly where the
  kind's reference says — never in the oddyssey package, a home directory,
  or a temp path. Create the directory when it does not exist.
- **Committed**: the files stay tracked, never added to `.gitignore`.
- A report file is named `YYYY-MM-DD-HHmm-<run_name>.md`: the run's
  **UTC** start time to the minute, so two same-day runs never collide
  and a plain listing sorts chronologically — computed with `date -u`,
  never from the local clock (a session crossing local midnight while
  UTC has not names the wrong day) — then a short kebab-case slug
  naming the content, not the date. The kind's reference adds its own
  prefixes and variants.

## The frontmatter and the body

- A report opens with a YAML frontmatter so later runs can filter the
  store **without parsing prose**. Every field mirrors the run as it
  actually executed — defaults applied, not as requested. The kind's
  reference lists the fields and their meaning.
- The body is the producing agent's artifact **as-is**, whole: the
  section contract belongs to the agent, not to the persistence,
  and a summary cannot feed a later diff.

## Append-only, with one exception

- The report stores and the ruling ledgers are **append-only
  evidence**: one run, one file — never edit a stored report to
  "update" it, a new run writes a new file and the diff lives there; a
  decision is a row appended, never rewritten, and the latest row for a
  finding wins, as does the latest row for a tree entry. A report is
  never modified to carry a decision: the ledger is the decision's only
  home — and a ledger is written by the script its reference names,
  which checks the row before it lands, never by a file tool; the
  reference's prose steps are the fallback where the script cannot
  run.
- A **benchmark is living source**, not a run record: it is updated in
  place through reviewed diffs, and git history, not file accumulation,
  is its memory. It is never overwritten silently — an update is a diff
  the maintainer reviews like any other committed change. A **custom
  stack file** is living source the same way.
- The consumers keep the two apart: `/odd-verify` and `/odd-status`
  treat a commit that touches only the report stores or a ledger as
  memory, not code, while a commit that changes a benchmark or a custom
  stack file is a code change.

## Recall: reading the memory

For the two report stores — a benchmark is recalled by service and by
name, a custom stack by name, each ledger is one file; their references
own that:

- List the store newest first (the filenames sort chronologically). A
  missing or empty store is a first run — say so, never fail.
- At that stage read **frontmatter blocks only**, never whole files;
  the kind's reference owns the matching rules.
- The first match is the baseline: read it **by section, never
  whole** — the kind's reference names the sections a mission needs.
  Reading beyond that set is the exception, for a stated need that the
  calling agent records.
- Older matches are history: read them only when a trend or the
  evolution of one decision matters, and only the sections in question.

## No secrets, no real identifiers

Every file of the memory is made to be committed and shared. Never
write a token, credential, cookie, or connection string into one —
refer to access material by variable or secret name only. The same for
**real identifiers** that carry no access on their own: tenant,
workspace, subscription, resource-group or site names and GUIDs,
account or login names, home-directory paths — anything that identifies
a real customer, tenant or environment. A live CLI excerpt, a
configuration display, or a mission block's preflight handoff is the
likeliest source: every such value lands in the file as an obviously
fake placeholder (`Contoso`, a zeroed or patterned GUID,
`example-user`, `<scratchpad>`). On a host that runs the package's
lifecycle hooks, a hook flags what slipped through, after the write.

## The work branch and the lone commit

- **Never commit on the default branch.** Before committing, compare
  `git branch --show-current` with the repository's default branch
  (`git symbolic-ref --short refs/remotes/origin/HEAD` stripped of its
  `origin/` prefix; if unset, `main` — or `master` when that is the
  checked-out branch). Only when on the default branch, create and
  switch to the work branch the kind's reference names (switching to it if
  it already exists), commit there, and say so in the reply. If
  switching is impossible, do not commit: state the path and leave the
  commit to the caller. On a host that runs the package's lifecycle
  hooks, a hook refuses the commit itself; this rule stays the
  enforcement everywhere else.
- **Commit the artifact's files alone**: `git add` the files the
  persistence just wrote, then `git commit` with the subject the
  kind's reference gives (`docs(odd): ...`) — never stage anything else; a
  dirty working tree stays untouched otherwise. If committing is
  impossible (not a git repository, or the caller said not to), state
  the path and leave the commit to the caller.
- Either way the reply states the stored path and the carrying commit
  (`git rev-parse --short HEAD` right after the commit), or
  `not committed` with the reason.

## The reply and the synthesis

- The persistence's return value carries the stored path, the
  carrying commit, and the **synthesis inputs** its `## Show` renders
  from — quoted from the artifact where the artifact carries the
  value, never rephrased; the kind's reference lists them — and never the
  artifact's body: an observation report runs 300 to 500 lines, the
  reply travels back into the caller's context, and the synthesis is
  its only reader. What the next wave needs is in the file, at the
  stored path.
- `## Show` renders from that return value, or reads a stored
  artifact the caller names from disk, by section, with its carrying
  commit from git (`git log -1 --format=%h -- <path>`) — never from the
  conversation's memory of the mission.
- Everything in the synthesis comes from the stored artifact: no
  backend query, no doc fetch, no re-derivation, no invented value; the
  carrying commit is the one value outside the file, and a value the
  artifact does not carry is absent from the synthesis too.
- One screen, hard cap: prefer dropping rows behind a
  `+N more in the report` marker over growing sections.
- The synthesis renders in the conversation's language; the stored
  artifact itself stays English.
- The synthesis never replaces the artifact: the next wave consumes
  the stored file — state its path, never re-inline the full body.
