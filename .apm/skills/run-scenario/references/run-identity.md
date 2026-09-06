# The run's identity

The clean-base order, the identity every query is qualified by, and
the situations that change how it is obtained — read the block that
applies, after `SKILL.md`. The record shape is `SKILL.md` step 4.

## A clean backend is not a clean run

`odd_stack_reset` clears the **store**, not the **process**: cumulative
counters and histograms live in the application and keep their pre-run
history, while traces and logs are window-scoped — the two signal
families disagree about what "the run" is. Restart order matters too: an
old process that outlives the reset flushes its whole cumulative history
into the brand-new store on its next periodic export.

Start a clean run in this order — the reverse of what feels natural:

1. **Restart the observed process first** — its dying flush lands in the
   old store;
2. **then `odd_stack_reset`** — the wipe takes that flush with it;
3. record the new process's identity in the protocol —
   `service.instance.id` when the SDK emits one, or the backend
   equivalent when it is absent (its start time, a
   `target_info` label, a container id) — and qualify every
   cumulative-metric query with it: an unfiltered query mixes instances
   the moment an old one got a last export in.

   **Prefer creating the identity over hunting for a substitute.** When
   the driven service honors `OTEL_RESOURCE_ATTRIBUTES` — any OTel SDK
   service, including `oddyssey-mcp`, which strips the SDK's default
   UUID unless opted in — launch its process with
   `OTEL_RESOURCE_ATTRIBUTES=service.instance.id=<run slug>` and record
   the slug you chose. One bounded label per run makes the run's
   cumulative series attributable by name and keeps a co-resident
   server's re-exported history (an installed `uvx oddyssey-mcp`
   long-lived process dumps its whole counter history into a
   seconds-old store) separable instead of merely suspected. The
   substitutes above stay the fallback for services that cannot opt in.
   The OTel attribute never reaches a Pyroscope SDK: when the service
   pushes profiles, pass the same slug to the profiler as a tag
   (`service_instance_id=<run slug>`) so its profiles are attributable
   too — otherwise its profiles fall back to `process.runtime.version`
   and application frames, stated in the record.

## The port is already served

Before launching the service, look at
who listens on its port: `lsof -nP -iTCP:<port> -sTCP:LISTEN` (exit 1
and no output on a free port). When the port is served by a process
the run did not start — a stale instance from an earlier session, a
compose container, someone's work — **never kill it**: run your own
instance on a free port, launched with the run slug as its
`service.instance.id` (above), and drive `127.0.0.1:<port>`, never
`localhost` — on a dual-stack host `localhost` may resolve to whichever
listener bound the other address family. Qualify every query by the
run's identity: co-resident emitters sharing a `service.name` fold into
one series otherwise, and their divergent code states re-export into
the fresh store. A mission that says "start the service on :<port>"
reads as "on that port, or the next free one": the deviation is a
`Listeners:` line in the record — each foreign listener with its pid,
command and bind address, and the port the run used instead; record
those fields, never the raw `lsof` output, whose `USER` column is a
login name — and a sentence in section 1 of the report. A replay
reads the recorded port the same way: the requests and counts must
match, the port need not, and a moved port is another `Listeners:`
line. When the port cannot be moved — fixed in an image, a compose
file or the code — neither kill the listener nor drive it: stop and
report what holds the port, with the probe's fields. A run that cannot
prove which process it measured is not a measurement.

## The run launches nothing

A remote target the run cannot start — a
deployed service with public ingress, driven by someone else's traffic
too — offers no process to launch with a slug and no
`OTEL_RESOURCE_ATTRIBUTES` to set: the identity travels **in the
requests** instead. Carry it in two headers on every driven request,
and never in only one of them:

