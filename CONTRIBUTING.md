# Contributing to oddyssey

Thanks for helping build Observability-Driven Development for coding
agents. This project is young and external feedback has already shaped
it — issues, docs fixes, and code are all welcome.

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

# Validate the APM package like CI does
uvx --from apm-cli==0.28.0 apm install --target claude && uvx --from apm-cli==0.28.0 apm audit
```

Two hard constraints on the MCP server (owned by the
[instrumentation spec](docs/superpowers/specs/2026-08-22-mcp-otel-instrumentation-design.md)
§2 — it wins if this summary ever drifts):

- **stdout is the JSON-RPC wire.** Nothing may ever print to stdout.
- **Telemetry never breaks a tool.** Export failure is the normal
  state; bootstrap failure degrades to no telemetry, never to a dead
  server.

## Pull requests

- **The PR title IS the release note.** We squash-merge with the PR
  title as the commit message, and versions are computed from
  [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:` → minor, `fix:`/others → patch. Use
  `type(scope): lowercase imperative description`.
- **Never add a `!` or `BREAKING CHANGE` marker** without discussing it
  in the PR first — it triggers a major release.
- CI must be green: the 8-target APM matrix runs on every PR; the
  server's lint/unit/integration jobs run when `src/` or `tests/`
  change.
- Keep one logical change per PR, and match the surrounding style —
  the agent/skill markdown files are executable contracts, so wording
  changes there are behavior changes.

## Issues

Use the issue forms (bug / feature) — the bug form's fields, including
its confirmed-vs-observed status, ARE the house style. Questions belong
in [Discussions](https://github.com/using-system/oddyssey/discussions).

## Trying your changes end to end

The product tests itself: install your working copy into a scratch
consumer
(`uvx --from apm-cli==0.28.0 apm install /path/to/your/clone --target claude`),
or run
the ODD loop on the repo itself (`/odd-observe` on `oddyssey-mcp`) —
the stored reports under `.odd/` show what a healthy run looks like.
