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
requests and exits when the last one is done — never as a background
job plus a poll loop. When the platform blocks foreground `sleep`, use
its blocking wait primitive (a Monitor-style until-condition tool)
instead of pushing the wait itself into the background (the scenario
may then have to run as a background job — the wait never does). Never
end the turn to "wait for a completion notification": as a subagent —
the nominal case — ending the turn terminates the mission, the
scenario keeps running orphaned, and the waiting sentence becomes the
final result (only a main conversation is re-invoked when a background
task finishes).

## Scenarios longer than a tool call

A job running 15–30 minutes cannot be polled inside a single tool call
on hosts with a hard tool timeout (some enforce ~10 minutes): the call
dies mid-wait and takes its observations with it. The working shape is
a **detached poller**: start the job, then launch a small script with
`nohup` (survives the tool call that spawned it) that polls the job and
appends timestamped progress to a file; later tool calls only read that
file. The scenario record cites the poller script and its output file
verbatim — they are part of the protocol, and a replay re-runs the same
poller, not a hand-watched approximation.

