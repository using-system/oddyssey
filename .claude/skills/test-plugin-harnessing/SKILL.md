---
name: test-plugin-harnessing
description: Measure and optimise one phase of an oddyssey run - preflight, drive, observation, or the whole run - under one of the coding-agent CLIs the package is benchmarked on (opencode, claude, copilot), against main measured just before the work. Use when a phase is too slow or too expensive, when a harnessing change must be proven rather than asserted, when a run is suspected of composing work the package should ship, and before the PR of any change on the path of /odd-observe, /odd-verify or /odd-status. Drives the CLI headless, measures the phase, names where the time went, and separates what the package controls from provider latency. Never a substitute for launch-llms-benchmark, which grades findings; this grades the harness.
---

# Testing a phase of the plugin's harness

`launch-llms-benchmark` asks *how good is this model's report*. This asks
a different question: **how much work does the package still make the
model compose before it can do anything** — and it answers it for one
named phase at a time, under one named CLI. Do not run the benchmark
protocol for this; it grades findings, costs a full run, and its row is
not what moves when a skill stops making the model write a script.

The rules a change here must satisfy are `AGENTS.md`'s **Plugin
harnessing** section. This skill is how you prove one landed — and that
section says when a measurement is owed: before the PR of any change on
the path of `/odd-observe`, `/odd-verify` or `/odd-status`.

## What you need before starting

- **The phase**, named by the caller: `preflight`, `drive`,
  `observation`, or `whole`. Ask if it is not named — measuring the
  wrong phase wastes the run.
- **The CLI** the runs are driven by: `opencode`, `claude` or
  `copilot` — the three `launch-llms-benchmark` runs, and the source
  of everything CLI-specific here: how a run is launched headless, the
  form of the model id it takes, where its session lives and how it is
  read. The scripts below implement those per CLI; the command's steps
  3, 6 and 7 are the reference when one of them looks wrong. Default
  `opencode` — the fastest instrument on this table so far; measure on
  the CLI whose behaviour the change is about.
- **The mission**, the same on every sample, and by preference an
  observation in **drive mode on the local stack**: the run generates
  its own traffic, so every window holds the same requests and the
  samples differ in how they worked, not in what there was to find. A
  post-hoc window holds whatever landed that minute (a late burst, a
  real error — measured 2026-09-09: one 502 gave three samples an extra
  finding and 34 to 40 queries against 24 to 30): measure post-hoc only
  when post-hoc is what changes, with one scripted burst per sample and
  the stack's facts re-read per window; a remote stack only when the
  change is that stack's, never by default. A preflight alone
  (`/odd-verify`, the dispatch as its end marker) is the cheapest
  mission when the change is the preflight's.
- **The baseline**, which is the published row in
  `.llms-benchmark/README.md` for the model and CLI you will use: its
  phase durations, its turn count and its **median turn**. Read it from
  `origin/main`, never from the working tree.
- **A model whose median turn is small**, as the canonical
  `vendor/name` id (`google/gemini-3.7-flash`,
  `anthropic/claude-haiku-4.5`, `openai/gpt-5.6-sol`): the scripts hand
  each CLI its own form. The published median is the instrument's
  precision: a model at 3 s per turn measures the harness, one at 20 s
  measures the provider. Prefer the fastest row in the table for that
  CLI, whatever its findings score — this is not a quality test.

## The procedure

1. **Rebuild the generated tree.** A CLI agent loads
   `marketplace/`, not `.apm/`, so an unregenerated tree runs the
   *previous* version of every prompt, agent and skill — the run then
   measures the old package while looking exactly like it measures the
   new one. `bash scripts/build-marketplace.sh`, then grep the change in
   the generated file the run will read. This is the single most
   expensive mistake available here; make it once and every number since
   the change is void.

2. **Deploy to every scope the host reads, and prove they match** —
   the scopes are the CLI's, as `launch-llms-benchmark` step 3 states
   them:
   - `opencode`: `uvx --from 'apm-cli==0.29.1' apm install --target opencode`
     in the lab clone; opencode also reads `~/.claude/skills/`, so copy
     `.apm/skills/*` there too;
   - `claude`: nothing in the clone (the claude target deploys hooks
     that load into the running session) — the package at **user
     scope**, `apm install --global --target claude`, which writes
     `~/.claude/commands/`, `~/.claude/agents/`, `~/.claude/skills/`;
     the MCP server in `~/.claude.json`;
   - `copilot`: `apm install --target copilot` in the lab clone
     (`.github/prompts/`, `.github/agents/`, `.github/hooks/`,
     `.github/mcp.json`, `.agents/skills/`); `~/.copilot/skills/` and
     the installed plugins' skills must not carry the package.

   Back the user scope up first and restore it at the end — it is the
   user's install, not yours — or, when the user's home must stay
   untouched, run the host under a fake `HOME` whose `.claude` carries
   the deploy and whose every other entry is a symlink to the real home
   (the credentials, the CLIs' logs, transcripts and session stores
   stay where the scripts read them). `diff -rq` the scopes against
   `.apm/`: a run that finds them different spends turns comparing
   them, and an older copy measures another version than the row
   claims.

