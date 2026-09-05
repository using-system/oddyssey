# AGENTS.md

## Working conventions

Never commit on the default branch: branch first, named
`type/short-description` (`fix/stack-env-reset`, `docs/reports-guide`).
Commit messages, PR titles, and issue titles all follow
[Conventional Commits](https://www.conventionalcommits.org/) —
`type(scope): lowercase imperative description`. The PR title becomes
the squash commit and the release note, and drives the version
(`feat:` → minor, `fix:`/others → patch): **never add a `!` or
`BREAKING CHANGE` marker without discussing it first** — it triggers a
major release. One logical change per PR. **Every PR references an
existing issue** (`Closes #N` in the body) — no exceptions: the issue
carries the problem and its discussion, the PR carries the change;
open the issue first when none exists. **When the implementation
deviates from what the issue specified** — a rule dropped, a
threshold changed, a scope narrowed, a design replaced — record each
amended choice as a comment on that issue, what changed and why,
before opening the PR: the issue is the decision record a later
reader opens first. The full contributor
workflow lives in [CONTRIBUTING.md](CONTRIBUTING.md); where this file
and CONTRIBUTING.md speak of the same thing, they say the same thing.

## English only

Every committed artifact is written in English, whatever language the
conversation uses: code identifiers, comments, docstrings, docs,
commit messages, PR and issue text, labels, release notes. Translate
user-provided content instead of copying it verbatim.

## No secrets, anywhere

Never write tokens, credentials, cookies, connection strings, or real
endpoints into anything committed or published: code, tests,
configuration, `.odd/` reports, issues, PR text. Refer to access
material by variable or secret name only. Placeholder values must be
obviously fake.

The same rule covers real identifiers and account/login names copied
from a live system, even when they carry no access on their own:
subscription/tenant/resource-group/workspace names and GUIDs (Azure,
AWS, GCP, ...), account or login names, every value persisted under a
remote stack's `stack_config` (a log group, a profile name — regions
excepted; the field's name in angle brackets stands in for it), and
anything else that identifies a real customer, tenant, or
environment. A bug repro or log
excerpt pasted straight from a live `odd_config_get`/CLI output is the
likeliest place for one to slip in — replace it with an obviously fake
placeholder (`Contoso`, a patterned or zeroed GUID, `example-user`)
before writing it down.

## Run what CI runs before a PR

Before opening or updating a PR, run the checks CI will run, scoped by
the paths touched (commands and pins are owned by
[CONTRIBUTING.md](CONTRIBUTING.md#building-and-testing);
`.github/workflows/` is canonical if they ever disagree):

- `src/mcp-server/`, `tests/`, or `integration-tests/` changed → CI
  runs lint, unit, **and** integration unconditionally: unit tests
  (`uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v`),
  lint/format at the CI-pinned ruff
  (`uvx ruff@0.16.4 check` / `format --check` on `src/mcp-server tests/mcp-server`),
  and the integration tests too when Docker is available
  (`bash integration-tests/mcp-server/run.sh`).
- `.apm/skills/*/scripts/`, `.apm/hooks/`, `tests/skills/` or
  `tests/hooks/` changed → CI lints and tests the scripts:
  `uvx ruff@0.16.4 check` / `format --check` and
  `uv run --no-project --with pytest pytest -v` on the matching
  `.apm/.../scripts` and `tests/...` directories; for hooks CI also
  deploys them with apm and builds the marketplace
  (`bash scripts/build-marketplace.sh`, then revert the generated
  trees).
- `.apm/` or `apm.yml` changed → validate the package like CI does:
  `uvx --from apm-cli==0.29.0 apm install --target claude && uvx --from apm-cli==0.29.0 apm audit`,
  and `python3 .apm/skills/observability-cli-guides/scripts/check_stack_reference.py`
  when a stack reference changed.
  The install deploys the package into the working tree and edits
  tracked files. Record `git status --porcelain` and `git diff` before
  running; once the check completes, delete the untracked files the
  command created and revert its edits to tracked files — leave
  anything that existed before untouched. The deployed hook loads into
  the running session: remove `.claude/settings.json` and
  `.claude/hooks/` together, never the script alone.

A PR pushed red costs a review round-trip; run the checks first.

## Tests follow the MCP server

Coverage moves with the code, in the same change — running the
existing suites (above) is not enough:

- Any behavior change in `src/mcp-server/` updates `tests/mcp-server/`
  — test-first.
- Any change to a tool's **wire surface** — result shape, arguments,
  the exposed tool set, stack lifecycle behavior — also adapts or
  extends `integration-tests/mcp-server/`: it is the only layer that
  proves the contract through a real MCP client against real Docker.
- A server change shipping without a matching test change states why
  in the PR (legitimate cases exist: a pure refactor, error-message
  wording — a wire-surface change is never one).
- A script bundled with a skill (`.apm/skills/*/scripts/`) or a hook
  (`.apm/hooks/scripts/`) follows the same rule: its tests live in
  `tests/skills/` or `tests/hooks/`, test-first, and CI runs them
  (see above).

## The MCP server's three hard constraints

Owned by the
[instrumentation spec](docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md)
§2 "Hard constraints" (failure semantics detailed in its §6) — the
spec wins if this summary ever drifts:

- **stdout is the JSON-RPC wire.** Nothing may ever print to stdout —
  not a log line, not a stray byte.
- **Telemetry never breaks a tool.** Export failure while the stack is
  down is the normal state, never an error surfaced to the client.
- **Tool registration must not change.** The exposed tool set is
  frozen — the unit tests assert the exact tools.

## The `.odd/` memory is append-only

The committed reports under `.odd/` are the ODD loop's memory: never
modify or delete a stored report — a new run writes a new file, and
the diff lives in the new report. An `.odd/`-only change never counts
as a fix. The formats and the rules a reviewer can enforce are in
[docs/guide/reports.md](docs/guide/reports.md); on a host that runs
the package's hooks, a hook refuses such an edit before it runs, and a
hook checks a report's filename and frontmatter against them after the
file is written, before it is persisted.

The rule governs the report stores — `.odd/observe-run-reports/`,
`.odd/otel-instrumentation-reports/`, `.odd/decisions.md`, and
`.odd/entry-classifications.md`. It does
not reach `.odd/benchmarks/` or `.odd/observability-stacks/`: a
benchmark or a custom stack file is living source, not a run record,
and its `odd-memory` reference updates it in place through reviewed
diffs like any other committed code.

## Marketplace is generated — never edit it by hand

`marketplace/`, `.claude-plugin/`, and `.agents/plugins/` are build
artifacts: the release workflow regenerates them
from `.apm/` via `scripts/build-marketplace.sh`. Author every change in
`.apm/` (agents, skills, prompts) and `apm.yml` only, and leave the
generated trees alone.

## Guides and the README are user documentation, not specs

`README.md` and `docs/guide/*.md` explain how and why to use the
package — never how it works inside. The contracts live in `.apm/`
(prompts, agents, skills) and `docs/superpowers/specs/`; a guide links
to them and never duplicates their rules. Keep a guide to what a user
needs to run the loop: the invocation, what they must supply, what
comes out and where, what the prompt will ask or refuse — one sentence
each — and a pointer to the contract for the rest. The "keep in sync"
sections below mean the guide's statements stay true and its examples
keep matching the contracts, not that every contract clause earns a
sentence in the guide. A guide paragraph that restates an internal
mechanism — a build order, a matching rule, a validation step, a
commit discipline — is a review finding, like a missing test.

## Keep the prompts guide in sync

`docs/guide/prompts.md` catalogs the packaged prompts with example
invocations. Update it in the same change whenever a prompt is added or
removed, or a prompt's behavior/arguments change — examples and
field-mapping annotations must keep matching the `.apm/prompts/`
contracts. Update the `README.md` too: the How to steps and the
Miscellaneous prompts subsection both reference prompts — and the
`Prompts` table of `docs/guide/dependencies.md` lists every prompt.
The editorial rule above applies: keep the guide true, never
exhaustive.

## Keep the dependency map in sync

`docs/guide/dependencies.md` maps who invokes what across prompts,
agents, skills, and MCP tools. Update it in the same change whenever a
prompt, agent, skill, or MCP tool is added or removed, or a dependency
between them changes — every edge must match an actual invocation in
the `.apm/` sources (no aspirational edges). Its `Prompts`, `Agents`,
and `Skills` tables list every component with its role and its edges —
they are the package's component catalog, the README carries none.
Update the `README.md` too: its MCP tools table lists the server's
tool surface.
The editorial rule above applies: keep the guide true, never
exhaustive.

## Keep the reports guide in sync

`docs/guide/reports.md` documents the `.odd/` report formats:
filename conventions, frontmatter fields and values, and body
structure for both report kinds. Update it in the same change whenever
the file contracts of `odd-memory` (its `SKILL.md` or its two report
references), or the report sections of the
`observe-run` or `otel-instrumentation-expert` agents, change — the
guide documents what a reader needs of those contracts and must never
lag them.
The editorial rule above applies: keep the guide true, never
exhaustive.

## Keep the backends guide in sync

`docs/guide/backends.md` documents, per backend, the CLI and how to
install it, the resource that must already exist on that backend
before it has anything to query ("nothing" stated explicitly where
that's true), the example switch prompt, and the `stack_config` values
(if any) the switch persists. Update it in the same change whenever a
backend's contract to call it changes — a new parameter becomes
required to query it, the CLI or its install command changes, the
resource prerequisite changes — or a backend is added to or removed
from `STACKS` — the guide must keep matching
`.apm/skills/observability-cli-guides/references/*.md`, the one place a
stack's knowledge lives (its query surface, its `## Configuration
display`, its `## What to persist`); `references/builtin-stacks.md`
there must list exactly the `STACKS` values (a unit test asserts it).

This applies to adding a new stack to `STACKS` and to modifying an
existing one — a new or changed `stack_config` field, a changed
targeting requirement, a changed CLI command or flag in any section of
the stack's `observability-cli-guides` reference. **Non-negotiable**:
every such change
must be verified live, through the backend's own CLI, against a real
account carrying real data — not from documentation, memory, or a
mocked response. Verification means actually querying every signal
that account has data for (metrics, logs, traces, profiles — whichever
apply to that backend) and confirming what the CLI really returns. A
change landed without this is unverified, whatever the diff claims.
The editorial rule above applies: keep the guide true, never
exhaustive.

## Keep the benchmarks guide in sync

`docs/guide/benchmarks.md` documents the benchmark lifecycle —
authoring today, running and verifying once those land. Update it in
the same change whenever `/odd-instrument-bench`, `k6-benchmark-expert`
or `odd-memory`'s `benchmark` reference's contract changes, and
expand its Run/Verify sections in the same change that implements
`/odd-observe`'s `benchmark:` field or `/odd-verify`'s benchmark replay
— the guide must never describe a contract that doesn't exist yet, or
lag one that does.
The editorial rule above applies: keep the guide true, never
exhaustive.

## Keep the custom backends guide in sync

`docs/guide/custom-backends.md` documents how a user creates, edits,
shares and lets the runs amend a custom stack file. Update it in the
same change whenever `/odd-config`'s create, link or complete shapes,
`odd-memory`'s `observability-stack` reference, the contract check
script's invocation, or `observe-run`'s learning rule change — the
guide must never describe a contract that doesn't exist yet, or lag
one that does. The README's "Every backend" section names the guide
and the built-in list; keep both true.
The editorial rule above applies: keep the guide true, never
exhaustive.

## Title and label every issue

GitHub issue titles follow the Conventional Commits form
`type(scope): summary`, exactly like commit messages and PR titles —
e.g. `feat(prompts): ...`, `fix(mcp): ...`, `fix(skill): ...`,
`feat(actions): ...`, `fix(ci): ...`, `docs(readme): ...`,
`docs(guide): ...`, `docs(agents): ...`. Pick the type and scope from
the existing issue titles.

When creating a GitHub issue, always set: a type label (`bug`,
`enhancement`, `documentation`), a `priority: low|medium|high` label,
and — when the issue concerns a specific observability stack — that
stack's label (`datadog`, `local`, ...; create the label if it does
not exist yet). Add `community` too when the issue is about
discoverability across external directories, marketplaces, or
community lists (submitting or updating a listing, tracking its
review).

When closing an issue as not planned, add the `wontfix` label and
close with a comment stating the rationale — the decision must be
readable from the issue itself.
