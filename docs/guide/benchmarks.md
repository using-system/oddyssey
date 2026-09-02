# Benchmark authoring and running

A k6 load-test benchmark, authored once as reviewed code and replayed
identically for as long as it stays useful.

## Install k6

Needed on both sides. Authoring **validates** the script with it —
`k6 inspect` (parse and schema, no network) and one smoke iteration at
the target — without ever running the benchmark; running one is
`/odd-observe`'s job. The `/odd-instrument-bench`, `/odd-observe`, and
`/odd-verify` preflights check for the binary before dispatching and
stop with the install steps when it is missing; nothing installs it
for you.

**Binary**: `k6` — `brew install k6` (macOS/Linux), or the official
install script / prebuilt binaries for other platforms:
https://grafana.com/docs/k6/latest/set-up/install-k6/

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

Before persisting, the agent validates what it wrote, in this order: a
static check for the `discardResponseBodies` / `res.json()`
self-contradiction (a runtime crash no parser sees), `k6 inspect` (a
parse and schema check that contacts nothing — a non-integer
`constant-arrival-rate` `rate` fails here), and a one-iteration smoke,
`k6 run --vus 1 --iterations 1 --no-thresholds`, which replaces the
script's scenarios with exactly one pass over its requests. A failure
is fixed and re-validated, never persisted. The manifest records the
validation (k6 version, date, the smoke's result — passed, declined,
not applicable when the script exports no default function, or the
functions it did not cover) and the closing synthesis renders it. The
smoke is self-authorized against a local target and asked for a remote
one, every time: its single iteration is real traffic with real side
effects. It never runs the benchmark itself — nothing beyond that one
iteration.

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
run is never re-driven. The replay compares the recorded revision with
the benchmark's current one: when the benchmark moved in between (a
diff-reviewed update landed), the run is reported as a new baseline,
never as a verdict on a fix. Checking the benchmark out **at the
recorded revision** instead of running it at `HEAD` is designed but not
built yet; the recorded revision in the scenario record is what that
step will read.
