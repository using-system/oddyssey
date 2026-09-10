# Long, expensive or non-deterministic scenarios

Three carve-outs of `SKILL.md` step 3, read when one applies.

## When an iteration is expensive or non-deterministic

The counts above assume cheap, repeatable iterations. Some scenarios are
neither: an LLM-backed job can cost real money and tens of minutes per
iteration, and two identical invocations legitimately differ (turn
count, tool mix, tokens, duration). Then:

- **How many samples to spend is the caller's decision, not yours** —
  state the count in the record and run that. When the mission names no
  count and an iteration is visibly expensive, stop after the first
  sample and ask: a sample spent is a decision the caller never made.
  Skipping the warmup is expected at these prices: keep the first
  sample and mark it cold instead of discarding it.
- **Never dress samples up as statistics** — quote every number with its
  sample count (`n=2`), and at one or two samples write *observation*,
  never a quantile or a mean. A verify run that diffs two single
  observations is comparing noise.
- **Non-deterministic runs are compared by structure and order of
  magnitude** — same steps present, similar proportions, durations and
  costs in the same range — never value against value. Record what varied
  between identical invocations, so the verify run knows what noise
  looks like.

## Waiting out the scenario — inside the turn, never past it

A scenario that fits a tool call's budget (hosts allow up to ~10
minutes) runs as **one blocking foreground command** that drives the
requests and exits when the last one is done — never as a background job
plus a poll loop. A wait — the flush wait, or a poll for the job's end —
is a `sleep` inside a `#!/bin/bash` helper file, written with the file
tool and run in the foreground as `bash <file>` under the tool's
timeout, a wait longer than one call's budget split across consecutive
calls (the scenario may then have to run as a background job — the wait
never does). A Monitor-style until-condition tool is a background
notifier: its events arrive after the turn ends, so it waits only in a
main conversation, which is re-invoked when they do — as a subagent it
is not a wait at all. Never end the turn to "wait for a completion
notification": as a subagent — the nominal case — ending the turn
terminates the mission, the scenario keeps running orphaned, and the
waiting sentence becomes the final result (only a main conversation is
re-invoked when a background task finishes).

## Scenarios longer than a tool call

A job running 15–30 minutes cannot be polled inside a single tool call
on hosts with a hard tool timeout (some enforce ~10 minutes): the call
dies mid-wait and takes its observations with it. The working shape is
a **detached job with a polled record**: start the job so it survives
the tool call that spawned it, have it write its progress and its
outcome to a file, and let later tool calls read that file.

**A stored benchmark needs none of this written**: its replay script
already ships that shape (`--detach` starts it, `--status --wait` blocks
until it finishes),
and authoring a poller for it is writing a command the package
supplies. What follows is for an **ad-hoc** scenario, which has no such
script. Start the job, then launch a small script with `nohup` that
polls it and appends timestamped progress to a file. The scenario
record cites the poller script and its output file verbatim — they are
part of the protocol, and a replay re-runs the same poller, not a
hand-watched approximation.

The poller, its state and its output live in the same scratchpad
subdirectory as every other file of the run (step 5): the directory the
caller named, else `<scratchpad>/<run slug>/`. Parallel missions share
the scratchpad root: an earlier run's `k6-exit.code` left in it makes
the poller's `while [ ! -f k6-exit.code ]` false on its first check, so
the poller exits at once and its log carries the other run's lines — a
finished run that never ran.

