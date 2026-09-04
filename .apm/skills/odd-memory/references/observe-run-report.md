# Observation reports

An observation run that cannot see the previous ones starts blind every
time. This skill defines the file contract that gives the ODD loop its
memory: reports live **in the observed repository**, so git versions
them, PRs review them, and every user of the repo shares them — no
side-channel storage, nothing opaque. What every kind of memory shares
is the contract in
`SKILL.md`; this reference states what is specific to observation
reports: how to persist one, how to recall the baseline, and how to
show a stored one (`## Show`).

The report is also the loop's **only durable artifact**: the raw
telemetry behind it lives in a volume-less container that any
`odd_stack_reset` — from this project or another on the same machine —
destroys irreversibly. A question that only occurs at verify time is
unanswerable unless its numbers were recorded at observe time: when in
doubt, record the number.

## Where reports live

```text
<observed-repo-root>/.odd/observe-run-reports/YYYY-MM-DD-HHmm-<run_name>.md
```

- `YYYY-MM-DD-HHmm` and `<run_name>` follow the memory contract: UTC
  via `date -u` (so do `date:` and `window`), and a slug naming what
  the run analyzed (`checkout-latency-sweep`, `orders-post-hoc-errors`).
- A **verification run** — a run that replays a stored report's
  protocol: an observation report's measurement protocol, or an
  instrumentation report's verification protocol (from
  `.odd/otel-instrumentation-reports/`) — names its file
  `YYYY-MM-DD-HHmm-verify-<run_name>.md`: its **own** UTC timestamp,
  then `verify-`, then the verified report's `run_name` unchanged (the
  baseline's timestamp is not repeated). Chronological sorting is
  preserved — verify reports interleave in the timeline instead of
  clustering — and "has this run been verified?" becomes a filename
  glob (`*-verify-<run_name>.md`). Re-verifications share the suffix
  and differ by their own timestamp. `verify-` always references the
  report **whose protocol is replayed**: re-verifying replays the
  original report's protocol again, so the new report references the
  original report. A verification report is a legal reference only
  when its own §7 measurement protocol — not the original's — is the
  one replayed: the reference names the protocol's actual source,
  never a report the run did not replay.
