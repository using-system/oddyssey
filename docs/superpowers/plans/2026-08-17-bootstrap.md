# Oddyssey Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap the oddyssey repo through roadmap steps 0-2: a measurable N+1 demo app, real spike numbers, the Tempo/Prometheus summarizer module with tests, and a README written from measured data.

**Architecture:** The repo root is the oddyssey project (standard Python src layout); the demo is a separate self-contained uv project in `examples/n-plus-one`. The demo app is auto-instrumented with OpenTelemetry and exports OTLP to a pinned `grafana/otel-lgtm` container. The summarizer queries the Tempo and Prometheus HTTP APIs and aggregates into a compact, versioned JSON report using OTel semantic-convention field names.

**Tech Stack:** Python 3.12+, uv, FastAPI, SQLAlchemy 2 (SQLite), OpenTelemetry auto-instrumentation, httpx, pytest, Docker Compose, grafana/otel-lgtm.

**Spec:** `docs/superpowers/specs/2026-08-17-bootstrap-design.md`

## Global Constraints

- All committed content (code, comments, docs, commit messages) is English. Conversation language does not leak into files.
- Conventional Commits on branch `features/bootstrap`. Every commit message ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Exact version pins (`==`) in every `pyproject.toml`; `uv.lock` committed per project. Pinned set (verified 2026-08-17): `grafana/otel-lgtm:0.30.2`, `fastapi==0.141.1`, `uvicorn==0.52.3`, `sqlalchemy==2.0.52`, `opentelemetry-distro==0.65b0`, `opentelemetry-exporter-otlp==1.44.0`, `opentelemetry-instrumentation-fastapi==0.65b0`, `opentelemetry-instrumentation-sqlalchemy==0.65b0`, `httpx==0.28.1`, `pytest==9.1.1`.
- The repo root is the oddyssey project: `pyproject.toml`, `src/`, and `tests/` at the root, `tests/` mirroring `src/`. The demo is a separate uv project in `examples/n-plus-one`. Docker Compose lives in `docker-compose/`.
- README numbers must come from the spike measurements recorded in Task 3 — never invented.
- `requires-python = ">=3.12"` in both projects.

## Verified-at-runtime names (single source of truth)

The OTel → Prometheus/Tempo names below are the plan's best knowledge. **Task 3 verifies them against the live stack** and records the real names in `docs/superpowers/spike-notes-2026-08-17.md`. Tasks 4-6 MUST use the names from that file if they differ:

- Prometheus histogram: `http_server_request_duration_seconds` (`_bucket`, `_count` suffixes), service selector label `job="n-plus-one"`, status label `http_response_status_code`.
- Tempo span attribute for DB spans: `span.db.system` (value `sqlite`).

---

### Task 1: Scaffold project layout

**Files:**
- Create: `docker-compose/docker-compose.yml`
- Create: `.odd/perf-budget.yml`
- Create: `pytest.ini`
- Create: `pyproject.toml` (repo root)
- Create: `src/oddyssey/__init__.py`, `src/oddyssey/summarize/__init__.py`, `src/oddyssey/summarize/app/__init__.py`
- Create: `examples/n-plus-one/pyproject.toml`, `examples/n-plus-one/app/__init__.py`
- Modify: `.gitignore` (append demo artifacts)

**Interfaces:**
- Consumes: nothing.
- Produces: importable empty package `oddyssey`; `uv sync` working in both project dirs; `docker compose -f docker-compose/docker-compose.yml up -d` exposing Grafana :3000, OTLP :4317/:4318, Tempo :3200, Prometheus :9090.

- [ ] **Step 1: Verify the pinned build backend version**

Run: `curl -s https://pypi.org/pypi/hatchling/json | python3 -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"`
Use the printed version in the `hatchling==<version>` pin in the root `pyproject.toml` below (do the same substitution nowhere else).

- [ ] **Step 2: Write `docker-compose/docker-compose.yml`**

```yaml
services:
  lgtm:
    image: grafana/otel-lgtm:0.30.2
    container_name: oddyssey-lgtm
    ports:
      - "3000:3000"   # Grafana UI
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
      - "3200:3200"   # Tempo API
      - "9090:9090"   # Prometheus API
```

- [ ] **Step 3: Write `.odd/perf-budget.yml`**

```yaml
# Performance budget for the demo scenario (format v1).
# Nothing enforces this file yet: the diff/verdict engine (roadmap step 3)
# will read it and fail the run when a limit is exceeded.
odd_version: "1"
service: n-plus-one
budget:
  http.server.request.duration.p95:
    max: 0.150            # seconds
  http.server.error.count:
    max_increase: 0       # errors must not increase vs baseline
  db.client.operation.count:
    max_increase: 0       # DB query count must not grow vs baseline
```

- [ ] **Step 4: Write the root `pyproject.toml`**

