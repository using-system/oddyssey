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

The report to render, in one of two forms:

- **The persistence return value** — what `create-observe-run-report`
  just returned for the mission being closed, carried in the agent's
  reply: the stored path, the carrying commit (or `not committed`),
  and the synthesis block — the frontmatter, section 1's
  recalled-baseline line, section 2's delta lines, check rulings or
  presence rulings, section 3's ranked table with the baseline
  anomalies' fates, the telemetry gaps with the baseline gaps' fates,
  and the open decisions, quoted from the file (the persistence
  skill's `## Return value` owns the list). Render from it; never
  re-read the file it just wrote — the block carries every input the
  synthesis below reads, and a value it lacks is absent from the
  synthesis (the way `show-benchmark` renders from
  `create-update-benchmark`'s return).
- **A stored report the caller names** — no return value in hand:
  read from disk the same set — that file's frontmatter, section 1's
  recalled-baseline line, section 2's delta lines, check rulings or
  presence rulings, section 3's table, sections 5 and 6 — never the
  whole file — and its carrying commit from git
  (`git log -1 --format=%h -- <path>`).

Either way the synthesis renders the stored content, never the
conversation's memory of the mission.

## The synthesis, in order

1. **Headline** — one bold line answering "how did it go", shaped by
   the report's `mode`: an observation leads with counts and the
   baseline delta (`3 anomalies (1 high, confirmed), 2 telemetry
   gaps, p95 stable vs baseline`); a verification leads with the
   ruling (`FAIL — 2/5 checks red`); a re-measure leads with drift
   (`no drift — 5/5 measurements within range`). A `quick` report says
   so in the headline (`quick — 1 anomaly (suspected), logs and
   profiles not queried`), and a quick verify counts what it did not
   rule (`PASS — 3/3 checks ruled, 2 not ruled (quick)`).
2. **Where it lives** — one line: the stored path and the commit that
   carries it.
3. **Run block** — compact `key: value` lines: services, stack, mode,
   depth (`full` when the frontmatter has none), window, detected
   environment (all from the frontmatter), and the baseline report
   used — `verifies` when present, else section 1's recalled
   baseline, or "none" when the report names none.
4. **The core, by kind** — tables, capped at ~10 rows with a
   `+N more in the report` marker:
   - observation / re-measure: the findings table (severity |
     confidence | one-line anomaly), then the telemetry gaps, one
     line each;
   - verification: the verdict table first (check | before | after |
     pass/fail), then the anomalies ruled fixed / still present /
     worse and the gaps ruled filled / still missing, one line each —
     for an instrumentation baseline, the presence rulings instead
     (planned item | closed / present, unattributed / still missing),
     and nothing else to rule.
5. **Decisions the spec must settle** — the count, then one line per
   open question.
6. **Next action** — one line naming the loop's next step: build the
   fix plan from the report, replay the protocol with `/odd-verify`,
   or settle the open decisions first.

## Rules

The memory contract's synthesis rules (`odd-memory`): everything from
the stored report, the carrying commit the one value outside it; one
screen with `+N more`; the conversation's language; never a
replacement for the file.
