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
- `Verdict` — one word: `wontfix` today, and the column is free-form
  beyond that so later verdicts (e.g. `accepted-by-design`) need no
  format change; `open` is reserved for a reversal.
- `Rationale` — one sentence, required. No secrets.

## Recording a decision

The ledger is written by the script this skill carries — standard
library and git only — never by a file tool: it applies every rule
below before one row lands, and writes nothing when one fails; one
stderr line names the reason, exit code 2. Invoke it as

```bash
python3 <this skill's directory>/scripts/odd_ledger.py --repo <path inside the repository> <subcommand> ...
```

`--help` lists the rest.

1. **Resolve the finding** to `report filename + finding ID` — the
   row's `Finding` value is only as good as this step. When the caller
   names the report, the key is `<report filename>/<ID>` and step 3
   checks it. When the caller gives only an ID ("wontfix F4"), run
   `resolve F4`, with `--service`, `--stack` or `--env` for whatever
   the caller named: it lists the stored reports whose ranked-findings
   table (or section 3 prose) carries the ID, newest first, with the
   finding's title — one match (exit 0) is the key; several (exit 3)
   are a question, never a guess: show the list and **ask** which one;
   none (exit 2) is **say so and stop** — a row pointing at a finding
   that does not exist is worse than no row. The script reads a
   report's section 3 exactly as the status does, so a row it accepts
   is a row the memory invariant accepts; a stored report it cannot
   read stops `resolve` with its name — never guess around it.
2. **Require a rationale.** A decision without one is not recordable:
   the ledger's whole value is that a future reader learns *why* a
   finding stopped counting as open, and "wontfix" alone teaches
   nothing. Ask for the sentence; do not invent one from the report's
   own prose. The script refuses an empty rationale, a multi-line one,
   one carrying a `|`, and one carrying a real identifier — a GUID, a
   personal home path, a value of the global configuration's
   `stack_config` — with the placeholders the no-secrets rule
   recommends (a zeroed GUID, `<user>`, `Contoso`) accepted.
3. **Append the row**:
   `decide <report filename>/<ID> <verdict> --rationale "<sentence>"`.
   The script checks that the report is stored and carries the ID,
   creates the file with the skeleton above when it is absent (and
   `.odd/` too), appends one row — today's UTC date, or the day a
   decision was actually taken with `--today YYYY-MM-DD`, the
   resolved `<filename> / <ID>`, the verdict (one word), the rationale
   on one line — and leaves every existing row byte for byte as it
   was. It prints the path, the row, the work branch and the commit
   subject of the Rules below.
4. **A reversal is a new row**:
   `reopen <report filename>/<ID> --rationale "<sentence>"` — the
   verdict `open`, the one verdict the status recognizes as reopening;
   never delete or rewrite the superseded row. The latest row for a
   finding wins, and the history of the decision stays readable,
   exactly like the reports this ledger complements; `decide` refuses
   the verdict `open` for that reason.

**By hand, only when the script cannot run** (no `python3`, an
install that dropped `scripts/`): the same four steps applied by you —
open the named report and confirm its ranked-findings table carries
the ID, or list `.odd/observe-run-reports/` and read **bodies only for
candidates whose frontmatter matches** what the caller named; create
the file with the skeleton when absent; append the row with today's
UTC date (`date -u`); never reflow or re-sort the existing rows. Say
in the reply that the row was written by hand.

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
  `docs(odd): finding decision <finding ID> <verdict>`. The script
  prints both values; the branch and the commit stay yours, under the
  memory contract's rule.
- The reply states the appended row with the path and the commit —
  and that a decision on a work branch reaches `/odd-status` on the
  default branch only once that branch is merged, so it is not
  recorded a second time from there.
