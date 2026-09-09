# Replay a stored k6 benchmark

When the mission names a benchmark under `.odd/benchmarks/<name>/`
(`k6-benchmark-expert` authored it, `odd-memory`'s `benchmark`
reference stored it),
the load comes from its script instead of a curl loop. On a **local**
drive the identity reference and `SKILL.md` steps 3 and 5 apply
unchanged — the clean-base order, the run's t0 after the warmup, the
sample-count rules, the flush wait — and `SKILL.md` step 4 applies with
the record shape below; a remote drive changes four things, in its own
section; and a run you do not drive at all — `observe-run`'s observe
mode, someone else running the script — is the last section, read with
this one and never instead of it. What
differs is how the load is generated and how the record cites it:

## Replaying is the `k6-guides` skill's job

Do not build a k6 command here. `k6-guides` owns everything k6 in this
package — the knowledge and the tooling — and its `## Running` section
carries the replay script, what it refuses, and what the caller still
decides (the run slug, the run-time inputs, and whether a traceparent
goes out). Run it and bring back its record.

What belongs to this side is what happens **around** the replay: the
clean base below, the warmup the manifest's stages define, waiting for
the flush before querying, and the fact that k6's own exit status is
evidence and never the verdict — the verdict comes from the telemetry.
## The clean base is the run slug; the reset is a separate decision

For a local drive, the clean base is `references/run-identity.md`'s
order **without** its wipe: restart the observed process with the run
slug as its `service.instance.id`, and the run is separated from
everything the store already held — the slug qualifies the cumulative
metrics, and the replay's own recorded window scopes the trace and log
queries to this run. That is the default, and it costs nothing.

`odd_stack_reset` on top of it buys an empty store and nothing else,
while costing a container recreation and its health wait **inside the
preflight** and destroying the history a later post-hoc comparison
would have read. Take it only when the mission asks for an empty store,
when a baseline is expressed in absolute counts rather than deltas, or
when retention would drown the run's own data — and say which of the
three in the record. When a reset is taken, `run-identity.md`'s order
is load-bearing; when an env forbids one, its forbidden-reset block is
the protocol (time-scope every query to the recorded window, qualify by
the identity, read cumulative metrics as window-edge deltas). The
record's `Backend:` line says which case the run had. A remote drive
has no reset at all (below).

## Warmup is the manifest's stage boundaries

A k6 run is one
continuous window, so `SKILL.md` step 2's "discard the warmup" becomes a
sub-window: quote steady-state numbers from the interval the
manifest's ramp and steady stages delimit, record those boundaries
as UTC timestamps, and say the ramp was excluded. `SKILL.md` step 3's
standard sample counts apply (>= 30 requests before a p95, ~100 before a p99)
— k6 load is cheap, high-volume, and deterministic, so the
expensive-iteration carve-out of `references/long-scenarios.md` does
not.

**Two anchors, named separately — they are not the same instant.** The
manifest's stage offsets (`from`/`to`, seconds since the scenario
started) convert to UTC from the **run's first request row**: the
warmup is a scheduled stage of the profile, not something discarded
before the load begins, so the stages are laid out from the run's own
first request — never from k6's process start (init and VU allocation
land that request ~1 s later), never from the summary's start, and
never backwards from the end (a run may exit before the manifest's
total duration when nothing is left to schedule in a ramp-down, and
boundaries carved back from the end then slide). `run-identity.md`'s
**t0 is the other anchor** — the first *measured* request, the start of
the numbers the report quotes — and it sits at the end of the
manifest's warmup stage, typically tens of seconds after the first
request row. Annotate both on the record's stages line; a record that
conflates them mis-buckets by a whole warmup stage. When the manifest
declares no warmup stage — a smoke quoting its whole run, say — the two
anchors coincide, and the record says so rather than inventing a warmup
the manifest denies; what such a profile excludes instead (a first
iteration carrying the handshake) is the manifest's own words to
follow. Where the manifest
declares a per-request `stage` tag, neither arithmetic is needed for
the stages at all: read them off the tag, which the script stamps as
each request goes out. To the second is the precision the record
states: `date -u +%Y-%m-%dT%H:%M:%SZ`, never `%3N` — BSD `date` on
macOS has no `%N` and prints the literal `…14.3NZ`. The record's window
runs from the first request row to k6's exit, and a query bounded on a
stage takes ±1 s around the boundary.

