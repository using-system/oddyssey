---
name: show-otel-instrumentation-report
description: Render a short synthesis of a persisted OpenTelemetry instrumentation investigation report for the human closing the mission - verdict-first headline, the stored path, the plan-at-a-glance table, the open decisions, and the recommended next action - never a replacement for the report itself. Use when an /odd-instrument-otel mission ends and the final answer must synthesize the stored report instead of dumping it raw.
---

# Show an OTel Instrumentation Report

The stored report is the input the spec-driven instrumentation plan is
built from — the right artifact for the next wave, the wrong one for
the human closing the mission: several screens of tables, env blocks,
and doc links bury the takeaways. This skill renders the closing
synthesis. The report file stays the deliverable; only what the human
sees at the end of the mission changes.

## Input

The persisted report to render: the file the
`create-otel-instrumentation-report` skill just stored, or any stored
report the caller names. Read it from disk — the synthesis renders
the stored file, not the conversation's memory of it.

## The synthesis, in order

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

## Rules

- Everything comes from the stored report: no doc fetch, no
  re-derivation, no invented package or version (the carrying commit,
  read from git, is the one value outside the file) — a value the
  report does not carry is absent from the synthesis too.
- One screen, hard cap: trim the summary table's widest columns
  (endpoint, signals) before dropping rows; a dropped row gets a
  `+N more in the report` marker.
- Render in the conversation's language; the stored report itself
  stays English.
- The synthesis never replaces the report: the plan is built from the
  stored file — state its path, never re-inline the full body.
