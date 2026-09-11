# Observation reports

An observation run that cannot see the previous ones starts blind every
time. This reference states what is specific to observation reports on
top of the memory contract in `SKILL.md`: the script that owns the
file's deterministic steps, the judgment the run keeps, how the
baseline is recalled, and how a stored report is shown. The report is
the loop's **only durable artifact**: the telemetry behind it dies with
the next `odd_stack_reset` — when in doubt, record the number.

## The script owns the format

```bash
python3 <this skill's directory>/scripts/odd_report.py new [--repo <observed repo>] \
  --service <name> [--service <name> ...] --stack <stack> --env <detected environment> \
  --mode <drive|observe|post-hoc|verify|re-measure> --depth <quick|full> \
  --window <start>/<end> | --from <start> --to <end> --run-name <slug> \
  [--verifies <baseline>] [--workload <text>] [--instance <service>=<identity> ...] \
  [--process-restarted <true|false|service=true|false> ...] [--repository <value>] \
  [--at <UTC instant>] [--no-revision] [--custom-stack]
python3 <this skill's directory>/scripts/odd_report.py check <path>
python3 <this skill's directory>/scripts/odd_report.py read <path> [--sections 1,2,3,7] [--record]
python3 <this skill's directory>/scripts/odd_report.py persist <path> --body <draft> [--no-commit]
python3 <this skill's directory>/scripts/odd_report.py synthesis <path>
python3 <this skill's directory>/scripts/odd_report.py show <path>
```

That is the whole surface; `--help` adds nothing and the file has
nothing to read. `--repo` defaults to the working directory and
`--sections` to `1,2,3,7`; `--service` is repeated per service, or one
comma-separated value; `--kind` exists and defaults to `observation`,
the only kind `new` writes.

- `new` prints the report's path. It names the file
  (`YYYY-MM-DD-HHmm-<run_name>.md` from the window's UTC start, the
  `-observe-<stack>` suffix in observe mode, the `verify-` and
  `remeasure-` prefixes, the next free ordinal when the path is taken),
  fills `date`, `revision`, `tree_anchor` and `repository` from the
  repository itself, writes the frontmatter and the seven-section
  skeleton — eight with `--custom-stack`, the flag a mission passes
  when the handoff names a custom stack: the frontmatter then carries
  `stack_friction: 0` and the skeleton the `## 8. Stack friction`
  heading — and on a replay pre-fills section 3's ruling table and
  section 5's gaps from the baseline, and prints that body after the
  path. Every `<fill>` it leaves is yours to replace: the sections are
  the judgment — written, filled, to a **draft** file of your own with
  your file tool, never by editing the report file.
- `check` runs the memory contract's checks — what a host's hook
  enforces after a write, plus no placeholder left and, on a replay,
  one ruling row per baseline finding with a verdict from the contract.
  One stderr line per problem, exit 2; `persist` refuses a report that
  fails it.
- `read` prints the frontmatter and the named sections, nothing else;
  `--record` reduces section 1 to its scenario record and replay notes.
- `persist --body <draft>` writes the draft under the file's
  frontmatter (a frontmatter the draft carries is dropped), recounts
  `stack_friction` from section 8's bullets when the file carries the
  field, runs `check` — a failing draft leaves the file as `new` wrote it, rulings
  and gaps included, and names what the draft lacks; nothing committed —
  leaves the default branch for `docs/odd-observe-run-report-<run_name>`,
  commits the file alone (`docs(odd): observation report <run_name>`,
  the verification and re-measure subjects for a replay), and prints the
  return value below. Without `--body` it persists the file as it is.
  `--no-commit` when the caller said not to; outside a repository it
  says `not committed` and why.
- `synthesis` prints the synthesis block of a stored report; `show`
  renders the closing synthesis from it.

## What the run decides

The frontmatter mirrors the run **as it executed**, defaults applied —
`new` writes what it is told, so the judgment is in the flags:

- `--env` is **detected**, never asked: the `deployment.environment.name`
  the service's telemetry reports; `local` by construction on the local
  stack; `unknown` when the service emits none (stated, and a telemetry
  gap). One observation, one environment.