- `User-Agent: odd-<prompt>/<run slug>` (`odd-verify/<slug>`,
  `odd-observe/<slug>`; `-warmup` appended on warmup requests — the
  suffix that dates the run, "The run starts after the warmup" below).
  The server's HTTP instrumentation records the header as
  `user_agent.original`, selectable on the request rows of every backend
  (`customDimensions['user_agent.original']` in KQL,
  `span.user_agent.original` in TraceQL) — this is the identity a
  latency question reads, and it survives a service that ignores
  `traceparent`. One store reads it on **whichever span roots the
  trace**. An X-Ray trace summary carries no user agent when the root
  is a client's own instrumented span (an instrumented load generator
  — `Http.UserAgent` `null` on every summary, verified 2026-09-05; the
  filter empty over a range holding the run's traces, 2026-09-04):
  there the trace-id prefix below identifies the run, and its latency
  reads from the server segment through `batch-get-traces`, never from
  a summary's `Duration`. When the generator emits no client span of
  its own, the server's own segment roots the trace and the identity
  is readable — `Http.UserAgent` carrying the run's User-Agent on
  every summary (verified 2026-09-06).
- `traceparent: 00-<trace id>-<span id>-01`, the trace id being
  **32 hex in three parts**: a fixed 8-hex prefix shared by every run
  of the protocol (`0ddc0ffe` unless the protocol records another),
  8 hex derived from the run slug (the first 8 of
  `sha256(<slug>)`), and the zero-padded 16-hex request sequence
  number; the span id is the sequence number on 16 hex. The sequence
  numbers every driven request of the run, warmup included, from
  **1** — one counter for the whole run, or, where the generator
  holds no counter its workers share, a field made **disjoint per
  worker by construction**, over every worker that sends a request (a
  k6 script's VUs, and its setup and teardown: the stored-benchmark
  paragraph below): a span id of all zeros is
  invalid under W3C trace context, the instrumentation then starts a
  fresh trace and that request drops out of every prefix selector,
  and a counter restarted per phase gives two requests one id. The prefix is
  what a selector matches — `operation_Id startswith '<prefix>'`
  (KQL), `{ trace:id =~ "<prefix>.*" }` (TraceQL), `trace_id =~
  "<prefix>.*"` (LogQL) — and pulls every request, dependency, log and
  exception row of the run with no process identity at all; the slug
  part is what keeps two runs apart: a trace id made of the prefix and
  the sequence alone is the **same set of ids on every replay**, and
  the backend merges the runs under them (observed: one trace id, two
  instances, two User-Agents). Two runs may share a prefix, never an
  id. A trace store may print the id **without its leading zeros** —
  Tempo does (`0ddc0ffe…` reads `ddc0ffe…` in `gcx traces query`
  output, while Loki keeps the 32 hex; verified 2026-09-05) — so a
  prefix check on such output strips them on both sides
  (`sub("^0+"; "")`), and pads them back when the id is then passed to
  a flag that validates its width.

**A stored k6 benchmark carries the identity its manifest declares.**
Its script may not be edited (`references/benchmark-replay.md`), so the
identity is the one it was authored with, read from the manifest's
`identity:` block: the `user_agent` its requests carry
(`odd-bench/<name>[/<slug>]` in the stored benchmarks), the
`run_slug_env` variable the slug travels in (`RUN_SLUG` there), the
request tags, and whether a `traceparent` is sent. **Pass the slug
through the variable the manifest names, every run** — `-e
RUN_SLUG=<slug>`: without it the User-Agent is the benchmark's name
alone, every replay sends the same one, and the runs merge under it
exactly as two runs sharing a trace id do. k6's `--user-agent` flag
(verified k6 v2.2.0) sets only the default k6 uses when the script sets
no header of its own — against a script that sets one it is at best
redundant and at worst a second, conflicting identity, so it is passed
only when the manifest declares no `user_agent`. There is no `-warmup`
suffix mid-run either (one process, one User-Agent): what dates t0 is
the manifest's own warmup stage — its per-request `stage` tag when the
manifest declares one, the record's `Warmup:` line otherwise ("The run
starts after the warmup" below). No flag sets a `traceparent` either:
whether one goes out is the script's doing, and the `identity:` block
is what says so. A script authored to send it
(`k6-benchmark-expert`'s authoring contract: both headers built from
the slug the `run_slug_env` variable carries, the `traceparent` behind
a second gate the block names — read by presence, so a remote drive
sets it and a local one leaves it out of the command rather than
giving it a value meaning off — a launched process already carries
`service.instance.id`, and the caveat below would cost it its trace
roots for nothing) makes such a run **prefix-selectable like any
other** — the same three-part trace id above, its sequence field
disjoint per runtime rather than one run-wide counter, since k6 holds
no counter across the runtimes that send its requests (its VUs, and
its setup and teardown); the manifest states the scheme it used and
the prefix the script baked in at authoring time — that recorded
literal, never a prefix the protocol names later, is what the run's
rows carry — and the rootless caveat below travels with the header
wherever it goes out. A block that says the header is not sent —
every benchmark stored today — and a drive that leaves the gate unset
both leave the run **UA-selected**: its `Identity:` line quotes the
User-Agent form the rows actually carry, the trace-id prefix selectors
above have nothing
to match, and every ruling comes from `user_agent.original` (an
uninstrumented k6 emits no client span, so the server's own span roots
each trace and the User-Agent is readable on the summary rows — the
last case of the bullet above). Either way the header block is
authored, never written into the script at mission time: giving a
stored benchmark one is a re-authoring, through
`/odd-instrument-bench`'s reviewed diff.

