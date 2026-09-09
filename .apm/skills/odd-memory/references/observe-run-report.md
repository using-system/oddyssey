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
python3 <this skill's directory>/scripts/odd_report.py new --repo <observed repo> \
  --service <name> [--service <name> ...] --stack <stack> --env <detected environment> \
  --mode <drive|observe|post-hoc|verify|re-measure> --depth <quick|full> \
  --window <start>/<end> --run-name <slug> \
  [--verifies <baseline>] [--workload <text>] [--instance <service>=<identity> ...] \
  [--process-restarted <true|false|service=true|false> ...] [--repository <value>] \
  [--at <UTC instant>] [--no-revision]
python3 <this skill's directory>/scripts/odd_report.py check <path>
python3 <this skill's directory>/scripts/odd_report.py read <path> --sections 1,2,3,7 [--record]
python3 <this skill's directory>/scripts/odd_report.py persist <path> --body <draft> [--no-commit]
python3 <this skill's directory>/scripts/odd_report.py synthesis <path>
python3 <this skill's directory>/scripts/odd_report.py show <path>
```

That is the whole surface; `--help` adds nothing and the file has
nothing to read. `--service` is repeated per service (never two names
after one flag); `--kind` exists and defaults to `observation`, the
only kind `new` writes.

- `new` prints the report's path. It names the file
  (`YYYY-MM-DD-HHmm-<run_name>.md` from the window's UTC start, the
  `-observe-<stack>` suffix in observe mode, the `verify-` and
  `remeasure-` prefixes, the next free ordinal when the path is taken),
  fills `date`, `revision`, `tree_anchor` and `repository` from the
  repository itself, writes the frontmatter and the seven-section
  skeleton, and on a replay pre-fills section 3's ruling table and
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
  frontmatter (a frontmatter the draft carries is dropped), runs
  `check` — a failing file stays in place to fix, nothing committed —
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
- `--window` is the observed interval: in drive mode the scenario's own
  start and end; in observe mode the driven run's own span — its first
  request row, warmup included, to its end — never the minutes spent
  watching. The filename's minute is that start; `--at` overrides it
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
`show`; the calling agent's contract says what each carries. Three
shapes are machine-read and fixed here:

- **Section 3 on a replay** opens with the pre-filled ruling table
  `| # | Baseline finding | Verdict | Evidence |`: one row per finding of
  the baseline's ranked table, `#` the baseline's id verbatim (the key
  `decisions.md` names a finding by), the verdict one of `fixed`,
  `still present`, `worse`, `not ruled (quick)` — a nuance after the
  word. The run's own findings follow in the ranked table, numbered
  after the baseline's. A ruling written elsewhere closes nothing.
- **Section 5** opens with the `not queried (<depth>)` line when the run
  has one, then one bullet per gap — `- <gap> — <fate> — <discovery
  query>`, the fate `filled`, `still missing`, `new` or `not ruled
  (quick)` — never several gaps in one paragraph.
- **Section 2** carries a `### GenAI` subsection when `gen_ai.*` spans
  existed in the window: the per-model table (model, operation, calls,
  tokens in, tokens out, p50, p99, error %, cost — the cost only from a
  price the mission handed over, `no price given` otherwise), the delta
  line per model against a baseline that carries the subsection, then
  the agent-loop reading. Numbers only; its findings are section 3's,
  its gaps section 5's.

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
reason), `branch:` and `subject:` when it committed, then the synthesis
block — the frontmatter whole, section 1's recalled-baseline line with
its dropped-baseline or provisional note, section 2's delta lines (a
replay's check rulings instead: check, before, after, verdict), section
3's ruling table on a replay and its findings table (id, finding,
severity, confidence — never the evidence), section 5's not-queried line
and gap bullets, section 6's open decisions. The reply carries it
verbatim, plus, on a custom stack, the stack file's fate (the
`observability-stack` reference's learning rule) — and never the report
body: the next wave reads the file at the stored path.

## Show

`show <path>` renders the closing synthesis from the stored file and
its carrying commit (`git log -1 --format=%h -- <path>`), in English —
the caller prints it translated to the conversation's language, and
adds the stack file's fate from the reply when the run changed one. In
order: the headline shaped by `mode` (counts and the baseline for an
observation, `PASS`/`FAIL` with the check counts for a verification,
drift for a re-measure, `quick` and the unqueried signals stated), where
the file lives, the run block (services, stack, mode, depth, window,
environment, repository, baseline), the core by kind — the findings
table or the verdict table and the rulings, then the gaps — capped at
ten rows with `+N more in the report`, the open decisions, and the
loop's next action. Everything comes from the stored file; the synthesis
never replaces it — the next wave consumes the file, whose path the
reply states.