3. **Clean what the next run must not read.** Any report a previous run
   stored, and any leftover container, process or scratch directory. A
   run that reads the last run's conclusions is not measuring anything.
   Between two samples, let the previous run's process end and wait a
   few seconds: a launch that reads the CLI's log while the previous
   run still writes it can take that run's id.

4. **Measure**, with `scripts/measure_phase.py`:

   ```bash
   python3 <this skill's directory>/scripts/measure_phase.py \
     --cli <opencode|claude|copilot> --model <vendor/name> --tag <short label> \
     --phase <phase> --prompt-file <mission> --out <study dir>
   ```

   A mission that opens with a slash command (`/odd-observe ...`) is
   handed to the host the way a typed command is: opencode through its
   own expansion (`--command`), claude as text the host expands,
   copilot as text it does not expand (its runs invoke the package's
   skills through the `skill` tool all the same). Passed as raw text
   where the host would have expanded it, a run hunts for the command
   file first — globs, reads of the command and of the agent it
   dispatches — a cost no host pays, folded into every phase number
   (measured: 8 to 10 turns of a 75-turn run). The record carries the
   form used, so a number taken one way is never compared with one
   taken another.

   Its whole surface, so `--help` has nothing to add: `--cli` (default
   `opencode`), `--model`, `--tag`, `--phase`, one of `--prompt` /
   `--prompt-file`, `--out`, plus `--end-pattern` (a regular expression
   over the run's own lines — opencode's log, claude's transcripts,
   copilot's events — for a mission with no k6 drive to mark the
   phase: the first telemetry query, or the agent's dispatch, which
   reads `permission=task pattern=observe-run` on opencode,
   `subagent_type":"observe-run` on claude, `subagent.started.*observe-run`
   on copilot), `--effort` (default `medium`, the same level on the
   three CLIs; `--variant` is its alias), `--timeout` (default 2700 s)
   and `--keep-running` to let the run continue past the phase. It
   records the run's own id at launch — opencode's from its log, the
   session id it generated for claude and copilot — stops at the
   phase's marker, and exits non-zero rather than return a fast wrong
   number when the phase never closed — a run that exits non-zero, or
   prints an error, is never a measured phase. The record names the
   CLI, the model as passed, the id, the directory, the stdout stream
   and copilot's usage file, which the analysis reads.

   **A study's samples are run by `scripts/run_samples.py`, never by a
   chain you write** — every study before it rewrote the same loop (the
   branch checkout, the leftovers, the scope sync, the launch, the
   analysis, a journal to watch) and each copy carried its own bug:

   ```bash
   python3 <this skill's directory>/scripts/run_samples.py --lab <lab clone> --fake-home <dir> --out <study dir> \
     --cli <opencode|claude|copilot> --model <vendor/name> --phase <phase> \
     base1=<lab branch>:<mission file> after1=<lab branch>:<mission file> base2=... after2=...
   ```

   One sample is `<tag>=<lab branch>:<mission file>`, run in the order
   given (alternate the sides). For each: the lab is put on the branch
   and cleared of what a run left after the tip recorded when the chain
   started (a report branch, a report commit, an untracked report, a
   rewritten `opencode.json` — a lab dirty in any other way is refused
   before the launch), the fake user scope is synced from the branch's
   deploy and checked identical (`--scope <lab path>:<fake-home path>`,
   repeatable; opencode's two pairs are the default, the other CLIs
   state theirs), `--scratch <dir>` is cleared when given (the CLI's
   scratch directory; nothing outside the study is touched otherwise),
   the measurement above is launched (once more when it exits non-zero
   within 30 s — a launch that died measured nothing; `SAMPLE
   RELAUNCHED <tag> (...)` says so) and the analysis below run, and
   one line goes to `<study dir>/samples.log`: `SAMPLE DONE <tag>
   <wall> on <branch>`, `SAMPLE FAILED <tag> (<why>)`, then `SAMPLE
   CHAIN DONE <n> of <m>` — or `SAMPLE CHAIN ABORTED at <tag>: <why>`
   when a sample is refused before its launch — the lines to watch
   instead of polling. Its whole surface, so `--help` has nothing to
   add: the flags above, `--end-pattern`, `--effort` (default
   `medium`), `--timeout` (default 2700 s), `--pause` (default 10 s
   between samples), `--before <command>` (run before each launch:
   recreate the demo stack, send a traffic burst), `--alongside
   <command>` (started right after each launch and waited for: a driver
   that replays a benchmark from a second shell), `--after <command>`,
   `--measure-script` and `--analyze-script` (the kit of another
   revision). The hooks see `SAMPLE_TAG`, `SAMPLE_BRANCH`,
   `SAMPLE_OUT`, `SAMPLE_MISSION`, `LAB` and `FAKE_HOME`. Exit 0 when
   every sample was measured, 1 otherwise.