**Exact per-stage counts come from the trace listing.** A sub-window
carved out of a cumulative metric is export-interval-aligned, so it
answers at the last export before the boundary rather than at the
boundary: a counter read at a stage's end gave 126 where the trace
listing held 180 for the same stage (60-s export, verified
2026-09-06). Count on the rows, and quote any metric-derived per-stage
value with the shift it carries (≤ one export interval).

## Bucketing a ramp for the degradation curve

A ramp is read as a curve, and two replays must carve it identically:
**30-second segments measured from the ramp stage's own start** (the
manifest's `from` for that stage, converted as above), and the
**offered rate quoted per segment is the stage's rate at the segment's
midpoint** (linear interpolation between the stage's endpoints), never
its start or its end. No manifest declares a segment width today, so 30
seconds is the rule in practice; where one does, its width wins. Either
way the width belongs to the record — it is part of the protocol a
replay repeats, like a request count — as one clause on the stages
line: `ramp 10:04:12–10:14:12, read in 30 s segments, offered rate at
each segment's midpoint`. It is the stress and breakpoint ramps that
are read this way; an excluded warmup ramp is carved by nobody.

## k6's own summary and exit status are evidence, never the verdict

Record the exit code (`0` every threshold passed, `99` a threshold
was crossed, anything else a setup or script error — read stderr),
the request count, failed checks, dropped iterations, and script
exceptions from stderr — folded into the record's `k6:` line, which
is what survives. **Read the export through `running-tests.md`'s
"Reading k6's own evidence" before quoting a number from it**: its
threshold booleans and its `Rate` fields do not mean what their names
suggest, and a `k6:` line that reads them as plain English inverts the
run. The summary file itself is transient: write it to
a scratch location, never inside `.odd/benchmarks/<name>/` (it would
dirty the directory the record just declared clean), and never
count on it existing when the run is verified later. Then measure
through the service's own telemetry, after `SKILL.md` step 5's flush wait. A
generator that never connected, crashed mid-run, or threw on every
iteration leaves telemetry that looks deceptively clean — "a failed
or partial run is data" applies to the generator too; a
`level=info msg="... failed to upload metrics: context canceled"` line
at shutdown is **not** one of those (`running-tests.md`: k6 cancelled
its exporter's last flush after every row had landed), and never
enters the `k6:` line as a partial run. The manifest's
thresholds are what the observation rules on, each against a
telemetry-derived measurement carrying its query — **unless the
generator threw**: script exceptions above zero mean the benchmark
did not exercise what it was built to measure, every threshold
ruling is void, and the run is reported as a defective benchmark (a
finding against the script, to fix through `/odd-instrument-bench`),
never as a pass.

## k6's own OpenTelemetry output is a bonus signal

Against the local
stack, `K6_OTEL_GRPC_EXPORTER_INSECURE=true k6 run -o opentelemetry
<script>` lands k6's client-side view in the same store under
`service_name="k6"` (`running-tests.md`): cross-confirm against it
when it lands, never require it, never mistake it for the target
service. How those series are selected, what a store-side quantile over
them is worth, and how an empty result reads are that same reference's
subject — read it there before quoting one of them.

One consequence for an arrival-rate benchmark: on the one run recorded,
a `dropped_iterations` of zero had no series at all in the store
(`running-tests.md`, which does not generalise it to every counter at
zero) — so when the series is missing, that threshold is not
cross-confirmable here. Rule it from the service's own telemetry
instead — **received against scheduled**, the scheduled count being the
integral of the manifest's stage rates over the run — and say in the
report that this is what the number is.

## The replay is always detached

**Every replay runs with `--detach <dir>`, whatever the benchmark's
length** — never in the foreground:

```bash
python3 <skills>/k6-guides/scripts/replay_benchmark.py <benchmark dir> --run-slug <slug> --detach <scratch>/<slug> [--otel] [-e KEY=value ...] [--send-traceparent]
python3 <skills>/k6-guides/scripts/replay_benchmark.py --status <scratch>/<slug> --wait <the benchmark's length plus a margin, e.g. 5m>
```

The first starts the run in its own session and returns at once; the
second blocks until it finishes and prints the finished record with its
UTC window and k6's real exit status (exit 3 when the bound passes with
the run still going: run it again). The whole surface is those two lines
plus `--summary <file>`, `--dry-run` and `--json`; `--otel` is the local
stack's OTLP output, `--send-traceparent` the gated header of a remote
drive, `-e KEY=value` a mission-time input. Nothing else: `--help` has
nothing to add and the file has nothing to read. When the mission block
carries a `Replay:` line, it is this invocation with every value filled
in — run it as is, under your own scratch directory. A foreground replay
killed at the host's timeout leaves k6 running and no record, and the
next move is a second drive. **Never author a poller for this** — a
loop on `--status`, a `sleep` in a helper — it is a command the package
ships, written again, and one more thing to write before the drive.

Whatever watches the run **watches it, it does not drive the service**:
it reads k6's own output and the process, and sends no request the
benchmark did not. When a liveness probe is genuinely needed, it goes
to a route the benchmark excludes, at a fixed interval, and its route,
interval and total count go on the record's `Poller:` line — load a
replay repeats and the measured numbers leave out.

## Reading a breakpoint run

A `breakpoint` benchmark has no steady state, so the steady-state
sub-window above does not exist: the per-segment (or per-checkpoint)
view replaces it, and **the end time is the result**. Three outcomes
are named; which of the first two a crossed threshold produces is the
manifest's `abort_on_fail`, not the run's:

- **the ceiling was reached** — a threshold with `abort_on_fail: true`
  stopped the run, and the manifest's own reading of the breaking point
  applies: the elapsed time and the rate at the abort;
- **a threshold was crossed without aborting** — exit 99 at the run's
  full length, the shape a threshold with `abort_on_fail: false`
  produces (this repository's breakpoint has one such threshold next to
  three aborting ones). The ceiling is where that metric crossed, read
  from the telemetry per segment, not from the exit code, which only
  says that it did;
- **no threshold crossed, ceiling not reached** — the run went its full
  length at its top rate and exited 0. That is a result, not a missing
  one: report the ceiling as being **above** the top rate reached, with
  that rate and the length as its evidence, never as a pass on a
  question the run did not answer.

**Dropped iterations are read against the service's own latency.**
With a **flat** server-side p95 they are the generator's: VU allocation
lagging a slow path, or VUs parked in a back-off, drops iterations
while the service does not bend (observed: 52 drops while `vus_max`
grew 24 → 75 on a checkout tail) — a generator limit to record, never
a ruling on the service. With a **rising** one they are a breakpoint
signal in their own right, the arrival rate outrunning the VU cap
because the service slowed, which is what an arrival-rate manifest
expects to see; the manifest's own reading of them wins where it has
one.

## Driving a remote target is the caller's decision, and changes the record

Whether a
benchmark may be driven at a remote target is the observation
caller's decision, given at mission time through `observe-run`'s own
rule — never read from the manifest, never decided here. Once it is
given, four things change and nothing else does:

- **the identity travels in the requests** (`run-identity.md`, "The run
  launches nothing"): there is no launched process to name, so the
  manifest's `user_agent` with the slug passed through its
  `run_slug_env` is the identity the requests carry — and **this is
  the drive that sets the `traceparent` gate**, through the variable
  the manifest's `identity:` block names, since nothing else here
  identifies the run. A benchmark whose script builds the header is
  then selected on the trace-id prefix as well (`run-identity.md`'s
  stored-benchmark paragraph); one whose block says the header is not
  sent — a script that cannot send one — is UA-selected, with the
  prefix selectors unavailable and nothing the gate can turn on. The
  `Identity:` line says which of the two the run had, and the instance
  is read from the rows;
- **`Backend: no reset (remote)`** — there is no reset to take, so the
  run is isolated by its window and its identity alone;
- **`Listeners: n/a (remote)`** — no port was probed and no process
  launched; the instance is read from the run's own rows;
- **the flush wait is the backend's**, sized by `observe-run` from the
  backend's documented ingest latency or proven with a bounded query,
  never the local ~10 s / ~60 s — that proof is what the
  `Query points:` line cites.

The record replaces `SKILL.md` step 4's `Commands:` lines with the benchmark's
identity, the single command, and k6's own evidence:

```text
Scenario:  benchmark orders-read-heavy
Benchmark: .odd/benchmarks/orders-read-heavy/ @ 3ccfd18 (clean; HEAD 1a73941 at start)
Base URL:  http://127.0.0.1:8080   # BASE_URL, mission-time
Listeners: none
Backend:   odd_stack_reset, env: defaults
Instance:  orders-run-0902 (restarted before reset)
Identity:  service.instance.id=orders-run-0902 on the launcher; User-Agent "odd-bench/orders-read-heavy/orders-run-0902" (the manifest's identity block, slug through -e RUN_SLUG); traceparent not sent — its gate is unset on a local drive, so the run keeps its trace roots and the instance id is the identity
Warmup:    the manifest's ramp-up stage, 60 s (excluded from the quoted numbers)
Stages (UTC): offsets converted from the first request row 10:04:12 — ramp-up 10:04:12–10:05:12 (excluded), steady 10:05:12–10:25:12, ramp-down 10:25:12–10:25:42; t0 (first measured request, where the quoted numbers start) 10:05:12
Started (UTC): 2026-09-02T10:04:12Z
Ended   (UTC): 2026-09-02T10:25:42Z
Query points: 1 (after Ended)
Poller:    none written - the replay ran detached and --status --wait blocked until it finished
Command:
  python3 <skills>/k6-guides/scripts/replay_benchmark.py .odd/benchmarks/orders-read-heavy --run-slug orders-run-0902 --otel --detach <scratch>/orders-run-0902   # --otel: local stack only; then --status <scratch>/orders-run-0902 --wait 25m
  k6 run .odd/benchmarks/orders-read-heavy/script.js --summary-export <scratch>/k6-summary-orders-run-0902.json -e BASE_URL=http://127.0.0.1:8080 -e RUN_SLUG=orders-run-0902 -o opentelemetry   # what it ran, from the record it printed
k6:        exit 0, 4210 requests, checks 100%, dropped iterations 0, script errors 0 (summary file transient, numbers above are the record)
Not reproducible: none
```

Both `Command:` blocks carry two lines on purpose: **what you ran** -
always the replay script - and **what it ran**, copied from the record
that script printed. Never compose the second line yourself; the script
is where the mapping lives (the surface stated in `## The replay is
always detached`). A flag that is not on its surface is not a flag this
replay has.

The same record for a remote drive, carrying the four changes above:

```text
Scenario:  benchmark orders-api-spike (remote drive, authorized in the mission)
Benchmark: .odd/benchmarks/orders-api-spike/ @ 454af15 (clean; HEAD 454af15 at start)
Base URL:  https://orders.example.com   # BASE_URL, mission-time
Listeners: n/a (remote)
Backend:   no reset (remote) — isolated by window and identity
Instance:  read from the run's rows: orders-api-7c9f (one instance)
Identity:  User-Agent "odd-bench/orders-api-spike/observe-spike-0906" and traceparent "00-0ddc0ffeb9197c59<seq:016x>-<seq:016x>-01" (the manifest's identity block, slug through -e RUN_SLUG, header gated on -e SEND_TRACEPARENT=1 as the block names it — set here because the drive is remote; sequence disjoint per runtime, the scheme the manifest states); selected on the UA and on the trace-id prefix 0ddc0ffeb9197c59 (the protocol prefix and sha256("observe-spike-0906")[:8]); latency read from the UA identity — the synthetic parent leaves the run's traces rootless
Warmup:    the manifest's baseline stage, 30 s (excluded), carried by the per-request stage tag
Stages (UTC): read off the stage tag, no arithmetic — baseline 08:30:11–08:30:41 (excluded), ramp-up 08:30:41–08:30:51, burst 08:30:51–08:31:21, ramp-down 08:31:21–08:31:31, recovery 08:31:31–08:32:01; t0 (first measured request) 08:30:41
Started (UTC): 2026-09-06T08:30:11Z
Ended   (UTC): 2026-09-06T08:32:01Z
Query points: 1 (after Ended + the backend's ingest wait, proven by a bounded count query)
Poller:    none written - the replay ran detached and --status --wait blocked until it finished
Command:
  python3 <skills>/k6-guides/scripts/replay_benchmark.py .odd/benchmarks/orders-api-spike --run-slug observe-spike-0906 -e BASE_URL=https://orders.example.com --send-traceparent --detach <scratch>/observe-spike-0906   # then --status <scratch>/observe-spike-0906 --wait 5m
  k6 run .odd/benchmarks/orders-api-spike/script.js --summary-export <scratch>/k6-summary-observe-spike-0906.json -e BASE_URL=https://orders.example.com -e RUN_SLUG=observe-spike-0906 -e SEND_TRACEPARENT=1   # what it ran, from the record it printed
k6:        exit 0, 4812 requests, checks 100%, dropped iterations 52 (generator: maxVUs saturated while the server p95 stayed flat), script errors 0
Not reproducible: none
```

## Watching a run someone else drives

`observe-run`'s **observe** mode with a benchmark: another mission — or
another person — runs the script, and you read only the telemetry.
Everything above about the manifest still holds — the `identity:` block
that says how the run is selected, the stage arithmetic and its two
anchors, the 30-second segments of a ramp, the breakpoint reading, the
thresholds ruled from the service's own telemetry. What changes is that
you hold none of k6's own evidence, and that the run's identity, its
start and its end are things you discover rather than decide.

- **The identity is discovered, not handed over.** The manifest's
  `identity:` block gives the stable half of the User-Agent
  (`odd-bench/<name>` in the stored benchmarks); the run slug is the
  half the driver passed through `run_slug_env`, and no mission block
  has to carry it. Select the run on that prefix inside the window,
  then **read the slug off the rows**, and record the whole User-Agent
  on the `Identity:` line with the instance, as a drive does. A
  `traceparent` the manifest declares shortens none of that — the
  driver may not have set its gate at all, and on a local drive should
  not have: the trace-id prefix the manifest records is shared by every
  run of that benchmark, and the 8 hex that single this run out are
  derived from the slug you are still looking for — so the User-Agent
  is what finds the run, and the trace-id selector becomes available
  only once the slug has been read off the rows, for what the
  User-Agent cannot reach (a log line, a dependency call). A prefix
  matching several slugs in the window is several runs, not one: watch
  the one the mission names, and otherwise report the ambiguity — each
  slug with its first row — rather than folding them into one set of
  numbers. What only the driver knows is recorded as exactly that: the
  driving mission under the name the mission block gives it (`not
  named` when it gives none), `Base URL: not observed` when the block
  does not state it, and k6's own evidence per the next bullet.
- **k6's evidence is the driver's, never inferred as if it were
  yours.** The exit code, the stderr and the summary belong to the
  process you did not launch. When the driver's record reaches you —
  its stored report's `k6:` line, or a `k6:` line the mission block
  hands over — quote it verbatim with where it came from, and the void
  precondition of "k6's own summary and exit status are evidence,
  never the verdict" above applies exactly as on a drive: script
  exceptions above zero void every threshold ruling. When it does not
  reach you, the `k6:` line reads **`not observed`**, and what stands
  in is the next bullet's — never a silent assumption that the
  generator ran clean, and never a `pass` resting on one.
- **What can stand in depends on the manifest's executor.** The rows
  attest only what the executor makes checkable, so the substitute is
  read off `profile.executor` before anything is counted:
  - **an open model** (`ramping-arrival-rate`, `constant-arrival-rate`
    — of the stored benchmarks, the breakpoint alone) schedules the arrivals
    themselves, so **received against scheduled** is a real check — the
    run's request rows counted per stage against the integral of the
    manifest's stage rates over the same interval, which is the
    arrival-rate consequence stated above and carries that scope. Both
    numbers go on the `k6:` line, and every threshold ruled under them
    says in the report that this is its evidence: the count attests
    that the generator kept the schedule, it does **not** attest zero
    script exceptions, since one thrown after the response came back
    leaves the arrivals intact. `dropped_iterations` is ruled from that
    same received-against-scheduled number, named as such (the k6-side
    counter and the OpenTelemetry bonus signal both land in the
    driver's store, not necessarily in yours).
  - **a closed model** (`constant-vus`, `ramping-vus` — every other
    stored benchmark: load, soak, smoke, stress, spike) schedules
    **VUs, not arrivals**: the rate is VUs × requests per iteration ÷
    iteration duration, and it drifts down with the target's own
    response time by design — several of the stored manifests say so in
    as many words under `pacing.expected_rate`. There is no schedule to
    integrate, and a
    count below expectation is a legitimate reading of a slower service
    before it is anything else. What stands in, in this order: the
    manifest's `pacing.expected_rate`, quoted as the expectation it is
    and never as a pass criterion; the run's **continuity** — arrivals
    present in every bin of the window at the shape the profile's VU
    count implies, rather than stopping or gapping mid-stage; and,
    where the manifest offers neither, one explicit line saying **no
    schedule exists and the generator's completeness is unattested**.
    Under a closed model **no threshold is ever voided on the arrival
    count alone**.
  - **any other executor** is read as closed unless it schedules the
    arrivals itself. The iteration-bounded pair
    (`shared-iterations`, `per-vu-iterations`) is the closed case with
    the strongest substitute of all: the manifest declares a total
    number of iterations, so the expected request count is that total
    × `pacing.requests_per_iteration` — an exact figure rather than a
    band, and a run whose rows fall short of it stopped early. It stays
    a closed model all the same: that shortfall is a finding, never an
    automatic `void`.
- **A shortfall is not a pass.** Under an **open** model, arrivals
  below the schedule beyond its own rounding — the fractional last
  iteration a stage's rate leaves, nothing more — mean the run may not
  have exercised what it measures: the thresholds it touches read
  `void (arrivals short of schedule, the generator's evidence not
  observed)`, never `pass`, and the shortfall is a finding of its own.
  Under a **closed** model the same shape — arrivals stopping before a
  stage's end, a count far under the expected band — is a finding to
  raise and investigate, never an automatic `void`. Either way it is
  read against the service's own latency, by the dropped-iterations
  rule above: a flat server-side p95 makes it the generator's, a rising
  one makes it the service bending.
- **The window is the run's, not the watch's.** The recorded window —
  and the report's `window` frontmatter, and the minute its filename
  carries — runs from **the run's first request row** on the identity
  to its end as the criterion below fixes it, the two instants
  `Started (UTC)` and `Ended (UTC)` carry; a drive's window opens on
  the same row and closes on k6's exit. The minutes the mission spent
  waiting are the record's `Watch:` line instead. A window padded with
  idle time is not the interval a replay reproduces, and every rate in
  the report divides by it.
- **The announced start is a hint; the identity is the fact.** Poll
  from the moment the mission is dispatched and its readiness
  preflight has passed — never sleep until the announced clock time:
  an announced start is a plan, and a ramp observed four minutes ahead
  of it carves a truncated window for anyone who trusted it. The
  `Watch:` line carries both, the hint as stated and the first row
  actually seen.
- **Both anchors come from the rows, and a k6 run marks no warmup on
  its User-Agent.** You do not hold the launcher's clock, so the first
  request row of the identity anchors the stage offsets and the
  manifest's own warmup stage dates t0, exactly as in "Warmup is the
  manifest's stage boundaries" above: read the boundaries off the
  per-request `stage` tag where the manifest declares one, and convert
  the offsets from that first row where it does not. There is no
  `-warmup` suffix to look for — one process, one User-Agent
  (`references/run-identity.md`, the stored-benchmark paragraph) — and
  an observer hunting for one finds nothing and dates the run from a
  warmup request instead, which mis-buckets every stage after it (that
  suffix belongs to an observe run with no benchmark, whose driver
  drove ad-hoc requests: `run-identity.md`'s "The run starts after the
  warmup" then applies as written). Both anchors go on the record's
  `Stages (UTC):` line, the same line and the same words as a drive's.
- **The end criterion applies only once the run has started.** Before
  the first row on the identity, an empty poll means **not started**,
  never ended, and the watch continues to the mission's deadline; a
  watch that reaches that deadline with no row at all is a
  stop-and-report ("no run observed in the window"), never an analysis
  of an empty one. **After** the first row, the run has ended when the
  identity stops producing rows: no row in **four consecutive
  30-second bins** — the segment width a ramp is already read at —
  counted on data old enough to have landed, since a backend that lags
  a minute makes a live run look finished. That quiet must also be
  longer than any gap the profile itself schedules where it fell: an
  open model opening at a low arrival rate, or a closed model with few
  VUs and a long sleep, spaces its own requests, and the bins widen to
  the profile's own spacing before an end is called. `Ended (UTC)` is
  then the last request row, never the last empty poll. Quiet arriving
  before the manifest's scheduled total means the run ended early — a
  threshold with `abort_on_fail: true`, or a generator that died — and
  the report says which the telemetry supports, with the elapsed time
  and the rate at the stop; a truncated window is never presented as
  the whole run.
- **The watch outlasts a tool call, so its poller is resumable.** The
  primitives are `references/long-scenarios.md`'s and nothing new: a
  detached `nohup` script that runs one bounded count query on the
  identity every 30 s and **appends** a timestamped line per poll to a
  file, later tool calls reading only that file — so a call that
  expires mid-watch loses nothing. Where the host or the query CLI
  will not detach, the same script runs inside the turn in the form
  `references/long-scenarios.md` gives, with the end criterion as its
  `until` condition, and is **re-invoked** the moment the call's
  budget runs out. That is safe only while each invocation holds no
  state from the last: it re-derives where the run stands from the
  append-only poll file and the backend alone — whether a first row has been seen
  and when, the newest arrival, and the empty bins since — and appends
  rather than truncates, so invocation *n+1* continues the watch
  instead of restarting it. Give it outcomes a caller can tell apart:
  exit `0` when the end criterion is met, a distinct status meaning
  "still running (or not started yet), re-invoke me". Re-invoking is
  the same turn's next tool call — the turn never ends waiting (ending
  it terminates the mission). The poller **watches, it never drives**:
  an observer's polls go to the backend only, and no request is sent
  at the service, whose traffic is the driver's alone. The `Poller:`
  line carries the script, its output file, the interval, the end
  criterion and how many invocations it took.

The record then keeps every line of a drive's and replaces what you did
not do — here the breakpoint benchmark, whose ramp outlasts a tool call
and whose executor is the open model above:

```text
Scenario:  benchmark orders-api-breakpoint (observed; driven by another mission, "the campaign's drive mission")
Benchmark: .odd/benchmarks/orders-api-breakpoint/ @ 3ccfd18 (clean; HEAD 454af15 at the watch's start)
Base URL:  not observed — the driver's, and the mission block does not state it
Listeners: n/a (nothing driven or launched here)
Backend:   no reset — the run is someone else's; isolated by window and identity
Instance:  read from the run's rows: orders-api-7c9f (one instance)
Identity:  User-Agent "odd-bench/orders-api-breakpoint/campaign-bp-0906" — the manifest's prefix, the slug read off the rows (one slug in the window); UA-selected, no traceparent
Warmup:    the manifest's baseline stage, 30 s (excluded), carried by the per-request stage tag
Stages (UTC): read off the stage tag, no arithmetic — baseline 08:54:02–08:54:32 (excluded), ramp 08:54:32–09:04:32, ramp-down 09:04:32–09:04:38; t0 (first measured request) 08:54:32; ramp read in 30 s segments, offered rate at each segment's midpoint
Watch:     announced "from 08:58, within 15 minutes"; polled from dispatch 08:52:40; first row on the identity 08:54:02, four minutes before the hint; last poll 09:07:10
Started (UTC): 2026-09-06T08:54:02Z   # the run's first request row, not the watch's start
Ended   (UTC): 2026-09-06T09:04:38Z   # last request row; four empty 30 s bins after it, against a 1 s-spaced schedule at that point
Query points: 1 (after Ended + the backend's ingest wait, proven by a bounded count query)
Poller:    /tmp/watch-campaign-bp-0906.sh -> /tmp/watch-campaign-bp-0906.log, every 30 s, one bounded count on the identity per poll, backend only (no request at the service); not-started until the first row, then ends on four empty 30 s bins; 3 invocations, exit 0 on the third
Command:   none run here — the driver's
k6:        not observed (driven elsewhere); open model (ramping-arrival-rate), arrivals 2327 request rows against 2327.5 scheduled by the manifest's stage rates — the half is the schedule's own rounding, so the schedule was met; script exceptions unknown, and every threshold below is ruled under that proxy
Not reproducible: the drive itself — this mission did not run it, and a replay needs the same benchmark driven again at the same revision
```
