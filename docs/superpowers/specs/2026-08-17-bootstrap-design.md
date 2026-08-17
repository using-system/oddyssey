# Oddyssey Bootstrap Design

Date: 2026-08-17
Branch: `features/bootstrap`
Status: approved design, pending implementation plan

## Context

Oddyssey is an Observability-Driven Development (ODD) tool for CLI coding agents.
AI coding agents write code they cannot verify: they see stdout and exit codes,
not latency, error rates, or the N+1 query they just introduced. Oddyssey closes
the loop: spin up a local OpenTelemetry backend, instrument the app, replay a
scenario, and hand the agent a compact report it can diff against the previous
run.

The full product roadmap (from the founding design discussion) is:

- **Step 0 — Spike**: prove on a real example that traces let an agent make a
  better decision than stdout alone (an N+1 query, invisible in logs, obvious in
  a trace).
- **Step 1 — README-driven development**: write the README as the transcript of
  the ideal session, using real numbers from the spike.
- **Step 2 — Summarizer**: the core module that queries Tempo and Prometheus and
  emits a compact JSON report. This is the only piece nobody has built properly;
  everything else is plumbing.
- **Step 3 — Baseline + diff + verdict** (out of scope here): store the previous
  run, compare, exit non-zero when the perf budget is exceeded.
- **Step 4 — Packaging** (out of scope here): MCP server, thin per-CLI shells,
  APM (Agent Package Manager) manifest, auto-instrumentation of user projects.

**This bootstrap covers steps 0 through 2.**

## Decisions already made

| Decision | Choice |
| --- | --- |
| Project name | oddyssey (odd + odyssey) |
| License | MIT (already committed) |
| Tool language | Python, managed with `uv`, tested with `pytest` |
| Telemetry backend | `grafana/otel-lgtm` Docker image (Tempo, Loki, Prometheus, Grafana, OTel Collector) |
| Data access | Query the Tempo and Prometheus HTTP APIs (no custom OTLP parsing) |
| Report vocabulary | OpenTelemetry semantic conventions for all field names |
| Committed content language | English only (docs, comments, commits) |
| Commit convention | Conventional Commits |

## Repository layout

Each Python project is self-contained with its own `pyproject.toml`. There is no
root `pyproject.toml`. The root `tests/` directory mirrors the `src/` tree of
the `oddyssey/` project.

```
repo/
├── README.md                    # rewritten: positioning + ideal-session transcript
├── LICENSE                      # MIT, already in place
├── .odd/
│   └── perf-budget.yml          # budget format, versioned (not enforced yet — step 3)
├── docker-compose/
│   └── docker-compose.yml       # grafana/otel-lgtm service (ports 3000, 4317/4318)
├── examples/
│   └── n-plus-one/              # FastAPI + SQLite + SQLAlchemy demo app
│       ├── pyproject.toml
│       └── app/
│           ├── main.py          # GET /users → users + posts, classic N+1
│           ├── seed.py          # deterministic dataset (50 users × posts)
│           └── load.py          # replays the scenario: 200 requests, deterministic
├── oddyssey/
│   ├── pyproject.toml
│   └── src/
│       └── oddyssey/
│           └── summarize/
│               └── app/
│                   ├── tempo.py       # minimal Tempo API client (TraceQL search)
│                   ├── prometheus.py  # minimal Prometheus API client
│                   └── report.py      # aggregation into the compact report
└── tests/
    └── oddyssey/
        └── summarize/
            ├── fixtures/        # recorded Tempo/Prometheus HTTP responses
            ├── test_report.py
            └── test_integration.py   # marked `integration`, requires the stack
```

## Dependency pinning

All dependencies are pinned to exact versions (`==`) in each project's
`pyproject.toml`, and `uv.lock` files are committed. The Docker image tag is
pinned as well. Versions below were verified against PyPI and Docker Hub on
2026-08-17:

