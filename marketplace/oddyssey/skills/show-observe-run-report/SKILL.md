---
name: show-observe-run-report
description: Render a short synthesis of a persisted observation report for the human closing the mission - verdict-first headline, the stored path, a compact run block, the findings that matter, and the recommended next action - never a replacement for the report itself. Use when an /odd-observe or /odd-verify mission ends and the final answer must synthesize the stored report instead of dumping it raw.
---

# Show an Observe-Run Report

The stored report is the ODD loop's memory and the fix plan's input —
the right artifact for the next wave, the wrong one for the human
closing the mission: several screens deep, the takeaways drown. This
skill renders the closing synthesis. The report file stays the
deliverable; only what the human sees at the end of the mission
changes.

## Input

The persisted report to render: the file the
`create-observe-run-report` skill just stored, or any stored report
the caller names. Read it from disk — the synthesis renders the
stored file, not the conversation's memory of it.

## The synthesis, in order

1. **Headline** — one bold line answering "how did it go", shaped by
   the report's `mode`: an observation leads with counts and the
   baseline delta (`3 anomalies (1 high, confirmed), 2 telemetry
   gaps, p95 stable vs baseline`); a verification leads with the
   ruling (`FAIL — 2/5 checks red`); a re-measure leads with drift
   (`no drift — 5/5 measurements within range`).
2. **Where it lives** — one line: the stored path and the commit that
   carries it.
3. **Run block** — compact `key: value` lines: services, stack, mode,
   window, detected environment (all from the frontmatter), and the
   baseline report used — `verifies` when present, else section 1's
   recalled baseline, or "none" when the report names none.
4. **The core, by kind** — tables, capped at ~10 rows with a
   `+N more in the report` marker:
   - observation / re-measure: the findings table (severity |
     confidence | one-line anomaly), then the telemetry gaps, one
     line each;
   - verification: the verdict table first (check | before | after |
     pass/fail), then the anomalies ruled fixed / still present /
     worse and the gaps ruled filled / still missing, one line each —
     for an instrumentation baseline, the presence rulings instead
     (planned item | closed / still missing), and nothing else to
     rule.
5. **Decisions the spec must settle** — the count, then one line per
   open question.
6. **Next action** — one line naming the loop's next step: build the
   fix plan from the report, replay the protocol with `/odd-verify`,
   or settle the open decisions first.

## Rules

- Everything comes from the stored report: no backend query, no
  re-derivation, no invented number (the carrying commit, read from
  git, is the one value outside the file) — a value the report does
  not carry is absent from the synthesis too.
- One screen, hard cap: prefer dropping rows (behind the `+N more`
  marker) over growing sections.
- Render in the conversation's language; the stored report itself
  stays English.
- The synthesis never replaces the report: the next wave consumes the
  stored file — state its path, never re-inline the full body.
