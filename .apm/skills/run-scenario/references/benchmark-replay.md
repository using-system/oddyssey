# Replay a stored k6 benchmark

A mission naming a benchmark under `.odd/benchmarks/<name>/` takes its
load from that script instead of a curl loop. `SKILL.md` steps 3 to 5
and `references/run-identity.md` apply unchanged; what this file adds
is stated as invocations and one bullet per fact a script cannot
absorb. A local drive reads every section but the last two; a remote
drive adds its own; a run you do not drive — `observe-run`'s observe
mode — reads the last section with the rest, never instead of it.

## Replaying is the `k6-guides` skill's job

- Never build a k6 command: `k6-guides`' `references/running-tests.md`
  `## Running` states the replay script, its whole surface, what it
  refuses, and the record and status shapes it prints. Run it and bring
  back its record.
- What the caller still decides: the run slug, any `-e KEY=value` the
  manifest left to run time, and `--send-traceparent` on a remote drive
  only.

## The clean base is the run slug; the reset is a separate decision

- Local drive: `run-identity.md`'s order **without** its wipe — restart
  the observed process with the slug as `service.instance.id`; the slug
  qualifies the cumulative metrics and the record's window scopes the
  trace and log queries. Default, costs nothing.
- `odd_stack_reset` only when the mission asks for an empty store, when
  a baseline is in absolute counts, or when retention would drown the
  run — and the record's `Backend:` line names which. A forbidden reset
  follows `run-identity.md`'s forbidden-reset block. A remote drive has
  no reset.

## Warmup is the manifest's stage boundaries

- The stages are laid out from the run's **first request row**, never
  from k6's start, its summary, or backwards from the end; t0 is the
  first quoted stage's start. The arithmetic is shipped — run it with
  the first row the driver's record or the rows give:

```bash
python3 <skills>/k6-guides/scripts/replay_benchmark.py --stages <benchmark dir> --first-row <first request row, UTC> [--segment 30s] [--json]
```

  It prints the `Stages (UTC):` and `Warmup:` lines to paste into the
  record, t0, the end, and every ramp's segments (`running-tests.md`
  states the shape). Where the manifest declares a per-request `stage`
  tag, read the stages off the tag and keep the printed line as the
  cross-check.
- `SKILL.md` step 3's sample counts apply (≥ 30 before a p95, ~100
  before a p99); `long-scenarios.md`'s expensive-iteration carve-out
  does not.
- Exact per-stage counts come from the trace listing: a cumulative
  metric read at a stage's end answers at the last export before it
  (126 against 180 rows on a 60 s export, 2026-09-06); quote a
  metric-derived per-stage value with that shift.
- Timestamps to the second: `date -u +%Y-%m-%dT%H:%M:%SZ`, never `%3N`
  (BSD `date` prints the literal); a query bounded on a stage takes
  ±1 s around it.

## Bucketing a ramp for the degradation curve

- A ramp is read in the segments `--stages` prints: `--segment` wide
  (30 s unless the manifest declares a width), from the ramp's own
  start, the offered rate at each segment's **midpoint**. The width is
  part of the protocol: it is on the `Stages (UTC):` line the script
  prints. Stress and breakpoint ramps are read this way; an excluded
  warmup ramp is carved by nobody.

## k6's own summary and exit status are evidence, never the verdict

- The record's `k6:` line: exit code (`0` thresholds met, `99` one
  crossed, else a setup or script error — read stderr), request count,
  failed checks, dropped iterations, script exceptions. Read the export
  through `running-tests.md`'s "Reading k6's own evidence" first: its
  threshold booleans and `Rate` fields read backwards.
- The summary file is transient: a scratch location, never inside
  `.odd/benchmarks/<name>/`, never counted on later.
- The verdict is the telemetry, after `SKILL.md` step 5's flush wait,
  each manifest threshold ruled against a telemetry-derived measurement
  carrying its query.
- Script exceptions above zero void every threshold ruling: the run is
  a defective benchmark (a finding against the script, fixed through
  `/odd-instrument-bench`), never a pass. A shutdown `failed to upload
  metrics: context canceled` info line is not a partial run.

## k6's own OpenTelemetry output is a bonus signal

- `--otel` on the local stack lands k6's client-side series under
  `service_name="k6"` (`running-tests.md` says how they read):
  cross-confirm when it lands, never require it, never mistake it for
  the target.
- On an arrival-rate benchmark a `dropped_iterations` of zero had no
  series at all; rule that threshold from the service's own rows —
  **received against scheduled**, the schedule being the integral of the
  manifest's stage rates — and say so in the report.

## The replay is always detached