```toml
[project]
name = "oddyssey"
version = "0.1.0"
description = "Observability-driven development for CLI coding agents"
requires-python = ">=3.12"
license = "MIT"
dependencies = [
    "httpx==0.28.1",
]

[dependency-groups]
dev = [
    "pytest==9.1.1",
]

[build-system]
requires = ["hatchling==<version from Step 1>"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/oddyssey"]
```

- [ ] **Step 5: Write `examples/n-plus-one/pyproject.toml`**

```toml
[project]
name = "n-plus-one"
version = "0.1.0"
description = "Demo FastAPI app with a deliberate N+1 query, used by the oddyssey spike"
requires-python = ">=3.12"
dependencies = [
    "fastapi==0.141.1",
    "uvicorn==0.52.3",
    "sqlalchemy==2.0.52",
    "httpx==0.28.1",
    "opentelemetry-distro==0.65b0",
    "opentelemetry-exporter-otlp==1.44.0",
    "opentelemetry-instrumentation-fastapi==0.65b0",
    "opentelemetry-instrumentation-sqlalchemy==0.65b0",
]

[tool.uv]
package = false
```

- [ ] **Step 6: Write `pytest.ini` at repo root**

```ini
[pytest]
testpaths = tests
addopts = -m "not integration"
markers =
    integration: requires the running otel-lgtm stack and a freshly loaded demo app
```

- [ ] **Step 7: Create the empty package files**

`src/oddyssey/__init__.py`, `src/oddyssey/summarize/__init__.py`, `src/oddyssey/summarize/app/__init__.py`, `examples/n-plus-one/app/__init__.py` — each containing only a one-line docstring, e.g. `"""oddyssey — observability-driven development for CLI coding agents."""` for the top package and `"""Demo app package."""` for the example.

- [ ] **Step 8: Append demo artifacts to `.gitignore`**

Append at the end of the existing `.gitignore`:

```gitignore
# Oddyssey demo artifacts
examples/n-plus-one/demo.db
```

- [ ] **Step 9: Lock and sync both projects**

Run from repo root: `uv sync` then `uv sync --project examples/n-plus-one`
Expected: both create `.venv` and write `uv.lock` with the exact pinned versions; no resolution errors.

- [ ] **Step 10: Verify scaffold**

Run: `docker compose -f docker-compose/docker-compose.yml config -q && uv run python -c "import oddyssey; print('ok')"`
Expected: no compose errors, prints `ok`.

- [ ] **Step 11: Commit**

```bash
git add docker-compose .odd pytest.ini pyproject.toml uv.lock src examples/n-plus-one/pyproject.toml examples/n-plus-one/app examples/n-plus-one/uv.lock .gitignore
git commit -m "chore: scaffold project layout"
```

---

### Task 2: N+1 demo app

**Files:**
- Create: `examples/n-plus-one/app/main.py`
- Create: `examples/n-plus-one/app/seed.py`
- Create: `examples/n-plus-one/app/load.py`

**Interfaces:**
- Consumes: scaffold from Task 1.
- Produces: `GET /users` on port 8000 (N+1 by default, fixed variant with `ODD_FIXED=1`); `python -m app.seed` creates a deterministic `demo.db`; `python -m app.load` sends 200 requests and prints `done: 200 requests, 0 errors`.

- [ ] **Step 1: Write `examples/n-plus-one/app/main.py`**

```python
"""Demo FastAPI app with a deliberate N+1 query on GET /users.

The default implementation loads users, then lazily loads each user's
posts one query at a time — the classic N+1. Setting ODD_FIXED=1
switches to a single joined query. Both variants live here so the
before/after comparison stays reproducible.
"""

import os

from fastapi import FastAPI
from sqlalchemy import ForeignKey, create_engine, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    joinedload,
    mapped_column,
    relationship,
)

DB_URL = os.environ.get("ODD_DB_URL", "sqlite:///./demo.db")
FIXED = os.environ.get("ODD_FIXED") == "1"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    posts: Mapped[list["Post"]] = relationship(back_populates="author")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author: Mapped[User] = relationship(back_populates="posts")


engine = create_engine(DB_URL)
app = FastAPI(title="n-plus-one")


@app.get("/users")
def list_users() -> list[dict]:
    with Session(engine) as session:
        stmt = select(User)
        if FIXED:
            stmt = stmt.options(joinedload(User.posts))
        users = session.scalars(stmt).unique().all()
        return [
            {"id": user.id, "name": user.name, "posts": [post.title for post in user.posts]}
            for user in users
        ]
```

- [ ] **Step 2: Write `examples/n-plus-one/app/seed.py`**

```python
"""Create and populate demo.db deterministically: 50 users x 5 posts."""

from app.main import Base, Post, User, engine
from sqlalchemy.orm import Session

USER_COUNT = 50
POSTS_PER_USER = 5


def main() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for user_index in range(1, USER_COUNT + 1):
            user = User(name=f"user-{user_index:03d}")
            user.posts = [
                Post(title=f"post-{user_index:03d}-{post_index}")
                for post_index in range(1, POSTS_PER_USER + 1)
            ]
            session.add(user)
        session.commit()
    print(f"seeded {USER_COUNT} users with {POSTS_PER_USER} posts each")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write `examples/n-plus-one/app/load.py`**

```python
"""Replay the load scenario: 200 sequential GET /users requests."""

