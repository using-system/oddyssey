# Stack/Environment Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the observation-report frontmatter `environment` field to `stack`, add a new `environment` field detected from the observed service's `deployment.environment.name` resource attribute, and align every prose contract with the one-vocabulary rule.

**Architecture:** Prose contracts only — no Python (the MCP config already says `stack`). The core contract lands first in `create-observe-run-report`, then the observation pipeline (agent + observe prompt), the verify/status prompts, the instrumentation side (`target` → `stack`), and finally the vocabulary sweep + migration of this repo's four stored reports.

**Tech Stack:** APM markdown contracts under `.apm/`, stored reports under `.odd/observe-run-reports/`, README.

**Spec:** `docs/superpowers/specs/2026-08-26-stack-environment-rename-design.md` (authored from GitHub issue #94, fully decided). The spec wins over this plan on conflict.

## Global Constraints

- All committed text English; Conventional Commits; NO breaking markers (`!`) anywhere — this ships as `fix`.
- `marketplace/` is generated — never edit it.
- House prose style: terse contract prose, em dashes as the surrounding files use, ~72-column wrap.
- One vocabulary: `stack` = which backend (`local | grafana | azure-monitor | cloudwatch | datadog | dynatrace | splunk`); `environment` = the deployment environment the service's telemetry reports (`deployment.environment.name`), `local` forced on the local stack, `unknown` when the attribute is absent.
- **Exemptions from the rename (never touch):** backend-native product terms (Dynatrace's "environment" is its tenant term — all dynatrace reference files), environment *variables* (`env`, container environment, `OTEL_*`), the `otel-guides` references (official OTel docs vocabulary), and `deployment.environment.name` itself.
- Detection sequence (issue-decided, restated wherever a contract needs it): pre-run bounded discovery probe on recent telemetry; when empty (fresh reset/first run), the value is provisional until the first scenario telemetry lands; the `observe-run` agent is the actor of detection and of the verify hard stop.
- No tolerance layer in any contract; this repo's four stored reports are migrated in Task 5.

---

### Task 1: core contract — `create-observe-run-report/SKILL.md`

**Files:**
- Modify: `.apm/skills/create-observe-run-report/SKILL.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the frontmatter contract every later task's prose references: `stack:` (old `environment` values, same comment), `environment:` (detected), and the recall matching rule (services ∩ + same `stack` + same `environment`).

- [ ] **Step 1: Rename the field in the frontmatter example.** `environment: local            # local | the remote backend name (grafana, datadog, ...)` becomes `stack: local                  # local | the remote backend name (grafana, datadog, ...)`, and directly below it add `environment: local            # detected: deployment.environment.name reported by the service's telemetry (local forced on the local stack; unknown when absent)`. Keep column alignment with the sibling lines.
- [ ] **Step 2: Add the environment contract bullet** after the frontmatter bullet list's `window` bullet (before the verification bullet): `environment` is **detected**, never asked: the `deployment.environment.name` resource attribute the service's telemetry reports — pre-run probe on recent telemetry, provisional until the first scenario telemetry lands when the pre-run window is empty. On `stack: local` the value is `local` by construction — a service emitting a different attribute still records `local`, with the discrepancy stated as a finding (misconfigured resource attributes). `unknown` when the service emits no attribute — stated, never guessed, and the absence is a telemetry gap. One observation, one environment: services detecting different values stop the run — observe them as separate missions.
- [ ] **Step 3: Update every other `environment` mention in the file** to the new split: the recall matching step 2 ("its `environment` is the mission's") becomes: a report matches when its `services` intersect the mission's, its `stack` is the mission's, and its `environment` is the one the run detects — an `unknown` environment matches only another `unknown`, and with a warning (the comparison may span environments without the reports being able to say so). The verification frontmatter bullet's example and any remaining `environment`-as-backend phrasing follow the rename.
- [ ] **Step 4: Verify** — `grep -n "environment" .apm/skills/create-observe-run-report/SKILL.md` shows only detected-environment or env-var senses; `grep -n "stack:" …` shows the renamed example line.
- [ ] **Step 5: Commit** — `fix(skill): report frontmatter records stack and the detected environment` with a body explaining the conflation being fixed, trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 2: observation pipeline — `observe-run.agent.md` + `odd-observe.prompt.md`

**Files:**
- Modify: `.apm/agents/observe-run.agent.md`
- Modify: `.apm/prompts/odd-observe.prompt.md`

**Interfaces:**
- Consumes: Task 1's frontmatter contract (`stack` + detected `environment`).
- Produces: the mission vocabulary (**Stack** input replaces **Environment**) and the detection procedure later prompts reference.

- [ ] **Step 1: Agent — rename the mission input.** The `- **Environment** —` mission bullet becomes `- **Stack** —` with the same local/remote/default content ("Default when the mission is silent: the **configured stack**" stays). Sweep the agent's other environment-as-backend phrasings (description line's "in any environment", "local environments", "the environment's CLI", "Local environment." setup heading, "remote backends") to stack/backend wording — the deployment-environment sense and env-var sense stay untouched.
- [ ] **Step 2: Agent — add the detection step.** In Setup, extend step 3 (preflight) or add a step 3bis: detect the deployment environment — a bounded discovery query for the service's `deployment.environment.name` on recent telemetry, BEFORE any reset or scenario; on `stack: local` record `local` (an emitting-different service is a finding, not a different environment); empty pre-run telemetry = provisional until the first scenario telemetry lands; no attribute = `unknown` + a Telemetry gaps line. Services detecting different values: stop and report the split — one observation, one environment. Record the detected value in section 1 and in the persisted frontmatter (Task 1's contract).
- [ ] **Step 3: Agent — baseline comparison.** In the Investigation "Baseline" bullet and Setup step 4 (recall), the matching now includes the detected environment (Task 1's rule); when the mission carries a baseline environment to compare against (verify missions — Task 3), a divergence is the hard stop the mission block mandates.
- [ ] **Step 4: Prompt — vocabulary.** In `odd-observe.prompt.md`, the expected mission field `environment (defaults to the configured stack - the preflight resolved it)` becomes `stack (defaults to the configured one - the preflight resolved it)`; the preflight's step 1 "Resolve the target stack" already says stack — leave it.
- [ ] **Step 5: Verify** — `grep -n "environment" both files`: remaining hits are only deployment-environment, env-var, or exempted senses.
- [ ] **Step 6: Commit** — `fix(agent): observe-run takes a stack and detects the environment` + trailer.

---

### Task 3: verify + status prompts — `odd-verify.prompt.md` + `odd-status.prompt.md`

**Files:**
- Modify: `.apm/prompts/odd-verify.prompt.md`
- Modify: `.apm/prompts/odd-status.prompt.md`

**Interfaces:**
- Consumes: Task 1's contract; Task 2's detection procedure and mission vocabulary.
- Produces: nothing downstream.

- [ ] **Step 1: Verify prompt — preflight.** `the report's `environment` (`target` for an instrumentation report) is the contract being replayed` becomes `the report's `stack` is the contract being replayed` (both report kinds now name it `stack` — Task 4 renames the instrumentation side). Update the surrounding "backend" sentences only where they said environment-as-backend.
- [ ] **Step 2: Verify prompt — mission block.** The bullet `services and environment come from its frontmatter` becomes stack-based; add to the mission block: hand the agent the baseline's `environment` — the agent (the actor of detection) compares the environment its own run detects against it and **stops hard on divergence**: no cross-environment verdict, name both values, recommend rerunning against the baseline's environment or observing the detected one as a new baseline. When the baseline is an instrumentation report (no environment by design), the check is skipped and the detected environment is recorded fresh.
- [ ] **Step 3: Status prompt.** In `odd-status.prompt.md`: argument scoping "service name(s) and/or an environment to restrict the status to" becomes "service name(s), a stack, and/or a deployment environment"; step 2's per-service columns "(date, environment, mode, ...)" list `stack` and `environment` distinctly; step 4's comparability "same service, environment and `workload`" becomes "same service, stack, environment and `workload`".
- [ ] **Step 4: Verify** — grep both files for `environment`/`target`: only the new senses remain.
- [ ] **Step 5: Commit** — `fix(prompts): odd-verify replays the stack and stops on environment divergence; odd-status filters both` + trailer.

---

### Task 4: instrumentation side — `create-otel-instrumentation-report/SKILL.md`, `otel-instrumentation-expert.agent.md`, `odd-instrument.prompt.md`

**Files:**
- Modify: `.apm/skills/create-otel-instrumentation-report/SKILL.md`
- Modify: `.apm/agents/otel-instrumentation-expert.agent.md`
- Modify: `.apm/prompts/odd-instrument.prompt.md`

**Interfaces:**
- Consumes: the one-vocabulary rule.
- Produces: instrumentation frontmatter `stack:` replacing `target:` (values unchanged: `local | the remote backend name`); NO `environment` field on instrumentation reports.

- [ ] **Step 1: Skill.** Frontmatter example `target: local                 # local | the remote backend name (grafana, datadog, ...)` → `stack: local …` (same comment); the prose bullet "`target` the export target the recommendations were derived for" → "`stack` the export stack the recommendations were derived for"; recall matching "its `target` is compatible" → "its `stack` is compatible". No environment field is added.
- [ ] **Step 2: Agent.** The "export target" prose names the stack: description ("if known, the export target" → "the export stack"), the Input paragraph ("intended **export target**" → "intended **export stack**", "remote environments may use a different backend" → "a remote stack uses its backend's endpoint"), section 5's "start the export target — `odd_stack_up` for the local stack; for a remote target, name the backend and the preflight it needs" → "start the export stack — `odd_stack_up` for the local one; for a remote stack, name the backend and the preflight it needs", and the auth rule "When the export target needs authentication" → "When the export stack needs authentication". `deployment.environment.name` mentions stay untouched.
- [ ] **Step 3: Prompt.** `the intended export target (default: the local oddyssey stack)` → `the intended export stack (default: the local one)`.
- [ ] **Step 4: Verify** — `grep -n "target" the three files`: no export-target-as-backend hits remain (generic English uses of "target" as a verb/adjective are fine — read each hit).
- [ ] **Step 5: Commit** — `fix(skill): instrumentation reports record stack instead of target` + trailer.

---

### Task 5: vocabulary sweep + report migration — `observability-cli-guides/SKILL.md`, README, `.odd/` reports

**Files:**
- Modify: `.apm/skills/observability-cli-guides/SKILL.md`
- Modify: `README.md`
- Modify: `.odd/observe-run-reports/2026-08-22-2154-mcp-otel-instrumentation-verification.md`
- Modify: `.odd/observe-run-reports/2026-08-22-2227-verify-mcp-otel-instrumentation-verification.md`
- Modify: `.odd/observe-run-reports/2026-08-26-1003-config-set-env-preservation.md`
- Modify: `.odd/observe-run-reports/2026-08-26-1039-verify-config-set-env-preservation.md`

**Interfaces:**
- Consumes: Task 1's frontmatter contract.
- Produces: a repo with zero pre-rename reports (no tolerance layer needed anywhere).

- [ ] **Step 1: cli-guides SKILL.md.** Description "to pick the environment's backend" → "to pick the stack's backend"; body line 9 "Pick the backend of the environment you are observing" → "Pick the backend of the stack you are observing" — wait, the backend IS the stack: use "Pick the observed stack's backend"; line 41 "If the environment's backend is not in the table" → "If the stack's backend is not in the table". Line 37 ("Credentials come from the environment") is the env-var sense — untouched.
- [ ] **Step 2: README.** Line 78 "For **remote** environments, only the backend changes" → "For **remote** stacks, only the backend changes"; lines 200-201 "run a remote observation on the environment to seed the next SDD wave" → "run a remote observation on the deployed environment's stack to seed the next SDD wave" — keep it natural: "run a remote observation to seed the next SDD wave" is acceptable if the sentence stays true; line 256 "on remote environments the stack behind it can be something other than Grafana" → "on remote stacks the backend behind it can be something other than Grafana". Line 168 (`/odd-status` scope example) and 261 (container environment) are correct senses — untouched.
- [ ] **Step 3: Migrate the four reports.** In each frontmatter, replace the single line `environment: local` with the two lines `stack: local` + `environment: local` (order: after `services`, matching Task 1's example order). Bodies untouched (the report body is stored as-is by contract). All four are local-stack reports, so `environment: local` is by-construction correct — no guessing.
- [ ] **Step 4: Verify** — `grep -rn "^environment:" .odd/observe-run-reports/` shows 4 hits (the new detected field), `grep -rn "^stack:" …` shows 4; full-repo `grep -rn "environment" .apm README.md` re-read: every remaining hit is an exempted sense (Dynatrace tenant, env vars, otel-guides, deployment environment).
- [ ] **Step 5: Commit** — `fix(docs): finish the stack vocabulary sweep and migrate the stored reports` + trailer.