```bash
python3 <skills>/k6-guides/scripts/replay_benchmark.py <benchmark dir> --run-slug <slug> --detach <scratch>/<slug> [--otel] [-e KEY=value ...] [--send-traceparent]
python3 <skills>/k6-guides/scripts/replay_benchmark.py --status <scratch>/<slug> --wait <the benchmark's length plus a margin, e.g. 5m>
```

- Whatever the benchmark's length: the first returns at once, the
  second blocks until the run ends (exit 3 when the bound passes with
  the run still going — run it again). A `Replay:` line in the mission
  block is this invocation filled in: run it as is, under your own
  scratch directory.
- Never author a poller or a wrapper around it — a loop on `--status`,
  a `sleep` in a helper — it is the shipped command written again.
- A liveness probe, when one is genuinely needed, goes to a route the
  benchmark excludes, at a fixed interval, on the record's `Poller:`
  line; the watcher watches, it never drives.

## Reading a breakpoint run

- No steady state: the per-segment view replaces it and **the end time
  is the result**. Which outcome a crossed threshold produces is the
  manifest's `abort_on_fail`: aborted — the elapsed time and the rate at
  the abort; crossed without aborting (exit 99 at full length) — the
  ceiling is where the metric crossed, read per segment from the
  telemetry; nothing crossed — the ceiling is **above** the top rate
  reached, with that rate and the length as evidence, never a pass.
- Dropped iterations read against the service's own latency: flat
  server-side p95, the generator's (a limit to record); rising p95, a
  breakpoint signal — the arrival rate outran the VU cap because the
  service slowed.

## Driving a remote target is the caller's decision, and changes the record

- Allowed only when the observation caller says so at mission time,
  never read from the manifest. Then four things change, nothing else:
  the identity travels in the requests — the manifest's `user_agent`
  with the slug through `run_slug_env`, and this is the drive that sets
  the `traceparent` gate (`--send-traceparent`; a script that cannot
  send one is UA-selected, the `Identity:` line says which);
  `Backend: no reset (remote)`; `Listeners: n/a (remote)`, the instance
  read from the rows; the flush wait is the backend's, sized by
  `observe-run`, cited on the `Query points:` line.

The record keeps every line of `SKILL.md` step 4 and replaces its
`Commands:` with the benchmark's identity, the single command and k6's
evidence — the `Stages (UTC):` and `Warmup:` lines as `--stages`
printed them, the `Command:` block carrying **what you ran** (the
replay script) and **what it ran** (the `command` of the record it
printed, copied never composed):

```text
Scenario:  benchmark orders-read-heavy
Benchmark: .odd/benchmarks/orders-read-heavy/ @ 3ccfd18 (clean; HEAD 1a73941 at start)
Base URL:  http://127.0.0.1:8080   # BASE_URL, mission-time
Listeners: none
Backend:   no reset — separated by the slug and the window
Instance:  orders-run-0902 (restarted with the slug)
Identity:  service.instance.id=orders-run-0902 on the launcher; User-Agent "odd-bench/orders-read-heavy/orders-run-0902" (the manifest's identity block, slug through -e RUN_SLUG); traceparent not sent — its gate is unset on a local drive
Warmup:    the manifest's baseline stage, 60 s (excluded from the quoted numbers); t0 and the first row are 60 s apart
Stages (UTC): offsets converted from the first request row 10:04:12 — baseline 10:04:12–10:05:12 (excluded), steady 10:05:12–10:25:12, ramp-down 10:25:12–10:25:42 (excluded); t0 (first measured request, where the quoted numbers start) 10:05:12; ramp-down 10:25:12–10:25:42 read in 30 s segments, offered rate at each segment's midpoint
Started (UTC): 2026-09-02T10:04:12Z
Ended   (UTC): 2026-09-02T10:25:42Z
Query points: 1 (after Ended)
Poller:    none written - the replay ran detached and --status --wait blocked until it finished
Command:
  python3 <skills>/k6-guides/scripts/replay_benchmark.py .odd/benchmarks/orders-read-heavy --run-slug orders-run-0902 --otel --detach <scratch>/orders-run-0902   # then --status <scratch>/orders-run-0902 --wait 25m
  k6 run .odd/benchmarks/orders-read-heavy/script.js --summary-export <scratch>/k6-summary-orders-run-0902.json -e BASE_URL=http://127.0.0.1:8080 -e RUN_SLUG=orders-run-0902 -o opentelemetry   # what it ran, from the record it printed
k6:        exit 0, 4210 requests, checks 100%, dropped iterations 0, script errors 0 (summary file transient)
Not reproducible: none
```