Then **read the instance from the run's own rows** —
`service.instance.id` (or the backend's equivalent) on the requests
the identity selects — and record it; it is never asserted up front,
and a run whose rows name two instances says so (a deploy in the
window, a scaled service). One caveat travels with the scheme: a
synthetic `traceparent` makes every run trace **rootless** — the
parent span id never existed — which is fine for presence and count
rulings and wrong for a latency investigation, whose numbers come
from the User-Agent identity alone. The `Identity:` line of the
record (`SKILL.md` step 4) carries both headers' forms with the slug, the prefix
and the instance read from the rows.

## The run starts after the warmup

The warmup requests of `SKILL.md` step 2 are discarded from the quoted
numbers — and from the run's **start**: **t0 is the first measured
request, never the first request the run sent**. A `min(start time)`
taken over the whole identity dates the run from a warmup request, and
every stage boundary derived from t0 shifts with it — the run
mis-buckets, with no error anywhere (verified 2026-09-06: stage counts
of n=1 and n=176 until the warmup requests were excluded from t0).
What marks them depends on how the identity travels: the `-warmup`
suffix on the User-Agent when it travels in the requests (above) — so
carve t0 from the rows whose User-Agent has none — and otherwise the
`Warmup:` line of the record (`SKILL.md` step 4), which says how many
requests per operation to drop before taking t0.

## Reset once

That clean-base reset is the only reset this skill takes
on its own. Any further `odd_stack_reset` inside a mission is an
explicit mission requirement — an operation the mission observes (a
lifecycle test whose subject is the reset itself), an env change the
mission dictates mid-run — never the agent's initiative: a reset
costs ~6 s, wipes the store, and restarts the flush wait (`SKILL.md` step 5) from
zero. Every reset the mission requires is its own `Commands:` line in
the record (`SKILL.md` step 4), carrying the env it passed and the reason it
exists.

## When restarting is not possible

Say so in the record — and still record
the identity **and the process start time**: the start time is what
dates the pre-window history. Traces and logs stay trustworthy, but
cumulative metrics read inside the window include pre-window activity —
treat them as deltas between the window's edges, never as run totals
(valid only within one instance, which the recorded identity proves).

## When a reset is forbidden

Not impossible, actively harmful: a
creation-time env the reset would not reapply (credential-named
variables are never persisted — `env_not_persisted` names them — and a
manually run or pre-persistence container has nothing recorded to
reapply), or shared stored
history the caller still needs — do not take the clean slate at all.
Isolate the window without one: **time-scope every query explicitly**
to the recorded start/end (no unscoped search, no store-equals-run
shortcut), qualify every cumulative-metric query with the recorded
identity and read it as a window-edge delta, and say in the record
that the run rode a shared store and why the reset was off the table.
A window carved by timestamps out of a live store is a weaker
isolation than a wipe — the record must let the verify run reproduce
the same carving.

