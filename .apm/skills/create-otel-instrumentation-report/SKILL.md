---
name: create-otel-instrumentation-report
description: Persist an OpenTelemetry instrumentation investigation report into the investigated repository at .odd/otel-instrumentation-reports/ with a structured frontmatter, commit it, and recall previous investigations of the same project - the file contract that keeps instrumentation expertise feeding later SDD waves. Use when storing the report an instrumentation investigation produced, or when loading past investigations before a new one.
---

# Create an OTel Instrumentation Report

An instrumentation investigation that vanishes with the conversation must
be redone from scratch the next time the stack changes. This skill defines
the file contract that persists it: reports live **in the investigated
repository**, so git versions them, PRs review them, and every user of the
repo shares them — the next SDD instrumentation wave starts from what the
last investigation already established. What every kind of memory
shares is the `odd-memory` skill's contract; this skill states what is
specific to instrumentation reports.

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

## Recall: reading the memory

Before a new investigation, load what is already known, per the
memory contract's recall (newest first, frontmatter only at this
stage, the baseline by section) — the matching rules are this skill's:

1. List `.odd/otel-instrumentation-reports/` in the investigated repo.
2. A report matches when its `project` covers the mission's scope and
   its `stack` is compatible.
3. The first match is the baseline: its stack inventory, per-service
   decisions and pinned versions are the sections the new
   investigation diffs against (new services, changed frameworks,
   moved pins). What the comparison must report belongs to the calling
   agent's contract, not to this skill.

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
