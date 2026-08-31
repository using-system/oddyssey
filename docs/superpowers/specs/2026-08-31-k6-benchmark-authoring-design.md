# k6 Benchmark Authoring & Execution — Design

Implements [#75](https://github.com/using-system/oddyssey/issues/75):
`run-scenario` drives simple, cheap request sequences — fine for
functional observation, but latency and capacity findings need
reproducible *load* profiles to produce statistically defensible
p95/p99 before/after numbers. Today a load scenario is ad-hoc: invented
at observation time, recorded in prose inside the report, hard to
review, hard to replay identically months later.

## Problem

Make benchmarks a first-class, versioned artifact — the project's own
principle that the memory lives with the code. Two distinct halves:
**authoring** a benchmark as reviewed, committed code, and **running**
one through the existing `/odd-observe` / `/odd-verify` loop without
inventing a parallel execution path.

## Design

### Components

Five new pieces, each with exactly one job:

| Component | Kind | Owns | Owns nothing about |
| --- | --- | --- | --- |
| `/odd-instrument-bench` | prompt | The entry point — builds the mission from arguments **and interactive Q&A with the caller** (which questions to ask comes from `k6-guides`), then dispatches. The last point where asking the human back is cheap — once `k6-benchmark-expert` is dispatched, going back and forth gets a lot harder. | The service investigation, the manifest content, persistence — it gathers what only a human can decide, the agent decides everything discoverable. |
| `k6-benchmark-expert` | agent | Investigating the service and deciding the benchmark's content — the k6 script and the manifest. The k6 domain expert, the same role `otel-instrumentation-expert` holds for OTel instrumentation. | Writing files to disk (the skill below), running anything (never), k6's own documentation (reads it through `k6-guides`, never from memory). |
| `create-update-benchmark` | skill | Persisting the agent's decided content to `.odd/benchmarks/<name>/` — naming, versioning, the commit, recalling the benchmarks already stored for the target service. A benchmark is not a report — it's a living artifact, not a run record — so this plays the persistence role `create-otel-instrumentation-report` plays for `otel-instrumentation-expert`, without that skill's immutability rule (see "What `.odd/benchmarks/` is" below). Writing and updating is the point, not an exception to it. | Any k6 or service-specific knowledge — it persists whatever content the agent hands it, unopinionated about what that content says. |
| `k6-guides` | skill | A curated map of the official k6 docs, one reference file per topic — install, running a script, scripting, test types, results output, protocols, and which questions a benchmark's inputs require. Read by `/odd-instrument-bench` for **which questions to ask**, by `k6-benchmark-expert` while **authoring**, and by `run-scenario` while **executing** a stored benchmark — three callers, not one. | This project's benchmarks, the manifest format, `.odd/` — it only knows about k6 itself, the same way `otel-guides` only knows about OpenTelemetry. |
| `show-benchmark` | skill | Closes an authoring mission: a one-screen synthesis of what `create-update-benchmark` just stored (or changed, for an update) — the stored path, a short description of what the benchmark exercises, the next recommended action. The same role `show-otel-instrumentation-report` plays for `otel-instrumentation-expert`'s missions. | Deciding or persisting anything — it only renders what the skill above already wrote. |

The five-part split mirrors `/odd-instrument-otel` exactly: prompt,
agent, a docs-guide skill (`otel-guides` / `k6-guides`), a persistence
skill (`create-otel-instrumentation-report` / `create-update-benchmark`),
a closing synthesis skill (`show-otel-instrumentation-report` /
`show-benchmark`).

### `/odd-instrument-bench` (prompt) + `k6-benchmark-expert` (agent)

`/odd-instrument-bench` is the entry point, the same thin dispatcher
shape as every other prompt here — with one addition: it's also where
the caller gets asked back, when a benchmark needs a decision only a
human can make (a new benchmark or an update to an existing one, which
test type, which thresholds matter). That interaction happens here,
never inside `k6-benchmark-expert`. The precedent is `/odd-observe`'s
own preflight, which states the rule outright — *"in the main
conversation, before any dispatch (the steps needing the user cannot
happen inside a subagent)"* — and `update-backend-configuration`, which
asks its "what to persist" questions from the main conversation for the
same reason. The prompt consults `k6-guides`'s `authoring-inputs.md` for
which questions to ask — never invents them.

The agent:

- investigates the service (endpoints, existing `.odd/` reports for
  known hot operations) and decides the benchmark's content — a k6 load
  script plus a small manifest (target service, engine, profile stages:
  warmup / ramp / steady, duration, thresholds, output expectations);
- **k6 is the default engine** (decided): the plan is a k6 script, k6
  fits the Grafana ecosystem. The manifest declares the engine so another
  one can be introduced later without changing the contract;
- reads k6's own documentation through `k6-guides` — never invents k6
  usage, flags, or script structure from memory;
- hands the decided content to `create-update-benchmark` for persistence
  — the agent decides, the skill writes;
- closes the mission with `show-benchmark`'s synthesis of the stored path
  — the script and manifest are never re-dumped in the conversation;
- **recalls every benchmark already stored for the target service before
  authoring** — not only the one it might be updating. A service can
  legitimately carry several distinct benchmarks (a read-heavy endpoint,
  a write-heavy one); the agent must see all of them so it either
  extends the right one or states why the new one is genuinely distinct
  rather than a near-duplicate under a second name;
- may propose updating an existing benchmark as a **reviewed diff** when
  the service's endpoints have drifted from what the stored script
  exercises — never a silent replacement; the maintainer reviews it like
  any other committed change;
- **never runs the benchmark** — authoring and execution stay separate,
  the same separation `otel-instrumentation-expert` keeps (it plans
  instrumentation, never implements it). The authoring agent never
  executes what it wrote.

The manifest's exact schema (fields, format) is the agent's own design,
worked out in the implementation plan below. Two inputs that design must
settle:

- **whether the target base URL lives in the manifest at all.** "Remote
  authorization is mission-time only" (see Execution below) settles *who
  may authorize* driving load at a remote target; it does not settle
  whether the URL itself is a stored field with a mission-time override,
  or never stored. Both are compatible with the authorization rule.
- **how the profile stages map onto `run-scenario`'s warmup rule.**
  `run-scenario` requires warmup requests discarded from the quoted
  numbers; a k6 run is one continuous window, so "discard the warmup"
  becomes a sub-window boundary the manifest has to make queryable
  (stage boundaries as timestamps, or a stage tag on k6's output).
  Without it the ramp pollutes every steady-state percentile.

### `create-update-benchmark` (skill)

Mirrors `create-otel-instrumentation-report`'s role for
`otel-instrumentation-expert`, one level down: the agent above decides
*what* a benchmark says, this skill owns *how it lands in the repo*.

- writes the k6 script and manifest into `.odd/benchmarks/<name>/`,
  committed — versioned like the reports, so benchmarks get reviewed in
  PRs and evolve with the code;
- inherits the report skills' commit discipline: never commit on the
  default branch (create/switch to a work branch first), stage and
  commit the benchmark's files alone, state the stored path in the
  reply. Commit subject: `docs(odd): benchmark <name>` for a new one,
  `docs(odd): update benchmark <name>` for a diff-reviewed update;
- **recalls by service, lists by name.** The lookup key is a two-step:
  the target service returns the set of benchmarks that exist for it (so
  the agent cannot duplicate one it never saw), and the benchmark name
  identifies the single artifact an update rewrites;
- when the agent proposes updating an existing benchmark, presents it as
  a diff against the stored version — never a silent overwrite;
- carries no k6 or service-specific knowledge of its own — it persists
  whatever content the agent decided.

### `show-benchmark` (skill)

Mirrors `show-otel-instrumentation-report`'s role: every mission in this
repo closes with a `show-*` synthesis instead of dumping its stored
deliverable into the conversation.

- renders a one-screen synthesis after `create-update-benchmark` persists
  — the stored path, what the benchmark exercises (service, endpoints,
  test type), and the next recommended action (e.g. run it with
  `/odd-observe ... benchmark <name>`);
- for an update, states what changed against the previous version — the
  diff is already in the commit, this is the human-readable headline;
- never re-dumps the script or manifest itself — the stored files are the
  deliverable, the synthesis is a pointer to them;
- reads nothing beyond what `create-update-benchmark` just wrote.

### What `.odd/benchmarks/` is — and is not

`.odd/benchmarks/` is a **third kind** of `.odd/` content, and it does
not inherit the report stores' rules:

- **Not append-only.** `AGENTS.md`'s "`.odd/` memory is append-only" and
  `docs/guide/reports.md`'s "a report is never edited after the fact"
  govern the *committed reports*. A benchmark is living source, not a
  run record — git history, not file accumulation, is its memory.
  `AGENTS.md` and `docs/guide/reports.md` are amended in the same change
  to scope the append-only rule to `observe-run-reports/`,
  `otel-instrumentation-reports/`, and `decisions.md`, naming
  `benchmarks/` as the mutable exception.
- **Deletable, and nobody deletes it automatically.** A benchmark whose
  target service is deleted or renamed is stale source; no component in
  this design garbage-collects it. Removing a benchmark is a human's PR,
  like removing any other dead source file — no agent or skill ever
  deletes under `.odd/benchmarks/`. `k6-benchmark-expert` surfaces a
  benchmark whose target service it can no longer find as a finding in
  its answer, and stops there.
- **Committed, therefore under the no-secrets rule.** A load script
  against an authenticated API is the likeliest place a token gets
  committed in this whole design. The authored script never inlines
  credentials: it reads them through k6's own `k6/secrets` API with
  `--secret-source` (which also redacts them from k6's logs), or through
  environment variables the manifest names and never stores.
  `create-update-benchmark` refuses to persist a script carrying a
  literal credential.
- **Invisible to `/odd-status`.** `get-status` inventories the two report
  directories and the decisions ledger; benchmarks are not loop state and
  do not appear there. `/odd-verify`'s verify-vs-re-measure boundary
  already ignores commits that only touch `.odd/`, so authoring or
  updating a benchmark correctly never counts as "a fix landed".

### `k6-guides` (skill)

Same pattern as `otel-guides` (one file per language) and
`observability-cli-guides` (one file per backend): a selection map whose
callers open exactly the reference they need instead of re-deriving k6
usage from memory. Here the selection axis is the topic.

**Three callers, three different times:**

- `/odd-instrument-bench` reads it while **asking the caller what it
  needs to know** — which test type fits, which thresholds are worth
  asking about, new benchmark or update to an existing one — before
  dispatching `k6-benchmark-expert` (`authoring-inputs.md`);
- `k6-benchmark-expert` reads it while **authoring** — script structure,
  checks/thresholds/assertions, scenarios/executors;
- `run-scenario` reads it while **executing** a stored benchmark —
  `running-tests.md`, how to invoke `k6 run` itself (flags, output
  format, exit codes) and how to detect k6 is installed at all.
  `run-scenario` is what `observe-run` calls in drive mode, and what a
  `/odd-verify` replay reaches too (verify redispatches to `observe-run`,
  which calls `run-scenario` again with the same protocol) — one
  execution path, reached from two prompts.

The k6 install/detect check sits on the **execution** side, not the
authoring side: `k6-benchmark-expert` never runs k6 and does not need it
installed. "k6 is a documented prerequisite" means README's
**Prerequisites** section gains it next to Docker and gcx, and the
execution leg fails fast with the reference's install steps when the
binary is absent.

#### Fetching the docs

`grafana.com/docs/k6/latest/` serves raw markdown by appending `.md` to
any page URL, or via an `Accept: text/markdown` header — the same
convention `observability-cli-guides/references/datadog.md` already
documents for Datadog's docs. `https://grafana.com/llms.txt` (curated
index) and `https://grafana.com/llms-full.txt` (~1.4 MB, ~1000
`docs/k6/latest` URLs) exist at the site root — the cheapest way to
enumerate the k6 doc tree when building and later re-verifying this
skill's reference files; per-page fetching via the `.md` suffix is still
how the content is read.

#### Reference split

Mapped from the site's top-level structure: `Get started`, `Set up`,
`Using k6`, `Using k6 browser`, `Testing guides`, `JavaScript API`,
`Results output`, `Extensions`, `Examples`, `Reference`, `Release notes`
— `Grafana Cloud k6` and `k6 Studio` (the hosted product and a GUI
script generator) are out of scope for this project's self-hosted,
script-as-reviewed-code benchmarks. Representative split — final split
is worked out during implementation:

- **`install.md`** — install/detect k6 (Homebrew, binaries, Docker,
  package managers) and which k6 major version the guidance targets.
  Source: `Set up > Install k6`.
- **`running-tests.md`** — `k6 run`, flags, exit codes, the output
  surface (end-of-test summary, real-time outputs). Source: `Get started
  > Running k6`, `Results output`.
- **`scripting.md`** — HTTP requests, checks, thresholds, assertions
  (`expect` — a distinct third concept from checks and thresholds),
  options, test lifecycle hooks, scenarios/executors (the staged load
  model — warmup / ramp / steady, `stages` on the `ramping-vus` executor
  — the manifest's profile stages map onto), and `secret-source` /
  `k6/secrets`. Source: `Using k6`.
- **`test-types.md`** — the six documented load test types (smoke,
  average-load, stress, soak, spike, breakpoint) and picking one for a
  given investigation. Source: `Testing guides > Load test types`.
- **`authoring-inputs.md`** — not a k6 how-to page, a synthesis: every
  dimension a k6 benchmark structurally needs decided before it can be
  written, classified by who can answer it:

  | Dimension | Who decides | Why |
  | --- | --- | --- |
  | New benchmark, or update to a named existing one | human | intent; the agent can list what exists but not choose |
  | Test type (smoke / load / stress / soak / spike / breakpoint) | human | encodes what the caller wants to learn |
  | Thresholds (the pass/fail targets) | human | a target is a product decision, not a measurement |
  | Load shape and executor | agent proposes, human confirms | follows mechanically from the test type, but concurrency changes every latency number — `run-scenario` requires it stated explicitly |
  | Target scope (which endpoints/operations) | agent | discoverable: routes, OpenAPI, hot operations in stored `.odd/` reports |
  | Duration and stage lengths | agent proposes, human confirms | the type's documented range is discoverable; the actual budget is the caller's |
  | Target base URL / environment | human | mission-time input, never guessed by probing |

  This is what the prompt reads to know which questions to ask, and what
  stops it from either interrogating the caller about things it could
  discover itself or silently guessing things it shouldn't.
- **`protocols.md`** — protocol support beyond plain HTTP/1.1 (HTTP/2,
  WebSockets, gRPC natively; SQL / Kafka / ZeroMQ / Redis and others via
  `xk6` extensions). Source: `Using k6 > Protocols`, `Extensions`.
- **`browser.md`** — browser-level/frontend performance testing rather
  than API load — likely out of scope for this project's HTTP-API-focused
  benchmarks today, kept for when it isn't. Source: `Using k6 browser`,
  `JavaScript API > k6/browser`.

Conventions inherited from `otel-guides`/`observability-cli-guides`,
plus one new: reference content is a **snapshot** ("last verified
YYYY-MM"), the fetched official page always overrides it; recommendations
come from a fetched page, never memory; **the k6 major version is
stated** — `latest` currently documents k6 v2, which removed the
`externally-controlled` executor, `k6 pause/resume/scale/status`, and
`k6 login`, and moved the Go module path. `install.md` names the version
the rest of the skill assumes; `scripting.md` never recommends a removed
executor.

### Execution and verification (through `/odd-observe` and `/odd-verify`)

- **naming a stored benchmark is a `benchmark: <name>` field that
  composes with `observe-run`'s existing `drive`/`observe` modes — not a
  new, fourth mode.** `drive`/`observe`/`post-hoc` answer "who generates
  the traffic and when"; which stored plan is running is a different,
  orthogonal question — conflating them would make "someone else is
  driving our stored benchmark X on a shared environment, I'm just
  observing" inexpressible.
  - **`drive` + `benchmark: X`** — `observe-run` runs k6 itself against
    the stored plan `X` (via `run-scenario`'s new stored-benchmark mode)
    instead of inventing ad-hoc requests;
  - **`observe` + `benchmark: X`** — someone else is running `X`
    elsewhere; `observe-run` only watches telemetry, but the report can
    now cite `X`'s name and revision as the replayable protocol instead
    of an untyped time window;
  - **`post-hoc`** does not take a `benchmark` field — the caller was not
    present for the run and cannot attest that plan `X` is what produced
    the window, so an unverifiable `benchmark:` claim would make a
    report look replayable when it is not.
- the observation report's scenario record references the benchmark by
  name **and git revision** rather than verbatim commands — `/odd-verify`
  replays the exact same plan. **A replay reads the benchmark at the
  recorded revision, not at `HEAD`**: benchmarks are mutable, so a
  diff-reviewed update between an observation and its verification would
  silently change the protocol — the exact thing `run-scenario`'s "one
  changed variable invalidates the comparison" rule forbids. When the
  stored benchmark has moved since the baseline, the run is a new
  baseline, stated as such, never a verdict on a fix.
- `/odd-verify` replays the **mode stored in the baseline report's own
  frontmatter** — never re-derives drive-vs-observe from whether a
  scenario or benchmark is present. (Fixes an interface bug: an `observe`
  + `benchmark: X` report *does* record a replayable scenario, so
  inferring "drive" from that presence would have oddyssey generate load
  nobody authorized.)
- **the pass/fail verdict is telemetry-only, never k6's own thresholds or
  stdout summary.** Consistent with this project's method everywhere
  else ("never conclude from one signal what two could confirm"): a
  benchmark run is observed with the same cross-signal method as any
  other run — metrics, **traces** (error root cause, which span explains
  the latency), and logs. Only where the load comes from (a stored k6
  plan instead of ad-hoc commands) and where the pass/fail thresholds
  come from (the manifest, instead of invented at observe time) change.
  **The manifest is the sole source of the thresholds ruled on**, each
  one ruled against a telemetry-derived measurement carrying the query
  that produced it.
- **k6's own client-side telemetry is a bonus signal, never a
  requirement.** k6 ships a real-time OpenTelemetry output and a
  Prometheus remote-write one: when the load generator can actually
  reach an OTLP endpoint, its own view (VU count, `http_req_duration`,
  dropped iterations) lands in the same store as the service's own
  signals and counts toward the verdict too — a legitimate second signal
  to cross-confirm against, not merely "evidence." **This is a local-stack
  reality, not a general one.** Verified live against oddyssey's own
  local stack, where it works with zero extra configuration because
  `K6_OTEL_GRPC_EXPORTER_ENDPOINT` defaults to `localhost:4317`, the
  local stack's own default OTLP port — but most remote backends
  (`cloudwatch`, `azure-monitor`, `datadog`, `dynatrace`, `splunk`) have
  no bare OTLP-push endpoint the machine running k6 can reach at all:
  they take telemetry through their own SDK/agent/exporter, not a plain
  `K6_OTEL_GRPC_EXPORTER_ENDPOINT`, and the machine driving load against
  a remote target frequently has no network path to push there even
  when one exists (firewalls, VPNs, auth the load generator doesn't
  carry). The verdict never depends on k6's OTel output landing
  anywhere: the service's own telemetry is what every backend already
  guarantees access to (that's the whole premise of `/odd-observe`
  working at all), and remains sufficient on its own. k6's own view is
  opportunistic - used when reachable, never required, never assumed. A
  load-generator-shaped `service.name` in the store, on the backends
  where it does land, must not be mistaken for a second copy of the
  target service by the observation's service preflight and environment
  detection.
- **k6's own execution summary is still recorded, as evidence, not as the
  verdict.** A load generator that failed to connect, crashed mid-run, or
  dropped iterations produces telemetry that looks deceptively clean
  without that context — `run-scenario`'s existing "a failed or partial
  run is data" rule already covers this: k6's exit status, request-level
  errors, and check failures go into the scenario record alongside the
  telemetry-derived numbers.
- **standard `run-scenario` sample-count rules apply** (≥30 requests
  before a p95, ~100 before a p99), not the expensive/non-deterministic
  carve-out built for individually-expensive, non-deterministic
  iterations (an LLM-backed job costing real money and minutes per
  call) — k6 load is the opposite: cheap, high-volume, deterministic.
- **a sustained/staged k6 run routinely exceeds a single tool call's
  budget.** Use `run-scenario`'s existing detached-poller pattern by
  default rather than capping benchmark duration to fit inside one turn.
  `observe-run`'s drive-mode text is updated to name the poller as an
  allowed in-turn wait shape (it currently only names two: a blocking
  foreground command, or a blocking wait primitive — the poller does
  satisfy "inside your turn," the job detaches, the wait does not, but
  the text must say so or a benchmark mission reads as forbidden).
- **`run-scenario` step 0 applies unchanged, and matters more here.** A
  benchmark run is exactly the case where cumulative metrics span an
  hour: restart the observed process, then `odd_stack_reset`, then
  record the process identity and qualify every cumulative query with
  it.
- **remote targets: authorization is given explicitly at mission time,
  through `/odd-observe`, never persisted in the benchmark manifest.**
  This is `observe-run`'s existing rule ("drive a remote service only
  when the caller explicitly says so") — `run-scenario` itself is scoped
  to locally running services and carries no remote rule of its own. A
  manifest-level "this benchmark may target remote" flag would be a
  standing, easy-to-forget permission; the caller authorizes it fresh,
  every run.
- **warmup vs. one continuous k6 window.** `run-scenario` mandates
  discarding warmup requests from quoted numbers; a staged k6 run is one
  window, so the ramp pollutes every steady-state percentile unless
  stage boundaries are queryable from the record (see the manifest inputs
  above).

### Documentation

Beyond the routine per-primitive updates `AGENTS.md`'s existing sync
rules already require (`docs/guide/prompts.md`, `dependencies.md`, the
README primitives table), two things need a place none of those
produce:

- **README — `#### /odd-instrument-bench`, right after `/odd-status`
  under "Miscellaneous prompts".** Same shape as every other subsection
  there: a fenced block of example prompts, then a short paragraph.
  Closes with a pointer to the new guide below, the same way "How to"
  step 4 points to `docs/guide/backends.md`.
- **New `docs/guide/benchmarks.md` — the end-to-end lifecycle.** None of
  the four existing guides own this story: `prompts.md` catalogs one
  prompt at a time, `dependencies.md` maps the dispatch graph,
  `reports.md` documents file formats, `backends.md` documents
  per-backend setup. Authoring, running, and verifying a benchmark span
  three prompts and two dispatch paths — this guide walks it in order:
  1. **Author** — `/odd-instrument-bench` example invocations, the
     human-decided vs. agent-discoverable split from
     `authoring-inputs.md`, what lands in `.odd/benchmarks/<name>/` and
     what `show-benchmark` renders back.
  2. **Run** — `/odd-observe ... benchmark: <name>` in both `drive` and
     `observe` composition, what changes in the report, the
     telemetry-only verdict.
  3. **Verify** — `/odd-verify` replaying at the recorded revision, what
     happens when the benchmark moved since the baseline.
  - Gets the same `AGENTS.md` sync-rule treatment `docs/guide/backends.md`
    got in #194: a "Keep the benchmarks guide in sync" section, same
    placement as the other four.

## Acceptance (from #75)

### Authoring

1. `/odd-instrument-bench` asks the caller back for whatever
   `authoring-inputs.md` classifies as human-decided (new-vs-update,
   test type, thresholds, target base URL) and confirms what it
   classifies as agent-proposed (load shape, duration) before
   dispatching — never inside `k6-benchmark-expert`.
2. `/odd-instrument-bench` dispatches to `k6-benchmark-expert`, which
   authors a benchmark plan (k6 script + manifest declaring the engine)
   and never executes it.
3. `create-update-benchmark` persists the plan under
   `.odd/benchmarks/<name>/`, on a work branch, committing the
   benchmark's files alone and stating the stored path.
4. Before authoring, the agent is handed every benchmark already stored
   for the target service, not just a single match, and its answer
   states which one it extends or why the new one is distinct.
5. The agent may propose a reviewed diff updating an existing benchmark
   when the service's endpoints have drifted, never a silent
   replacement.
6. `create-update-benchmark` refuses to persist a script carrying a
   literal credential; authored scripts read secrets through
   `k6/secrets` / `--secret-source` or named environment variables.
7. `k6-guides` exists as a curated, per-topic map of the official k6
   docs, states the k6 major version its guidance targets, and carries a
   "last verified" snapshot date.
8. `authoring-inputs.md` classifies every dimension it lists as
   human-decided or agent-discoverable — no dimension unclassified, none
   classified without being listed.
9. `/odd-instrument-bench` closes with `show-benchmark`'s synthesis of
   the stored path — the script and manifest are never re-dumped in the
   conversation.

### Execution and verification

10. `/odd-observe` accepts a `benchmark: <name>` mission field composing
    with `drive` and `observe`; `post-hoc` rejects it.
11. `/odd-observe` in drive mode runs a named stored benchmark via a
    `run-scenario` stored-benchmark mode, and `run-scenario` fails fast
    with `k6-guides`' install guidance when k6 is absent.
12. The report records the benchmark name + git revision as its
    scenario, and `create-observe-run-report` / `docs/guide/reports.md`
    document the field.
13. A benchmark run longer than a tool call uses `run-scenario`'s
    detached-poller pattern, and `observe-run`'s drive-mode text names
    the poller as an allowed in-turn wait shape.
14. `/odd-verify` replays the mode stored in the baseline report's own
    frontmatter — never re-derives drive-vs-observe from scenario/
    benchmark presence.
15. `/odd-verify` replays the benchmark at the revision the baseline
    recorded; a benchmark that changed since makes the run a stated new
    baseline, not a verdict.
16. `/odd-verify` rules every threshold declared in the replayed
    benchmark's manifest pass/fail against a telemetry-derived
    measurement (metrics, traces, logs — plus k6's own OpenTelemetry
    output as an opportunistic bonus signal on backends where it's
    reachable, never required) — never k6's own threshold
    or stdout summary.
17. k6's own execution summary (exit status, request errors, failed
    iterations, checks) is captured in the scenario record as evidence,
    alongside the telemetry-derived numbers.
18. Warmup/ramp stages are excluded from the quoted steady-state
    numbers, with the boundary readable from the record.
19. Before/after latency numbers from benchmark runs use `run-scenario`'s
    standard sample-count rules (not the expensive/non-deterministic
    carve-out).
20. Remote-target authorization is given at mission time only, never
    stored in the benchmark manifest.

### Package and documentation

21. `AGENTS.md` and `docs/guide/reports.md` scope the append-only rule to
    the report stores and name `.odd/benchmarks/` as mutable,
    human-deletable source.
22. `docs/guide/prompts.md` gains an `/odd-instrument-bench` section with
    example invocations and field mapping, and updates `/odd-observe` /
    `/odd-verify` for the `benchmark` field.
23. `README.md`'s "Miscellaneous prompts" gains a `#### /odd-instrument-bench`
    subsection right after `/odd-status`, closing with a pointer to the
    new guide.
24. A new `docs/guide/benchmarks.md` walks the full author → run → verify
    lifecycle end to end, distinct in scope from `prompts.md`,
    `dependencies.md`, `reports.md`, and `backends.md`.
25. `AGENTS.md` gains a "Keep the benchmarks guide in sync" rule, same
    placement and style as the other four.
26. `docs/guide/dependencies.md` gains an `/odd-instrument-bench`
    diagram, updates the `/odd-observe` and `/odd-verify` subgraphs
    (`run-scenario` → `k6-guides`), and corrects the bird's-eye counts
    (5 prompts → 6, 2 agents → 3, 12 skills → 15).
27. `README.md` updates the primitives table (new prompt, agent, and
    three skills) and adds k6 to the Prerequisites section.
28. `apm.yml` / the package manifest expose the new prompt, agent, and
    skills (`marketplace/`, `.claude-plugin/`, `.agents/plugins/` stay
    generated — authored in `.apm/` only).

## Out of scope / Deferred

**Authoring** (blocks implementation, resolved in the implementation
plan, not here):

- the benchmark manifest's exact schema (fields, format), including
  whether the target base URL is a stored field, and how stage
  boundaries become queryable;
- `k6-guides`'s final reference-file split — the list above is a
  starting point, not the final set.

**Execution** (the maintainer drives this discussion separately, not
part of this implementation):

- the mechanics of `run-scenario`'s stored-benchmark mode and its exact
  interface with `observe-run`;
- how routing k6's own OpenTelemetry output into the stack works end to
  end, per backend — counting it as an opportunistic bonus signal when
  reachable is decided (above, and never a requirement); the wiring on
  each backend where it's even possible (only the local stack is
  verified so far; most remote backends have no bare OTLP-push path at
  all), and keeping its `service.name` from being mistaken for the
  target service, is not;
- whether `post-hoc` + `benchmark` stays forbidden on the reasoning
  above.