- A **re-measure run** — a run that replays a stored report's protocol
  verbatim while testing no fix (same code, drift or stability check)
  — names its file `YYYY-MM-DD-HHmm-remeasure-<run_name>.md`: the same
  mechanics as a verification (its own UTC timestamp, the replayed
  report's `run_name`), its own glob (`*-remeasure-<run_name>.md`).
  It never matches the `*-verify-*` glob: a re-measure is not a
  verification, and "has this run been verified?" must stay blind to
  it.

## The file format

A YAML frontmatter, then the complete report:

```markdown
---
services: [checkout, payment]
stack: local                  # local | the remote backend name (grafana, datadog, ...)
environment: local            # detected: deployment.environment.name reported by the service's telemetry (local forced on the local stack; unknown when absent)
mode: drive                   # drive | observe | post-hoc | verify | re-measure
depth: full                   # quick | full: how far the mission went (the agent's Depth section); absent = written before the field, ran the full protocol
window: 2026-08-22T10:04:12Z/2026-08-22T10:05:03Z
run_name: checkout-latency-sweep
date: 2026-08-22
revision: 2299d4c             # optional: commit of the observed repo at run time
tree_anchor: {src: "5ea231f…", tests: "8e29aac…"}  # optional: FULL top-level entry map at revision (git ls-tree) - the squash-proof anchor
workload: repo-under-analysis # optional: the input that shaped this run
instance: {checkout: af6070c1}   # optional: per service, the identity the numbers belong to
process_restarted: true       # optional: restarted before the window (or per-service map)
---

<the observation report, verbatim and complete>
```

A verification run (stored as
`2026-08-25-0930-verify-checkout-latency-sweep.md`) differs only in
these fields:

```yaml
mode: verify
run_name: checkout-latency-sweep                     # the baseline's, unchanged
verifies: 2026-08-20-1012-checkout-latency-sweep.md  # exact filename of the replayed baseline
```

A re-measure run (stored as
`2026-08-27-1408-remeasure-checkout-latency-sweep.md`) uses the same
fields with its own mode:

```yaml
mode: re-measure
run_name: checkout-latency-sweep                     # the replayed report's, unchanged
verifies: 2026-08-20-1012-checkout-latency-sweep.md  # exact filename of the replayed report
```

- Every field mirrors the run as it executed (the memory contract) —
  mission parameters and execution context alike, defaults applied,
  not as requested. One exception: a verification or re-measure run
  records `mode: verify` / `mode: re-measure` even though it executes
  in the replayed report's mode — that execution mode stays reachable
  through `verifies`.
- `window` is the observed interval as `start/end` in UTC; in drive mode
  it is the scenario's own start and end.
- `depth` is how far the mission went — `quick` (the agent's bounded
  protocol: the signals the question touched, one exemplar per
  operation, sections 3 to 6 collapsed, section 7 carrying only what
  was measured) or `full` (the whole protocol). Required on every new
  report, so `/odd-status` and the recall can tell the two apart and a
  quick run is never silently taken as the baseline of a full one. A
  report without the field predates it and ran the full protocol: read
  it as `full`. A verification or re-measure records the depth **it**
  ran at (inherited from the baseline's field, or — the one deliberate
  asymmetry — `quick` when an observation baseline has none: the
  absent field says "ran full" to every reader and "replay quick" to
  `/odd-verify`, whose preflight says so before dispatch and whose run
  record says it was defaulted), which may differ from the baseline's.
- `environment` is **detected**, never asked: the
  `deployment.environment.name` resource attribute the service's
  telemetry reports — pre-run probe on recent telemetry, provisional
  until the first scenario telemetry lands when the pre-run window is
  empty. On `stack: local` the value is `local` by construction — a
  service emitting a different attribute still records `local`, with the
  discrepancy stated as a finding (misconfigured resource attributes).
  `unknown` when the service emits no attribute — stated, never guessed,
  and the absence is a telemetry gap. One observation, one environment:
  services detecting different values stop the run, and so does a single
  service reporting several values across the window — observe them as
  separate missions.
- A verification run sets `mode: verify` and `verifies: <exact filename
  of the replayed baseline report>`, and takes its `run_name` from that
  baseline. A **re-measure run** — same replay, but no fix under test:
  the code is unchanged since the replayed report's `revision` and the
  run measures drift or stability — sets `mode: re-measure` instead,
  with the same `verifies` mechanics; what separates the two modes is
  whether a fix is being ruled on, never how the run executed. Plain
  observation reports (drive, observe, post-hoc) never carry `verifies`
  and record their execution mode — the mode a verification or
  re-measure replayed is the replayed report's, reachable through
  `verifies`, so it is not repeated. In both modes `verifies` names the
  report **whose protocol was actually replayed** — a verification
  report is a legal value only when its own updated protocol is the
  one replayed. The exact
  filename (not just the run_name) is what disambiguates two baselines
  sharing a run_name and survives an accidental rename; the field is
  the machine contract, the `verify-`/`remeasure-` filename the
  readable convention.
  The baseline may also be an **instrumentation report**: `verifies`
  then carries its repo-relative path
  (`.odd/otel-instrumentation-reports/<filename>`), so the value's
  shape says which directory the baseline lives in — a bare filename
  always names a sibling observation report. The deliverable stays an
  observation report in this directory either way.
- `revision` (`git rev-parse --short HEAD` in the observed repo) is what
  makes a before/after honest — omitted, with `tree_anchor`, when the
  observed service lives outside the repository the report is stored
  in, and section 1 says so: a report is a before-value for a fix
  wave, and the fix is a diff against some revision. In a squash-merge
  repository that commit never joins the merged history — a fresh
  clone cannot even resolve it — so record `tree_anchor` alongside it:
  the full top-level entry map of `git ls-tree <revision>`, one
  `name: object-hash` pair per entry. Content-derived, the anchor
  survives squashes and clones: "code unchanged since the report"
  becomes an entry-by-entry hash comparison against `git ls-tree` of
  any later commit, with `.odd` and every entry that cannot change the
  observed service's runtime behavior (documentation, CI
  configuration, generated artifacts, release metadata) ignored by
  the consumers — `.odd` because its top-level hash moves with every
  report written, not because everything under it is memory:
  consumers test `.odd/benchmarks/` separately, by path, since a
  benchmark is living source and a change to it is a code change.
- `workload` names the input that shaped the run when the runtime
  profile depends on what was processed, not only on the service (an
  analysis service run against two different repositories produces
  incomparable numbers). Free-form, omit when the service alone defines
  the profile — and if the workload changes mid-mission, that is a new
  run, not a note.
- `instance` and `process_restarted` pin which process the numbers
  belong to (run-scenario step 0). `instance` maps each observed service
  to its identity: `service.instance.id` when the SDK emits one, or the
  backend equivalent when it is absent — the process start time, a
  `target_info` label, a container id. `process_restarted`
  is one boolean when it holds for every listed service, a per-service
  map when only some were restarted. Cumulative-metric
  queries in the measurement protocol must be qualified by the recorded
  identity — a number that cannot be attributed to a process is not a
  before-value. Profiles carry no `service.instance.id`: the identity
  that qualifies them is the per-run profiler tag, or, absent one,
  `process.runtime.version` plus application frames — `instance` says
  which holds for the profiles.

