# k6 Benchmark Authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the authoring half of #75 — a new `/odd-instrument-bench`
prompt that dispatches to a new `k6-benchmark-expert` agent, which
investigates a service, asks the caller (through the prompt) whatever
only a human can decide, and authors a k6 benchmark (script + manifest)
into `.odd/benchmarks/<name>/` through `create-update-benchmark`,
closing with `show-benchmark`'s synthesis. `k6-guides` gives the prompt
and the agent everything they need to know about k6 itself.

**Architecture:** Five new `.apm/` primitives (1 prompt, 1 agent, 3
skills) following this repo's existing `/odd-instrument-otel` /
`otel-instrumentation-expert` / `otel-guides` /
`create-otel-instrumentation-report` / `show-otel-instrumentation-report`
shape exactly. No Python, no MCP server changes, no new tests under
`tests/mcp-server/` — this is pure `.apm/` markdown content plus the
docs updates `AGENTS.md`'s existing sync rules require. Execution
(`/odd-observe` running a stored benchmark, `/odd-verify` replaying one)
is explicitly **out of scope** — see the spec's "Out of scope /
Deferred" section; this plan produces working, reviewable *authoring*
software on its own, with nothing in `.odd/benchmarks/` runnable yet by
oddyssey itself (a human can still `k6 run` an authored script directly).

**Tech Stack:** Markdown (`.apm/prompts/*.prompt.md`,
`.apm/agents/*.agent.md`, `.apm/skills/*/SKILL.md`,
`.apm/skills/*/references/*.md`), `apm-cli` for validation
(`uvx --from apm-cli==0.28.0 apm install --target claude && apm audit`),
k6 v2 (installed and verified live for this plan — `brew install k6`,
confirmed `k6 v2.2.0` on this machine).

**Spec:** `docs/superpowers/specs/2026-08-31-k6-benchmark-authoring-design.md`

## Global Constraints

- English-only in every committed file (`AGENTS.md`).
- No secrets, no real identifiers, no real account/tenant names in any
  committed file (`AGENTS.md`) — every example in this plan's file
  content uses generic placeholders (`checkout`, `myteam`, fake URLs).
- Never commit on the default branch — branch first, `type/short-desc`
  (`AGENTS.md`).
- Conventional Commits for every commit message (`AGENTS.md`,
  `git-commit` skill).
- `.apm/` is the only source of truth for prompts/agents/skills —
  `marketplace/`, `.claude-plugin/`, `.agents/plugins/` are generated,
  never edited by hand (`AGENTS.md`).
- Every task that touches `.apm/` or `apm.yml` ends with
  `uvx --from apm-cli==0.28.0 apm install --target claude && uvx --from apm-cli==0.28.0 apm audit`
  run and passing (`AGENTS.md`), with `git status --porcelain` recorded
  before and the command's generated artifacts (`.claude/agents/`,
  `.claude/commands/`, `.claude/skills/`, any `.gitignore` edit) reverted
  afterward so only the intended files land in the commit.
- Cross-references between `.apm/` primitives are **by name only**, never
  by path (`CONTRIBUTING.md`) — so they survive materialization into any
  CLI target.
- One logical change per PR; every PR references an existing issue
  (`Closes #75` for the whole feature, or a sub-issue if this plan is
  split across PRs) (`AGENTS.md`).
- k6 v2 is the version this feature targets — `k6 v2.2.0` confirmed
  installed and working on this machine as of 2026-08-31; v1-only
  guidance (`externally-controlled` executor, `k6 pause/resume/scale/status`,
  `k6 login`) is never written into any reference file.

---

## Verified ground truth (read before starting Task 1)

Everything below was run live on this machine while writing this plan —
not copied from docs without checking. Later tasks cite these facts by
name instead of re-deriving them.

- **Install:** `brew install k6` → `k6 v2.2.0 (commit/devel, go1.26.5, darwin/arm64)`.
  Real docs source: `https://grafana.com/docs/k6/latest/set-up/install-k6.md`
  (verified 200, `content-type: text/markdown`).
- **`.md` suffix fetches raw markdown** on every `grafana.com/docs/k6/latest/*`
  page tested (11 distinct pages across this plan's research, all HTTP
  200 `text/markdown`). `https://grafana.com/llms.txt` (curated index)
  and `https://grafana.com/llms-full.txt` (~1.4 MB, ~1000
  `docs/k6/latest/*` URLs) exist at the site **root**, not under
  `/docs/k6/latest/` — verified 200 both.