import httpx

BASE_URL = "http://127.0.0.1:8000"
REQUEST_COUNT = 200


def main() -> None:
    errors = 0
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        for _ in range(REQUEST_COUNT):
            response = client.get("/users")
            if response.status_code >= 400:
                errors += 1
    print(f"done: {REQUEST_COUNT} requests, {errors} errors")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Smoke-test without instrumentation**

Run from `examples/n-plus-one/`:

```bash
uv run python -m app.seed
uv run uvicorn app.main:app --port 8000 &   # note the PID
sleep 2
curl -s http://127.0.0.1:8000/users | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d), d[0]['name'], len(d[0]['posts']))"
uv run python -m app.load
kill %1
```

Expected: seed prints `seeded 50 users with 5 posts each`; curl check prints `50 user-001 5`; load prints `done: 200 requests, 0 errors`.

- [ ] **Step 5: Commit**

```bash
git add examples/n-plus-one/app
git commit -m "feat: add n-plus-one demo app"
```

---

### Task 3: Spike — measure both variants for real

**Files:**
- Create: `docs/superpowers/spike-notes-2026-08-17.md`

**Interfaces:**
- Consumes: Task 1 compose file, Task 2 demo app.
- Produces: measured p95 and DB span counts for both variants, plus the **verified** Prometheus metric names, label names, and Tempo attribute names. Tasks 4-7 read this file.

- [ ] **Step 1: Start the stack and wait for readiness**

```bash
docker compose -f docker-compose/docker-compose.yml up -d
until curl -sf http://localhost:9090/-/ready && curl -sf http://localhost:3200/ready; do sleep 2; done
```

Expected: both readiness endpoints answer within ~60s. If port 3200 or 9090 refuses connections permanently, inspect `docker compose logs lgtm` — the summarizer depends on both APIs being mapped.

- [ ] **Step 2: Run the N+1 variant under instrumentation and load it**

From `examples/n-plus-one/`:

```bash
uv run python -m app.seed
env OTEL_SERVICE_NAME=n-plus-one \
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
    OTEL_EXPORTER_OTLP_PROTOCOL=grpc \
    OTEL_SEMCONV_STABILITY_OPT_IN=http \
    OTEL_METRIC_EXPORT_INTERVAL=5000 \
    uv run opentelemetry-instrument uvicorn app.main:app --port 8000 &
sleep 3
BASELINE_START=$(date +%s)
uv run python -m app.load
sleep 10        # let the last metric export flush
BASELINE_END=$(date +%s)
kill %1
```

Record `BASELINE_START` / `BASELINE_END`.

- [ ] **Step 3: Verify the actual metric and attribute names**

```bash
# Prometheus: find the real duration histogram name and its labels
curl -s 'http://localhost:9090/api/v1/label/__name__/values' | python3 -m json.tool | grep -i http
curl -s 'http://localhost:9090/api/v1/query?query=http_server_request_duration_seconds_count' | python3 -m json.tool | head -40

# Tempo: confirm DB spans carry a db.system-like attribute
curl -s -G 'http://localhost:3200/api/search' \
  --data-urlencode 'q={resource.service.name="n-plus-one" && span.db.system != nil}' \
  --data-urlencode "start=$BASELINE_START" --data-urlencode "end=$BASELINE_END" \
  --data-urlencode 'limit=5' | python3 -m json.tool | head -60
```

Expected: the histogram exists (name may differ, e.g. old-semconv `http_server_duration_milliseconds`); the label carrying the status code and the label selecting the service (`job` or `service_name`) are visible in the query output; the Tempo search returns traces with `spanSets[].matched > 0`. **Write every real name into the spike notes.** If `span.db.system != nil` returns nothing, try `span.db.system.name != nil` and record which one works.

- [ ] **Step 4: Measure the N+1 baseline**

Using the verified names (shown here with the expected defaults):

```bash
W=$((BASELINE_END - BASELINE_START))
# p95 latency (seconds)
curl -s -G 'http://localhost:9090/api/v1/query' --data-urlencode "time=$BASELINE_END" \
  --data-urlencode "query=histogram_quantile(0.95, sum by (le) (increase(http_server_request_duration_seconds_bucket{job=\"n-plus-one\"}[${W}s])))"
# request count
curl -s -G 'http://localhost:9090/api/v1/query' --data-urlencode "time=$BASELINE_END" \
  --data-urlencode "query=sum(increase(http_server_request_duration_seconds_count{job=\"n-plus-one\"}[${W}s]))"
# DB span count: sum of "matched" across traces
curl -s -G 'http://localhost:3200/api/search' \
  --data-urlencode 'q={resource.service.name="n-plus-one" && span.db.system != nil}' \
  --data-urlencode "start=$BASELINE_START" --data-urlencode "end=$BASELINE_END" \
  --data-urlencode 'limit=500' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(sum(m for t in d.get('traces',[]) for m in [sum(s.get('matched',0) for s in t.get('spanSets',[]))]))"
```