5. **Analyse before concluding**, with `scripts/analyze_run.py`:

   ```bash
   python3 <this skill's directory>/scripts/analyze_run.py --record <study dir>/<tag>.record.json
   ```

   Surface: `--record`, or `--cli` with `--run-id` plus `--stdout` (the
   run's stdout stream: required for copilot, whose model calls it
   carries; claude's cost when the run reached its exit) and `--usage`
   (copilot's usage file); `--gap` (default 60 s) sets the gap it
   reports; `--json`. It reads the run's own lines under that CLI —
   opencode's log and session store, claude's root and subagent
   transcripts, copilot's events and stream — and prints the commands,
   the turns, the generation time and the median turn, the tokens and
   the cost the CLI states (`null` with the reason otherwise), then the
   four behaviours a harnessing change removes — scripts the run
   authored, stack resets, machine questions already answered upstream,
   `--help` calls on shipped scripts — and every silent gap.

6. **Read the gaps before believing the clock.** A gap with no command
   in it is the model generating. One far above the run's median turn is
   the provider, not the package: the script says so, and when it does,
   the wall clock is not comparable to anything. Compare **generation
   time** and **commands** instead, or measure again later.

7. **Fix one lever, then measure again.** One change per run, rebuilt
   and redeployed per steps 1-2. Two changes in one run cannot be
   attributed, and the run-to-run spread is wide enough to hide a small
   effect either way.

8. **Restore the machine.** The user's command, agent and skill scopes
   from the backup, the generated trees to `origin/main` (the release
   workflow owns them), `.gitignore` and anything else `apm install`
   edited, the containers down, the stray processes killed.

## Judging what you measured

**The baseline is main, measured just before the work starts**, with
the same mission, the same machine, the same CLI and the same harness
as the runs that follow — never the published row alone, never a number
taken on another day. State it on four axes at once: turns, tokens
(input with the cached share, output), cost and wall clock — per phase,
since the report phase is a tenth of a run and a change there vanishes
in the investigation's spread. The analysis prints the tokens and the
cost the CLI states — opencode's store carries both for the session
tree; claude's transcripts carry the tokens per request and the cost
only in the result the run prints when it reaches its exit; copilot's
usage file carries the tokens, a stopped run's included, and no dollars
— `null` with the reason otherwise; a run left to finish
(`--keep-running`, a `whole` phase) is read the way
`launch-llms-benchmark` step 7 reads it. When a number looks like
variance, replay rather than argue: two samples of the same
configuration settle what one cannot.

**A harnessing change goes to review only with a substantial gain on
those axes against that baseline** — not a conformant output alone,
not a behaviour count alone. A change that moved the target phase and
left the totals level, or worse, is reworked, not argued: find where
the turns and the context went (per-phase accounting, the reads of
every file the change touched, the calls the new invocation caused),
fix the cause, and measure again. A change on the path made for
another reason (a fix, a feature) owes no degradation on those axes,
not a gain — `AGENTS.md` states the split.

**Under review, measure once, at the end.** The fix waves a reviewer
asks for are not measured one by one: apply them, run the suites, and
measure the branch as it will be merged once the reviewer is green —
two samples minimum, against the numbers that sent it to review. A
wave that changes what the run reads or runs (a line the run copies, a
shape it used as a source, a new invocation) is the exception: measure
it before the next round, because the measured 2026-09-09 case cost the
whole gain and only the numbers said so. A loss at the end reopens the
review with the mechanism named, never a re-run alone.

**When the phase reaches the report, the findings are a metric too.**
A harness change that cuts turns and loses findings moved the cost
onto the reader. For every sample that wrote a report, count what it
found - section 3's ranked findings by severity and confidence, section
5's gaps - on the baseline and on the change alike (the report script's
`synthesis` prints both lists), and **review them before comparing**:
re-run the query each finding cites, open what it accuses, and rule it
confirmed or not - the way `launch-llms-benchmark` grades a row, on
evidence, never on the report's own confidence label. State the
confirmed count next to the reported one, per side, in the study and
in the PR; a change that reports more but confirms less is worse.

**Two samples minimum before claiming a wall-clock gain**, and state
both. The spread between two runs of one configuration reached 17 s in
practice; a single sample below the baseline proves nothing.

**A behaviour count is stronger evidence than a duration.** Commands
before the phase closed, scripts authored, resets taken, redundant
questions — these are what the package controls, they do not move with
the provider's mood, and they are what the PR should quote.

**When a run writes its own script, the shipped one is missing a shape
of the work.** Read what it wrote before hardening any instruction: a
wrapper that only chains a shipped command with a wait is the
repository's own helper-file pattern and is not a defect; one that
rebuilds a command the package ships is a gap in that script.

**Report what did not improve.** A lever that cost a run and moved
nothing belongs in the PR body too — it is what stops the next person
from trying it again.
