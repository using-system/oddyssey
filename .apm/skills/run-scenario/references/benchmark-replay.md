# Replay a stored k6 benchmark

When the mission names a benchmark under `.odd/benchmarks/<name>/`
(`k6-benchmark-expert` authored it, `odd-memory`'s `benchmark`
reference stored it),
the load comes from its script instead of a curl loop. On a **local**
drive the identity reference and `SKILL.md` steps 3 and 5 apply
unchanged — the clean-base order, the run's t0 after the warmup, the
sample-count rules, the flush wait — and `SKILL.md` step 4 applies with
the record shape below; a remote drive changes four things, in its own
section. What
differs is how the load is generated and how the record cites it:

## Confirm k6 is installed before anything else

Before the clean-base reset (`references/run-identity.md`):
`command -v k6`, per the `k6-guides` skill's `install.md`. Reached
from a prompt's preflight (the nominal case, inside `observe-run`),
the binary is already there — a still-missing one is a contract
failure to report with the reference's install steps, never a reason
to install from a subagent. Entered directly in the main
conversation, with no preflight behind it, run that reference's
auto-install step first. Either way, when k6 is absent the observed
process and the store stay untouched: never restart or reset for a
run you cannot perform, never approximate the script with a curl
loop. `running-tests.md` in the same skill carries the flags, the
output surface, the exit codes and the summary export cited below.

## Read the manifest, then run the script unmodified