Record: p95 (s), request count, DB span count. Expected shape: request count ≈ 200, DB spans ≈ 200 × 51 or at least clearly in the thousands/hundreds — much larger than the fixed variant.

- [ ] **Step 5: Measure the fixed variant**

Repeat Steps 2 and 4 with `ODD_FIXED=1` added to the `env` list, recording `FIXED_START`/`FIXED_END` and the same three numbers. Expected: DB span count collapses (≈ 200), p95 drops.

- [ ] **Step 6: Stop the stack and write the spike notes**

`docker compose -f docker-compose/docker-compose.yml down`

Write `docs/superpowers/spike-notes-2026-08-17.md`:

```markdown
# Spike measurements — 2026-08-17

Scenario: 200 sequential GET /users, 50 users x 5 posts, SQLite, single uvicorn worker.

## Verified names

| Concept | Verified value |
| --- | --- |
| Prometheus duration histogram | <real name> |
| Service selector label | <job="n-plus-one" or other> |
| Status code label | <real label> |
| Tempo DB attribute (TraceQL) | <span.db.system or span.db.system.name> |

## Measurements

| Metric | N+1 (default) | Fixed (ODD_FIXED=1) |
| --- | --- | --- |
| p95 latency | <s> | <s> |
| HTTP requests | <n> | <n> |
| DB spans | <n> | <n> |

## Conclusion

<2-3 sentences: is the N+1 invisible in stdout but obvious in the trace data? This is the go/no-go evidence for the README.>
```

Every `<...>` MUST be replaced with the measured value — that is the entire point of this task.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/spike-notes-2026-08-17.md
git commit -m "docs: record spike measurements for both demo variants"
```

---

### Task 4: Summarizer clients (errors, Tempo, Prometheus)

**Files:**
- Create: `src/oddyssey/summarize/app/errors.py`
- Create: `src/oddyssey/summarize/app/tempo.py`
- Create: `src/oddyssey/summarize/app/prometheus.py`
- Test: `tests/oddyssey/summarize/test_tempo.py`, `tests/oddyssey/summarize/test_prometheus.py`

**Interfaces:**
- Consumes: verified names from `docs/superpowers/spike-notes-2026-08-17.md`.
- Produces:
  - `errors.StackUnreachableError(RuntimeError)`, `errors.EmptyWindowError(RuntimeError)`
  - `TempoClient(base_url="http://localhost:3200", timeout=10.0, transport=None)` with `search(query: str, start: int, end: int, limit: int = 500, spans_per_spanset: int = 100) -> dict`
  - `PrometheusClient(base_url="http://localhost:9090", timeout=10.0, transport=None)` with `query(promql: str, time: int) -> list[dict]` returning the instant-query result vector

- [ ] **Step 1: Write the failing tests**

`tests/oddyssey/summarize/test_tempo.py`:

```python
import httpx
import pytest

from oddyssey.summarize.app.errors import StackUnreachableError
from oddyssey.summarize.app.tempo import TempoClient


def test_search_returns_parsed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/search"
        assert request.url.params["q"] == '{resource.service.name="demo"}'
        assert request.url.params["start"] == "100"
        assert request.url.params["end"] == "200"
        return httpx.Response(200, json={"traces": [], "metrics": {}})

    client = TempoClient(transport=httpx.MockTransport(handler))
    result = client.search('{resource.service.name="demo"}', start=100, end=200)
    assert result == {"traces": [], "metrics": {}}


def test_unreachable_raises_explicit_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = TempoClient(transport=httpx.MockTransport(handler))
    with pytest.raises(StackUnreachableError, match="Tempo is unreachable"):
        client.search("{}", start=0, end=1)
```

`tests/oddyssey/summarize/test_prometheus.py`:

```python
import httpx
import pytest

from oddyssey.summarize.app.errors import StackUnreachableError
from oddyssey.summarize.app.prometheus import PrometheusClient


def _success(result: list[dict]) -> dict:
    return {"status": "success", "data": {"resultType": "vector", "result": result}}


def test_query_returns_result_vector():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        assert request.url.params["query"] == "up"
        assert request.url.params["time"] == "123"
        return httpx.Response(200, json=_success([{"metric": {}, "value": [123, "1"]}]))

    client = PrometheusClient(transport=httpx.MockTransport(handler))
    assert client.query("up", time=123) == [{"metric": {}, "value": [123, "1"]}]


def test_failed_status_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "error": "bad query"})

    client = PrometheusClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="Prometheus query failed"):
        client.query("up", time=123)


def test_unreachable_raises_explicit_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = PrometheusClient(transport=httpx.MockTransport(handler))
    with pytest.raises(StackUnreachableError, match="Prometheus is unreachable"):
        client.query("up", time=123)
