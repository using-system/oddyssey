# Finding decisions

A finding no verification ever ruled on stays open forever — the status
has no other verdict for it, however deliberately the maintainer decided
to live with it. The decision is real, it is just homeless: it was taken
between runs, and the only artifacts that could carry it are past
evidence that must never be rewritten. This reference gives it a committed
home of its own, next to the reports and never inside them. What every
kind of memory shares is the contract in `SKILL.md`; this reference
states what is specific to the ledger.

## The ledger

Path: `<repo-root>/.odd/decisions.md`, committed. Created on first
decision with this exact skeleton:

```markdown
# ODD finding decisions

Decisions the maintainer took on findings recorded in
`.odd/observe-run-reports/` — the committed memory that lets
`/odd-status` stop rendering a declined finding as open. Rows are
appended, never rewritten; a later row for the same finding supersedes
the earlier one. Reports themselves are never edited — this ledger is
the only place a decision lives.

| Date | Finding | Verdict | Rationale |
|---|---|---|---|
```

One row per decision:

```markdown
| 2026-08-28 | 2026-08-26-1003-config-set-env-preservation.md / F4 | wontfix | Port-move is rare; ~14.5 s accepted |
```

- `Date` — the decision's UTC date, `YYYY-MM-DD`.
- `Finding` — `<exact report filename> / <finding ID as the report's
  ranked-findings table names it>`. The exact filename disambiguates
  finding IDs, which are report-local (two reports can both have an
  "F4").
- `Verdict` — `wontfix` today; the column is free-form so later verdicts
  (e.g. `accepted-by-design`) need no format change.
- `Rationale` — one sentence, required. No secrets.

## Recording a decision

1. **Resolve the finding** to `report filename + finding ID` — the row's
   `Finding` value is only as good as this step. When the caller names
   the report, open it and confirm its ranked-findings table carries
   that ID; when it does not, **say so and stop** — a row pointing at a
   finding that does not exist is worse than no row. When the caller
   gives only an ID ("wontfix F4"), list
   `.odd/observe-run-reports/` and find which reports' ranked-findings
   tables carry it, reading **bodies only for candidates whose
   frontmatter matches** any service, stack, or environment the caller
   named — the frontmatter is what keeps this from becoming a
   full-corpus read. More than one match is a question, never a guess:
   list the matching filenames with the finding's title from each and
   **ask** which one.
2. **Require a rationale.** A decision without one is not recordable:
   the ledger's whole value is that a future reader learns *why* a
   finding stopped counting as open, and "wontfix" alone teaches
   nothing. Ask for the sentence; do not invent one from the report's
   own prose.
3. **Append the row.** Create the file with the skeleton above when it
   is absent (create `.odd/` too if needed), then append one row —
   today's UTC date, the resolved `<filename> / <ID>`, the verdict, the
   rationale on one line. Never reflow or re-sort the existing rows.
4. **A reversal is a new row**, with the verdict `open` — the one
   verdict the status recognizes as reopening — and its own rationale;
   never delete or rewrite the superseded row. The latest row for a
   finding wins, and the history of the decision stays readable,
   exactly like the reports this ledger complements.

## Rules

- **Recording a decision writes `decisions.md` and nothing else.** A decision
  that "should be in the report" is still a ledger row: reports are
  append-only evidence (the memory contract).
- **No secrets** in a rationale (the memory contract).
- **The work branch** (the memory contract) is
  `docs/odd-finding-decision-<finding ID>-<verdict>`, both values
  normalized for the branch name only: lowercased, every run of
  characters outside `[a-z0-9]` replaced by a single `-`, leading and
  trailing `-` trimmed (`A5 (2026-08-22-2227)` + `wontfix` →
  `docs/odd-finding-decision-a5-2026-08-22-2227-wontfix`); the ledger
  row keeps the finding ID exactly as the report names it. **The
  commit** carries `.odd/decisions.md` alone, subject
  `docs(odd): finding decision <finding ID> <verdict>`.
- The reply states the appended row with the path and the commit —
  and that a decision on a work branch reaches `/odd-status` on the
  default branch only once that branch is merged, so it is not
  recorded a second time from there.
