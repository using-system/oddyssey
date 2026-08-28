# /odd-status Wontfix Ledger — Design

Implements [#131](https://github.com/using-system/oddyssey/issues/131)
(finding decisions ledger, two-skill restructuring of `/odd-status`) and
absorbs [#110](https://github.com/using-system/oddyssey/issues/110)
(defined no-match behavior), per the grouping comments on both issues.
The implementing PR closes both.

## Problem

`/odd-status` knows three states for a finding: open,
fixed-and-verified, or regressed — and its contract is explicit that "a
finding no verification ever ruled on stays open, whatever a commit
message claims". A finding the maintainer has decided **not** to treat
(F4's ~14.5 s port-move hang, accepted) therefore renders as "open" in
every status, forever.

The loop has only half a mechanism for this: verify runs can rule
"accepted by design", and reports queue arbitrations under "Decisions
the spec must settle" — but both exist only *inside* an observe/verify
run. A decision taken cold, between runs, has no committed home that
`/odd-status` reads. That is the actual hole: not the absence of a
wontfix label, but the absence of a committed carrier for out-of-run
decisions.

A second, smaller hole (#110): a filtered status
(`/odd-status for service X on stack Y`) with no matching report has
undefined behavior.

## Constraints (from the maintainer, recorded in conversation and issues)

1. **No new `/odd-*` command.** The prompt surface must not grow; the
   `/odd-config` routing pattern (thin prompt, skills own the logic) is
   the model.
2. **Reports are immutable evidence.** No mechanism may edit a stored
   report — decisions live in a separate committed artifact.
3. **Offline computability.** The status stays derivable from the clone
   alone: no backend queries, no GitHub-state dependency (issue labels
   are not a source).
4. **Skill names** are fixed by the issue: `get-status` and
   `record-finding-decision` (extensible-verdict naming chosen over
   `wont-fix`).

## Design

### The decisions ledger — `.odd/decisions.md`

A committed, append-only markdown ledger; one table row per decision:

| Column | Content |
|---|---|
| Date | decision's UTC date, `YYYY-MM-DD` |
| Finding | `<exact report filename> / <finding ID>` — finding IDs are report-local (two reports can both carry an "F4"), so the filename is the disambiguator |
| Verdict | `wontfix` today; free-form so `accepted-by-design` or others need no format change; `open` reopens |
| Rationale | one required sentence; no secrets |

Rows are appended, never rewritten; the latest row for a finding wins.
Reversal is a new `open` row — history stays readable, like the
reports it complements. The file is created on first decision from a
fixed skeleton (the `record-finding-decision` skill owns the exact
text).

### Skill `record-finding-decision` — the only write

Resolves the caller's reference to `report filename + finding ID`
(asking when a bare ID matches several reports — never guessing),
requires a rationale, appends the row (creating the file when absent),
and commits the ledger file alone
(`docs(odd): finding decision <finding ID> <verdict>`), mirroring the
report-persistence skills' commit ritual. It never touches a report.

### Skill `get-status` — the rendering

Takes over the whole rendering contract of the current `/odd-status`
prompt — sources, the six build steps (per-service loop state, findings
ledger, trends, gaps, next action), graceful degradation — semantics
preserved, including the `mode: re-measure` rules and squash-merge
coverage caveats. Two additions:

- **Decision cross-reference:** a finding whose latest ledger row
  carries a declining verdict renders as **declined** (verdict, date,
  rationale) instead of open; the burn-down counts
  open / fixed-and-verified / regressed / declined separately. The
  "stays open, whatever a commit message claims" rule keeps its force,
  amended by "— unless the decisions ledger declines it".
- **Defined no-match (#110):** a filtered status with no matching
  report states what was searched (each filter and value) and what
  exists (the distinct services, stacks, environments across stored
  frontmatters) and stops — that IS the status, never an error, never a
  silent empty table.

### Prompt `/odd-status` — thin router

Keeps mission, arguments, and contract; delegates rendering to
`get-status`; on an explicit decision request (in the arguments or as a
follow-up), routes to `record-finding-decision` and re-renders the
affected finding. Contract amendment: reports remain read-only here;
the decisions ledger is the prompt's only write surface; still no
backend queries, still no committed status artifact.

### Out of scope

- `/odd-verify` ratification of ledger decisions in its rulings tables
  (a possible later wave; the ledger alone closes the hole).
- Documenting `decisions.md` in `docs/guide/reports.md` (the ledger is
  not a report; its format authority is the skill).

## Acceptance

1. Recording a decision makes the next `/odd-status` render that
   finding as declined (verdict, date, rationale) instead of open.
2. No mechanism introduced here modifies `.odd/observe-run-reports/`.
3. The status remains computable offline from the clone alone.
4. A filtered `/odd-status` with no match states what was searched and
   what exists (#110's acceptance).
5. AGENTS.md sync duties honored in the same change:
   `docs/guide/prompts.md`, `docs/guide/dependencies.md`, README
   primitives table and `/odd-status` subsection.
