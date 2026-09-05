# Instrumentation reports

An instrumentation investigation that vanishes with the conversation must
be redone from scratch the next time the stack changes. This reference
defines
the file contract that persists it: reports live **in the investigated
repository**, so git versions them, PRs review them, and every user of the
repo shares them — the next SDD instrumentation wave starts from what the
last investigation already established. What every kind of memory
shares is the contract in `SKILL.md`; this reference states what is
specific to instrumentation reports: how to persist one, how to recall
the baseline, and how to show a stored one (`## Show`).

## Where reports live

```text
<investigated-repo-root>/.odd/otel-instrumentation-reports/YYYY-MM-DD-HHmm-<run_name>.md
```

- `YYYY-MM-DD-HHmm` and `<run_name>` follow the memory contract: UTC
  via `date -u` (so does `date:`), and a slug naming what was
  investigated (`mcp-server-python`, `checkout-monorepo-full`).

## The file format

A YAML frontmatter, then the complete report:

```markdown
---
project: oddyssey/src/mcp-server
stack: local                  # local | the remote backend name (grafana, datadog, ...)
run_name: mcp-server-python
date: 2026-08-23
revision: 2299d4c             # optional: commit of the investigated repo
tree_anchor: {src: "5ea231f…", tests: "8e29aac…"}  # optional: FULL top-level entry map at revision (git ls-tree) - the squash-proof anchor
repository: github.com/example-org/checkout  # optional: the repository revision was taken from - its origin remote, normalized
---

<the investigation report, verbatim and complete>
```

- The frontmatter exists so future runs can filter reports **without
  parsing prose**: `project` names what was investigated (repo, or
  repo/path for a scoped investigation), `stack` the export stack the
  recommendations were derived for, `revision` which code the findings
  hold for (`git rev-parse --short HEAD`) — the stack may have changed
  since. In a squash-merge repository that commit never joins the
  merged history, so record `tree_anchor` alongside it: the full
  top-level entry map of `git ls-tree <revision>`, one
  `name: object-hash` pair per entry — the squash-proof,
  clone-resolvable form of "which code the findings hold for".
  `repository` names the repository both were taken from, taken at
  the same moment: the `origin` remote (`git remote get-url origin` in that
  repository) normalized so that two agents on the same repository
  always write the same value: the host lower-cased, then the remote's
  path as it is (its case kept, any depth — `gitlab.com/group/subgroup/project`
  is as valid as `github.com/org/repo`); the scheme, the user info
  and the port dropped, one trailing `/` and one trailing `.git`
  stripped; the SSH form `git@host:owner/name.git` read as
  `host/owner/name`. A token in the remote URL is a secret: it never
  reaches the report, the run record or the reply. No remote, no value — never a local
  path (the no-secrets rule). A plan investigates one repository, so
  the value is a scalar; `project` keeps naming what was investigated
  in it (the repository, or a path inside it) and does not change.
  Absent on a report that predates the field; a consumer then reads
  the report as investigating the repository it is stored in.
- The body's sections are the agent's contract — five, numbered, and
  read by number. One subsection is optional, named here so the
  recall, the synthesis and a reader find it: a service whose
  manifest names a model SDK carries a **GenAI approach** under a
  `### GenAI approach` heading in section 3 — prose, never a table:
  the instrumentation library the plan adopts, what it emits, what
  stays hand-coded (cost, the agent loop) and the content-capture
  switch with its direction — and two entries in section 4, prompt
  and completion content capture and cost attribution, open like every
  other decision there. Absent on a service that calls no model; a
  report predating the subsection simply lacks it.

## Recall: reading the memory

Before a new investigation, load what is already known, per the
memory contract's recall (the script first, newest first, the baseline
by section; frontmatter only, by hand, when the script cannot run) —
the matching rules are this reference's:

1. Run the recall script in the investigated repo:
   `python3 <this skill's directory>/scripts/odd_recall.py --repo
   <path> --kind instrumentation --project <scope> [--stack <stack>]`
   — it lists `.odd/otel-instrumentation-reports/` newest first and
   prints the matches by the rule below, one tab-separated line each,
   the same ten columns as an observation's with `project` in the
   third and `-` in the observation-only ones.
2. A report matches when its `project` covers the mission's scope
   (equal to it, or a parent path of it) and its `stack` is the
   mission's when one is named.
3. The first match — the first line printed — is the baseline: its
   stack inventory, per-service decisions (their GenAI approach with
   them, when a service carries one) and pinned versions are the
   sections the new investigation diffs against (new services, changed
   frameworks, moved pins, a model SDK added or dropped). What the
   comparison must report belongs to the calling agent's contract, not
   to this reference.

## Rules

- **No secrets, no real identifiers** (the memory contract) — a live
  CLI excerpt (a component's `show` output, a resource id) is the
  likeliest source. The rule reaches the **verification protocol's
  checks**: a check whose query projects
  a credential-bearing field (a connection string, a key, a token, an
  auth-header value) or whose expected outcome is one is a leak
  deferred, not avoided — `/odd-verify` replays the query verbatim and
  quotes its result into a committed report. A check proves a secret
  is wired by naming the wiring (a secret reference, an env var name,
  a redacted flag, the resource identity it binds to), never the value.
- **The work branch** (the memory contract) is
  `docs/odd-instrumentation-report-<run_name>`; **the commit** carries
  the report file alone, subject
  `docs(odd): instrumentation investigation <run_name>`.

## Show

The stored report is the input the spec-driven instrumentation plan is
built from — the right artifact for the next wave, the wrong one for
the human closing the mission: several screens of tables, env blocks,
and doc links bury the takeaways. This section renders the closing
synthesis. The report file stays the deliverable; only what the human
sees at the end of the mission changes.

### Input

The persisted report to render: the file the
persistence step above just stored, or any stored
report the caller names — read from disk by section (its summary
table, its open decisions, its verification protocol), per the
contract (`SKILL.md`), never from the conversation's memory of it.

### The synthesis, in order

1. **Headline** — one bold line answering "what will happen": services
   covered, dominant approach, package count, open decisions
   (`2 services, zero-code approach, 7 pinned packages, 3 decisions
   open`).
2. **Where it lives** — one line: the stored path and the commit that
   carries it.
3. **Plan at a glance** — the report's own summary table (its
   section 2), reused as-is: it already carries one row per service
   with approach, pinned key packages, effort, and risk flags — the
   pinned packages ARE what the implementation wave will add. Follow
   it with the recommended implementation order, one line.
4. **Decisions the spec must settle** — the count, then one line per
   open question (the report's section 4).
5. **Next action** — one line naming the loop's next step: build the
   spec-driven plan from the report, or settle the open decisions
   first — and a one-line pointer to the verification protocol (the
   report's section 5 carries the replayable checks a later
   `/odd-verify` run rules on).

### Rules

The contract's synthesis rules apply; the one specific: trim the
summary table's widest columns (endpoint, signals) before dropping
rows behind the `+N more in the report` marker.
