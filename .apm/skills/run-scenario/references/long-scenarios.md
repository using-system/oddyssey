# Long, expensive or non-deterministic scenarios

Two carve-outs of `SKILL.md` steps 2 and 3, read when one applies.

## When an iteration is expensive or non-deterministic

The counts of step 3 assume cheap, repeatable iterations. Some scenarios
are neither: an LLM-backed job can cost real money and tens of minutes
per iteration, and two identical invocations legitimately differ (turn
count, tool mix, tokens, duration). Then:

- **How many samples to spend is the caller's decision, not yours** —
  state the count in the record and run that. When the mission names no
  count and an iteration is visibly expensive, stop after the first
  sample and ask: a sample spent is a decision the caller never made.
  Skipping the warmup is expected at these prices (`--warmup 0`): keep
  the first sample and mark it cold instead of discarding it.
- **Never dress samples up as statistics** — quote every number with its
  sample count (`n=2`), and at one or two samples write *observation*,
  never a quantile or a mean. A verify run that diffs two single
  observations is comparing noise.
- **Non-deterministic runs are compared by structure and order of
  magnitude** — same steps present, similar proportions, durations and
  costs in the same range — never value against value. Record what varied
  between identical invocations, so the verify run knows what noise
  looks like.

## Scenarios longer than a tool call

A job running 15–30 minutes cannot be polled inside a single tool call
on hosts with a hard tool timeout (some enforce ~10 minutes): the call
dies mid-wait and takes its observations with it. Nothing is written for
a drive: an ad-hoc scenario is the drive script's `--detach`, then
`--status --wait` (`SKILL.md` step 2); a stored benchmark is its replay
script's, the same two flags (`benchmark-replay.md`). Authoring a poller
for either is writing a command the package supplies.

What follows is for one case only: the **watch of a run someone else
drives, on a backend whose reference ships no watch script** —
`benchmark-replay.md`'s watching section carries the criteria, this
section the shape: a **detached job with a polled record**. Start the
poller so it survives the tool call that spawned it, have it append
timestamped progress and its outcome to a file, and let later bounded
calls read that file — inside the turn, never a turn ended to wait for
a completion notification (as a subagent, ending the turn ends the
mission). The record cites the poller and its output file verbatim on
its `Poller:` line — they are part of the protocol, and a replay re-runs
the same poller, not a hand-watched approximation. Its state and its
output live in the run's own scratchpad subdirectory (`SKILL.md` step
2): parallel missions share the scratchpad root, and a state file left
by an earlier run makes a poller's first check true — a finished run
that never ran.
