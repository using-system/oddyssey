# Benchmark authoring and running

A k6 load-test benchmark, authored once as reviewed code and replayed
identically for as long as it stays useful.

## Install k6

Needed on both sides. Authoring **validates** the script with it —
`k6 inspect` (parse and schema, no network) and one smoke iteration at
the target — without ever running the benchmark; running one is
`/odd-observe`'s job. The `/odd-instrument-bench`, `/odd-observe`, and
`/odd-verify` preflights make sure it is present before dispatching:
when it is missing and Homebrew is available, `brew install k6` runs on
the spot, no confirmation asked — k6 needs no account and no
configuration, the binary is the whole setup. Without Homebrew, the
preflight follows the official page's non-interactive path where one
exists (Windows package managers) and otherwise hands you the steps
(the Linux packages need `sudo` and a repository key) and stops.

**Binary**: `k6` on your path — `brew install k6` (macOS/Linux), or
the official packages, MSI installer, or standalone binary for other
platforms: https://grafana.com/docs/k6/latest/set-up/install-k6/

## Author

```text
/odd-instrument-bench author a load benchmark for checkout, stress test, p95 under 300ms
```

Investigates the service and writes a k6 script + manifest into
`.odd/benchmarks/<name>/`. It asks you back for whatever only you can
decide — test type, thresholds, target environment, new benchmark or an
update to an existing one, and, for a remote target, whether one smoke
iteration may be sent at it — and proposes a load shape/duration for
you to confirm; everything else (which endpoints matter) it figures
out on its own.

Your thresholds are yours, but the agent checks them against what it
finds in the service: a fixed delay, a rate limit, an injected error
rate, a downstream floor, each with its file and line. A threshold the
service can structurally never meet on the path it gates (a
`p(95)<300ms` on a handler that sleeps 300–800 ms before answering)
comes back to you with that evidence instead of being persisted — such
a threshold can only "pass" by measuring traffic that never reaches
the gated logic. You raise it, drop it, re-scope it to the path it
means, or keep it with the floor acknowledged (a goal your fix wave is
driving toward is a valid target once you have seen the floor); the
agent never adjusts a target on its own, and persists nothing until
you have decided. An ambitious-but-reachable threshold, or one with no
floor found, is kept as given, with its floor recorded next to it in
the manifest.

Before persisting, the agent validates what it wrote, in this order: a
static check for the `discardResponseBodies` / `res.json()`
self-contradiction (a runtime crash no parser sees) and for a
tag-scoped threshold no request populates (a pass that measures
nothing), `k6 inspect` (a
parse and schema check that contacts nothing — a non-integer
`constant-arrival-rate` `rate` fails here), and a one-iteration smoke,
`k6 run --vus 1 --iterations 1 --no-thresholds`, which replaces the
script's scenarios with exactly one pass over its requests. A failure
is fixed and re-validated, never persisted. The manifest records the
validation (k6 version, date, the smoke's result — passed, declined,
not applicable when the script exports no default function, or the
functions it did not cover — and the threshold cross-check: each
threshold, its floor or none found, and the outcome) and the closing
synthesis renders it. The smoke is self-authorized against a local
target and asked for a remote one, every time: its single iteration is
real traffic with real side effects. It never runs the benchmark
itself — nothing beyond that one iteration.

Updating an existing benchmark follows the same prompt — the change
comes back as a reviewed diff against the stored version, never a
silent replacement.

## Run

```text
/odd-observe run .odd/benchmarks/checkout-read-heavy/
/odd-observe drive the checkout-read-heavy benchmark on the local stack, focus on latency
/odd-observe someone is running checkout-read-heavy against uat right now - observe it
```

A benchmark is a mission field of `/odd-observe`, named by its
directory under `.odd/benchmarks/` or by that path. It composes with
the mode — the mode says who generates the traffic, the benchmark says
which stored plan is running:

- **drive** + benchmark (the first two examples): the `observe-run`
  agent runs the stored script itself, unmodified, through the
  `run-scenario` skill's stored-benchmark step — one blocking
  `k6 run <script> --summary-export <file>` command (or its detached
  poller when the run outlasts a tool call), preceded by the same
  clean-base order as any driven scenario (restart the service, then
  `odd_stack_reset`, then record the process identity). The service is
  the manifest's target service unless the prompt names one; a base URL
  or a named secret the manifest leaves open is passed at mission time
  through k6's `-e`, and recorded by name.
- **observe** + benchmark (the third example): someone else runs it
  elsewhere; the agent only watches the telemetry, and the report cites
  the benchmark as the replayable protocol instead of a bare window.
- **post-hoc** takes no benchmark: the agent was not there and cannot
  attest that the plan produced the window, so it refuses the
  combination.

What changes in the report: the scenario record cites the benchmark by
**name and git revision** (and whether its directory was clean) rather
than by verbatim commands, records the manifest's stage boundaries so
the steady-state numbers exclude the ramp, and carries k6's own exit
status and summary as **evidence, never as the verdict**. The verdict
is telemetry-only, like every other observation: the manifest's
thresholds are ruled on against measurements taken through the
service's own signals (metrics, traces, logs), each carrying the query
that produced it. k6's own OpenTelemetry output (`service_name="k6"`)
is a bonus signal when it lands in the store, never a requirement.

Driving a **remote** target is authorized in the prompt, every run —
a manifest never carries a standing permission.

## Verify

`/odd-verify` replays a benchmark-backed report through the same
`observe-run` dispatch, in the mode the report's frontmatter records —
never inferring `drive` from the benchmark's presence, so an observed
run is never re-driven. A `drive` replay against a **remote** target
asks you first, every time, naming the benchmark and its recorded
revision: the authorization the original run had was for that run.

A benchmark is living source, so a change to the benchmark a replay
runs counts as changed code for the verify-vs-re-measure boundary
(`/odd-verify` and `/odd-status` alike): a fix to its script or
manifest makes the next replay a **verification**, never a re-measure
— only the two report stores and `.odd/decisions.md` are the loop's
memory that a replay ignores. What that verification can rule depends on what
moved: the baseline's findings against the benchmark itself (a script
defect, an unattainable threshold) are ruled on the new revision;
the service's before/after numbers compare only when the load did not
change (same requests, pacing, and stages) — otherwise the report
says so, rules what it can, and its numbers open the service's new
baseline. Checking the benchmark out **at the recorded revision**
instead of running it at `HEAD` is designed but not built yet; the
recorded revision in the scenario record is what that step will read.