```

- [ ] **Step 2: Run tests to verify they fail**

Run from repo root: `uv run pytest tests/oddyssey/summarize/ -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'oddyssey.summarize.app.errors'` (or similar import errors).

- [ ] **Step 3: Write the implementation**

`src/oddyssey/summarize/app/errors.py`:

```python
"""Exceptions raised by the summarize module."""


class StackUnreachableError(RuntimeError):
    """The Tempo or Prometheus API could not be reached."""


class EmptyWindowError(RuntimeError):
    """No telemetry was found in the requested time window."""
```

`src/oddyssey/summarize/app/tempo.py`:

```python
"""Minimal Tempo HTTP API client (TraceQL search)."""

from __future__ import annotations

import httpx

from oddyssey.summarize.app.errors import StackUnreachableError

DEFAULT_BASE_URL = "http://localhost:3200"

_UNREACHABLE_HINT = (
    "Is the otel-lgtm stack running? "
    "Try: docker compose -f docker-compose/docker-compose.yml up -d"
)


class TempoClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def search(
        self,
        query: str,
        start: int,
        end: int,
        limit: int = 500,
        spans_per_spanset: int = 100,
    ) -> dict:
        """Run a TraceQL search; start/end are unix epoch seconds."""
        params = {
            "q": query,
            "start": start,
            "end": end,
            "limit": limit,
            "spss": spans_per_spanset,
        }
        try:
            response = self._client.get("/api/search", params=params)
            response.raise_for_status()
        except httpx.TransportError as exc:
            raise StackUnreachableError(
                f"Tempo is unreachable at {self._client.base_url}. {_UNREACHABLE_HINT}"
            ) from exc
        return response.json()
```

`src/oddyssey/summarize/app/prometheus.py`:

```python
"""Minimal Prometheus HTTP API client (instant queries)."""

from __future__ import annotations

import httpx

from oddyssey.summarize.app.errors import StackUnreachableError

DEFAULT_BASE_URL = "http://localhost:9090"

_UNREACHABLE_HINT = (
    "Is the otel-lgtm stack running? "
    "Try: docker compose -f docker-compose/docker-compose.yml up -d"
)


class PrometheusClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def query(self, promql: str, time: int) -> list[dict]:
        """Run an instant query evaluated at `time` (unix epoch seconds).

        Returns the result vector (possibly empty).
        """
        try:
            response = self._client.get("/api/v1/query", params={"query": promql, "time": time})
            response.raise_for_status()
        except httpx.TransportError as exc:
            raise StackUnreachableError(
                f"Prometheus is unreachable at {self._client.base_url}. {_UNREACHABLE_HINT}"
            ) from exc
        payload = response.json()
        if payload.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed: {payload}")
        return payload["data"]["result"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/oddyssey/summarize/ -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/oddyssey/summarize/app tests/oddyssey/summarize
git commit -m "feat(summarize): add tempo and prometheus clients"
```

---

### Task 5: Report aggregation

**Files:**
- Create: `src/oddyssey/summarize/app/report.py`
- Test: `tests/oddyssey/summarize/test_report.py`
- Create: `tests/oddyssey/summarize/fixtures/tempo_search_all.json`, `tests/oddyssey/summarize/fixtures/tempo_search_db.json`

**Interfaces:**
- Consumes: `TempoClient.search`, `PrometheusClient.query`, `EmptyWindowError` from Task 4; verified names from the spike notes.
- Produces: `report.summarize(service: str, start: int, end: int, tempo: TempoClient | None = None, prometheus: PrometheusClient | None = None) -> dict` returning the compact report defined in the spec; constants `ODD_VERSION = "1"`, `HTTP_DURATION_METRIC`, `TOP_SPANS_LIMIT = 5`.

**Adjustment rule:** if the spike notes recorded different Prometheus/Tempo names, substitute them in `HTTP_DURATION_METRIC`, the status-code label, and `DB_SPAN_QUERY` — and keep the report's *output* field names exactly as in the spec (they are the contract). (Spike outcome: all names matched the defaults; the query FORM was adjusted to `last_over_time` cumulative reads per the spike notes' deviation #1 — already reflected in the code below.)

- [ ] **Step 1: Write the fixtures**

`tests/oddyssey/summarize/fixtures/tempo_search_all.json` — all spans of the service (2 traces, request spans + SQL spans):

```json
{
  "traces": [
    {
      "traceID": "aaa111",
      "spanSets": [
        {
          "matched": 3,
          "spans": [
            {"spanID": "s1", "name": "GET /users", "durationNanos": "340000000"},
            {"spanID": "s2", "name": "SELECT posts", "durationNanos": "1500000"},
            {"spanID": "s3", "name": "SELECT posts", "durationNanos": "1300000"}
          ]
        }
      ]
    },
    {
      "traceID": "bbb222",
      "spanSets": [
        {
          "matched": 3,
          "spans": [
            {"spanID": "s4", "name": "GET /users", "durationNanos": "320000000"},
            {"spanID": "s5", "name": "SELECT users", "durationNanos": "2000000"},
            {"spanID": "s6", "name": "SELECT posts", "durationNanos": "1200000"}
          ]
        }
      ]
    }
  ],
  "metrics": {}
}
```

`tests/oddyssey/summarize/fixtures/tempo_search_db.json` — only the DB spans (matched counts are what the code sums):

```json
{
  "traces": [
    {"traceID": "aaa111", "spanSets": [{"matched": 2, "spans": []}]},
    {"traceID": "bbb222", "spanSets": [{"matched": 2, "spans": []}]}
  ],
  "metrics": {}
}
```

- [ ] **Step 2: Write the failing tests**

`tests/oddyssey/summarize/test_report.py`:

```python
import json
from pathlib import Path

import pytest

from oddyssey.summarize.app.errors import EmptyWindowError
from oddyssey.summarize.app.report import summarize

FIXTURES = Path(__file__).parent / "fixtures"


class FakeTempo:
    """Returns the DB fixture for DB queries, the full fixture otherwise."""

    def search(self, query, start, end, limit=500, spans_per_spanset=100):
        name = "tempo_search_db.json" if "db." in query else "tempo_search_all.json"
        return json.loads((FIXTURES / name).read_text())


class FakePrometheus:
    """Maps PromQL substrings to instant-query result vectors."""

    def __init__(self, p95=0.34, requests=200.0, errors=0.0):
        self._answers = [
            ("histogram_quantile", p95),
            ("5..", errors),          # error-count query filters on 5xx codes
            ("_count", requests),
        ]

    def query(self, promql, time):
        for needle, value in self._answers:
            if needle in promql:
                return [{"metric": {}, "value": [time, str(value)]}]
        return []


def test_summarize_builds_compact_report():
    report = summarize("n-plus-one", 100, 400, tempo=FakeTempo(), prometheus=FakePrometheus())

    assert report["odd_version"] == "1"
    assert report["service"] == "n-plus-one"
    assert report["window"] == {"start": 100, "end": 400}
    assert report["metrics"]["http.server.request.duration.p95"] == {"value": 0.34, "unit": "s"}
    assert report["metrics"]["http.server.request.count"] == 200
    assert report["metrics"]["http.server.error.count"] == 0
    assert report["metrics"]["db.client.operation.count"] == 4


def test_top_spans_grouped_by_name_sorted_by_total_duration():
    report = summarize("n-plus-one", 100, 400, tempo=FakeTempo(), prometheus=FakePrometheus())

    assert report["top_spans"][0] == {"name": "GET /users", "count": 2, "total_duration_ms": 660.0}
    assert report["top_spans"][1] == {"name": "SELECT posts", "count": 3, "total_duration_ms": 4.0}
    assert report["top_spans"][2] == {"name": "SELECT users", "count": 1, "total_duration_ms": 2.0}


def test_empty_window_raises():
    with pytest.raises(EmptyWindowError, match="no HTTP requests recorded"):
        summarize("n-plus-one", 100, 400, tempo=FakeTempo(), prometheus=FakePrometheus(requests=0.0))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/oddyssey/summarize/test_report.py -v`
Expected: FAIL with `ImportError: cannot import name 'summarize'` (or module not found).

- [ ] **Step 4: Write `src/oddyssey/summarize/app/report.py`**

```python
"""Aggregate Tempo and Prometheus data into the compact ODD report.

The report is the contract handed to the agent: compact enough for a
context window, versioned, and named after OpenTelemetry semantic
conventions.
"""

from __future__ import annotations

from collections import defaultdict

from oddyssey.summarize.app.errors import EmptyWindowError
from oddyssey.summarize.app.prometheus import PrometheusClient
from oddyssey.summarize.app.tempo import TempoClient

ODD_VERSION = "1"
# Backend-side names, verified against the live stack during the spike
# (docs/superpowers/spike-notes-2026-08-17.md). Output field names below
# follow OTel semantic conventions and are the stable contract.
HTTP_DURATION_METRIC = "http_server_request_duration_seconds"
STATUS_CODE_LABEL = "http_response_status_code"
DB_SPAN_QUERY = '{{resource.service.name="{service}" && span.db.system != nil}}'
ALL_SPAN_QUERY = '{{resource.service.name="{service}"}}'
TOP_SPANS_LIMIT = 5


def _scalar(result: list[dict]) -> float:
    """Sum the values of an instant-query result vector (0.0 when empty)."""
    return sum(float(item["value"][1]) for item in result)


def _matched_count(search_result: dict) -> int:
    return sum(
        span_set.get("matched", 0)
        for trace in search_result.get("traces", [])
        for span_set in trace.get("spanSets", [])
    )


def _top_spans(search_result: dict) -> list[dict]:
    grouped: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_duration_ms": 0.0})
    for trace in search_result.get("traces", []):
        for span_set in trace.get("spanSets", []):
            for span in span_set.get("spans", []):
                entry = grouped[span["name"]]
                entry["count"] += 1
                entry["total_duration_ms"] += int(span["durationNanos"]) / 1e6
    ranked = sorted(grouped.items(), key=lambda item: item[1]["total_duration_ms"], reverse=True)
    return [
        {"name": name, "count": data["count"], "total_duration_ms": round(data["total_duration_ms"], 1)}
        for name, data in ranked[:TOP_SPANS_LIMIT]
    ]


def summarize(
    service: str,
    start: int,
    end: int,
    tempo: TempoClient | None = None,
    prometheus: PrometheusClient | None = None,
) -> dict:
    """Summarize one run of `service` over [start, end] (unix epoch seconds)."""
    tempo = tempo or TempoClient()
    prometheus = prometheus or PrometheusClient()
    window = f"{end - start}s"

    # last_over_time (cumulative read), not increase(): a short run finishes
    # inside one metric-export interval, so the counter's first sample already
    # holds the final value and increase() evaluates to 0/NaN (see the spike
    # notes). Assumes one fresh app process per measured run.
    p95 = _scalar(
        prometheus.query(
            f"histogram_quantile(0.95, sum by (le) "
            f'(last_over_time({HTTP_DURATION_METRIC}_bucket{{job="{service}"}}[{window}])))',
            time=end,
        )
    )
    request_count = _scalar(
        prometheus.query(
            f'sum(last_over_time({HTTP_DURATION_METRIC}_count{{job="{service}"}}[{window}]))',
            time=end,
        )
    )
    error_count = _scalar(
        prometheus.query(
            f"sum(last_over_time({HTTP_DURATION_METRIC}_count"
            f'{{job="{service}", {STATUS_CODE_LABEL}=~"5.."}}[{window}]))',
            time=end,
        )
    )
    if request_count == 0:
        raise EmptyWindowError(
            f"no HTTP requests recorded for service {service!r} between {start} and {end}; "
            "did the load scenario run?"
        )

    db_result = tempo.search(DB_SPAN_QUERY.format(service=service), start, end)
    all_result = tempo.search(ALL_SPAN_QUERY.format(service=service), start, end)

    return {
        "odd_version": ODD_VERSION,
        "service": service,
        "window": {"start": start, "end": end},
        "metrics": {
            "http.server.request.duration.p95": {"value": round(p95, 4), "unit": "s"},
            "http.server.request.count": int(request_count),
            "http.server.error.count": int(error_count),
            "db.client.operation.count": _matched_count(db_result),
        },
        "top_spans": _top_spans(all_result),
    }
```

- [ ] **Step 5: Run the full unit suite**

Run: `uv run pytest tests/ -v`
Expected: 8 tests PASS (5 from Task 4, 3 from this task).

- [ ] **Step 6: Commit**

```bash
git add src/oddyssey/summarize/app/report.py tests/oddyssey/summarize
git commit -m "feat(summarize): add report aggregation"
```

---

### Task 6: Integration test against the live stack

**Files:**
- Test: `tests/oddyssey/summarize/test_integration.py`

**Interfaces:**
- Consumes: `summarize` from Task 5; the demo app and compose stack from Tasks 1-2.
- Produces: a repeatable end-to-end check that the summarizer works against real telemetry.

- [ ] **Step 1: Write `tests/oddyssey/summarize/test_integration.py`**

```python
"""End-to-end check against the live otel-lgtm stack.

Prerequisites (see README):
1. docker compose -f docker-compose/docker-compose.yml up -d
2. seed + run the instrumented demo app
3. run the load scenario within the last 15 minutes

Run with: uv run pytest tests/ -m integration -o addopts=""
"""

import time

import pytest

from oddyssey.summarize.app.report import summarize

pytestmark = pytest.mark.integration


def test_summarize_against_live_stack():
    end = int(time.time())
    start = end - 900

    report = summarize("n-plus-one", start, end)

    assert report["odd_version"] == "1"
    assert report["metrics"]["http.server.request.count"] >= 200
    assert report["metrics"]["http.server.request.duration.p95"]["value"] > 0
    assert report["metrics"]["db.client.operation.count"] > 0
    assert report["top_spans"], "expected at least one aggregated span"
```

- [ ] **Step 2: Verify it is excluded from the default run**

Run: `uv run pytest tests/ -v`
Expected: the integration test shows as deselected; unit tests still pass.

- [ ] **Step 3: Run it for real**

Bring the stack up, seed, run the instrumented N+1 variant, run the load (exact commands in Task 3 Step 2), wait at least 60 seconds for Tempo to make the run searchable (see the spike notes' timing caveat: immediate searches can return stale block data), then:

Run: `uv run pytest tests/ -m integration -o addopts="" -v`
Expected: PASS. Sanity-check the printed/observed values against the spike notes (same order of magnitude). If the test fails on names (empty results), reconcile `report.py` constants with the spike notes — this is the checkpoint that catches any drift.

- [ ] **Step 4: Tear down and commit**

```bash
docker compose -f docker-compose/docker-compose.yml down
git add tests/oddyssey/summarize/test_integration.py
git commit -m "test(summarize): add live-stack integration test"
```

---

### Task 7: README rewrite with measured numbers

**Files:**
- Modify: `README.md` (full rewrite)

**Interfaces:**
- Consumes: measured numbers and conclusion from `docs/superpowers/spike-notes-2026-08-17.md`.
- Produces: the public face of the repo.

- [ ] **Step 1: Rewrite `README.md`**

Use this content, replacing every `{{...}}` token with the value from the spike notes (`{{P95_N1}}`, `{{P95_FIXED}}`, `{{DB_N1}}`, `{{DB_FIXED}}`, and the percentage improvement computed from them). Leaving a token in place is a task failure.

```markdown
# oddyssey

**Observability-driven development for CLI coding agents.**

AI coding agents write code they can't verify. They see stdout and exit
codes — not latency, not error rates, not the N+1 query they just
introduced.

oddyssey closes the loop. It spins up a local OpenTelemetry backend,
instruments your app, replays a scenario, and hands the agent a compact
report it can diff against the previous run: p95 latency, error rate,
query count, top spans. Define a budget, and the agent iterates until
the numbers pass.

No dashboards to read. No cloud account. Just a verdict.

## The idea in 30 seconds

This repo ships a demo FastAPI app with a deliberate N+1 query. In
stdout, both variants look identical: 200 requests, 200 × HTTP 200.
In the telemetry, they don't (numbers measured on this repo's demo,
200 sequential requests, 50 users × 5 posts, SQLite):