- The window is the observed interval, pasted as a query script printed
  it (`--from <start> --to <end>`) or given as `--window <start>/<end>`
  — never an instant recomputed by hand: in drive mode the scenario's own start and
  end; in observe mode the driven run's own span — its first request
  row, warmup included, to its end — never the minutes spent watching. The filename's minute is that start; `--at` overrides it
  only when the run's start is not the window's.
- `--mode observe` names the run **and the observer**: pass the run's
  name (the benchmark's directory name when the mission carries one),
  the script appends `-observe-<stack>`. One report per mission, never a
  shared file; section 1 names the run's driver and its stored report
  when it is already committed.
- A replay passes `--verifies <exact filename of the report whose
  protocol it replayed>` — a repo-relative
  `.odd/otel-instrumentation-reports/<file>` for an instrumentation
  baseline — and records `--mode verify` when a fix is under test,
  `--mode re-measure` when the code is unchanged since the baseline's
  `revision`. The run name and the depth are inherited from the baseline
  when the flags are omitted (`quick` when an observation baseline
  predates the field; `full` for an instrumentation baseline); a replay
  knowingly run on another stack says so in section 1.
- `--depth` is how far the mission went (the agent's Depth section);
  `--workload` when the input shaped the run (a different workload is a
  new run, not a note); `--instance` and `--process-restarted` pin the
  process the numbers belong to (`run-scenario`'s `run-identity.md`) —
  cumulative queries in the protocol are qualified by that identity.
- `--repo` is the observed service's own repository; `--repository`
  stands in for its origin when the run spans repositories (a
  per-service map); `--no-revision` only when the observed code is in
  no repository the run can reach. A local path is never a value.

## The body

Seven numbered sections, read by number by the recall, the status and
`show`. What each carries is the calling agent's judgment, stated here
beside the format it fills and read at report time — its Investigation
gathers the evidence, its Depth section collapses sections 3 to 6 at
`quick` depth. Three shapes in it are the script's, never yours to
vary: section 3's ruling table on a replay (`new` pre-fills it,
`check` wants one row per baseline finding), section 5's
`- <gap> — <fate> — <query>` bullets and its not-queried line, and
section 2's `### GenAI` heading:

1. **Mission and run record** — the mission as understood (services,
   stack and backend, mode, window, focus, expectations) and every
   default you applied; the deployment environment you detected, with
   the query that found it and its `provisional` or `unknown` status if
   it has one; plus the recalled baseline: the previous report's path,
   or "no previous report" — and, when a provisional environment turned
   out to disagree, the baseline you dropped and why. In drive mode,
   include the scenario record from the `run-scenario` skill: the exact
   commands, counts, and UTC start/end — for a stored benchmark, its
   name and revision, the `k6 run` command, k6's exit status and
   summary, and the stage boundaries — so the run replays verbatim. In
   observe mode with a benchmark, the same record with the lines that
   mode replaces (`run-scenario`'s `benchmark-replay.md`, watching a
   run someone else drives): the benchmark's name and revision stand in
   for the commands you did not run, `Stages (UTC):` carries the
   boundaries and both anchors exactly as a drive's, `Watch:` the
   announced start against the first row you saw, `Poller:` the watch's
   script with its end criterion, and `k6:` either the driver's line
   quoted with where it came from or `not observed` with whatever the
   manifest's executor makes checkable in its place. The `Identity:`
   line carries the User-Agent you selected on with the slug you read
   off the rows. Name the run's driver there too — the driving mission
   as the mission block states it (or that it names none), and its
   stored report by path when that report is already committed. On a
   custom stack, name the stack's directory and the check's verdict on
   it; what the run met as friction with it is section 8's, never
   here.
2. **Observed behavior** — start with the per-operation summary table:

   | Operation | Requests | Rate | p50 | p95 | p99 | Error % | DB/downstream calls per req | Notable |

   An **operation** — a row of that table — is the smallest unit the
   service serves distinctly, which is usually already the span name.
   On an **HTTP server** that unit is the pair `http.request.method` +
   `http.route`, **never the route alone**: a route two verbs share is
   two rows, and folded, a 2.5 ms `GET` and a 62 ms `DELETE` on one
   route read as one 66 ms p95 that belongs to neither. On any other
   surface it is that surface's own unit — the RPC method and the tool
   or procedure it names (`tools/call odd_stack_status`), the topic a
   consumer reads — never an HTTP shape imposed on a service that
   serves none. Group the numbers on that key: the service's own OTel
   HTTP histogram carries both labels, so its quantiles group by
   `http_request_method` and `http_route` (beside `le`) and its counts
   by the two alone; a backend's span-derived series key by span name,
   which carries the verb already and needs no second label.

   With a benchmark in the mission, follow it with the threshold table
   — one row per threshold in the benchmark's manifest
   (`.odd/benchmarks/<name>/`; `run-scenario` reads it when you drive,
   read it directly when you only observe), ruled from the service's
   own telemetry, never from k6's summary:

   | Threshold (manifest) | Measured | Query | Pass/fail |

   When the scenario record's `k6:` line carries script errors above
   zero, no threshold is ruled: every row reads `void`, and the defect
   is section 3's first finding (`run-scenario`'s `benchmark-replay.md` — the
   benchmark did not exercise what it measures). When that line reads
   `not observed` — observe mode with no driver's record — every ruled
   row names the proxy it rests on, which the manifest's
   `profile.executor` fixes: under an **open**, arrival-rate model the
   arrivals against the scheduled integral, and rows whose arrivals
   fell short read `void` with that reason; under a **closed**,
   VU-driven one the manifest's `pacing.expected_rate` band and the
   run's continuity, where a shortfall is a finding and never a `void`
   on the count alone. The shortfall itself
   is a finding either way.

   When `gen_ai.*` spans exist in the window (the agent's GenAI
   section), follow it with the **GenAI** subsection under its own
   `### GenAI` heading: the per-model table, then the agent-loop
   reading — numbers only; its abnormal loops are section 3's findings
   and its gaps section 5's, with the others.

   Then the narrative: what the service actually does, in its own
   vocabulary — request rates, latency distribution, error rates, query
   volumes, hottest spans, notable log lines — every number carrying the
   query that produced it and a sample (trace ID, metric series, log line).
   With a recalled baseline, follow with the deltas: per operation,
   improved / regressed / unchanged / new against the previous report's
   numbers — the fate of its findings is section 3's ruling table, never
   prose here. A run that first **splits** a baseline's coarser row — a
   route into its verbs — says so: each new row names the baseline row
   it replaces. The memory is append-only, so that baseline keeps its
   key forever, and a reader, or anything matching operation names
   verbatim across two reports, otherwise sees one row vanish and two
   appear with nothing saying why. Close with the service graph: who
   calls whom, and how often.
3. **Anomalies and probable causes** — ranked table first:

   | # | Finding | Severity | Confidence | Evidence | Expected gain |

   Then the detail per row. **Confidence** is `confirmed` (the query and
   its result are quoted) or `suspected` (state the targeted probe that
   would confirm it). Findings resting on a single signal say so.

   A **verify or re-measure** puts one more table above that one, at
   the top of the section: the baseline's findings, ruled.

   | # | Baseline finding | Verdict | Evidence |

   One row per finding of the baseline's own ranked table, none left
   out, `#` carrying **the baseline's id verbatim** — `1`, `F4`,
   whatever that table wrote, never renumbered, never re-prefixed: it
   is the key `.odd/decisions.md` names a finding by, and the only
   thing that ties your ruling to it. **Verdict** is `fixed`, `still
   present` or `worse` — a nuance goes after the word (`still present,
   reduced`) — or `not ruled (quick)` for a baseline finding the
   queried signals could not rule. A ruling written anywhere else — in
   prose, in a row of the ranked table, under an id you renumbered — is
   a ruling no reader can key to the baseline: the finding stays open
   in the loop's burn-down however plainly your report calls it fixed.
   The ranked table that follows it then carries **this run's own**
   findings only, under identifiers that cannot collide with a baseline
   id: continue the baseline's numbering instead of restarting it — a
   baseline whose last finding is `F6` makes your first one `F7`.

   A **re-measure** writes the same table — it replays the same protocol
   and sees the same anomalies — but it rules on no fix: its rows record
   what the run measured, and only a verification's rows close a finding
   in the loop's memory.
4. **Improvement opportunities** — each with a measurable expected gain
   (e.g. "collapsing the per-user query loop should cut DB operations from
   ~52 to ~2 per request") and the query that will prove it landed.
5. **Telemetry gaps** — what the service should emit but does not: missing
   latency histograms, logs without trace IDs, absent database or
   downstream spans, missing resource attributes. The `not queried
   (<depth>)` statement, when the section carries one (the agent's Depth section),
   is its own first line, never spliced into a gap; then one bullet per
   gap — `- <gap> — <filled | still missing | new | not ruled (quick)>
   — <discovery query>` — the fate ruled against the baseline (`new`
   when no baseline carries the gap, `not ruled (quick)` when a quick
   replay left it unqueried) and the discovery query that came back
   empty as evidence; never several gaps in one paragraph. When gaps
   dominate the picture, add a one-line handoff to the
   `otel-instrumentation-expert` agent.
6. **Decisions the spec must settle** — the open questions telemetry cannot
   answer (intended behavior, acceptable trade-offs, priorities). Anything
   you actually concluded belongs in section 3 with its evidence, not here.
7. **Measurement protocol for the fix** — how the next run must observe:
   in drive mode, the exact scenario to replay (the same commands as
   section 1, via the `run-scenario` skill — for a stored benchmark,
   the same benchmark at the same revision); otherwise, the window and
   conditions a comparable run needs. Then every verification check with
   its before-value and its pass criterion — a threshold to meet (for a
   benchmark, the manifest's thresholds, carried over from section 2's
   table), an error that must be gone, a gap that must be filled — so the
   improvement is verified with evidence, not impressions. A check that
   measures an operation keys it by that operation's own identity
   (section 2) — on an HTTP server the method and the route together, on
   another surface that surface's unit — and groups its query the same
   way: a check keyed more coarsely than the operations it rules can
   never be re-read per operation later. In a verify or re-measure, this
   table rules the baseline's **checks**, each under the key the baseline
   gave it; a check key is never a finding id, and a check ruled here
   never stands in for section 3's ruling on a baseline finding — the two
   tables answer to different keys. A baseline check grouped more
   coarsely than the operations it rules — by the route alone, its verbs
   folded — is replayed **as written**, never silently regrouped: the two
   runs' numbers compare only when the query does not, so the ruling
   names what the number folds, and the finer check written beside it
   carries a key of its own — the baseline's, plus the verb. Each check
   states how its query was validated — on healthy data, and on the
   **shape the pass criterion expects**: a check that passes when
   something reaches zero, drops to N, or disappears (dependencies
   per request, error lines, spans of a kind) is authored on data
   where that branch never occurs, and a query that only ever saw the
   populated branch silently loses the rows it exists to count — a
   `leftouter` join whose aggregate skips the nulls of the unmatched
   side, a ratio whose absent series makes the result empty rather
   than zero. Validate the zero branch before marking it: run the
   query with a selector known to match nothing on the joined side and
   read a zero, or assert the row count equals the request count; in
   KQL write `coalesce(<right column>, 0)` after a `leftouter` join
   (or count on the request side), in PromQL `or vector(0)`, in LogQL
   a count that yields zero rather than an empty result (the
   two-raw-counts form of `## Rules` below is the same discipline for
   an equality check). The validation marker then says which shapes were
   exercised — `validated: before-shape` when only today's data
   answered, `validated: before-shape, after-shape` when the zero
   branch was too — or carries `not validated` (`## Rules` below
   defines the markers); a replay treats a check validated on the
   before-shape only as a query suspect the moment its after-value
   comes back empty, zero-free or NaN. For an
   expensive or non-deterministic scenario (`run-scenario`'s `long-scenarios.md`),
   every before-value carries its sample count and pass criteria are
   structural or magnitude-bounded — never a value from one or two
   samples.

8. **Stack friction** — present only when the mission ran against a
   custom stack (`new --custom-stack` wrote the heading and the
   frontmatter's `stack_friction`): one bullet per point of friction
   with the stack **as shipped** — a script that failed as written, an
   output shape the guide did not state, a flag it lacked, a section
   the run could not follow, a query it had to compose by hand —
   `- <what did not work> — <the invocation, as run> — <what it
   answered> — <what the run did instead>`; or the one bullet
   `- none — every shipped invocation answered as its guide states`.
   A friction with the preflight's or the switch's sections is a
   bullet like any other. `persist` counts the bullets into
   `stack_friction`, `show` renders them, and
   `/odd-instrument-stack from report <path>` turns them into the fix
   — the run itself never edits the stack (the `observability-stack`
   reference's rule). Stated once, here, never spliced into section 1
   or 5: a friction is about the stack, a gap is about the service.

## Recall: reading the memory

1. `python3 <this skill's directory>/scripts/odd_recall.py --repo <path>
   [--service <name>]... --stack <stack> --env <detected environment>
   --depth <quick|full>` — `--service` repeated per service, `--mode` to
   restrict to one mode, `--env` omitted while the environment is
   provisional. It lists `.odd/observe-run-reports/` newest first, one
   tab-separated line per match: filename, kind, services, stack,
   environment, mode, depth, `verifies`, `workload`, `repository` (`-`
   when absent); a flagged report is named on stderr, matched or not.
2. A report matches on intersecting `services`, the same `stack` and the
   detected `environment` (`unknown` matches only `unknown`, with a
   warning; a provisional environment matches on services and stack
   alone, pending re-confirmation). A differing `workload` is kept and
   warned about. A `full` mission's baseline is the newest `full` (or
   depth-less) match, the skipped newer quick ones named on stderr and
   in section 1; a `quick` mission takes either depth.
3. The first line is the baseline, read **by section, never whole**:
   `read <path> --sections 1,2,3,7 --record` — section 1's scenario
   record and replay notes, section 2's numbers and deltas (its GenAI
   subsection with them), section 3's findings, section 7's checks and
   before-values; `--sections 1,2,3,5,7` on a verify or re-measure, which
   rules on every gap too. An instrumentation baseline reads
   `--sections 2,3,5`: its summary table, per-service decisions and
   verification protocol. Reading beyond that set is for a stated need
   the run record names.
4. Older matches are history: read only the numbers in question, when a
   trend matters.
5. The observed → verified chain is the `verifies` field (the filename
   glob `*-verify-<run_name>.md` only proposes candidates); a re-measure
   never answers "has this run been verified". A pre-convention report
   stays a valid match whose chain is not machine-readable: a fact to
   state.

## Rules

- **No secrets, no real identifiers** (the memory contract): the
  mission block's `Preflight:` handoff and a live CLI excerpt are the
  likeliest sources.
- **A query run through a backend's shipped script is recorded as the
  script invocation, followed by the backend queries the script
  printed** — never one without the other, never a query re-derived by
  hand from what the script computed.
- **A recorded query is a contract only once shown to work**: each
  section 7 check states how its query was validated and on which shape
  — `validated: before-shape` when only today's data answered,
  `validated: before-shape, after-shape` when the shape the pass
  criterion expects was exercised too (a zero, a vanished series), or
  `not validated`; a stored check naming no shape reads as
  `before-shape`. An equality check on log line counts is stated as two
  raw counts over the recorded window and selector, naming the lines it
  excludes.
- **Record how the backend was started** when it needed configuration:
  the `env` passed to `odd_stack_up` / `odd_stack_reset` belongs in
  section 7, secrets by name only.

## Return value

`persist` prints it: `path:`, `commit:` (or `not committed` with the
reason), `headline:`, plus `branch:` and `subject:` when it committed,
and on a custom stack the `stack_friction` count it recounted, on
stderr. The reply carries those lines verbatim — and nothing of the
body: the synthesis is rendered once, by the caller's `show`, and the
next wave reads the file at the stored path.
`synthesis <path>` prints the inputs `show` renders from, quoted from
the file, for a reader who wants them rather than the rendering.

## Show

`show <path>` renders the closing synthesis from the stored file and
its carrying commit, in English, one screen — on a custom stack, its
friction count and entries, with the prompt that fixes them; what
running it cannot tell the caller: print it translated to the
conversation's language, and never let it replace the file — the next
wave consumes the file, whose path the reply states.
