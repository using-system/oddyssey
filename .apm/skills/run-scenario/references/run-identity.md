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
  `odd-observe/<slug>`; `-warmup` appended on warmup requests). The
  server's HTTP instrumentation records it as `user_agent.original`,
  selectable on the request rows of every backend
  (`customDimensions['user_agent.original']` in KQL,
  `span.user_agent.original` in TraceQL) — this is the identity a
  latency question reads, and it survives a service that ignores
  `traceparent`.
- `traceparent: 00-<trace id>-<span id>-01`, the trace id being
  **32 hex in three parts**: a fixed 8-hex prefix shared by every run
  of the protocol (`0ddc0ffe` unless the protocol records another),
  8 hex derived from the run slug (the first 8 of
  `sha256(<slug>)`), and the zero-padded 16-hex request sequence
  number; the span id is the sequence number on 16 hex. The sequence
  numbers every driven request of the run, warmup included, from
  **1** — one counter for the whole run: a span id of all zeros is
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
  id.

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