## Recall: reading the memory

Before a new run, load the baseline, per the memory contract's recall
(newest first, frontmatter only at this stage, the baseline by
section) — the matching rules are this reference's:

1. List `.odd/observe-run-reports/` in the observed repo.
2. A report matches when its `services` intersect the mission's,
   its `stack` is the mission's, and its `environment` is the one the
   run detects — an `unknown` environment matches only another
   `unknown`, and with a warning (the comparison may span environments
   without the reports being able to say so). While the run's
   environment is still **provisional** (empty pre-run telemetry on a
   remote stack), a candidate matches on `services` and `stack` alone,
   the environment check pending the re-confirmation the agent performs
   once the value settles. When a match's `workload` differs from the
   mission's (or only one side has one), keep it but **warn**: its
   numbers were shaped by a different input, and diffing across
   workloads violates the one-changed-variable rule. Depth filters the
   match: a **`full`** mission's baseline is the newest match whose
   `depth` is `full` (or absent) — a newer `quick` match is skipped,
   and section 1 names it ("newer quick report skipped: <path>") so the
   skip is visible; a **`quick`** mission takes the newest match of
   either depth (a full report carries more than a quick run needs).
3. The first match is the baseline. Read it **by section, never
   whole** — the same partial read applies when the mission names the
   baseline itself: the frontmatter; section 1's scenario record block
   (`Scenario:` through `Not reproducible:`) together with the replay
   notes around it — deviations, false starts, anything the report
   flags as mattering for a replay — but not section 1's mission
   restatement or its recalled-baseline line; section 2 (the
   per-operation numbers and their deltas); section 3 (the findings
   the new run rules on); and section 7 (the protocol's checks and
   before-values). A **verification** or **re-measure** run also reads
   section 5 (every gap it must rule filled or still missing).
   Sections 4 and 6 are never part of the recall: a stored report runs
   300 to 500 lines, and the new run re-derives those from live
   telemetry. An **instrumentation report** baseline
   (`.odd/otel-instrumentation-reports/`, the
   `otel-instrumentation-report` reference) is read the same
   way: its frontmatter, its summary table, its per-service decisions,
   and its verification protocol — never its stack inventory or its
   open decisions. Reading beyond that set is the exception — for a
   stated need (a finding's detail, a gap's discovery query) — and the
   calling agent's run record says so. What the comparison must report
   belongs to the calling agent's contract, not to this reference.
4. Older matches are history: only when a trend matters (a number
   degrading run after run), read at most the few most recent matches,
   and only the numbers in question — never the full files.
5. The observed → verified chain is machine-readable — never parse
   prose for it. Whether a report has been verified is the glob
   `*-verify-<run_name>.md` on later timestamps, confirmed by the
   candidate's `mode: verify` and its `verifies` field naming that
   report's exact filename
   (the field is authoritative; the filename is convention). A
   re-measure report never answers that question: `mode: re-measure`
   replayed the protocol without ruling on a fix — it extends the
   run's measurement history (`*-remeasure-<run_name>.md`, comparable
   by construction with the report its `verifies` names), not its
   verification chain. Verification and re-measure reports are
   themselves full reports — when one is the newest
   match, it is the baseline, and its `verifies` field says whose
   protocol its numbers replayed. Pre-convention reports (free-form
   slug, no `verifies`) stay valid matches: their chain simply is not
   machine-readable, which is a fact to state, not an error.

## Return value

After persisting, return — to the agent, and through its reply to the
caller closing the mission:

- the stored path, repo-relative;
- the carrying commit (`git rev-parse --short HEAD` right after the
  commit), or `not committed` with the reason (default branch and no
  work branch possible, not a repository, the caller said not to);
- on a custom stack, the stack file's fate: `unchanged`, or its path
  with the commit of the run's diff (or `not committed` with the
  reason) and the one-line reason the run record gives (the
  `observability-stack` reference's learning rule);
- the **synthesis block** — the inputs `## Show` below
  renders from, quoted verbatim from the file just written (never
  rephrased, never re-derived), and nothing else of the body:
  - the frontmatter block, whole;
  - section 1's recalled-baseline line — the previous report's path,
    or "no previous report" — with the line that names a dropped
    baseline or a provisional environment when the report carries one;
  - from section 2, when a baseline was recalled, the delta lines —
    one per operation (improved, regressed, unchanged, new), never
    the per-operation or threshold tables; for a verify or
    re-measure, every check's ruling instead — its name, before-value,
    after-value and pass/fail cells, not the row's narrative — and
    every check that reads `not ruled (quick)`; for an instrumentation
    baseline, the presence rulings section 2 carries in place of the
    numeric deltas: planned item and ruling (closed / present,
    unattributed / still missing);
  - section 3's ranked table — the identifier, finding, severity and
    confidence cells the table carries, never the evidence or the
    detail per row; in a verify or re-measure, each baseline anomaly's
    fate with it (fixed, still present, worse);
  - section 5's telemetry gaps, one line each (at quick depth, its
    single line); in a verify or re-measure, each baseline gap's fate
    with it (filled, still missing);
  - section 6's open decisions, one line each, or that there are none.

