---
name: test-plugin-harnessing
description: Measure and optimise one phase of an oddyssey run - preflight, drive, observation - against the published benchmark row for that model. Use when a phase is too slow or too expensive, when a harnessing change must be proven rather than asserted, or when a run is suspected of composing work the package should ship. Drives opencode headless, measures the phase, names where the time went, and separates what the package controls from provider latency. Never a substitute for launch-llms-benchmark, which grades findings; this grades the harness.
---

# Testing a phase of the plugin's harness

`launch-llms-benchmark` asks *how good is this model's report*. This asks
a different question: **how much work does the package still make the
model compose before it can do anything** — and it answers it for one
named phase at a time. Do not run the benchmark protocol for this; it
grades findings, costs a full run, and its row is not what moves when a
skill stops making the model write a script.

The rules a change here must satisfy are `AGENTS.md`'s **Plugin
harnessing** section. This skill is how you prove one landed.

## What you need before starting

- **The phase**, named by the caller: `preflight`, `drive`,
  `observation`, or `whole`. Ask if it is not named — measuring the
  wrong phase wastes the run.
- **The mission**, the same on every sample, and by preference an
  observation in **drive mode on the local stack**: the run generates
  its own traffic, so every window holds the same requests and the
  samples differ in how they worked, not in what there was to find. A
  post-hoc window holds whatever landed that minute (a late burst, a
  real error — measured 2026-09-09: one 502 gave three samples an extra
  finding and 34 to 40 queries against 24 to 30): measure post-hoc only
  when post-hoc is what changes, with one scripted burst per sample and
  the stack's facts re-read per window; a remote stack only when the
  change is that stack's, never by default.
- **The baseline**, which is the published row in
  `.llms-benchmark/README.md` for the model you will use: its phase
  durations, its turn count and its **median turn**. Read it from
  `origin/main`, never from the working tree.
- **A model whose median turn is small.** The published median is the
  instrument's precision: a model at 3 s per turn measures the harness,
  one at 20 s measures the provider. Prefer the fastest row in the
  table, whatever its findings score — this is not a quality test.

## The procedure

1. **Rebuild the generated tree.** A CLI agent loads
   `marketplace/`, not `.apm/`, so an unregenerated tree runs the
   *previous* version of every prompt, agent and skill — the run then
   measures the old package while looking exactly like it measures the
   new one. `bash scripts/build-marketplace.sh`, then grep the change in
   the generated file the run will read. This is the single most
   expensive mistake available here; make it once and every number since
   the change is void.

2. **Deploy to every scope the host reads, and prove they match.**
   `uvx --from 'apm-cli==0.29.1' apm install --target opencode` for the
   repository, and copy `.apm/skills/*` and `.apm/agents/*` over
   `~/.claude/skills` / `~/.claude/agents` when the host also reads a
   user scope. Back the user scope up first and restore it at the end —
   it is the user's install, not yours — or, when the user's home must
   stay untouched, run the host under a fake `HOME` whose `.claude`
   carries the deploy and whose every other entry is a symlink to the
   real home (the credentials, the log and the session store stay
   where the scripts read them). `diff -rq` the two scopes: a run
   that finds them different spends turns comparing them.

3. **Clean what the next run must not read.** Any report a previous run
   stored, and any leftover container, process or scratch directory. A
   run that reads the last run's conclusions is not measuring anything.

4. **Measure**, with `scripts/measure_phase.py`:

   ```bash
   python3 <this skill's directory>/scripts/measure_phase.py \
     --model <openrouter id> --tag <short label> --phase <phase> \
     --prompt-file <mission> --out <study dir>
   ```

   A mission that opens with a slash command (`/odd-observe ...`) is
   launched through the host's own expansion (`--command`), the way a
   typed command is: passed as raw text, the run spends its first turns
   hunting for the command file - globs, reads of the command and of
   the agent it dispatches - a cost no host pays, folded into every
   phase number (measured: 8 to 10 turns of a 75-turn run). The record
   carries `command` so a number taken the old way is never compared
   with one taken this way.

   Its whole surface, so `--help` has nothing to add: `--model`,
   `--tag`, `--phase`, one of `--prompt` / `--prompt-file`, `--out`,
   plus `--end-pattern` (a regular expression over the run's own log
   lines, for a mission with no k6 drive to mark the phase - a post-hoc
   observation, a scenario the mission names), `--variant` (default
   `medium`), `--timeout` (default 2700 s) and `--keep-running` to let
   the run continue past the phase. It records
   the run's own id at launch, stops at the phase's marker, and exits
   non-zero rather than return a fast wrong number when the phase never
   closed.

5. **Analyse before concluding**, with `scripts/analyze_run.py`:

   ```bash
   python3 <this skill's directory>/scripts/analyze_run.py --record <study dir>/<tag>.record.json
   ```

   Surface: `--record`, or `--run-id`; `--gap` (default 60 s) sets the
   gap it reports; `--json`. It prints the
   commands, the
   turns, the generation time and the median turn, then the four
   behaviours a harnessing change removes — scripts the run authored,
   stack resets, machine questions already answered upstream, `--help`
   calls on shipped scripts — and every silent gap.

6. **Read the gaps before believing the clock.** A gap with no command
   in it is the model generating. One far above the run's median turn is
   the provider, not the package: the script says so, and when it does,
   the wall clock is not comparable to anything. Compare **generation
   time** and **commands** instead, or measure again later.

7. **Fix one lever, then measure again.** One change per run, rebuilt
   and redeployed per steps 1-2. Two changes in one run cannot be
   attributed, and the run-to-run spread is wide enough to hide a small
   effect either way.

8. **Restore the machine.** The user's skill and agent scopes from the
   backup, the generated trees to `origin/main` (the release workflow
   owns them), `.gitignore` and anything else `apm install` edited, the
   containers down, the stray processes killed.

## Judging what you measured

**The baseline is main, measured just before the work starts**, with
the same mission, the same machine and the same harness as the runs
that follow — never the published row alone, never a number taken on
another day. State it on four axes at once: turns, tokens (input with
the cached share, output), cost and wall clock — per phase, since the
report phase is a tenth of a run and a change there vanishes in the
investigation's spread. When a number looks like variance, replay
rather than argue: two samples of the same configuration settle what
one cannot.

**A change goes to review only with a substantial gain on those axes
against that baseline** — not a conformant output alone, not a
behaviour count alone. A change that moved the target phase and left
the totals level, or worse, is reworked, not argued: find where the
turns and the context went (per-phase accounting, the reads of every
file the change touched, the calls the new invocation caused), fix the
cause, and measure again.

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
