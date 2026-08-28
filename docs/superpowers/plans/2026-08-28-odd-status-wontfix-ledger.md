# /odd-status Wontfix Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the ODD loop a committed ledger of finding decisions
(`.odd/decisions.md`) so a finding the maintainer declines to fix stops
rendering as "open" in every `/odd-status`, and restructure `/odd-status`
into a thin prompt over two new skills — `get-status` (rendering, absorbs
the #110 no-match fix) and `record-finding-decision` (ledger writes).

**Architecture:** The `/odd-status` prompt keeps only mission, arguments,
and contract, and routes to skills the way `/odd-config` already routes to
`check-backend-configuration`/`update-backend-configuration`. Reports stay
immutable; the ledger is a new append-only artifact the status
cross-references. No backend queries anywhere; status is computable
offline from the clone alone.

**Tech Stack:** Markdown contracts under `.apm/` (APM package primitives);
no executable code. The agent/skill markdown files are executable
contracts: wording changes are behavior changes.

**Spec:** `docs/superpowers/specs/2026-08-28-odd-status-wontfix-ledger-design.md`
(authored from issues [#131](https://github.com/using-system/oddyssey/issues/131)
and [#110](https://github.com/using-system/oddyssey/issues/110), absorbed
per the comments on both). The implementing PR must carry `Closes #131`
and `Closes #110`.

## Global Constraints

- Every committed artifact in English (AGENTS.md "English only").
- No secrets anywhere (AGENTS.md).
- `marketplace/`, `.claude-plugin/`, `.agents/plugins/` are generated —
  never touched (AGENTS.md).
- Cross-references between `.apm/` primitives are **by name only, never by
  path** — they must survive materialization into any CLI (CONTRIBUTING
  "two-minute orientation" table).
- `.odd/` reports are append-only and never edited; the new
  `.odd/decisions.md` is a **ledger, not a report**: rows are appended,
  never rewritten — a later row for the same finding supersedes the
  earlier one (latest wins).
- Docs sync duties (AGENTS.md): `docs/guide/prompts.md`,
  `docs/guide/dependencies.md`, and the README tables are updated in the
  same change (Task 4).
- Conventional Commits on every commit; no `!`/`BREAKING CHANGE` marker.
- One skill file per skill: `.apm/skills/<name>/SKILL.md` with a YAML
  frontmatter carrying exactly `name:` and `description:` (see any
  sibling skill). The description is the trigger contract — write it in
  the same "Use when ..." register as the siblings.
- House prose register: dense, imperative, em-dash-heavy; read two
  sibling skills before writing (`create-observe-run-report`,
  `update-backend-configuration`).

## The ledger contract (shared by Tasks 1-3 — verbatim reference)

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

---

### Task 1: `record-finding-decision` skill

**Files:**
- Create: `.apm/skills/record-finding-decision/SKILL.md`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the ledger contract above (quote it in the skill — it is the
  file-format authority other components point at) and the skill name
  `record-finding-decision` that Tasks 2-4 reference.

- [ ] **Step 1: Read the register sources** — `.apm/skills/create-observe-run-report/SKILL.md`
  (the persistence-skill house pattern: where files live, commit rules,
  no-secrets rule, "state the stored path in the reply") and
  `.apm/skills/update-backend-configuration/SKILL.md` (a skill that owns
  a write and guards it).

- [ ] **Step 2: Write the skill.** Frontmatter `name:
  record-finding-decision`; description in the sibling register, e.g.:
  "Record a maintainer decision (wontfix, ...) on a finding of a stored
  observation report into the committed ledger at .odd/decisions.md —
  the write that lets /odd-status stop rendering a declined finding as
  open. Use when the user declines a finding, marks it wontfix, or
  reverses such a decision. Never edits a report."
  Body sections, in this order:
  1. **Why** — one short paragraph: findings a verification never rules
     on stay open forever in the status; the decision needs a committed
     home that is not an edit of past evidence.
  2. **The ledger** — the exact contract from "The ledger contract"
     above, including the creation skeleton and the row format, verbatim.
  3. **Recording a decision** — the procedure: (a) resolve the finding to
     `report filename + finding ID`: when the caller gives only an ID,
     list `.odd/observe-run-reports/`, find which reports' ranked-findings
     tables carry that ID (read bodies only for candidates whose
     frontmatter matches any service/stack the caller named), and **ask**
     when more than one matches — never guess; when the report named
     carries no such finding ID, say so and stop; (b) require a
     rationale — a decision without one is not recordable; (c) append the
     row (create the file with the skeleton first when absent);
     (d) reversal is a new row with the new verdict (e.g. `open`) — never
     delete or rewrite rows.
  4. **Rules** — never modify or delete a report (`.odd/` reports are
     append-only; this skill writes only `decisions.md`); no secrets in
     rationales; after writing, commit the ledger file alone:
     `git add .odd/decisions.md` then
     `git commit -m "docs(odd): finding decision <finding ID> <verdict>"`
     — never stage anything else; if committing is impossible, state the
     path and leave the commit to the caller; either way state the
     ledger path and the appended row in the reply.

- [ ] **Step 3: Self-check.** Grep your file: it must reference other
  primitives by name only (no `.apm/` paths); it must quote the exact
  skeleton; frontmatter has exactly `name` and `description`.

- [ ] **Step 4: Commit**

```bash
git add .apm/skills/record-finding-decision/SKILL.md
git commit -m "feat(skill): record-finding-decision - the committed wontfix ledger of the ODD loop"
```

### Task 2: `get-status` skill

**Files:**
- Create: `.apm/skills/get-status/SKILL.md`
- Read (source to migrate from): `.apm/prompts/odd-status.prompt.md`

**Interfaces:**
- Consumes: the ledger contract (quoted in "The ledger contract" above;
  the authority lives in the `record-finding-decision` skill — point at
  it **by name**).
- Produces: the skill name `get-status` and the full rendering contract
  that Task 3's thin prompt delegates to.

- [ ] **Step 1: Read the sources** — the current
  `.apm/prompts/odd-status.prompt.md` (its numbered build steps 1-6, the
  sources block, and the degrade-gracefully rule are the contract to
  migrate — preserve their semantics INCLUDING the `mode: re-measure`
  rules and the squash-merge coverage caveats, verbatim where possible),
  issue #110 (`gh issue view 110`) for the no-match behavior, and one
  sibling skill for register.

- [ ] **Step 2: Write the skill.** Frontmatter `name: get-status`;
  description e.g.: "Render the state of the ODD loop from the
  repository's committed .odd/ history and git alone - per-service loop
  state, findings ledger, trends, open telemetry gaps, next recommended
  action - read-only, no backend queries, no report written. Use when
  answering where the loop is, when /odd-status runs, or when a status
  must be computed offline from the clone."
  Body:
  1. **Sources — and nothing else**: migrated from the prompt (the two
     report directories, frontmatters first; git metadata), **plus**
     `.odd/decisions.md` — read via the ledger contract owned by the
     `record-finding-decision` skill (name reference). Never query a
     backend, never start the stack, never write anything — this skill
     reads the loop; the one write in the status surface belongs to
     `record-finding-decision`.
  2. **Build the status in this order**: the six steps migrated from the
     prompt with two integrations:
     - Step 3 (findings ledger) gains the decision cross-reference: a
       finding whose latest `decisions.md` row carries a declining
       verdict (`wontfix`, or any non-`open` verdict) renders in a
       **declined** state — verdict, decision date, rationale — instead
       of open; the burn-down counts open / fixed-and-verified /
       regressed / declined separately. A finding with no ledger row
       stays exactly as before. A later `open` row reopens it.
     - The rule "a finding no verification ever ruled on stays open,
       whatever a commit message claims" keeps its force, amended with:
       "— unless the decisions ledger declines it".
  3. **Filtered no-match** (closes #110): when arguments restrict the
     status (service, stack, environment) and no report matches, the
     status states exactly what was searched (each filter and its value)
     and what exists instead (the distinct services, stacks, and
     environments present across the stored frontmatters), then stops —
     that IS the status, not a failure. Never render an empty table
     silently and never error.
  4. **Degrade gracefully** paragraph migrated as-is, extended to the
     ledger: a malformed ledger row is reported and skipped, never fatal.

- [ ] **Step 3: Self-check.** The six build steps' semantics match the
  current prompt (diff them side by side — re-measure rules, squash
  caveats, pre-convention handling all present); name-only references;
  no instruction to write any file.

- [ ] **Step 4: Commit**

```bash
git add .apm/skills/get-status/SKILL.md
git commit -m "feat(skill): get-status - the ODD loop status rendering, ledger-aware and with defined no-match output"
```

### Task 3: Thin `/odd-status` prompt

**Files:**
- Modify (rewrite): `.apm/prompts/odd-status.prompt.md`

**Interfaces:**
- Consumes: skill names `get-status` and `record-finding-decision`
  (Tasks 1-2).
- Produces: the prompt contract Task 4 documents.

- [ ] **Step 1: Read** the current prompt (what remains), the `/odd-config`
  prompt (`.apm/prompts/odd-config.prompt.md`) as the routing pattern to
  imitate, and both new skills' descriptions.

- [ ] **Step 2: Rewrite the prompt** to exactly this structure (keep the
  existing frontmatter `description:` but amend its tail: still
  "read-only, no backend queries, no report written" for reports, plus
  "can record finding decisions (wontfix) into .odd/decisions.md"):
  1. Mission line: answer "where is the loop?" from committed memory
     alone.
  2. Arguments block (unchanged fields: service(s), stack, environment)
     **plus**: a decision request — "wontfix finding F4 of <report>",
     "decline F2: <rationale>", "reopen F4" — may arrive in the
     arguments or as a follow-up after a rendered status.
  3. Render: invoke the `get-status` skill (by name) — it owns sources,
     build order, no-match behavior, and graceful degradation. The
     status renders in the conversation, as tables — never a committed
     artifact.
  4. Record: when (and only when) the user asks for a decision, invoke
     the `record-finding-decision` skill (by name) — it owns resolution,
     the ledger format, and the commit. After recording, re-render the
     affected finding's row so the user sees the status change.
  5. Contract paragraph: reports are read-only here — this prompt never
     writes or edits a report; its only write surface is the decisions
     ledger, through `record-finding-decision`; never query a backend,
     never start the stack.

- [ ] **Step 3: Self-check.** No rendering logic remains in the prompt
  (the six steps live in `get-status` only — no duplication); both skill
  references are by name; the frontmatter description still lets a user
  find the prompt by asking "where is the loop".

- [ ] **Step 4: Commit**

```bash
git add .apm/prompts/odd-status.prompt.md
git commit -m "feat(prompts): /odd-status routes to get-status and record-finding-decision - reports read-only, decisions writable"
```

### Task 4: Docs sync (AGENTS.md duties) — one batch

**Files:**
- Modify: `docs/guide/prompts.md` (the `## /odd-status` section)
- Modify: `docs/guide/dependencies.md` (components + edges)
- Modify: `README.md` (primitives table; `#### /odd-status` subsection)

**Interfaces:**
- Consumes: the Task 3 prompt contract and both skill names/descriptions.

- [ ] **Step 1: Read** the three files' existing treatment of
  `/odd-status` and of sibling skills, plus AGENTS.md's three sync
  sections (the compliance spec).

- [ ] **Step 2: `docs/guide/prompts.md`** — in the `/odd-status` section:
  state the two-skill routing (render via `get-status`, decisions via
  `record-finding-decision`), add one example invocation for a decision
  (`/odd-status wontfix F4 of my last checkout report - port-move is
  rare, 14.5s accepted`) and one for the no-match answer, and state the
  amended contract (reports read-only; the decisions ledger is the only
  write).

- [ ] **Step 3: `docs/guide/dependencies.md`** — add the two skills as
  components and exactly these new edges: `/odd-status → get-status`
  (invokes), `/odd-status → record-finding-decision` (invokes on a
  decision request). No aspirational edges: `get-status` invokes no
  other component (it reads files), `record-finding-decision` invokes no
  other component. Follow the file's existing per-prompt diagram format.

- [ ] **Step 4: `README.md`** — primitives table: one row per new skill
  (register-matched one-liners); update the `/odd-status` row's
  description tail ("... and record wontfix decisions on findings");
  update the `#### /odd-status` subsection in "Miscellaneous prompts" to
  mention declining findings and the `.odd/decisions.md` ledger.

- [ ] **Step 5: Self-check.** Every edge added matches an actual
  invocation written in Task 3's prompt text; every component in the
  README table exists in `.apm/`; no reference to `marketplace/`.

- [ ] **Step 6: Commit**

```bash
git add docs/guide/prompts.md docs/guide/dependencies.md README.md
git commit -m "docs(guide): document the /odd-status two-skill routing and the decisions ledger"
```