Never the report body (the memory contract says why);
`## Show` below renders the closing synthesis from this
value, and the file on disk is read again only by a later mission's
recall or by a caller naming a stored report.

## Rules

- **No secrets, no real identifiers** (the memory contract): the
  mission block's `Preflight:` handoff and a live `odd_config_get` or
  CLI excerpt are the likeliest sources — never restate the
  identifiers they carry.
- **A recorded query is a contract only once shown to work**: a check is
  authored against *broken* data, so "returns NaN/empty" and "the query
  is wrong" are indistinguishable at authoring time (measured: `rate()`
  over a single burst makes every `histogram_quantile` NaN by
  construction on any window sampled after the burst, whatever the fix
  did). Each verification check states how its query was validated —
  run against a healthy or adjacent series, or a synthetic one — and on
  which **shape**: `validated: before-shape` when only today's data
  answered, `validated: before-shape, after-shape` when the shape the
  pass criterion expects was exercised too (a "reaches zero" check run
  with a selector matching nothing on its joined side, a row count
  equal to the request count) — or carries `not validated`. A stored
  check whose validation note names no shape (every report written
  before these markers) reads as `before-shape`. Either of the two
  weaker markers tells the verify run to suspect the query before the
  fix: a check authored on the populated branch alone can
  drop the very rows it measures once they go to zero (a `leftouter`
  join aggregated without `coalesce`, a ratio over an absent series).
  An equality check on log line counts ("every
  line carries a trace id") is stated as two raw line counts over the
  recorded window and stream selector, one of them carrying the
  trace-id filter — never as a range vector
  evaluated at the window's edge, whose samples reach outside it — and
  names the lines it excludes (startup lines, excluded URLs), so the
  replay rules on the same residue.
- **Record how the backend was started** when it needed configuration:
  the `env` passed to `odd_stack_up` / `odd_stack_reset` belongs in the
  measurement protocol (key names and values — secrets by name only). A
  replayed reset recreates the container bare; only a recorded env lets
  the verify run pass the same one.
- **The work branch** (the memory contract) is
  `docs/odd-observe-run-report-<run_name>`; **the commit** carries the
  report file alone, subject `docs(odd): observation report
  <run_name>` — `docs(odd): verification report <run_name>` for a
  verification, `docs(odd): re-measure report <run_name>` for a
  re-measure.

## Show

The stored report is the ODD loop's memory and the fix plan's input —
the right artifact for the next wave, the wrong one for the human
closing the mission: several screens deep, the takeaways drown. This
section renders the closing synthesis. The report file stays the
deliverable; only what the human sees at the end of the mission
changes.

### Input

The report to render, in one of two forms:

- **The persistence return value** — what the persistence step above
  just returned for the mission being closed, carried in the agent's
  reply: the stored path, the carrying commit (or `not committed`),
  and the synthesis block — the frontmatter, section 1's
  recalled-baseline line, section 2's delta lines, check rulings or
  presence rulings, section 3's ranked table with the baseline
  anomalies' fates, the telemetry gaps with the baseline gaps' fates,
  and the open decisions, quoted from the file (`## Return value` above
  owns the list). Render from it; never
  re-read the file it just wrote — the block carries every input the
  synthesis below reads, and a value it lacks is absent from the
  synthesis (the way a benchmark's synthesis renders from its
  persistence return).
- **A stored report the caller names** — no return value in hand:
  read from disk the same set — that file's frontmatter, section 1's
  recalled-baseline line, section 2's delta lines, check rulings or
  presence rulings, section 3's table, sections 5 and 6 — never the
  whole file — and its carrying commit from git
  (`git log -1 --format=%h -- <path>`).

Either way the synthesis renders the stored content, never the
conversation's memory of the mission.

### The synthesis, in order

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
   carries it; on a custom stack whose file the run changed, a second
   line: the stack file's path, its commit and the one-line reason.
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

### Rules

The contract's synthesis rules (`SKILL.md`): everything from
the stored report, the carrying commit the one value outside it; one
screen with `+N more`; the conversation's language; never a
replacement for the file.
