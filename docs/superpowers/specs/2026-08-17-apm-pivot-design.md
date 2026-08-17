# Oddyssey APM Pivot Design

Date: 2026-08-17
Branch: `features/bootstrap`
Status: approved design (supersedes the product framing of
`2026-08-17-bootstrap-design.md`; that spec's steps 0-2 artifacts are kept and
reused)

## Context

Oddyssey is an **APM package** (Agent Package Manager,
https://microsoft.github.io/apm/) that equips any CLI coding agent — Claude
Code, Copilot, Cursor, Codex, Gemini, OpenCode, Windsurf, Kiro, Grok Build —
for **Observability-Driven Development**: skills that teach the agent the ODD
loop, an MCP server that gives it measurement tools, and tooling for a local
LGTM observability stack. A developer runs `apm install` and their agent can
observe local runs, measure changes, and refuse regressions.

The previous bootstrap (steps 0-2) produced assets this pivot reuses as-is:
the pinned `grafana/otel-lgtm` compose file, the n-plus-one demo app, the real
spike measurements (`docs/superpowers/spike-notes-2026-08-17.md`), the
perf-budget format, and the summarizer code (Tempo/Prometheus clients +
compact report).

## Repository layout (binding)

Root rules, permanent: `src/` at the repo root contains each project; `tests/`
at the repo root mirrors `src/`; **never** a `pyproject.toml` at the root —
one per project, inside its own directory; each project's code lives in its
`app/` subfolder. The root carries only the APM package identity.

```
repo/  (= APM package "oddyssey")
├── apm.yml                      # the manifest — the only root "identity"
├── apm.lock.yaml                # written by apm install (committed if generated)
├── README.md
├── LICENSE
├── .odd/
│   └── perf-budget.yml          # budget format (documented, consumed by odd_diff)
├── skills/
│   └── odd/
│       └── SKILL.md             # the ODD loop skill (agentskills.io format)
├── docker-compose/
│   └── docker-compose.yml       # grafana/otel-lgtm:0.30.2 (canonical copy)
├── src/
│   ├── summarize/               # project 1: the summarizer (existing code migrated)
│   │   ├── pyproject.toml
│   │   └── app/
│   │       └── oddyssey_summarize/   # tempo.py, prometheus.py, report.py, errors.py
│   └── mcp-server/              # project 2: the MCP server
│       ├── pyproject.toml
│       └── app/
│           └── oddyssey_mcp/    # server.py, stack.py, baseline.py, budget.py, resources/
├── tests/
│   ├── summarize/               # migrated unit tests + fixtures + integration test
│   └── mcp-server/              # unit tests for stack/baseline/diff/budget
├── examples/
│   └── n-plus-one/              # demo project (unchanged)
│       ├── pyproject.toml
│       └── app/
└── docs/                        # specs, plans, spike notes
```

## Decisions

| Decision | Choice |
| --- | --- |
| Package identity | APM package `oddyssey`; skills at `skills/<name>/SKILL.md`; MCP server declared in `apm.yml` under `dependencies.mcp` with `registry: false`, `transport: stdio` |
| Tool language | Python ≥3.12, uv, pytest — one self-contained uv project per `src/` entry |
| MCP SDK | `mcp==2.0.0` (official Python SDK; exact FastMCP import path verified against SDK 2.0 docs at implementation time) |
| New pins (verified on PyPI 2026-08-17) | `mcp==2.0.0`, `pyyaml==6.0.3`; all prior pins unchanged (httpx==0.28.1, pytest==9.1.1, grafana/otel-lgtm:0.30.2, demo deps) |
| Import names | Code folders are `app/`; the inner package directory carries the unique import name (`app/oddyssey_summarize/`, `app/oddyssey_mcp/`), packaged with hatchling `packages = ["app/<name>"]` (prefix strip — editable-safe; a prefix *change* via `sources` is rejected by hatchling in dev mode). Internal imports are relative. |
| Project dependency | `src/mcp-server` depends on `src/summarize` via a uv path source (`editable = true`) |
| Language / commits | Committed content in English; Conventional Commits |

## The MCP server (`src/mcp-server`, project `oddyssey-mcp`)

Stdio server, console script `oddyssey-mcp`. Six tools; all return JSON-safe
dicts; all errors surface as explicit tool errors (never silent partial data).

### Stack tools

- `odd_stack_up()` — starts the LGTM stack: `docker compose -f <compose> up -d
  --wait`-style flow, then polls readiness (`:9090/-/ready`, `:3200/ready`,
  timeout ~120 s). Returns `{running: true, grafana_url, otlp_endpoint}`.
- `odd_stack_down()` — `docker compose -f <compose> down`. Returns
  `{running: false}`.
- `odd_stack_status()` — no Docker calls; probes the two readiness endpoints.
  Returns `{running: bool, prometheus: bool, tempo: bool}`.

Compose file resolution: env `ODD_COMPOSE_FILE` if set; otherwise a copy of
the compose file packaged as a resource inside `oddyssey_mcp`
(`app/resources/docker-compose.yml`, read via `importlib.resources`, written
to a temp path for docker). The repo-root `docker-compose/docker-compose.yml`
stays the canonical human-facing copy; a unit test asserts both copies are
byte-identical (drift guard).

### Measurement tools

- `odd_summarize(service: str, window_seconds: int = 900)` — computes
  `end=now`, `start=end-window_seconds`, calls the summarizer, returns the
  compact report (contract unchanged from the previous spec: `odd_version`,
  `service`, `window`, `metrics` keyed by OTel semconv names, `top_spans`).
- `odd_baseline(service: str, window_seconds: int = 900)` — runs the same
  summarize and stores it at `<odd_dir>/baseline.json` (env `ODD_DIR`,
  default `./.odd` relative to the server's cwd — the user's project).
  Returns the stored report plus `{baseline_path}`.
- `odd_diff(service: str, window_seconds: int = 900)` — runs summarize,
  loads the stored baseline (missing baseline → explicit error telling the
  agent to run `odd_baseline` first), computes deltas, evaluates the budget,
  returns:

```json
{
  "odd_version": "1",
  "service": "n-plus-one",
  "baseline": { "...": "stored report" },
  "current":  { "...": "fresh report" },
  "delta": {
    "http.server.request.duration.p95": {"before": 0.0228, "after": 0.0049, "unit": "s"},
    "http.server.request.count":        {"before": 200, "after": 200},
    "http.server.error.count":          {"before": 0, "after": 0},
    "db.client.operation.count":        {"before": 10400, "after": 400}
  },
  "verdict": "pass",
  "violations": []
}
```

### Budget evaluation

Budget file: env `ODD_BUDGET_FILE`, default `<odd_dir>/perf-budget.yml`.
Format is the committed `.odd/perf-budget.yml` (`odd_version`, `service`,
`budget:` map). Two rule kinds per metric key:

- `max: <number>` — fail if the **current** value exceeds it;
- `max_increase: <number>` — fail if `current - baseline` exceeds it.

Metric values that are `{value, unit}` dicts compare on `value`. Verdict is
`"fail"` with one violation entry per broken rule
(`{metric, rule, limit, baseline, current}`), `"pass"` when all rules hold.
No budget file → verdict `"no_budget"` (diff still returned in full);
malformed budget → explicit error.

## The skill (`skills/odd/SKILL.md`)

Agent Skills format (agentskills.io): YAML frontmatter (`name: odd`,
`description` tuned for triggering on "measure this change", "observability",
"performance regression", "N+1", "ODD loop") followed by the workflow:

1. Ensure the stack is up (`odd_stack_status`, else `odd_stack_up`).
2. Instrument the user's app with `opentelemetry-instrument` (zero-code; show
   the env vars: `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317`,
   `OTEL_SEMCONV_STABILITY_OPT_IN=http`, `OTEL_METRIC_EXPORT_INTERVAL=5000`).