- **`k6 run script.js`** — real run against a live local service
  (oddyssey's own local Grafana on `:3000`), `stages` (ramp/steady/ramp-down),
  `thresholds`, `checks`, all worked exactly as documented. Confirmed
  flags: `-u`/`--vus`, `-d`/`--duration`, `-i`/`--iterations`,
  `-s`/`--stage` (`[duration]:[target]`), `-o`/`--out`.
- **Exit codes, verified by deliberately failing a threshold:** `0` on
  pass; **`99`** specifically when a threshold is crossed (not a generic
  `1`) — stderr carries
  `level=error msg="thresholds on metrics '<name>' have been crossed"`.
- **`--out json=<file>`** produces newline-delimited JSON: one `"type":"Metric"`
  definition line per metric (name, type, thresholds), then
  `"type":"Point"` lines per sample, tagged with `scenario`, `status`,
  `method`, `url`, `expected_response`.
- **`-o opentelemetry` really works against oddyssey's own local stack
  with zero extra config**, because `K6_OTEL_GRPC_EXPORTER_ENDPOINT`
  defaults to `localhost:4317` — the exact default OTLP gRPC port
  `odd_stack_up` exposes. Only `K6_OTEL_GRPC_EXPORTER_INSECURE=true` was
  needed (the local stack has no TLS). Verified end to end: ran
  `K6_OTEL_GRPC_EXPORTER_INSECURE=true k6 run -o opentelemetry script.js`
  against the local stack, then queried Prometheus via `gcx metrics query`
  and found k6's own metrics landed as `job="k6"`, `service_name="k6"`,
  `service_version="2.2.0"` (confirms the spec's "load-generator-shaped
  `service.name`" concern with the *exact* label values), metric names
  `http_reqs_total`, `http_req_duration_milliseconds_{sum,count,bucket}`,
  `http_req_blocked_milliseconds_{sum,count,bucket}`. Full config
  surface (`K6_OTEL_SERVICE_NAME` default `k6`, `K6_OTEL_METRIC_PREFIX`,
  `K6_OTEL_EXPORT_INTERVAL` default `10s`, `K6_OTEL_EXPORTER_PROTOCOL`
  grpc/http-protobuf, TLS options) confirmed from
  `results-output/real-time/opentelemetry.md`.
- **Real page slugs confirmed (200) vs. guessed-wrong slugs (404), for
  the reference files below:**
  - `set-up/install-k6.md` — 200 (not `get-started/install-k6`)
  - `get-started/running-k6.md` — 200
  - `results-output/end-of-test.md` — 200
  - `results-output/real-time.md` — 200
  - `results-output/real-time/opentelemetry.md` — 200
  - `using-k6/http-requests.md` — 200
  - `using-k6/scenarios/executors.md` — 200
  - `using-k6/thresholds.md` — 200
  - `using-k6/checks.md` — 200
  - `using-k6/protocols.md` — 200
  - `using-k6/k6-options/reference.md` — 200
  - `testing-guides/test-types.md` — 200 (not `.../test-types/load-test-types`)
  - `javascript-api/k6-http.md` — 200
  - `javascript-api/k6-secrets.md` — 200 (not `using-k6/k6-secrets`)
- **Test types, verified from `testing-guides/test-types.md`:** six, not
  five — smoke, average-load (a.k.a. "load"), stress, soak, spike,
  **breakpoint**.
- **k6 v2 breaking changes, verified from `get-started/migrating-to-v2.md`
  (cited by the Opus design review, not re-fetched here — treat as
  needing a final confirmation pass in Task 1, Step 1):** the
  `externally-controlled` executor removed, `k6 pause/resume/scale/status`
  removed, `k6 login` removed, Go module path moved.

---

## File Structure

```
.apm/
  prompts/
    odd-instrument-bench.prompt.md          [Task 5]
  agents/
    k6-benchmark-expert.agent.md            [Task 4]
  skills/
    k6-guides/
      SKILL.md                              [Task 1]
      references/
        install.md                          [Task 1]
        running-tests.md                    [Task 1]
        scripting.md                        [Task 1]
        test-types.md                       [Task 1]
        authoring-inputs.md                 [Task 1]
        protocols.md                        [Task 1]
        browser.md                          [Task 1]
    create-update-benchmark/
      SKILL.md                              [Task 2]
    show-benchmark/
      SKILL.md                              [Task 3]
apm.yml                                      [Task 9, registers all five]
AGENTS.md                                    [Task 6: append-only scoping;
                                               Task 7: benchmarks guide sync rule]
docs/guide/
  reports.md                                [Task 6: append-only scoping]
  benchmarks.md                             [Task 7: new, Author section only]
  prompts.md                                [Task 8]
  dependencies.md                           [Task 8]
README.md                                    [Task 8]
```

---

## Task 1: `k6-guides` skill

**Files:**
- Create: `.apm/skills/k6-guides/SKILL.md`
- Create: `.apm/skills/k6-guides/references/install.md`
- Create: `.apm/skills/k6-guides/references/running-tests.md`
- Create: `.apm/skills/k6-guides/references/scripting.md`
- Create: `.apm/skills/k6-guides/references/test-types.md`
- Create: `.apm/skills/k6-guides/references/authoring-inputs.md`
- Create: `.apm/skills/k6-guides/references/protocols.md`
- Create: `.apm/skills/k6-guides/references/browser.md`

**Interfaces:**
- Consumes: nothing (no dependency on other tasks).
- Produces: skill name `k6-guides`, referenced by name (never by path)
  from Task 4 (`k6-benchmark-expert`, authoring) and Task 5
  (`/odd-instrument-bench`, which-questions-to-ask). `authoring-inputs.md`
  is the file Task 5 points to by name.

This task has no code to test in the pytest sense — the "test" is
`apm audit` passing and every cited URL actually resolving. Steps below
interleave writing content with verifying it, the same TDD shape adapted
to markdown content: write, then prove it's not invented.

- [ ] **Step 1: Confirm the v2 migration facts before writing `install.md`**

Run: `curl -s "https://grafana.com/docs/k6/latest/get-started/migrating-to-v2.md" | head -100`

Expected: 200, markdown content confirming the removed
`externally-controlled` executor, removed `k6 pause/resume/scale/status`,
removed `k6 login`, moved Go module path (per "Verified ground truth"
above, sourced from the design review but not re-fetched during this
plan — confirm now). If any detail differs from what's stated above,
use what this fetch actually says in Step 2's `install.md` content, not
what's written here.

- [ ] **Step 2: Write `.apm/skills/k6-guides/SKILL.md`**

```markdown
---
name: k6-guides
description: Curated map of the official k6 load-testing docs - installation, running a script, scripting (checks/thresholds/scenarios), test types, protocols, and which questions a benchmark's inputs require before it can be authored. Use when authoring or reasoning about a k6 benchmark - pick the topic, open its reference file, and follow the linked official docs. Read by /odd-instrument-bench (which questions to ask) and k6-benchmark-expert (authoring); run-scenario reads it separately at execution time.
---

# k6 guides

Same pattern as `otel-guides` (one file per language) and
`observability-cli-guides` (one file per backend): a selection map whose
callers open exactly the reference they need instead of re-deriving k6
usage from memory. Here the selection axis is the topic.

## Fetching the docs

`grafana.com/docs/k6/latest/` serves raw markdown by appending `.md` to
any page URL, or via an `Accept: text/markdown` header - the same
convention `observability-cli-guides/references/datadog.md` documents
for Datadog's docs. `https://grafana.com/llms.txt` (curated index) and
`https://grafana.com/llms-full.txt` (~1.4 MB, ~1000 `docs/k6/latest`
URLs) exist at the site root - the cheapest way to enumerate the k6 doc
tree when this skill's reference files need re-verifying; per-page
fetching via the `.md` suffix is still how the content itself is read.
Both live at the site **root**, not under `/docs/k6/latest/` (that path
404s) - a natural first mistake, verify against the root before
concluding they don't exist.

## Which reference

| Question | Reference |
| --- | --- |
| Is k6 installed? How do I install/detect it? | [install.md](references/install.md) |
| How do I run a k6 script, read its output, know if it passed? | [running-tests.md](references/running-tests.md) |
| How do I write the script - requests, checks, thresholds, staged load? | [scripting.md](references/scripting.md) |
| Which test type fits this investigation - smoke, load, stress, soak, spike, breakpoint? | [test-types.md](references/test-types.md) |
| What does a benchmark's authoring need decided, and by whom - human or agent? | [authoring-inputs.md](references/authoring-inputs.md) |
| Does k6 support the service's protocol (gRPC, WebSockets, ...)? | [protocols.md](references/protocols.md) |
| Is this browser/frontend performance testing rather than API load? | [browser.md](references/browser.md) |

## Conventions

- Reference content is a **snapshot** ("last verified YYYY-MM") - the
  fetched official page always overrides it. Recommendations must come
  from a fetched page, never from memory; anything unfetchable is marked
  unverified rather than presented as sourced.
- **The k6 major version is stated.** `latest` currently documents k6
  **v2** - `install.md` names it, and `scripting.md` never recommends a
  removed executor or command. A skill that silently mixes v1 and v2
  guidance produces scripts that fail to start.
- These references cover k6 **itself** - never this project's
  `.odd/benchmarks/` format, never the manifest schema. That knowledge
  lives with `create-update-benchmark` and `k6-benchmark-expert`.
```

- [ ] **Step 3: Write `.apm/skills/k6-guides/references/install.md`**

```markdown
# Install & detect k6

Official docs: https://grafana.com/docs/k6/latest/set-up/install-k6/
Raw markdown via `.md` suffix or `Accept: text/markdown` (verified 2026-08).

**This guide targets k6 v2** (confirmed `k6 v2.2.0` on 2026-08-31).
k6 v2 removed the `externally-controlled` executor, the
`k6 pause/resume/scale/status` commands, and `k6 login`, and moved the
Go module import path - never suggest any of those. See
[migrating-to-v2](https://grafana.com/docs/k6/latest/get-started/migrating-to-v2/)
if a script or command predates v2.

## Binary

- **Binary**: `k6`
- **Detect**: `command -v k6` - `k6 version` on success prints
  `k6 vX.Y.Z (commit/..., go..., <os>/<arch>)`.
- **Install**:
  - macOS: `brew install k6` (verified 2026-08: installs from the core
    Homebrew tap, no separate tap needed - `k6 v2.2.0` on Homebrew as of
    this writing).
  - Linux: the official APT/YUM repositories, or a static binary from
    the [releases page](https://github.com/grafana/k6/releases).
  - Docker: `grafana/k6` image, e.g.
    `docker run --rm -i grafana/k6 run - <script.js`.
  - Full platform matrix: `set-up/install-k6` (fetch for anything beyond
    macOS/Linux/Docker - Windows, package-manager specifics change
    between k6 releases, don't guess).

## Who needs k6 installed

**Not `k6-benchmark-expert`.** Authoring a benchmark never runs it - the
agent writes a script and a manifest, it does not execute `k6 run`.
Installation matters on the **execution** side (`run-scenario`, at
`/odd-observe`/`/odd-verify` time, out of scope for this authoring
implementation) - that is where "k6 is a documented prerequisite" (this
project's README Prerequisites section) actually gets checked and where
a missing binary fails fast with the install steps above.
```

- [ ] **Step 4: Verify `install.md`'s claims live**

Run: `brew list k6 --versions` (should already be installed on this
machine from this plan's own verification pass - if not,
`brew install k6` first) then `k6 version`

Expected: prints `k6 v2.2.0 (commit/devel, go1.26.5, darwin/arm64)` or a
newer patch/minor version - if the major version is no longer `2`, stop
and update every k6-guides reference file's version framing before
continuing this task.

- [ ] **Step 5: Write `.apm/skills/k6-guides/references/running-tests.md`**

```markdown
# Running a k6 test and reading its output

Official docs: https://grafana.com/docs/k6/latest/get-started/running-k6/,
https://grafana.com/docs/k6/latest/results-output/

## Running

`k6 run <script.js>` - single VU, once, by default. Flags (verified
2026-08 against k6 v2.2.0):

| Flag | Meaning |
| --- | --- |
| `-u`, `--vus <int>` | number of virtual users (default 1) |
| `-d`, `--duration <duration>` | test duration limit (e.g. `30s`, `5m`) |
| `-i`, `--iterations <int>` | total iteration limit across all VUs |
| `-s`, `--stage <dur>:<target>` | add one load stage - repeat the flag for multiple stages, or use `options.stages` in the script (see scripting.md) |
| `-o`, `--out <output>` | where to send results - `json=<file>` (newline-delimited JSON), `opentelemetry` (see below), and others |
| `--no-setup` / `--no-teardown` | skip the script's `setup()`/`teardown()` |

## Exit codes

**Verified live** (this machine, 2026-08-31, k6 v2.2.0):

- **`0`** - every threshold passed (or no thresholds declared).
- **`99`** - a declared threshold was crossed. Stderr carries
  `level=error msg="thresholds on metrics '<name>' have been crossed"`.
  This is **not** the pass/fail signal `/odd-verify` uses (that's
  telemetry-only, per the design) - but it is what `run-scenario` records
  as k6's own execution evidence alongside the telemetry-derived numbers.
- Other non-zero codes cover setup/script errors - always read stderr,
  don't infer the failure kind from the code alone (this repo's own
  convention with other CLIs' exit codes, e.g. `az`'s).

## Output surface

- **Default (stdout)**: a human-readable summary - per-threshold
  pass/fail, then `HTTP`/`EXECUTION`/`NETWORK` sections with
  avg/min/med/max/p90/p95 for each metric.
- **`--out json=<file>`** - newline-delimited JSON, verified live: one
  `{"type":"Metric",...}` line per metric definition (name, type,
  thresholds, submetrics), then `{"type":"Point","metric":...,"data":{...}}`
  lines per sample, tagged with `scenario`, `status`, `method`, `url`,
  `expected_response`, `group`.
- **`-o opentelemetry`** - pushes metrics to an OTLP endpoint instead of
  writing a local file. Configuration is entirely via `K6_OTEL_*`
  environment variables (no CLI flags for this beyond `-o opentelemetry`
  itself), verified against `results-output/real-time/opentelemetry.md`:

  | Variable | Default | Notes |
  | --- | --- | --- |
  | `K6_OTEL_SERVICE_NAME` | `k6` | the OTel `service.name` k6's own metrics carry - **verified live: lands as `service_name="k6"`, `job="k6"` in Prometheus** when exported to oddyssey's local stack. Distinguishable from the target service's own labels, never mistake one for the other. |
  | `K6_OTEL_GRPC_EXPORTER_ENDPOINT` | `localhost:4317` | **matches oddyssey's local stack's default OTLP gRPC port exactly** - verified live: `K6_OTEL_GRPC_EXPORTER_INSECURE=true k6 run -o opentelemetry script.js` against a running local stack needs no endpoint override at all. |
  | `K6_OTEL_GRPC_EXPORTER_INSECURE` | (unset = TLS required) | set `true` for the local stack (no TLS) - without it the exporter fails to connect. |
  | `K6_OTEL_HTTP_EXPORTER_ENDPOINT` | `localhost:4318` | for `K6_OTEL_EXPORTER_PROTOCOL=http/protobuf` instead of the grpc default |
  | `K6_OTEL_METRIC_PREFIX` | (empty) | prefix every exported metric name |
  | `K6_OTEL_EXPORT_INTERVAL` | `10s` | how often metrics flush to the collector |

  Verified live metric names landing in Prometheus:
  `http_reqs_total`, `http_req_duration_milliseconds_{sum,count,bucket}`,
  `http_req_blocked_milliseconds_{sum,count,bucket}` - the `_bucket`
  suffix confirms k6's Trend metrics (like `http_req_duration`) export
  as OTel histograms, queryable with standard PromQL histogram functions
  (`histogram_quantile`).

  **This is a local-stack reality, not a general one - never treat it as
  required.** It works with zero extra config against oddyssey's own
  local stack only because the endpoint default happens to match. Most
  remote backends (`cloudwatch`, `azure-monitor`, `datadog`, `dynatrace`,
  `splunk`) have no bare OTLP-push endpoint the machine running k6 can
  reach at all - they take telemetry through their own SDK/agent, not a
  plain gRPC/HTTP OTLP target, and even where one exists the load
  generator's network path to it is frequently blocked (firewalls, VPNs,
  auth the load generator doesn't carry). Treat k6's own OpenTelemetry
  output as an **opportunistic bonus signal, used when reachable, never
  assumed** - the service's own telemetry (what every backend already
  guarantees `/odd-observe` can reach, or nothing about this project
  works at all) is what a benchmark's verdict can always depend on.
```

- [ ] **Step 6: Verify `running-tests.md` against a fresh live run**

Run:
```bash
cat > /tmp/verify-k6.js << 'EOF'
import http from 'k6/http';
export const options = { vus: 1, iterations: 2 };
export default function () { http.get('https://httpbin.org/status/200'); }
EOF
k6 run --out json=/tmp/verify-k6.json /tmp/verify-k6.js
echo "exit: $?"
head -2 /tmp/verify-k6.json
```

Expected: exit `0`, and `/tmp/verify-k6.json`'s first line is a
`{"type":"Metric",...}` JSON object. If either the exit code or the
JSON shape differs from what Step 5 documents, fix Step 5's content
before moving on - do not let the reference file drift from what k6
actually does.

- [ ] **Step 7: Write `.apm/skills/k6-guides/references/scripting.md`**

```markdown
# Writing a k6 script

Official docs: https://grafana.com/docs/k6/latest/using-k6/

## Requests, checks, thresholds - three distinct concepts

- **Requests** - `k6/http`: `http.get(url)`, `http.post(url, body)`, etc.
  Source: https://grafana.com/docs/k6/latest/using-k6/http-requests/
- **Checks** - per-request pass/fail assertions that never stop the
  test (`check(res, {'status is 200': (r) => r.status === 200})`).
  Failures count toward `checks_failed`, never abort the run. Source:
  https://grafana.com/docs/k6/latest/using-k6/checks/
- **Thresholds** - pass/fail criteria on **aggregated metrics** across
  the whole run (`thresholds: {http_req_duration: ['p(95)<500']}`).
  A crossed threshold is what produces exit code 99 (see
  running-tests.md). Source:
  https://grafana.com/docs/k6/latest/using-k6/thresholds/
- **Assertions** (`expect`, from the `k6-testing` jslib) - a third,
  newer concept, Playwright-inspired, distinct from both checks and
  thresholds. Confirm current syntax against the official docs before
  using it - not yet exercised live for this plan.

## Staged load - `options.stages`

Verified live (this machine, k6 v2.2.0):

```javascript
export const options = {
  stages: [
    { duration: '3s', target: 5 },  // ramp up to 5 VUs
    { duration: '5s', target: 5 },  // hold at 5 VUs (steady state)
    { duration: '2s', target: 0 },  // ramp down to 0
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};
```

This is the shape a benchmark manifest's warmup/ramp/steady profile
stages map onto - `stages` is k6's own vocabulary for it (the
`ramping-vus` executor under the hood; see
https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/ for the
full executor list when a benchmark needs a shape other than staged
ramping - e.g. `constant-vus`, `constant-arrival-rate`).

**Discarding warmup**: k6 runs one continuous window - there is no
built-in "discard the first N seconds" the way `run-scenario`'s own
warmup rule expects. A benchmark's manifest needs the stage boundaries
recorded (as timestamps, since `options.stages` durations are known at
author time) so a later query can exclude the ramp stage from quoted
steady-state percentiles. This is one of the two inputs the manifest
schema (owned by `k6-benchmark-expert`, not fixed by this skill) must
settle.

## Secrets - never a literal credential in a committed script

An authenticated benchmark reads credentials through k6's own secrets
API, never inlined:

- `k6/secrets` module + `--secret-source` flag (source:
  https://grafana.com/docs/k6/latest/javascript-api/k6-secrets/) - the
  documented way to keep a secret out of both the script and k6's own
  logs.
- Alternative: environment variables the manifest names but never
  stores a value for (`__ENV.API_TOKEN` in the script, the manifest
  records only the variable's **name**).

`create-update-benchmark` refuses to persist a script containing a
literal credential - this reference is what the authoring agent follows
so that check never fires.
```

- [ ] **Step 8: Verify the scripting.md sources resolve**

Run:
```bash
for p in "using-k6/http-requests" "using-k6/checks" "using-k6/thresholds" "using-k6/scenarios/executors" "javascript-api/k6-secrets"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "https://grafana.com/docs/k6/latest/$p.md")
  echo "$p.md -> $code"
done
```

Expected: all five return `200`. (Already verified once while writing
this plan - re-verifying here catches any drift between writing the
plan and executing it.)

- [ ] **Step 9: Write `.apm/skills/k6-guides/references/test-types.md`**

```markdown
# Load test types

Official docs: https://grafana.com/docs/k6/latest/testing-guides/test-types/

Six documented types (verified 2026-08 - an easy miscount, five is a
common wrong answer that drops breakpoint):

| Type | What it answers | Shape |
| --- | --- | --- |
| **Smoke** | Does the system work at all, minimal load? | 1-2 VUs, short duration - a sanity check before anything bigger. |
| **Average-load** (often called "load") | How does the system behave under expected, everyday traffic? | Steady VUs at the expected concurrency, sustained duration. |
| **Stress** | Where does the system start to degrade under above-normal load? | Ramp VUs beyond expected traffic until latency/errors climb. |
| **Soak** | Does the system degrade over a long sustained run (leaks, resource exhaustion)? | Moderate, steady load held for a long duration (hours). |
| **Spike** | Does the system survive a sudden, sharp traffic burst? | Fast ramp to a high VU count, brief hold, fast ramp down. |
| **Breakpoint** | What's the system's actual capacity ceiling? | Continuously increasing load until the system breaks. |

Picking one is a **human decision** (see authoring-inputs.md) - it
encodes what the caller actually wants to learn, which this skill or
the authoring agent cannot infer from the service alone.
```

- [ ] **Step 10: Write `.apm/skills/k6-guides/references/authoring-inputs.md`**

```markdown
# What a benchmark's authoring needs decided

Not a k6 how-to page - a synthesis for `/odd-instrument-bench` and
`k6-benchmark-expert`: every dimension a k6 benchmark structurally needs
decided before it can be written, and who can answer it.

| Dimension | Who decides | Why |
| --- | --- | --- |
| New benchmark, or update to a named existing one | human | intent - the agent can list what exists for the service but not choose |
| Test type (smoke / load / stress / soak / spike / breakpoint) | human | encodes what the caller wants to learn (see test-types.md) |
| Thresholds (the pass/fail targets) | human | a target is a product decision, not a measurement |
| Load shape and executor | agent proposes, human confirms | follows mechanically from the test type, but concurrency changes every latency number - state it explicitly |
| Target scope (which endpoints/operations) | agent | discoverable: routes, OpenAPI, hot operations in stored `.odd/` reports |
| Duration and stage lengths | agent proposes, human confirms | the type's documented range is discoverable; the actual time budget is the caller's |
| Target base URL / environment | human | mission-time input, never guessed by probing |

**This is the whole contract**: `/odd-instrument-bench` asks about every
row marked "human" (and confirms the "agent proposes, human confirms"
rows) **before** dispatching `k6-benchmark-expert` - never inside the
agent, where going back and forth with the caller gets a lot harder.
The agent then investigates and decides every "agent" row on its own.

Every dimension above appears exactly once, classified. If a future
edit adds a dimension, it goes in this table with a "who decides"
value - an unclassified dimension is exactly the kind of gap this file
exists to prevent.
```

- [ ] **Step 11: Write `.apm/skills/k6-guides/references/protocols.md`**

```markdown
# Protocol support beyond plain HTTP

Official docs: https://grafana.com/docs/k6/latest/using-k6/protocols/

Native (verified 2026-08, `using-k6/protocols`):

- **HTTP/1.1** - the default.
- **HTTP/2** - k6 upgrades automatically if the server reports support.
- **WebSockets** - a different test structure and VU lifecycle than
  request/response protocols - read the dedicated page before scripting
  one.
- **gRPC** - via `k6/net/grpc`.

Beyond those, via `xk6` extensions (not in core k6, a separate build
step): SQL, Kafka, ZeroMQ, Redis, and others.

Relevant when the target service isn't a plain HTTP API -
`k6-benchmark-expert` checks this reference before assuming HTTP is the
right protocol for a benchmark.
```

- [ ] **Step 12: Write `.apm/skills/k6-guides/references/browser.md`**

```markdown
# k6 browser - frontend performance testing

Official docs: https://grafana.com/docs/k6/latest/using-k6-browser/,
https://grafana.com/docs/k6/latest/javascript-api/k6-browser/

`k6/browser` drives a real browser and collects frontend performance
metrics (page load, Web Vitals) - a different kind of test than the
API-load benchmarks this feature otherwise targets. Likely out of scope
for this project's HTTP-API-focused benchmarks today; kept as a
reference for when a service under test is a frontend rather than an
API.
```

- [ ] **Step 13: Validate the whole skill with `apm audit`**

Run:
```bash
cd /Users/usingsystem/Repos/github/oddyssey
git status --porcelain > /tmp/pre-apm-status.txt
uvx --from apm-cli==0.28.0 apm install --target claude && uvx --from apm-cli==0.28.0 apm audit
```

Expected: the scanned-file count includes the 8 new `k6-guides` files,
"no issues found" for them (the pre-existing 56-file drift from
unrelated `.agents/`/`.github/` paths is expected and unrelated - do
not treat it as a failure this task caused).

- [ ] **Step 14: Clean up apm install artifacts**

Run:
```bash
git checkout -- .gitignore
git clean -fd .claude/agents .claude/commands .claude/skills
git status --porcelain
```

Expected: only the 8 new files under `.apm/skills/k6-guides/` remain in
`git status` (no `.claude/` artifacts, no `.gitignore` diff).

- [ ] **Step 15: Commit**

```bash
git checkout -b feat/k6-guides-skill
git add .apm/skills/k6-guides/
git commit -m "$(cat <<'EOF'
feat(apm): add k6-guides skill

Curated map of the official k6 docs, one reference file per topic -
install, running-tests, scripting, test-types, authoring-inputs,
protocols, browser. Mirrors otel-guides/observability-cli-guides'
pattern. Every claim verified live against k6 v2.2.0 and the real
grafana.com/docs/k6/latest/ site while writing this skill, not copied
from memory.

Part of #75 (k6-benchmark-expert and /odd-instrument-bench, still to
come, will be this skill's callers).
EOF
)"
```

---

## Task 2: `create-update-benchmark` skill

**Files:**
- Create: `.apm/skills/create-update-benchmark/SKILL.md`

**Interfaces:**
- Consumes: nothing directly (no dependency on `k6-guides`' content -
  this skill is deliberately k6-agnostic).
- Produces: skill name `create-update-benchmark`, referenced by name
  from Task 4 (`k6-benchmark-expert` hands it content to persist) and
  Task 7 (the `docs/guide/benchmarks.md` guide's Author section).

- [ ] **Step 1: Read the skill this one mirrors, for the commit-discipline pattern**

Run: `cat /Users/usingsystem/Repos/github/oddyssey/.apm/skills/create-otel-instrumentation-report/SKILL.md`

Expected: confirms the never-commit-on-default-branch /
commit-the-file-alone / state-the-stored-path pattern this task's
`SKILL.md` inherits, and the *immutability* rule it deliberately does
**not** inherit (a benchmark is not a report - see the spec's "What
`.odd/benchmarks/` is" section, reproduced in Step 2 below).

- [ ] **Step 2: Write `.apm/skills/create-update-benchmark/SKILL.md`**

```markdown
---
name: create-update-benchmark
description: Persist a k6-benchmark-expert-authored benchmark (script + manifest) into .odd/benchmarks/<name>/ - naming, versioning, the commit, recalling the benchmarks already stored for a service. A benchmark is not a report - it is living source, updated in place via reviewed diffs, not append-only. Use when a benchmark's authored content needs to land in the repo, or when an update to an existing benchmark needs to be recalled before authoring a new one.
---

# Create / Update a Benchmark

`.odd/benchmarks/<name>/` is a **third kind** of `.odd/` content, and it
does **not** inherit the report stores' immutability rule
(`create-observe-run-report`, `create-otel-instrumentation-report`):
`AGENTS.md`'s "the `.odd/` memory is append-only" and
`docs/guide/reports.md`'s "a report is never edited after the fact"
govern the **committed reports** specifically - `observe-run-reports/`,
`otel-instrumentation-reports/`, and `decisions.md`. A benchmark is
living source, not a run record: git history, not file accumulation, is
its memory. Writing and updating is this skill's whole point, not an
exception to some other rule.

## What this skill owns

- **Persisting** the k6 script and manifest `k6-benchmark-expert` hands
  it, into `.odd/benchmarks/<name>/` - the directory name is the
  benchmark's identity.
- **Recall, two-step**: the target **service** returns the set of
  benchmarks that already exist for it (so the agent cannot duplicate
  one it never saw); the benchmark **name** identifies the single
  artifact an update rewrites. List every benchmark under
  `.odd/benchmarks/` and check each manifest's declared target service
  before the agent authors anything new.
- **Reviewed diffs, never silent overwrites.** When the agent proposes
  updating an existing benchmark, the change is presented as a diff
  against the stored version - the maintainer reviews it exactly like
  any other committed change, through the normal PR flow. This skill
  never overwrites a stored benchmark without that diff being visible.
- **Commit discipline**, inherited from the report-writing skills:
  - never commit on the default branch - create or switch to a work
    branch first;
  - stage and commit the benchmark's files **alone** (never bundled with
    unrelated changes);
  - commit subject: `docs(odd): benchmark <name>` for a new benchmark,
    `docs(odd): update benchmark <name>` for a diff-reviewed update;
  - state the stored path in the reply, so `show-benchmark` (a
    different skill) can point at it.
- **Refusing a literal credential.** Before persisting, scan the script
  for anything that looks like an inlined secret (the same discipline
  the report skills already apply to report bodies) - refuse and say why
  rather than committing it. `k6-guides`' `scripting.md` documents the
  correct alternative (`k6/secrets`, named environment variables) for
  the agent to use instead.

## What this skill does not own

- Any k6 knowledge - it persists whatever content the agent decided,
  unopinionated about whether the script or manifest is any good. That
  judgment belongs to `k6-benchmark-expert`, informed by `k6-guides`.
- The manifest's schema - this skill stores whatever shape the manifest
  has; it does not define that shape.
- Deleting a benchmark. A benchmark whose target service is gone is
  stale source, not something this skill garbage-collects - removing one
  is a human's PR, like removing any other dead source file.

## Lifecycle notes

- **Invisible to `/odd-status`.** `get-status` inventories the two
  report directories and the decisions ledger; benchmarks are not loop
  state and never appear there.
- `/odd-verify`'s verify-vs-re-measure boundary already ignores commits
  that touch only `.odd/` - authoring or updating a benchmark never
  counts as "a fix landed", by construction, with no special-casing
  needed here.
```

*The second lifecycle bullet above is superseded by #223 (2026-09-02):
`.odd/benchmarks/` now counts as changed code - see
`docs/guide/benchmarks.md`, "Verify".*

- [ ] **Step 3: Validate with `apm audit`**

Run:
```bash
cd /Users/usingsystem/Repos/github/oddyssey
uvx --from apm-cli==0.28.0 apm install --target claude && uvx --from apm-cli==0.28.0 apm audit
```

Expected: the new file scanned, "no issues found" for it.

- [ ] **Step 4: Clean up apm install artifacts**

Run: `git checkout -- .gitignore && git clean -fd .claude/agents .claude/commands .claude/skills`

- [ ] **Step 5: Commit**

```bash
git checkout -b feat/create-update-benchmark-skill
git add .apm/skills/create-update-benchmark/
git commit -m "$(cat <<'EOF'
feat(apm): add create-update-benchmark skill

Persists a k6-benchmark-expert-authored benchmark into
.odd/benchmarks/<name>/ - the same commit discipline as
create-otel-instrumentation-report, minus its immutability rule: a
benchmark is living source updated via reviewed diffs, not a report.

Part of #75.
EOF
)"
```

---

## Task 3: `show-benchmark` skill

**Files:**
- Create: `.apm/skills/show-benchmark/SKILL.md`

**Interfaces:**
- Consumes: whatever `create-update-benchmark` (Task 2) just persisted
  (stored path, benchmark name, what changed for an update) - read as
  plain text/tool-result, no code interface.
- Produces: skill name `show-benchmark`, referenced by name from Task 4
  (the agent's closing step) and Task 5 (the prompt's mission-close
  wording, mirroring `/odd-instrument-otel`'s).

- [ ] **Step 1: Read the skill this one mirrors**

Run: `cat /Users/usingsystem/Repos/github/oddyssey/.apm/skills/show-otel-instrumentation-report/SKILL.md`

Expected: confirms the "verdict/headline-first, stored path, never
re-dump the raw deliverable" shape this task's `SKILL.md` follows.

- [ ] **Step 2: Write `.apm/skills/show-benchmark/SKILL.md`**

```markdown
---
name: show-benchmark
description: Render a short synthesis of a persisted k6 benchmark for the human closing an /odd-instrument-bench mission - the stored path, what the benchmark exercises, the next recommended action - never a replacement for the script/manifest itself. Use when an /odd-instrument-bench mission ends and the final answer must synthesize what create-update-benchmark just stored instead of dumping it raw.
---

# Show a Benchmark

Every authoring mission in this repo closes with a `show-*` synthesis
instead of dumping its stored deliverable into the conversation
(`show-otel-instrumentation-report`, `show-observe-run-report`) -
authoring a k6 benchmark is no exception.

## What to render

- **Stored path** - where `create-update-benchmark` wrote the script and
  manifest (`.odd/benchmarks/<name>/`).
- **What it exercises** - target service, the endpoints/operations in
  scope, the test type (smoke/load/stress/soak/spike/breakpoint).
- **Next recommended action** - how to actually run it, e.g.
  `/odd-observe check checkout under benchmark checkout-read-heavy` (the
  exact composition with `/odd-observe`'s `benchmark:` field is out of
  scope for this authoring implementation - phrase the next action
  generically until execution is built, never invent a syntax that
  doesn't exist yet).
- **For an update**: a short headline of what changed against the
  previous version - the full diff already lives in the commit, this is
  the human-readable one-liner, not a diff dump.

## What never to render

- The script or manifest's full content - the stored files are the
  deliverable, this skill is a pointer to them, never a replacement.
  Same separation `show-otel-instrumentation-report` keeps from the
  report it summarizes.

## What this skill reads

Only what `create-update-benchmark` just wrote and returned - no k6
knowledge, no independent investigation of the service. If the stored
path or benchmark name is missing from what it's handed, that is an
upstream contract failure to surface, not something to guess at.
```

- [ ] **Step 3: Validate with `apm audit`**

Run:
```bash
cd /Users/usingsystem/Repos/github/oddyssey
uvx --from apm-cli==0.28.0 apm install --target claude && uvx --from apm-cli==0.28.0 apm audit
```

- [ ] **Step 4: Clean up apm install artifacts**

Run: `git checkout -- .gitignore && git clean -fd .claude/agents .claude/commands .claude/skills`

- [ ] **Step 5: Commit**

```bash
git checkout -b feat/show-benchmark-skill
git add .apm/skills/show-benchmark/
git commit -m "$(cat <<'EOF'
feat(apm): add show-benchmark skill

Closes an /odd-instrument-bench mission with a one-screen synthesis of
what create-update-benchmark stored - the same role
show-otel-instrumentation-report plays for otel-instrumentation-expert.

Part of #75.
EOF
)"
```

---

## Task 4: `k6-benchmark-expert` agent

**Files:**
- Create: `.apm/agents/k6-benchmark-expert.agent.md`

**Interfaces:**
- Consumes: a **mission block** from `/odd-instrument-bench` (Task 5) -
  already resolved for every `authoring-inputs.md` "human"-classified
  dimension (test type, thresholds, new-vs-update, target base URL) and
  agent-proposed-then-confirmed dimensions (load shape, duration); reads
  `k6-guides` (Task 1) by name for k6 usage; reads
  `create-update-benchmark` (Task 2) by name to persist; reads
  `show-benchmark` (Task 3) by name to close.
- Produces: agent name `k6-benchmark-expert`, referenced by name from
  Task 5 (the prompt's dispatch target) and Task 8 (README primitives
  table, `dependencies.md`).

- [ ] **Step 1: Read the agent this one mirrors, end to end**

Run: `cat /Users/usingsystem/Repos/github/oddyssey/.apm/agents/otel-instrumentation-expert.agent.md`

Expected: confirms the frontmatter shape (`name`, `description`, no
`tools:` restriction per #195's resolution - self-delegation is
forbidden by an explicit prompt-body instruction instead, see Step 2),
the investigation-numbered-steps structure, and the "never invoke
Agent/Task/Workflow yourself" instruction added by #195 - this new
agent needs the identical instruction, not a paraphrase.

- [ ] **Step 2: Write `.apm/agents/k6-benchmark-expert.agent.md`**

```markdown
---
name: k6-benchmark-expert
description: Investigate a service and author a k6 load-test benchmark (script + manifest) as reviewed, committed code - never executing it. Input - the service to benchmark, and every authoring-inputs.md "human"-decided value already resolved by /odd-instrument-bench (test type, thresholds, new-vs-update, target base URL) plus agent-proposed values the caller confirmed (load shape, duration). Persists through create-update-benchmark, closes with show-benchmark. Read-only against the service under test in the sense that it only investigates - it never runs the benchmark itself.
---

# k6 Benchmark Expert

You are a k6 domain expert - install, scripting, checks, thresholds,
scenarios, test types, protocols hold no secrets for you, the same way
`otel-instrumentation-expert` is the OpenTelemetry expert. Your job:
investigate the target service and author a well-formed k6 benchmark -
a script plus a small manifest - as reviewed, committed code. You never
run what you write; authoring and execution stay separate, the same
separation `otel-instrumentation-expert` keeps between planning
instrumentation and implementing it.

**Do the investigation and authoring work yourself.** Every step below
is your own tool call (`Read`/`Grep`/`Bash`, doc fetches via `k6-guides`,
skill calls to `create-update-benchmark`/`show-benchmark`) - never call
the `Agent`, `Task`, or `Workflow` tool (or any equivalent
delegation/subagent tool your runtime exposes) to delegate any part of
the mission, including to another instance of yourself. A mission you
cannot complete directly is a stop-and-report, never a delegation.

## Mission

Input: a **mission block** from `/odd-instrument-bench`, already
resolved for what `k6-guides`' `authoring-inputs.md` classifies as
human-decided:

- **Target service** - the service to benchmark.
- **New benchmark, or an update to a named existing one** - resolved by
  the prompt before you were dispatched; if this mission says "update
  `<name>`", the benchmark named `<name>` must already exist under
  `.odd/benchmarks/` (verify via `create-update-benchmark`'s recall - if
  it doesn't exist, stop and report rather than silently authoring a new
  one under that name).
- **Test type** - smoke / load / stress / soak / spike / breakpoint
  (`k6-guides`' `test-types.md`).
- **Thresholds** - the pass/fail targets the caller named.
- **Target base URL / environment** - where the benchmark points.
- **Load shape and duration** - proposed by the prompt, confirmed by the
  caller; refine within that confirmed envelope, never outside it
  without asking again.

## Investigation

1. **Recall what already exists for this service.** Call
   `create-update-benchmark`'s recall - every benchmark already stored
   for the target service, not just a name match. If the mission's
   target genuinely overlaps with an existing benchmark's scope, either
   extend that one (as an update) or state explicitly why the new one is
   distinct rather than a near-duplicate under a second name.
2. **Discover the service's endpoints and hot operations.** The
   service's own contract (OpenAPI/Swagger, a route table, a CLI entry
   point - read-only), and existing `.odd/observe-run-reports/` for this
   service naming known hot operations. Prefer a handful of
   representative operations covered properly over every endpoint
   covered once - the same preference `run-scenario` states for
   functional scenarios.
3. **Decide the script and manifest content**, informed by `k6-guides`:
   - `scripting.md` for requests/checks/thresholds/scenarios/secrets -
     never invent k6 syntax from memory, fetch and confirm;
   - `test-types.md` to shape the load profile around the confirmed test
     type;
   - the manifest schema is your own design (not fixed by this repo's
     source docs) - at minimum it names the target service, the engine
     (`k6`, so another can be introduced later without changing the
     contract), the profile stages with their boundaries recorded (so a
     later query can exclude warmup from steady-state numbers - see
     `scripting.md`'s note on this), the thresholds, and whatever you
     decide about storing the target base URL (a manifest field, or
     mission-time only - either is compatible with "remote authorization
     is mission-time only", which is a separate, already-settled rule
     about *who authorizes*, not about *where the URL lives*).
   - never inline a credential in the script - `k6-guides`' `secrets`
     guidance names the alternative (`k6/secrets`, or a named environment
     variable the manifest never stores a value for).
4. **Persist through `create-update-benchmark`.** Hand it the decided
   script and manifest; it owns the file layout, the commit, and the
   diff-review presentation for an update. You decide content, it
   writes.
5. **Close with `show-benchmark`.** Never re-dump the script or manifest
   in your final answer - the stored path and the synthesis are the
   deliverable a human reads.

## Rules

- **Never execute the benchmark.** No `k6 run`, not even to sanity-check
  the script. If you need to confirm k6 syntax, confirm it against
  `k6-guides`' fetched docs, not by running anything.
- **Every k6 claim is sourced from a fetched `k6-guides` reference**,
  never from memory - the same discipline `otel-instrumentation-expert`
  applies to OpenTelemetry claims.
- **A dimension `authoring-inputs.md` classifies as human-decided is
  never guessed.** If the mission is missing one (the prompt should have
  asked, but didn't), stop and report what's missing rather than
  inventing a value.
```

- [ ] **Step 3: Validate with `apm audit`**

Run:
```bash
cd /Users/usingsystem/Repos/github/oddyssey
uvx --from apm-cli==0.28.0 apm install --target claude && uvx --from apm-cli==0.28.0 apm audit
```

- [ ] **Step 4: Clean up apm install artifacts**

Run: `git checkout -- .gitignore && git clean -fd .claude/agents .claude/commands .claude/skills`

- [ ] **Step 5: Commit**

```bash
git checkout -b feat/k6-benchmark-expert-agent
git add .apm/agents/k6-benchmark-expert.agent.md
git commit -m "$(cat <<'EOF'
feat(apm): add k6-benchmark-expert agent

Investigates a service and authors a k6 benchmark (script + manifest)
as reviewed, committed code, through create-update-benchmark - never
executes it. The same split otel-instrumentation-expert keeps between
planning and implementing. Forbids self-delegation explicitly, per
#195's resolution for this exact class of agent.

Part of #75.
EOF
)"
```

---

## Task 5: `/odd-instrument-bench` prompt

**Files:**
- Create: `.apm/prompts/odd-instrument-bench.prompt.md`

**Interfaces:**
- Consumes: free-form mission arguments from the caller; `k6-guides`'
  `authoring-inputs.md` by name (Task 1) for which questions to ask.
- Produces: a mission block dispatched to `k6-benchmark-expert` (Task 4)
  by name.

- [ ] **Step 1: Read the prompt this one mirrors**

Run: `cat /Users/usingsystem/Repos/github/oddyssey/.apm/prompts/odd-instrument-otel.prompt.md`

Expected: confirms the thin-dispatcher shape (frontmatter
`description:` only, `$ARGUMENTS`, "Expected fields", "Invoke the
`<agent>` agent", "Close the mission with the `<show-skill>` skill").
This new prompt adds the interactive-Q&A step this one doesn't have -
see also `.apm/prompts/odd-observe.prompt.md` for the precedent (its
"preflight... before any dispatch" framing).

- [ ] **Step 2: Write `.apm/prompts/odd-instrument-bench.prompt.md`**

```markdown
---
description: Investigate a service and author a k6 load-test benchmark plan as code in .odd/benchmarks/ - asks back whatever only a human can decide before dispatching the authoring agent, never executes the benchmark
---

Before dispatching anything: consult the `k6-guides` skill's
`authoring-inputs.md` reference for which dimensions of this benchmark
only a human can decide, and which the agent can discover on its own.
Ask the caller, **in this conversation, before any dispatch** - the
steps needing the caller cannot happen inside a subagent, the same
principle `/odd-observe`'s own preflight states outright. Specifically:

- **New benchmark, or an update to a named existing one** - if
  ambiguous, list what already exists for the named service (via
  `create-update-benchmark`'s recall) and ask.
- **Test type** - smoke / load / stress / soak / spike / breakpoint
  (`k6-guides`' `test-types.md` names what each answers).
- **Thresholds** - the pass/fail targets that matter.
- **Target base URL / environment** - never guessed by probing.
- **Load shape and duration** - propose a value informed by the test
  type and the service's known scale, then confirm it with the caller
  rather than silently deciding.

Never ask about anything `authoring-inputs.md` classifies as
agent-discoverable (target scope/endpoints) - that's the agent's job,
asking about it here would be litigating something the caller cannot
actually answer better than the codebase can.

Once every human-decided value is resolved, invoke the
`k6-benchmark-expert` agent. It owns the investigation method and the
authoring - this prompt only hands it a well-formed mission.

Build the mission from the arguments and the Q&A above:

- Arguments: $ARGUMENTS
- Expected fields (any order, free-form): the **service** to benchmark
  (required), **new or update** (default: ask if ambiguous, per above),
  **test type**, **thresholds**, **target base URL**, and optionally a
  **load shape/duration** the caller already has in mind (otherwise
  propose one during the Q&A above).

Close the mission with the `show-benchmark` skill: render its synthesis
of the stored benchmark as the final answer, stating the stored path.
The script and manifest - not the synthesis - are the input any future
run of this benchmark will use: never re-dump them in the conversation,
and never let the synthesis replace the stored files as that input.
```

- [ ] **Step 3: Validate with `apm audit`**

Run:
```bash
cd /Users/usingsystem/Repos/github/oddyssey
uvx --from apm-cli==0.28.0 apm install --target claude && uvx --from apm-cli==0.28.0 apm audit
```

Expected: also confirm the materialized `.claude/commands/odd-instrument-bench.md`
exists after this `apm install` run, before cleanup - proof the prompt
name resolves to the expected slash command.

- [ ] **Step 4: Clean up apm install artifacts**

Run: `git checkout -- .gitignore && git clean -fd .claude/agents .claude/commands .claude/skills`

- [ ] **Step 5: Commit**

```bash
git checkout -b feat/odd-instrument-bench-prompt
git add .apm/prompts/odd-instrument-bench.prompt.md
git commit -m "$(cat <<'EOF'
feat(apm): add /odd-instrument-bench prompt

Entry point for k6-benchmark-expert - asks the caller back for
whatever authoring-inputs.md classifies as human-decided, in the main
conversation before any dispatch (the /odd-observe preflight
precedent), then builds and hands off the mission.

Closes #75 (authoring half - execution/verification through
/odd-observe and /odd-verify is a separate, deferred piece per the
design spec).
EOF
)"
```

---

## Task 6: Scope the `.odd/` append-only rule

**Files:**
- Modify: `AGENTS.md` (the "The `.odd/` memory is append-only" section)
- Modify: `docs/guide/reports.md` (wherever it states "a report is never
  edited after the fact")

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the textual exception `create-update-benchmark` (Task 2)
  already depends on - without this task, Task 2's own `SKILL.md`
  contradicts the still-unamended `AGENTS.md`.

**This task can run before or after Tasks 1-5** - it has no code
dependency on them, but land it in the **same PR** as Task 2 at the
latest: `create-update-benchmark`'s first real use would otherwise be a
documented rule violation.

- [ ] **Step 1: Find the exact current wording**

Run: `grep -n "append-only" /Users/usingsystem/Repos/github/oddyssey/AGENTS.md`

Expected: locates the "The `.odd/` memory is append-only" section
heading and its body - read the full section before editing, don't
guess at the surrounding sentences.

- [ ] **Step 2: Amend `AGENTS.md`'s append-only section**

Add a sentence naming the scope explicitly and the exception, e.g.
(adapt to the exact existing wording found in Step 1, don't just paste
this verbatim over it):

```markdown
This applies to `observe-run-reports/`, `otel-instrumentation-reports/`,
and `decisions.md` - the ODD loop's memory. `.odd/benchmarks/` is a
different kind of content: living source, not a run record, updated in
place via reviewed diffs like any other committed code (see
`create-update-benchmark`).
```

- [ ] **Step 3: Find and amend `docs/guide/reports.md`'s immutability line**

Run: `grep -n "never edited after the fact\|One run, one file" /Users/usingsystem/Repos/github/oddyssey/docs/guide/reports.md`

Then add an equivalent scoping note near that line - `docs/guide/reports.md`
documents report formats specifically, so state plainly that
`.odd/benchmarks/` is out of this guide's scope and point to
`docs/guide/benchmarks.md` (Task 7) instead.

- [ ] **Step 4: Verify no other file states the append-only rule without this scoping**

Run: `grep -rln "append-only\|never edited after the fact" /Users/usingsystem/Repos/github/oddyssey --include="*.md" | grep -v "^.*/marketplace/\|^.*/docs/superpowers/"`

Expected: only `AGENTS.md` and `docs/guide/reports.md` - if another live
source states the same rule, amend it too before committing.

- [ ] **Step 5: Commit**

```bash
git checkout -b docs/scope-odd-append-only-rule
git add AGENTS.md docs/guide/reports.md
git commit -m "$(cat <<'EOF'
docs(agents): scope the .odd/ append-only rule to the report stores

.odd/benchmarks/ (added by #75) is living source updated via reviewed
diffs, not a run record - the append-only rule never applied to it and
this states so explicitly, rather than leaving create-update-benchmark
contradicting AGENTS.md on its first real use.
EOF
)"
```

---

## Task 7: `docs/guide/benchmarks.md` (Author section) + its `AGENTS.md` sync rule

**Files:**
- Create: `docs/guide/benchmarks.md`
- Modify: `AGENTS.md` (new "Keep the benchmarks guide in sync" section)

**Interfaces:**
- Consumes: the finished shape of Tasks 1-5 (this guide documents what
  they produce - write this task last among the doc tasks, after Tasks
  1-6 are done, so nothing here describes an interface that changed
  mid-plan).
- Produces: nothing consumed elsewhere in this plan - a leaf task.

- [ ] **Step 1: Read `docs/guide/backends.md` for the sync-rule precedent**

Run: `grep -n "^## Keep the backends guide in sync" -A 15 /Users/usingsystem/Repos/github/oddyssey/AGENTS.md`

Expected: the exact section this task's new rule mirrors in placement
and style (added in #194).

- [ ] **Step 2: Write `docs/guide/benchmarks.md` - Author section only**

Execution/verification sections are explicitly deferred (see the spec) -
this file ships with only what's actually implementable from this plan:

```markdown
# Benchmark authoring, running, and verifying

A k6 load-test benchmark, authored once as reviewed code and replayed
identically for as long as it stays useful. This guide walks the full
lifecycle in order: author, run, verify.

**Status: authoring only, for now.** Running a stored benchmark through
`/odd-observe` and verifying one through `/odd-verify` are specified
(see the design spec linked below) but not yet implemented - this page
covers what exists today and will grow the Run/Verify sections once
that lands.

## Author

`/odd-instrument-bench` investigates a service and writes a k6 benchmark
- a script plus a manifest - into `.odd/benchmarks/<name>/`, through the
`k6-benchmark-expert` agent. It never runs what it writes.

```text
/odd-instrument-bench author a load benchmark for checkout, stress test, p95 under 300ms
```

Before dispatching the agent, the prompt asks back whatever only a
human can decide - test type, thresholds, new benchmark or an update to
an existing one, the target environment - and proposes a load
shape/duration for you to confirm. Everything else (which endpoints,
what the service already looks like from past `.odd/` reports) the
agent discovers on its own. The full breakdown of what's asked versus
discovered is in the `k6-guides` skill's `authoring-inputs.md`
reference.

The mission closes with a short synthesis of the stored benchmark (the
`show-benchmark` skill) - the stored path, what it exercises, and the
next step. The script and manifest themselves are never dumped into the
conversation; the stored files under `.odd/benchmarks/<name>/` are the
deliverable.

Updating an existing benchmark, when a service's endpoints have
drifted, follows the same prompt - the agent proposes the change as a
reviewed diff against the stored version, never a silent replacement.

Unlike this project's committed reports, a benchmark is **not**
append-only: it's living source, updated in place and reviewed like any
other code change (see `create-update-benchmark`). See
`docs/guide/reports.md` for how that differs from the report stores'
own immutability rule.

## Run

*Not yet implemented.* The design (see the spec below) is a `benchmark:
<name>` field on `/odd-observe`'s existing `drive`/`observe` modes -
`drive` runs the stored plan itself, `observe` watches someone else run
it while still citing the plan by name and revision.

## Verify

*Not yet implemented.* The design replays the benchmark at the git
revision an observation recorded it at, ruling on the manifest's
declared thresholds against telemetry (metrics, traces, logs) - never
k6's own pass/fail summary.

## Full design

The complete design, including what's deferred and why, is in
[the design spec](../superpowers/specs/2026-08-31-k6-benchmark-authoring-design.md)
and its tracking issue,
[#75](https://github.com/using-system/oddyssey/issues/75).
```

- [ ] **Step 3: Add the `AGENTS.md` sync rule**

Insert a new section, same placement pattern as the other four (near
"Keep the backends guide in sync", "Keep the reports guide in sync",
etc.):

```markdown
## Keep the benchmarks guide in sync

`docs/guide/benchmarks.md` documents the benchmark lifecycle -
authoring today, running and verifying once those land. Update it in
the same change whenever `/odd-instrument-bench`, `k6-benchmark-expert`,
`create-update-benchmark`, or `show-benchmark`'s contract changes, and
expand its Run/Verify sections in the same change that implements
`/odd-observe`'s `benchmark:` field or `/odd-verify`'s benchmark replay
- the guide must never describe a contract that doesn't exist yet, or
lag one that does.
```

- [ ] **Step 4: Verify the spec link resolves**

Run: `test -f /Users/usingsystem/Repos/github/oddyssey/docs/superpowers/specs/2026-08-31-k6-benchmark-authoring-design.md && echo "OK"`

Expected: `OK` - the relative link from `docs/guide/benchmarks.md` must
point at a file that actually exists.

- [ ] **Step 5: Commit**

```bash
git checkout -b docs/benchmarks-guide
git add docs/guide/benchmarks.md AGENTS.md
git commit -m "$(cat <<'EOF'
docs(guide): add the benchmarks guide (authoring section)

New docs/guide/benchmarks.md walks the benchmark lifecycle - today
that's authoring only, Run/Verify sections are stubbed as "not yet
implemented" pending the execution design pass (see #75's spec). Adds
the matching AGENTS.md sync rule, same placement as the other four
guides.
EOF
)"
```

---

## Task 8: Wire up the routine doc-sync updates

**Files:**
- Modify: `docs/guide/prompts.md`
- Modify: `docs/guide/dependencies.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the finished shape of Tasks 1-5 (same ordering note as
  Task 7 - do this last).
- Produces: nothing consumed elsewhere in this plan - a leaf task.

- [ ] **Step 1: Add `/odd-instrument-bench` to `docs/guide/prompts.md`**

Mirror the existing `## /odd-instrument-otel` section's shape exactly
(read it first: `sed -n '/^## \/odd-instrument-otel/,/^## /p' /Users/usingsystem/Repos/github/oddyssey/docs/guide/prompts.md`)
- a short intro paragraph, a fenced `text` block of 3-5 example prompts,
  then a bullet list mapping sentence fragments to mission fields
  (service, new-vs-update, test type, thresholds).

- [ ] **Step 2: Add the `/odd-instrument-bench` diagram to `docs/guide/dependencies.md`**

Mirror the existing `/odd-instrument-otel` mermaid diagram (prompt →
agent → skills, with the skill nodes `k6-guides` / `create-update-benchmark`
/ `show-benchmark`). Also correct the file's bird's-eye counts: 5
prompts → 6, 2 agents → 3, 12 skills → 15 (find them with
`grep -n "prompts\]\|agents\]\|skills\]" docs/guide/dependencies.md` or
similar - the exact phrasing may differ, read the file to find the real
count sentence before editing it).

- [ ] **Step 3: Update `README.md`**

- Primitives table: add rows for `/odd-instrument-bench` (prompt),
  `k6-benchmark-expert` (agent), `k6-guides` / `create-update-benchmark`
  / `show-benchmark` (skills) - same row format as the existing
  `/odd-instrument-otel` family's rows.
- **"Miscellaneous prompts" - `#### /odd-instrument-bench`, right after
  `/odd-status`** (per the spec's Documentation section): a fenced
  example-prompts block, a short paragraph, closing with a pointer to
  `docs/guide/benchmarks.md`.
- **Prerequisites section**: add k6, next to Docker and gcx - "needed to
  run an authored benchmark" (not to author one - authoring never
  executes k6, only a future execution implementation will actually
  need the binary present; phrase this precisely so the Prerequisites
  entry doesn't overclaim what this plan's software needs).

- [ ] **Step 4: Cross-check every new link resolves**

Run:
```bash
grep -o '\[.*\](\.\./[^)]*\.md[^)]*)\|\[.*\](docs/[^)]*\.md)' /Users/usingsystem/Repos/github/oddyssey/README.md | grep -i "benchmark\|instrument-bench"
```

Expected: at least one link to `docs/guide/benchmarks.md` - verify the
path resolves (`test -f docs/guide/benchmarks.md`).

- [ ] **Step 5: Commit**

```bash
git checkout -b docs/wire-up-odd-instrument-bench
git add docs/guide/prompts.md docs/guide/dependencies.md README.md
git commit -m "$(cat <<'EOF'
docs(guide): wire up /odd-instrument-bench across prompts, dependency map, README

Routine per-primitive sync required by AGENTS.md's existing rules:
prompts.md catalog entry, dependencies.md diagram and corrected
bird's-eye counts, README primitives table + Miscellaneous prompts
subsection + Prerequisites.
EOF
)"
```

---

## Task 9: Package registration + final full validation

**Files:**
- Modify: `apm.yml`

**Interfaces:**
- Consumes: the finished shape of every prior task.
- Produces: the shippable package - this is the task after which
  `apm install` on a machine with none of this actually deploys the new
  prompt/agent/skills.

- [ ] **Step 1: Check how existing primitives are registered**

Run: `cat /Users/usingsystem/Repos/github/oddyssey/apm.yml`

Expected: confirms whether `apm.yml` enumerates prompts/agents/skills
explicitly by path/glob, or auto-discovers everything under `.apm/`
(the AWS/cloudwatch work earlier in this project found no explicit
prompt-file references in `apm.yml` - if that's still true, this task
may be a no-op beyond a version bump or changelog note; verify, don't
assume).

- [ ] **Step 2: Add explicit registration if `apm.yml` requires it**

Only if Step 1 shows explicit enumeration - add the five new primitives
following whatever pattern the existing ones use.

- [ ] **Step 3: Full-repo `apm install` + `apm audit`, from a clean tree**

Run:
```bash
cd /Users/usingsystem/Repos/github/oddyssey
git status --porcelain
uvx --from apm-cli==0.28.0 apm install --target claude
uvx --from apm-cli==0.28.0 apm audit
```

Expected: "no issues found" across every scanned file, including all
five new primitives together for the first time (prior tasks validated
them individually - this is the first check that they're consistent
with each other, not just each internally clean).

- [ ] **Step 4: Confirm every new slash command and agent materialize**

Run:
```bash
ls .claude/commands/ | grep instrument-bench
ls .claude/agents/ | grep k6-benchmark
ls .claude/skills/ | grep -E "k6-guides|create-update-benchmark|show-benchmark"
```

Expected: `.claude/commands/odd-instrument-bench.md`,
`.claude/agents/k6-benchmark-expert.md` (or `.agent.md`, whatever this
`apm-cli` version names it - match what Task 4/5's own validation steps
already observed), and three skill directories all present.

- [ ] **Step 5: Clean up**

Run: `git checkout -- .gitignore && git clean -fd .claude/agents .claude/commands .claude/skills`

- [ ] **Step 6: Commit (if `apm.yml` changed) or note no-op**

```bash
git checkout -b chore/register-k6-benchmark-package
git add apm.yml
git commit -m "$(cat <<'EOF'
chore(apm): register the k6 benchmark authoring primitives

/odd-instrument-bench, k6-benchmark-expert, k6-guides,
create-update-benchmark, show-benchmark - the last piece of #75's
authoring half.
EOF
)"
```

If Step 1 found no explicit enumeration needed, skip the commit - say
so instead of committing an empty diff.

---

## Final self-review (done before handing this plan off)

**Spec coverage** — every "Authoring" acceptance criterion (spec items
1-9) maps to a task: 1→Task 5, 2→Tasks 4+5, 3→Task 2, 4→Task 4 Step 2 §1
(recall), 5→Task 4 Step 2 §3 (reviewed diff), 6→Task 2 (secrets refusal)
+ Task 1 (scripting.md's secrets section), 7→Task 1, 8→Task 1 Step 10
(authoring-inputs.md), 9→Tasks 3+4+5 (closing skill). "Package and
documentation" items 21, 22, 23, 24, 25, 26, 27, 28 map to Tasks 6, 8,
8, 7, 7, 8, 8, 9 respectively. Execution/verification items (10-20) are
out of scope by design — not tasked, per the spec's own boundary.

**Placeholder scan** — no "TBD"/"TODO" in any task's file content; every
reference file in Task 1 carries real, live-verified facts (exit codes,
env var defaults, label values) rather than generic descriptions; the
one deliberately-unfinished piece (`docs/guide/benchmarks.md`'s
Run/Verify sections) is explicit about being unfinished and why, which
is different from a placeholder — it documents real current state.

**Type/name consistency** — `k6-benchmark-expert` (agent name),
`k6-guides` / `create-update-benchmark` / `show-benchmark` (skill names),
`/odd-instrument-bench` (prompt) are spelled identically across every
task that references them by name (grep the plan for each name to
confirm before executing, since a typo'd cross-reference is exactly the
class of bug this check exists to catch).