| Metric | N+1 (default) | Fixed (`ODD_FIXED=1`) |
| --- | --- | --- |
| p95 latency | {{P95_N1}} s | {{P95_FIXED}} s |
| DB spans per run | {{DB_N1}} | {{DB_FIXED}} |

The target UX (roadmap — the diff/verdict engine is step 3):

```text
$ odd baseline
✓ 200 requests · p95 {{P95_N1}}s · 1 endpoint · {{DB_N1}} db spans

# ... the agent edits the code ...

$ odd diff
✓ p95            {{P95_N1}}s → {{P95_FIXED}}s
✓ db spans       {{DB_N1}} → {{DB_FIXED}}
✗ errors         0 → 2    NEW: TimeoutError in /users
verdict: FAIL (perf-budget: errors must not increase)
```

## Quickstart

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/).

```bash
# 1. Start the local observability backend (Grafana on :3000)
docker compose -f docker-compose/docker-compose.yml up -d

# 2. Seed and run the instrumented demo app
cd examples/n-plus-one
uv run python -m app.seed
env OTEL_SERVICE_NAME=n-plus-one \
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
    OTEL_SEMCONV_STABILITY_OPT_IN=http \
    OTEL_METRIC_EXPORT_INTERVAL=5000 \
    uv run opentelemetry-instrument uvicorn app.main:app --port 8000

# 3. In another terminal: replay the load scenario
cd examples/n-plus-one && uv run python -m app.load

# 4. Summarize the run
cd ../.. && uv run python -c "
import json, time
from oddyssey.summarize.app.report import summarize
end = int(time.time())
print(json.dumps(summarize('n-plus-one', end - 900, end), indent=2))
"
```