3. Replay a deterministic scenario against the running app.
4. `odd_baseline` before changing code; make the change; restart the app
   (fresh process per run — the counters depend on it); replay the same
   scenario; wait ~60 s for Tempo to make the run searchable; `odd_diff`.
5. Iterate while the verdict is `fail`; report the final diff numbers.

Constraints stated in the skill: one fresh app process per measured run;
same scenario each time; never trust stdout over the report.

## apm.yml

```yaml
name: oddyssey
version: 0.1.0
dependencies:
  mcp:
    - name: oddyssey
      registry: false
      transport: stdio
      command: uvx
      args:
        - "--from"
        - "git+https://github.com/using-system/oddyssey#subdirectory=src/mcp-server"
        - "oddyssey-mcp"
```

Skills ship implicitly with the package (consumers depend on
`using-system/oddyssey` and get `skills/odd`); the MCP server rides the
manifest's `mcp` section and reaches consumers through APM's transitive
resolution (trust-gated). Exact field spelling re-verified against
`apm init`/docs during implementation; local dev alternative documented in the
README (`uv run --project src/mcp-server oddyssey-mcp`).

## Testing

- `tests/summarize/` — the migrated existing suite (client tests, report
  tests, fixtures, live-stack integration test marked `integration`).
- `tests/mcp-server/` — unit tests, no Docker: budget evaluation (pass /
  fail on max / fail on max_increase / no-budget verdict / malformed budget),
  baseline store/load round-trip (tmp dir via `ODD_DIR`), diff delta
  computation with stubbed summarize, compose-resource drift guard
  (packaged copy == repo copy), stack status probe with `httpx.MockTransport`-
  style stubs where applicable.
- Each project runs its own suite:
  `uv run --project src/summarize pytest tests/summarize` and
  `uv run --project src/mcp-server pytest tests/mcp-server` from the repo
  root; pytest config (markers, addopts) lives in each project's
  `pyproject.toml` (`[tool.pytest.ini_options]`); no root pytest.ini.
- MCP tool functions are tested by calling the underlying functions directly;
  a full stdio round-trip is out of scope for v1.

## Migration from the current branch state

- Move `src/oddyssey/summarize/app/*` → `src/summarize/app/` (imports become
  relative); delete the old `src/oddyssey` tree, root `pyproject.toml`, root
  `uv.lock`, root `pytest.ini`.
- Move `tests/oddyssey/summarize/*` → `tests/summarize/` (imports become
  `oddyssey_summarize.*`).
- Keep unchanged: `docker-compose/`, `examples/n-plus-one/`,
  `.odd/perf-budget.yml`, spike notes, LICENSE.
- README: rewritten around the plugin positioning (APM install, skills, MCP
  tools, multi-CLI), keeping the measured spike numbers as the proof section.

## Out of scope (roadmap)

Auto-instrumentation of user projects by the skill/server; `http_route`/probe
filtering in the summarizer; MCP registry publication; per-CLI packaging
beyond APM; CI budget gate.