## Watching a run someone else drives

`observe-run`'s observe mode with a benchmark: another mission or
person runs the script; you read the telemetry only. Everything above
holds; what changes is that the run's identity, start and end are
discovered, and k6's evidence is the driver's.

- **The watch is the backend's script.** When the backend's reference
  ships a watch of a driven run (its traces section), run it on the
  manifest's User-Agent prefix from the moment you are dispatched, with
  the mission's window end as the deadline and a state file in your
  scratch directory; run the same invocation again when a call's budget
  cuts it — it resumes from its state. What it found goes on the
  record's `Started (UTC):`, `Ended (UTC):`, `Identity:` and `Watch:`
  lines, its queries on the record with the others; the `Poller:` line
  is that invocation, its state file and how many calls it took. Never
  compose the poll around it. When the backend ships none, the poller
  is `long-scenarios.md`'s detached-job shape (its last section, which
  names this case) with the criteria below as its conditions, cited
  verbatim on the `Poller:` line.
- **The identity is discovered, not handed over**: the manifest's
  `identity:` block gives the User-Agent prefix (`odd-bench/<name>`),
  the slug is read off the rows. A `traceparent` the manifest declares
  shortens nothing: the trace-id selector becomes available only once
  the slug is known, for what the User-Agent cannot reach. Several
  identity values on the rows are several runs (a shipped watch reads
  the identity on the first row, on the first row after a gap and on
  the last row, and says when they differ): watch the one the mission
  names, otherwise report the ambiguity, each identity with the bin it
  first appeared in.
- **The criteria** (the shipped watch applies them; a composed poller
  states them): poll from dispatch — the announced start is a hint;
  before the first row an empty poll means **not started**, and a watch
  reaching its deadline with no row is a stop-and-report ("no run
  observed in the window"); after the first row the run has ended on
  **four consecutive empty 30-second bins** of data old enough to have
  landed, widened to the profile's own spacing where it schedules
  sparser requests; `Ended (UTC)` is the last request row, never the
  last empty poll; quiet before the manifest's scheduled total is an
  early end (an aborting threshold, or a generator that died) — say
  which the telemetry supports, never present a truncated window as
  the whole run.
- **The window is the run's**: `Started`/`Ended` are the run's own
  rows and what the report's `window` carries; the minutes spent
  waiting go on the `Watch:` line. Both stage anchors come from the
  rows: `--stages` with the first row, or the per-request `stage` tag;
  a k6 run marks no `-warmup` suffix on its User-Agent.
- **Every poll goes to the backend, never to the service**: the traffic
  is the driver's alone.
- **k6's evidence is the driver's**: quote the `k6:` line the mission
  block or the driver's stored report hands over, verbatim with its
  source, and the void precondition above applies as on a drive.
  Absent both, the `k6:` line reads **`not observed`** and what stands
  in is read off the manifest's `profile.executor`:
  - **open model** (`ramping-arrival-rate`, `constant-arrival-rate`):
    **received against scheduled** — the run's rows per stage against
    the integral of the manifest's stage rates; both numbers on the
    `k6:` line, every threshold ruled under them says so. The count
    attests the schedule, not zero script exceptions.
    `dropped_iterations` is ruled from the same number. Arrivals short
    of the schedule beyond its own rounding void the thresholds they
    touch (`void (arrivals short of schedule, the generator's evidence
    not observed)`) and are a finding of their own.
  - **closed model** (`constant-vus`, `ramping-vus`, and the
    iteration-bounded pair, whose expected count is the declared total
    × `pacing.requests_per_iteration`): the rate drifts with the
    target's response time by design, so **no threshold is voided on
    the arrival count alone**. What stands in, in order: the manifest's
    `pacing.expected_rate` quoted as an expectation, the run's
    continuity (rows in every bin at the profile's shape), else one
    line saying no schedule exists and the generator's completeness is
    unattested. A shortfall is a finding to investigate, read against
    the service's latency by the dropped-iterations rule above.
  - **any other executor** is read as closed unless it schedules the
    arrivals itself.
- **The record** keeps every line of a drive's and replaces what you
  did not do: `Scenario: benchmark <name> (observed; driven by <the
  mission block's name, else "not named">)`, `Base URL: not observed`
  when the block does not state it, `Listeners: n/a`, `Backend: no
  reset — the run is someone else's`, `Instance:` read from the rows,
  `Identity:` as the watch printed it, `Watch:` as the watch printed it
  plus the announced start as stated, `Poller:` the watch invocation,
  `Command: none run here — the driver's`, `k6:` per the bullet above,
  `Not reproducible: the drive itself`.