Fix the N+1 by restarting the app with `ODD_FIXED=1`, rerun the load,
and compare the reports.

## What exists today

- `examples/n-plus-one` — reproducible demo app; both variants live in
  the same file, toggled by `ODD_FIXED=1`.
- `src/oddyssey/` — the summarizer: queries Tempo and Prometheus over a time
  window and emits a compact JSON report keyed by OpenTelemetry semantic
  conventions.
- `.odd/perf-budget.yml` — the budget format (not enforced yet).

## Roadmap

1. ~~Prove the loop on a real N+1~~ (done — numbers above)
2. ~~Summarizer: raw telemetry → compact report~~ (done)
3. Baseline storage, `diff`, budget verdict, non-zero exit code
4. MCP server + thin per-CLI shells, auto-instrumentation of user
   projects, APM (Agent Package Manager) manifest

## Under the hood

The backend is the [grafana/otel-lgtm](https://github.com/grafana/docker-otel-lgtm)
image (pinned): OpenTelemetry Collector, Tempo (traces), Prometheus
(metrics), Loki (logs), Grafana. The demo app is instrumented with
zero code changes via `opentelemetry-instrument`. The summarizer talks
to the Tempo and Prometheus HTTP APIs on :3200 and :9090.

## Development

```bash
uv run pytest tests/            # unit tests (no Docker needed)
uv run pytest tests/ -m integration -o addopts=""   # needs the stack + a fresh run
```

## License

[MIT](LICENSE)
```

- [ ] **Step 2: Verify no tokens remain and the suite is green**

Run: `grep -n "{{" README.md; uv run pytest tests/`
Expected: grep prints nothing; unit tests pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README with measured spike numbers"
```

- [ ] **Step 4: Suggest GitHub topics to the user**

Not a file change: remind the user to set repo topics `observability`, `opentelemetry`, `ai-agents`, `coding-agents`, `developer-tools`, `mcp`, `performance-regression`.
