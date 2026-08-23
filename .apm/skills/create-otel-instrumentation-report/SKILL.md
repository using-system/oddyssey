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
last investigation already established.

## Where reports live

```text
<investigated-repo-root>/.odd/otel-instrumentation-reports/YYYY-MM-DD-HHmm-<run_name>.md
```

- `YYYY-MM-DD-HHmm` is the investigation's **UTC** start time — to the
  minute so two same-day runs never collide, and a plain directory
  listing sorts chronologically.
- `<run_name>` is a short kebab-case slug naming what was investigated
  (e.g. `mcp-server-python`, `checkout-monorepo-full`). Name the
  content, not the date.
- Create the directory if it does not exist. The files are meant to be
  **committed**: leave them tracked, never add them to `.gitignore`.

## The file format

A YAML frontmatter, then the complete report:

```markdown
---
project: oddyssey/src/mcp-server
target: local                 # local | the remote backend name (grafana, datadog, ...)
run_name: mcp-server-python
date: 2026-08-23
---

<the investigation report, verbatim and complete>
```

- The frontmatter exists so future runs can filter reports **without
  parsing prose**: `project` names what was investigated (repo, or
  repo/path for a scoped investigation), `target` the export target the
  recommendations were derived for.
- The body is the producing agent's report **as-is** — the report
  contract (sections, tables, evidence rules) belongs to the agent, not
  to this skill. Store the whole thing.

## Recall: reading the memory

Before a new investigation, load what is already known:

1. List `.odd/otel-instrumentation-reports/` in the investigated repo
   (missing or empty directory = first investigation, no baseline — say
   so, do not fail).
2. Walk the listing newest first (filenames sort chronologically),
   reading **frontmatter blocks only** — never whole files at this
   stage. A report matches when its `project` covers the mission's scope
   and its `target` is compatible.
3. The first match is the baseline: read that one report in full — its
   stack inventory, per-service decisions, and pinned versions are what
   the new investigation diffs against (new services, changed
   frameworks, moved pins). What the comparison must report belongs to
   the calling agent's contract, not to this skill.
4. Older matches are history: read them only when the evolution of a
   specific decision matters, and only the sections in question.

## Rules

- **Never write secrets into a report**: no tokens, credentials, or
  connection strings — these files are made to be committed and shared.
  Refer to access material by variable or secret name only.
- One investigation, one file: never edit a previous report to "update"
  it — a new investigation writes a new file.
- Write the file exactly where the contract says: the report belongs to
  the **investigated** repository, not to the oddyssey package, a home
  directory, or a temp path.
- **After writing, commit the report file on its own**:
  `git add <report file>` then
  `git commit -m "docs(odd): instrumentation investigation <run_name>"` —
  never stage anything else; a dirty working tree stays untouched
  otherwise. If committing is impossible (not a git repository, or the
  caller said not to), state the path and leave the commit to the
  caller.
- Either way, state the stored path in the reply.