| Dependency | Pinned version | Used by |
| --- | --- | --- |
| `grafana/otel-lgtm` (Docker) | `0.30.2` | docker-compose |
| `fastapi` | `0.141.1` | n-plus-one |
| `uvicorn` | `0.52.3` | n-plus-one |
| `sqlalchemy` | `2.0.52` | n-plus-one |
| `opentelemetry-distro` | `0.65b0` | n-plus-one |
| `opentelemetry-exporter-otlp` | `1.44.0` | n-plus-one |
| `opentelemetry-instrumentation-fastapi` | `0.65b0` | n-plus-one |
| `opentelemetry-instrumentation-sqlalchemy` | `0.65b0` | n-plus-one |
| `httpx` | `0.28.1` | n-plus-one (load.py), oddyssey |
| `pytest` | `9.1.1` | oddyssey (dev) |

Note: the `0.x b0` versions are the normal versioning scheme of the OTel Python
instrumentation packages (contrib repo); they are the stable releases matching
core `1.44.0`.

## Step 0 — The spike (demo app)

The demo app exposes `GET /users` returning users with their posts. The default
implementation performs a classic N+1 (one query for users, then one query per
user for its posts). Setting `ODD_FIXED=1` switches to the fixed variant
(`joinedload`). Both variants live in the same file so the before/after
comparison is reproducible forever.

- Instrumentation: `opentelemetry-instrument` (zero app-code changes), OTLP
  export to the `otel-lgtm` stack started via `docker-compose/docker-compose.yml`.
- Load scenario: `load.py` sends 200 requests to the endpoint, deterministically.
- Success gate: both variants are run for real; the measured p95 latency and SQL
  span counts go into the README. No invented numbers.

## Step 2 — The summarizer

Module `oddyssey.summarize` has one responsibility: query the stack over a time
window and return a compact report. Three internal units:

- `tempo.py` — TraceQL search by service name and time window; returns raw span
  data.
- `prometheus.py` — instant/range queries: p95 via `histogram_quantile` on
  `http.server.request.duration`, error count, DB span counts.
- `report.py` — aggregates into the compact report. Field names follow OTel
  semantic conventions:

```json
{
  "odd_version": "1",
  "service": "n-plus-one",
  "window": {"start": "...", "end": "..."},
  "metrics": {
    "http.server.request.duration.p95": {"value": 0.340, "unit": "s"},
    "http.server.request.count": 200,
    "http.server.error.count": 0,
    "db.client.operation.count": 201
  },
  "top_spans": [
    {"name": "SELECT posts", "count": 200, "total_duration_ms": 280}
  ]
}
```

The report is the contract that later feeds the agent: compact (fits a context
window), versioned (`odd_version`), and stable.

Out of scope for this bootstrap: CLI entry point, baseline storage, diff,
verdict. `.odd/perf-budget.yml` is committed as a documented format only;
nothing reads it yet.

## Error handling

- Stack unreachable (connection refused on Tempo/Prometheus) → explicit
  exception with a hint to start the Docker stack. No silent partial report.
- Empty time window (zero spans found) → explicit exception; an empty report is
  a scenario error, not a valid measurement.

## Testing strategy

- **Unit tests**: pytest on aggregation and client parsing logic, driven by
  hand-written JSON fixtures matching the real Tempo/Prometheus response
  shapes verified during the spike. Deterministic; CI passes without Docker.
- **Integration test**: marked `@pytest.mark.integration`, requires the running
  `otel-lgtm` stack and the demo app; excluded from the default run.
- Test tree mirrors the source tree: `tests/oddyssey/summarize/`.

## README

Rewritten in English with:

1. The positioning paragraph ("AI coding agents write code they can't verify…").
2. The ideal-session transcript (`odd baseline` / `odd diff`) using the real
   numbers measured in the spike — presented as the target UX, clearly marked as
   roadmap where not yet implemented.
3. Quickstart: `docker compose up`, run the demo, run the summarizer.
4. An "Under the hood" section for the LGTM stack details (kept out of the
   short description on purpose).
5. GitHub topics suggestion: observability, opentelemetry, ai-agents,
   coding-agents, developer-tools, mcp, performance-regression.

## Commit sequence

Conventional Commits on `features/bootstrap`:

1. `docs: add bootstrap design spec`
2. `chore: scaffold project layout` (docker-compose, pyproject files, perf-budget format)
3. `feat: add n-plus-one demo app` (FastAPI app, seed, load script)
4. `feat: add summarizer module` (tempo/prometheus clients, report, tests + fixtures)
5. `docs: rewrite README with measured spike numbers`
