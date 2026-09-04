# Contributing to oddyssey

Thanks for helping build Observability-Driven Development for coding
agents. This project is young and external feedback has already shaped
it — issues, docs fixes, and code are all welcome.

## Contributing with a coding agent

This project is built for coding agents, and contributing through one
is the expected path. Agents read [AGENTS.md](AGENTS.md) — it carries
the working conventions (branching, Conventional Commits, the
breaking-marker rule), the CI checks to run before a PR, the
append-only `.odd/` rule, the generated-files list, and the
English-only and no-secrets rules. Point your agent at the repo root
so it picks the file up, and review what it produced before pushing:
**you remain responsible for everything your agent commits, opens, or
comments under your name.**

## The two-minute orientation

The repo is an [APM](https://microsoft.github.io/apm/) package plus a
Python MCP server:

| Where | What |
| --- | --- |
| `.apm/agents/`, `.apm/skills/`, `.apm/prompts/` | The product's primitives (markdown contracts). Cross-references between them are **by name only** — never by path — so they survive materialization into any CLI. |
| `src/mcp-server/` | The `oddyssey-mcp` Python package (self-contained uv project). `tests/` mirrors `src/`. |
| `marketplace/`, `.claude-plugin/`, `.agents/plugins/` | **GENERATED** by `scripts/build-marketplace.sh` at release time — never edit them by hand; edit `.apm/` and `apm.yml` instead. |
| `.odd/` | The repo's own ODD memory: committed observation reports (instrumentation reports join them as investigations run). Part of the product's dogfooding — do not delete. |
| `docs/superpowers/` | Specs and implementation plans of past waves — the design record. |

## Building and testing

Everything runs from the repo root. The pinned tool versions below are
the CI ones — `.github/workflows/` is canonical if they ever disagree:

```bash
# Unit tests (no Docker needed)
uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v

# Lint + format check (exactly what CI enforces; drop --check to apply fixes)
uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
uvx ruff@0.16.4 format --check src/mcp-server tests/mcp-server

# Integration tests (needs Docker; drives the real stack)
bash integration-tests/mcp-server/run.sh

# Skill scripts (.apm/skills/*/scripts): lint + tests, no Docker
uvx ruff@0.16.4 check .apm/skills/*/scripts tests/skills
uvx ruff@0.16.4 format --check .apm/skills/*/scripts tests/skills
uv run --no-project --with pytest pytest tests/skills -v

# Hook scripts (.apm/hooks/scripts): lint + tests, then the apm deploy
# and the marketplace build CI runs (revert the generated trees after)
uvx ruff@0.16.4 check .apm/hooks/scripts tests/hooks
uvx ruff@0.16.4 format --check .apm/hooks/scripts tests/hooks
uv run --no-project --with pytest pytest tests/hooks -v
bash scripts/build-marketplace.sh

# Validate the APM package like CI does (keep the apm-cli pin -
# older releases corrupt the install; see the README's install note)
uvx --from apm-cli==0.28.0 apm install --target claude && uvx --from apm-cli==0.28.0 apm audit
python3 scripts/check-reference-contract.py   # every stack reference follows references/CONTRACT.md
```

Three hard constraints on the MCP server (owned by the
[instrumentation spec](docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md)
§2 "Hard constraints", failure semantics detailed in its §6 — the
spec wins if this summary ever drifts):

- **stdout is the JSON-RPC wire.** Nothing may ever print to stdout.
- **Telemetry never breaks a tool.** Export failure while the stack is
  down is the normal state, never an error surfaced to the client.
- **Tool registration must not change.** The exposed tool set is
  frozen — the unit tests assert the exact tools.

## Pull requests

- **Every PR references an existing issue** (`Closes #N` in the body)
  — no exceptions. The issue carries the problem and its discussion,
  the PR carries the change; open the issue first when none exists.
- **The issue is the decision record.** When the implementation
  deviates from what the issue specified — a rule dropped, a threshold
  changed, a scope narrowed, a design replaced — record each amended
  choice as a comment on that issue, what changed and why, before
  opening the PR.
- **The PR title IS the release note.** We squash-merge with the PR
  title as the commit message, and versions are computed from
  [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:` → minor, `fix:`/others → patch. Use
  `type(scope): lowercase imperative description`.
- **Never add a `!` or `BREAKING CHANGE` marker** without discussing it
  in the PR first — it triggers a major release.
- CI must be green: the 8-target APM matrix runs on every PR; the
  server's lint, unit, and integration jobs all run when `src/`,
  `tests/`, or `integration-tests/` change.
- Keep one logical change per PR, and match the surrounding style —
  the agent/skill markdown files are executable contracts, so wording
  changes there are behavior changes.

## Issues

Use the issue forms (bug / feature) — the bug form's fields, including
its confirmed-vs-observed status, ARE the house style. Questions belong
in [Discussions](https://github.com/using-system/oddyssey/discussions).

## Security

Vulnerabilities go through
[private reporting](https://github.com/using-system/oddyssey/security/advisories/new)
— never a public issue; scope and expectations are in
[SECURITY.md](SECURITY.md). And because this repo asks you to commit
observation reports: `.odd/` reports in a PR must honor the no-secrets
rule — no tokens, credentials, or real endpoints, access material by
name only. The full set of rules a reviewer holds a report to is in
[docs/guide/reports.md](docs/guide/reports.md#what-a-reviewer-can-hold-a-report-to).

## Trying your changes end to end

The product tests itself: install your working copy into a scratch
consumer
(`uvx --from apm-cli==0.28.0 apm install /path/to/your/clone --target claude`),
or run
the ODD loop on the repo itself (`/odd-observe` on `oddyssey-mcp`) —
the stored reports under `.odd/` show what a healthy run looks like.