The benchmark
directory holds one k6 script and one manifest
(the `benchmark` reference's layout): the script is `script.js`
unless the manifest names another file. Run it from the repository
root, as one blocking foreground command (or the detached poller
below when the run outlasts a tool call), with k6's end-of-test
summary exported to a scratch file:

```text
k6 run .odd/benchmarks/<name>/script.js --summary-export <summary-file>
```

Inputs the manifest leaves to mission time (a base URL, a named
environment variable) are passed through k6's `-e KEY=value` or the
environment, and recorded by name — a credential's value never lands
in the record. Never edit the script or the manifest to make the run
nicer: a benchmark that cannot run as stored is a reported failure,
and a change to it goes through `/odd-instrument-bench`'s reviewed
diff, never through the run.
- **The manifest's `identity:` block is the authority on how the run
  is selected.** It declares the `user_agent` the script's requests
  carry, the `run_slug_env` variable the run slug travels in, the
  request tags (`name`, and a per-request `stage` where the manifest
  has one), and whether a `traceparent` is sent — never assume any of
  them. Pass the slug through the variable the manifest names, every
  run (`-e RUN_SLUG=<slug>` in the stored benchmarks): without it every
  replay sends the same User-Agent and the runs merge. The record's
  `Identity:` line quotes the form the rows actually carry — the
  launched process's `service.instance.id` and that User-Agent — and
  `references/run-identity.md`'s stored-benchmark paragraph carries the
  rest, including why `--user-agent` is the wrong lever against a
  script that sets the header itself.
- **Which flags a replay may add.** A flag that only names the run,
  carries an input the manifest left to mission time, or writes an
  extra output is not a modification: `-e KEY=value` (the base URL, the
  manifest's `run_slug_env`), `--tag <key>=<value>`,
  `--summary-export`, `--summary-trend-stats` (the way to make k6
  export a percentile outside its six defaults when the script may not
  be edited — `running-tests.md`), `-o opentelemetry` with its
  `K6_OTEL_*` env (local stack only, below), and `--user-agent` only
  when the manifest declares no `user_agent` of its own (above). Each one goes
  verbatim into the record's `Command:` line. A flag that moves the
  **load** or the **criteria** is an edit by another name and is
  refused like one: `--vus`, `--iterations`, `--duration`, `--stage`
  (such flags replace the script's `options.scenarios` entirely —
  `running-tests.md`), `--rps` (a global request-rate cap the
  benchmark's own pacing never declared), `--execution-segment` and
  `--execution-segment-sequence` (they run a fraction of the load),
  `--no-thresholds`, `--no-setup`/`--no-teardown` (flag names verified
  on k6 v2.2.0, 2026-09-06). A run that needs one
  of those to finish is a reported failure and a
  `/odd-instrument-bench` diff, never a flag added at mission time.
- **The record cites the benchmark by name and git revision, not by
  commands.** The revision that counts is the **benchmark's own** — the
  last commit touching its directory
  (`git log -1 --format=%h -- .odd/benchmarks/<name>/`), whatever
  `HEAD` is: on a shared checkout another mission commits while a long
  run is in flight and `HEAD` moves under it (observed on a 20-minute
  soak). Record both, plus whether the benchmark's directory is clean
  (`git status --porcelain .odd/benchmarks/<name>/` prints nothing). A
  dirty benchmark has no revision to replay at — say so in the record.
  A replay runs the same benchmark at the same revision; when the
  stored benchmark moved between the two runs (a diff-reviewed update
  landed), the load may have changed with it. The record then says
  what moved: findings against the benchmark itself (a script defect,
  an unattainable threshold) are ruled on the new revision, while the
  service's before/after numbers compare only when the requests,
  pacing, and stages are the same — otherwise the second run's numbers
  open the service's new baseline, stated as such, never a before/after
  against the first.

## The clean base is the reset, unless the caller needs the store

For a local drive, `references/run-identity.md`'s clean-base order is
the default and a silent mission does not turn it off: another
lineage's telemetry sitting in the store is not history the caller
asked to keep, and a fresh `service.instance.id` is a weaker isolation
rather than a substitute — it qualifies the cumulative metrics, it does
not empty the store the trace and log queries search. The reset is
dropped only when the caller needs that history or an env forbids it;
then `run-identity.md`'s forbidden-reset block is the protocol
(time-scope every query to the recorded window, qualify by the
identity, read cumulative metrics as window-edge deltas), and the
record's `Backend:` line says which of the two the run had. A remote
drive has no reset at all (below).

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

## A run longer than a tool call uses the detached poller of `references/long-scenarios.md`

A
staged benchmark routinely exceeds one tool call's budget; the poller
script and its output file are part of the record, on its `Poller:`
line. **The poller watches the run, it does not drive the service**: it
tails k6's own output and the process, and sends no request the
benchmark did not. When a liveness probe is genuinely needed, it goes
to a route the benchmark excludes, at a fixed interval, and its route,
interval and total count go on that line — load a replay repeats and
the measured numbers leave out.

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
  `run_slug_env` is the whole identity, and no stored benchmark sends a
  `traceparent` — the run is UA-selected, the `Identity:` line says so,
  and the instance is read from the rows;
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
Identity:  service.instance.id=orders-run-0902 on the launcher; User-Agent "odd-bench/orders-read-heavy/orders-run-0902" (the manifest's identity block, slug through -e RUN_SLUG); traceparent not sent
Warmup:    the manifest's ramp-up stage, 60 s (excluded from the quoted numbers)
Stages (UTC): offsets converted from the first request row 10:04:12 — ramp-up 10:04:12–10:05:12 (excluded), steady 10:05:12–10:25:12, ramp-down 10:25:12–10:25:42; t0 (first measured request, where the quoted numbers start) 10:05:12
Started (UTC): 2026-09-02T10:04:12Z
Ended   (UTC): 2026-09-02T10:25:42Z
Query points: 1 (after Ended)
Poller:    /tmp/poll-k6-orders-run-0902.sh -> /tmp/k6-poll-orders-run-0902.log, every 30 s, reads the k6 log only (no request at the service)
Command:
  K6_OTEL_GRPC_EXPORTER_INSECURE=true k6 run .odd/benchmarks/orders-read-heavy/script.js -o opentelemetry --summary-export /tmp/k6-summary-orders-run-0902.json -e BASE_URL=http://127.0.0.1:8080 -e RUN_SLUG=orders-run-0902   # -o opentelemetry and its env: local stack only
k6:        exit 0, 4210 requests, checks 100%, dropped iterations 0, script errors 0 (summary file transient, numbers above are the record)
Not reproducible: none
```

The same record for a remote drive, carrying the four changes above —
and short enough to need no poller:

```text
Scenario:  benchmark orders-api-spike (remote drive, authorized in the mission)
Benchmark: .odd/benchmarks/orders-api-spike/ @ 454af15 (clean; HEAD 454af15 at start)
Base URL:  https://orders.example.com   # BASE_URL, mission-time
Listeners: n/a (remote)
Backend:   no reset (remote) — isolated by window and identity
Instance:  read from the run's rows: orders-api-7c9f (one instance)
Identity:  User-Agent "odd-bench/orders-api-spike/observe-spike-0906" (the manifest's identity block, slug through -e RUN_SLUG); UA-selected, no traceparent — trace-id-prefix selection unavailable, presence and latency read from the UA identity
Warmup:    the manifest's baseline stage, 30 s (excluded), carried by the per-request stage tag
Stages (UTC): read off the stage tag, no arithmetic — baseline 08:30:11–08:30:41 (excluded), ramp-up 08:30:41–08:30:51, burst 08:30:51–08:31:21, ramp-down 08:31:21–08:31:31, recovery 08:31:31–08:32:01; t0 (first measured request) 08:30:41
Started (UTC): 2026-09-06T08:30:11Z
Ended   (UTC): 2026-09-06T08:32:01Z
Query points: 1 (after Ended + the backend's ingest wait, proven by a bounded count query)
Poller:    none (the run fits one tool call)
Command:
  k6 run .odd/benchmarks/orders-api-spike/script.js --tag run=observe-spike-0906 --summary-export /tmp/k6-summary-observe-spike-0906.json -e BASE_URL=https://orders.example.com -e RUN_SLUG=observe-spike-0906
k6:        exit 0, 4812 requests, checks 100%, dropped iterations 52 (generator: maxVUs saturated while the server p95 stayed flat), script errors 0
Not reproducible: none
```
