# Maintainer rulings

A finding no verification ever ruled on stays open forever — the status
has no other verdict for it, however deliberately the maintainer decided
to live with it. The decision is real, it is just homeless: it was taken
between runs, and the only artifacts that could carry it are past
evidence that must never be rewritten. This reference gives it a committed
home of its own, next to the reports and never inside them. The same
holds for a second ruling the status needs and cannot make alone —
whether a top-level tree entry of the repository can change the
observed services' runtime — which gets a ledger of its own below.
What every kind of memory shares is the contract in `SKILL.md`; this
reference states what is specific to the two ledgers.

## The finding ledger

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
in the reply that the row was written by hand. On a host that runs the
package's hooks the by-hand append is refused - the script is the
ledgers' only writer there; the fallback is for hosts without hooks.

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

## The entry-classification ledger

`/odd-status` decides whether the commits since a report changed the
observed service's runtime by comparing the report's tree anchor with
HEAD, entry by entry. It knows a built-in list of names that cannot
change any service's runtime in any repository (`.github`, `docs`,
`README.md`, ...) and defers every other entry it cannot classify —
`.apm`, `src`, a `marketplace` directory — to a judgment that is the
same on every run of the same repository. This ledger records that
judgment once.

Path: `<repo-root>/.odd/entry-classifications.md`, committed. Created
on first ruling with this exact skeleton:

```markdown
# ODD entry classifications

Rulings the maintainer took on the repository's top-level tree entries
— whether a change under one can alter the observed services' runtime
behavior — the committed memory that lets `/odd-status` settle a
report's code boundary without asking again. Rows are appended, never
rewritten; a later row for the same entry supersedes the earlier one.
A flag given to the status script overrides a row for one run and
persists nothing.

| Date | Entry | Class | Rationale |
|---|---|---|---|
```

One row per ruling:

```markdown
| 2026-09-05 | .apm | non-runtime | the package's prompts, agents and skills - never on the request path |
```

- `Date` — the ruling's UTC date, `YYYY-MM-DD`.
- `Entry` — a top-level path of the repository exactly as
  `git ls-tree HEAD` names it (`src`, `.apm`, `apm.yml`); the script
  checks the exact name, the status reads it case-insensitively, as
  it reads the flags and the built-in list. Never `.odd`: the tree
  anchor always ignores it.
- `Class` — `runtime` or `non-runtime`.
- `Rationale` — one sentence, required. No secrets.

**Recording a classification** — `classify <entry> <runtime|non-runtime>
--rationale "<sentence>"` with the script above: it checks that the
entry is a top-level entry of HEAD, requires the rationale under the
same rules as a decision's, appends the row (the skeleton when the
file is absent) and leaves the rows above untouched; it prints the
path, the row, the work branch
`docs/odd-entry-classification-<entry>-<class>` (both values
normalized as a decision's branch is) and the commit subject
`docs(odd): entry classification <entry> <class>`. The commit carries
`.odd/entry-classifications.md` alone, on that branch, under the
memory contract; the reply states the appended row with the path and
the commit, and that a ruling on a work branch reaches `/odd-status`
on the default branch only once that branch is merged. A change of
mind is a new row, never a rewrite. By hand, only when the script
cannot run and the host runs no hook of the package: the same steps,
and say so.

**Not recorded**: an entry that is runtime for one lineage and not
for another — the ledger holds for the whole repository, so the
deferral stays and the status says so; and an entry the built-in list
already settles, unless the repository contradicts it (a `docs`
directory the service serves is a `runtime` row).

**How the status reads it** — precedence, the same the flags always
had: a `--runtime` / `--non-runtime` flag for one run, then the
latest row of this ledger for the entry, then the built-in list. A
ruling settles an entry whose hash differs from the anchor's; an
entry present on one side only — added or removed since the anchor —
stays uncertain whatever its ruling. A row naming no top-level entry
of HEAD, or a class the rule does not know, is reported and skipped
by the memory invariant, never fatal — a new row supersedes it. A
commit that touches only this ledger is memory, not code.
