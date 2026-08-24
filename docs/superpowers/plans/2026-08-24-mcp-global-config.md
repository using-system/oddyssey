# MCP Global Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A persistent global configuration (`~/.oddyssey/config.json`: stack backend + the three local host ports) with `odd_config_get`/`odd_config_set` MCP tools, honored by every port-bearing code path of the server.

**Architecture:** New `app/config.py` module (tolerant `load`, strict atomic `save`); `stack.py`'s port/URL constants become call-time functions of the loaded config; `odd_config_set` auto-resets the stack when ports change while a container exists (maintainer decision — destruction stays visible via the embedded `services_wiped`); `telemetry.py` reads the OTLP export port once at server startup.

**Tech Stack:** Python 3.12, mcp 2.0 (`MCPServer`, `@mcp.tool()`), httpx 0.28, pytest 9, ruff 0.16.4, Docker (`grafana/otel-lgtm:0.30.2`), MCP Inspector CLI for integration tests.

**Spec:** `docs/superpowers/specs/2026-08-24-mcp-global-config-design.md`

## Global Constraints

- Run unit tests with: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -q`
- Lint/format with exactly: `uvx ruff@0.16.4 check src/mcp-server tests/mcp-server` and `uvx ruff@0.16.4 format src/mcp-server tests/mcp-server` — both must pass before every commit.
- Conventional Commits; never add a breaking-change marker (`!`); end commit bodies with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Never touch anything under `marketplace/` (generated at release; repo CLAUDE.md rule).
- All committed text (code comments, docstrings, docs) in English; comments state constraints, not narration; match the existing file's voice (hyphen dashes, rationale-bearing comments citing issues).
- Telemetry philosophy: nothing here may ever crash the server or write to stdout (stdio is the JSON-RPC wire).
- The container-side ports are fixed (`3000`, `4317`, `4318`); only host-side ports are configurable.
- `stack` values: exactly `grafana`, `azure-monitor`, `cloudwatch`, `datadog`, `dynatrace`, `splunk`; default `grafana`.

---

### Task 1: config module — tolerant load

**Files:**
- Create: `src/mcp-server/app/config.py`
- Test: `tests/mcp-server/test_config.py` (create)

**Interfaces:**
- Consumes: nothing (foundation module).
- Produces: `CONFIG_PATH: Path` (module constant, `Path.home() / ".oddyssey" / "config.json"`, monkeypatchable), `STACKS: tuple[str, ...]`, `DEFAULTS: dict`, and `load(path: Path | None = None) -> dict`. `load` returns `{"stack": str, "local": {"grafana_port": int, "otlp_grpc_port": int, "otlp_http_port": int}}`, plus an `"invalid_ignored": [<dotted field names>]` key ONLY when tolerated-invalid values were found. `path=None` means "use `CONFIG_PATH` at call time".

- [ ] **Step 1: Write the failing tests**

```python
# tests/mcp-server/test_config.py
import json

from oddyssey_mcp import config


def test_load_returns_defaults_when_file_is_missing(tmp_path):
    result = config.load(tmp_path / "config.json")

    assert result == {
        "stack": "grafana",
        "local": {
            "grafana_port": 3000,
            "otlp_grpc_port": 4317,
            "otlp_http_port": 4318,
        },
    }


def test_load_merges_stored_values_over_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"stack": "datadog", "local": {"grafana_port": 3300}}))

    result = config.load(path)

    assert result["stack"] == "datadog"
    assert result["local"]["grafana_port"] == 3300
    assert result["local"]["otlp_grpc_port"] == 4317


def test_load_tolerates_invalid_values_and_flags_them(tmp_path):
    # The file is hand-editable: a broken value must degrade to the
    # default for that field, visibly - never crash a tool call.
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"stack": "nagios", "local": {"grafana_port": "not-a-port"}})
    )

    result = config.load(path)

    assert result["stack"] == "grafana"
    assert result["local"]["grafana_port"] == 3000
    assert sorted(result["invalid_ignored"]) == ["local.grafana_port", "stack"]


def test_load_tolerates_unparseable_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{broken")

    result = config.load(path)

    assert result["stack"] == "grafana"
    assert result["invalid_ignored"] == ["<file>"]


def test_load_has_no_invalid_ignored_key_when_clean(tmp_path):
    assert "invalid_ignored" not in config.load(tmp_path / "config.json")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'oddyssey_mcp.config'` (import error at collection is the expected RED for a new module).

- [ ] **Step 3: Write the minimal implementation**

```python
# src/mcp-server/app/config.py
"""Global oddyssey configuration: one file per machine, like the stack.

One shared container for every project on the machine is the assumed
design (#50 closed not-planned), so the configuration is global too -
user scope, no per-project state. The file is hand-editable: reads are
tolerant (a broken value degrades to its default, visibly), writes are
strict (a rejected partial writes nothing).
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".oddyssey" / "config.json"

# The backends of the observability-cli-guides skill. No "local" value:
# local IS grafana - the specificity lives in the setup-local-stack skill.
STACKS = ("grafana", "azure-monitor", "cloudwatch", "datadog", "dynatrace", "splunk")

DEFAULTS = {
    "stack": "grafana",
    "local": {"grafana_port": 3000, "otlp_grpc_port": 4317, "otlp_http_port": 4318},
}


def _valid_port(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535


def load(path: Path | None = None) -> dict:
    """Effective configuration: defaults overlaid with the stored file.

    Tolerant by contract - the file is hand-editable and a tool call
    must never crash on it. Every tolerated-invalid field is listed in
    "invalid_ignored" (dotted names; "<file>" for unparseable JSON) so
    odd_config_get can surface the degradation.
    """
    target = CONFIG_PATH if path is None else path
    effective = {"stack": DEFAULTS["stack"], "local": dict(DEFAULTS["local"])}
    invalid: list[str] = []
    try:
        stored = json.loads(target.read_text())
    except FileNotFoundError:
        return effective
    except (OSError, ValueError):
        effective["invalid_ignored"] = ["<file>"]
        return effective
    if not isinstance(stored, dict):
        effective["invalid_ignored"] = ["<file>"]
        return effective

    stack = stored.get("stack", DEFAULTS["stack"])
    if stack in STACKS:
        effective["stack"] = stack
    else:
        invalid.append("stack")

    local = stored.get("local", {})
    if isinstance(local, dict):
        for key in DEFAULTS["local"]:
            if key not in local:
                continue
            if _valid_port(local[key]):
                effective["local"][key] = local[key]
            else:
                invalid.append(f"local.{key}")
    elif "local" in stored:
        invalid.append("local")

    if invalid:
        effective["invalid_ignored"] = invalid
    return effective
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_config.py -q`
Expected: 5 passed. Then run the full suite (same command without the file filter) — all pass.

- [ ] **Step 5: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server && uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/app/config.py tests/mcp-server/test_config.py
git commit -m "feat(mcp): global configuration module - tolerant load

Refs #59

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: config module — strict atomic save

**Files:**
- Modify: `src/mcp-server/app/config.py` (append `save`)
- Test: `tests/mcp-server/test_config.py` (append)

**Interfaces:**
- Consumes: Task 1's `load`, `STACKS`, `_valid_port`, `CONFIG_PATH`.
- Produces: `save(partial: dict, path: Path | None = None) -> dict` — deep-merges `partial` into the stored file (NOT into the effective config: unknown stored keys survive, defaults stay implicit), strict-validates BEFORE writing (`ValueError`, nothing written), writes atomically (temp file + `os.replace` in the same directory, parent dir created), returns `load(path)`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/mcp-server/test_config.py
import pytest


def test_save_merges_partial_and_returns_effective(tmp_path):
    path = tmp_path / "config.json"
    config.save({"stack": "datadog"}, path)

    result = config.save({"local": {"grafana_port": 3300}}, path)

    assert result["stack"] == "datadog"
    assert result["local"]["grafana_port"] == 3300
    assert result["local"]["otlp_http_port"] == 4318


def test_save_rejects_unknown_stack_and_writes_nothing(tmp_path):
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="stack"):
        config.save({"stack": "nagios"}, path)
    assert not path.exists()


def test_save_rejects_invalid_port_and_writes_nothing(tmp_path):
    path = tmp_path / "config.json"
    for bad in ({"grafana_port": 0}, {"grafana_port": "3000"}, {"otlp_http_port": 70000}):
        with pytest.raises(ValueError, match="port"):
            config.save({"local": bad}, path)
    assert not path.exists()


def test_save_rejects_colliding_ports(tmp_path):
    # Two signals cannot share one host port; catching it at write time
    # beats a cryptic docker error at the next reset.
    with pytest.raises(ValueError, match="distinct"):
        config.save(
            {"local": {"grafana_port": 4317}}, tmp_path / "config.json"
        )


def test_save_rejects_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="unknown"):
        config.save({"stak": "grafana"}, path)
    with pytest.raises(ValueError, match="unknown"):
        config.save({"local": {"grafana": 3000}}, path)
    assert not path.exists()


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "config.json"
    config.save({"stack": "splunk"}, path)
    assert json.loads(path.read_text())["stack"] == "splunk"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_config.py -q`
Expected: the 6 new tests FAIL with `AttributeError: module ... has no attribute 'save'`; the 5 Task-1 tests still pass.

- [ ] **Step 3: Write the minimal implementation**

```python
# append to src/mcp-server/app/config.py
import os
import tempfile


def save(partial: dict, path: Path | None = None) -> dict:
    """Validated deep-merge into the stored file; a rejected partial writes nothing.

    Strict where load is tolerant: the caller is a tool, not a hand
    edit, so a clear error beats a silent fallback. The merged EFFECTIVE
    ports are validated together, so a partial cannot collide with a
    stored or default port. Atomic write (temp + os.replace) so a
    concurrent MCP server never reads a half-written file.
    """
    target = CONFIG_PATH if path is None else path
    unknown = set(partial) - {"stack", "local"}
    if unknown:
        raise ValueError(f"unknown configuration keys: {sorted(unknown)}")
    if "stack" in partial and partial["stack"] not in STACKS:
        raise ValueError(
            f"stack must be one of {list(STACKS)}, got {partial['stack']!r}"
        )
    local_partial = partial.get("local", {})
    if not isinstance(local_partial, dict):
        raise ValueError("local must be an object of port fields")
    unknown_ports = set(local_partial) - set(DEFAULTS["local"])
    if unknown_ports:
        raise ValueError(f"unknown local keys: {sorted(unknown_ports)}")
    for key, value in local_partial.items():
        if not _valid_port(value):
            raise ValueError(f"{key} must be an integer port in 1-65535, got {value!r}")

    effective_local = {**load(target)["local"], **local_partial}
    if len(set(effective_local.values())) != len(effective_local):
        raise ValueError(f"ports must be pairwise distinct, got {effective_local}")

    try:
        stored = json.loads(target.read_text())
        if not isinstance(stored, dict):
            stored = {}
    except (OSError, ValueError):
        stored = {}
    if "stack" in partial:
        stored["stack"] = partial["stack"]
    if local_partial:
        stored_local = stored.get("local")
        stored["local"] = {
            **(stored_local if isinstance(stored_local, dict) else {}),
            **local_partial,
        }

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(stored, handle, indent=2)
        os.replace(temp, target)
    except BaseException:
        os.unlink(temp)
        raise
    return load(target)
```

(Move the `import os` / `import tempfile` lines up into the module's import block — ruff enforces import placement.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -q`
Expected: full suite passes.

- [ ] **Step 5: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server && uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/app/config.py tests/mcp-server/test_config.py
git commit -m "feat(mcp): global configuration module - strict atomic save

Refs #59

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: stack.py — ports and URLs derived from the configuration

**Files:**
- Modify: `src/mcp-server/app/stack.py`
- Test: `tests/mcp-server/test_stack.py` (modify one test, add one)

**Interfaces:**
- Consumes: Task 1's `config.load()` (no-arg form; tests repoint `config.CONFIG_PATH` via monkeypatch).
- Produces (later tasks and tools rely on these exact names):
  - `local_ports() -> dict` — the `local` block of the loaded config.
  - `grafana_base() -> str` — `http://localhost:<grafana_port>`.
  - `otlp_endpoint() -> str` — `http://localhost:<otlp_grpc_port>`.
  - `otlp_http_ingest() -> str` — `http://localhost:<otlp_http_port>/v1/traces`.
  - Module constants `PROMETHEUS_READY`, `TEMPO_READY`, `LOKI_READY`, `PYROSCOPE_READY`, `TEMPO_SERVICE_NAMES`, `PROMETHEUS_JOB_VALUES`, `LOKI_SERVICE_NAMES`, `GRAFANA_URL`, `OTLP_ENDPOINT`, `OTLP_HTTP_INGEST`, `PORTS` are REMOVED; every internal use goes through the functions. Proxy paths keep their exact strings (e.g. `/api/datasources/proxy/uid/prometheus/-/ready`).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/mcp-server/test_stack.py  (add `from oddyssey_mcp import config`
# to the imports; REMOVE `PORTS` from the `from oddyssey_mcp.stack import (...)` list
# and delete the `PORTS`-related assertions from test_run_args_build_the_pinned_container:
# the mapping assertions move to Task 4's config-driven test)
def test_urls_derive_from_the_configured_ports(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        '{"local": {"grafana_port": 3300, "otlp_grpc_port": 4417, "otlp_http_port": 4418}}'
    )
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    assert stack.grafana_base() == "http://localhost:3300"
    assert stack.otlp_endpoint() == "http://localhost:4417"
    assert stack.otlp_http_ingest() == "http://localhost:4418/v1/traces"
```

Also update `test_run_args_build_the_pinned_container` to stop importing/asserting `PORTS`:

```python
def test_run_args_build_the_pinned_container():
    args = run_args()

    assert args[:2] == ["docker", "run"]
    assert args[-1] == IMAGE
    assert IMAGE == "grafana/otel-lgtm:0.30.2"
    assert CONTAINER_NAME in args
    for mapping in ("3000:3000", "4317:4317", "4318:4318"):
        assert mapping in args
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_stack.py -q`
Expected: the new test FAILS (`AttributeError: ... no attribute 'grafana_base'`); everything else passes.

- [ ] **Step 3: Implement the derivation**

In `src/mcp-server/app/stack.py`:

1. Add `from . import config` to the imports.
2. Delete the constants `PORTS`, `PROMETHEUS_READY`, `TEMPO_READY`, `LOKI_READY`, `PYROSCOPE_READY`, `TEMPO_SERVICE_NAMES`, `PROMETHEUS_JOB_VALUES`, `LOKI_SERVICE_NAMES`, `GRAFANA_URL`, `OTLP_ENDPOINT`, `OTLP_HTTP_INGEST`.
3. Add, below `DEFAULT_ENV` (keep the existing comment about readiness probing through the Grafana proxy, moved onto `_proxy`):

```python
# Container-side ports are fixed by the image; only the host side is
# configurable (issue #59). Ports and URLs are resolved at call time so
# a configuration change is honored without restarting the server.
CONTAINER_PORTS = {"grafana_port": 3000, "otlp_grpc_port": 4317, "otlp_http_port": 4318}


def local_ports() -> dict:
    return config.load()["local"]


def grafana_base() -> str:
    return f"http://localhost:{local_ports()['grafana_port']}"


def otlp_endpoint() -> str:
    return f"http://localhost:{local_ports()['otlp_grpc_port']}"


def otlp_http_ingest() -> str:
    return f"http://localhost:{local_ports()['otlp_http_port']}/v1/traces"


def _proxy(uid: str, path: str) -> str:
    # One request checks both Grafana and the backend behind it, and
    # only Grafana's port needs to be exposed.
    return f"{grafana_base()}/api/datasources/proxy/uid/{uid}{path}"
```

4. Replace every use of a deleted constant:
   - `_probe(client, PROMETHEUS_READY)` → `_probe(client, _proxy("prometheus", "/-/ready"))`
   - `TEMPO_READY` → `_proxy("tempo", "/ready")`; `LOKI_READY` → `_proxy("loki", "/ready")`; `PYROSCOPE_READY` → `_proxy("pyroscope", "/ready")`
   - In `stored_services`: `TEMPO_SERVICE_NAMES` → `_proxy("tempo", "/api/search/tag/service.name/values")`; `LOKI_SERVICE_NAMES` → `_proxy("loki", "/loki/api/v1/label/service_name/values")`; `PROMETHEUS_JOB_VALUES` → `_proxy("prometheus", "/api/v1/label/job/values")`
   - `_otlp_ingest_ready`: `client.post(OTLP_HTTP_INGEST, ...)` → `client.post(otlp_http_ingest(), ...)`
   - `stack_up`'s success dict: `"grafana_url": GRAFANA_URL` → `"grafana_url": grafana_base()`, `"otlp_endpoint": OTLP_ENDPOINT` → `"otlp_endpoint": otlp_endpoint()`
   - `run_args`'s `port_flags`: `[flag for mapping in PORTS for flag in ("-p", mapping)]` → built from `local_ports()` and `CONTAINER_PORTS`:

```python
    ports = local_ports()
    port_flags = [
        flag
        for key, container_port in CONTAINER_PORTS.items()
        for flag in ("-p", f"{ports[key]}:{container_port}")
    ]
```

5. Update the module docstring's "(image pin, name, ports, environment)" phrase to "(image pin, name, environment; host ports come from the global configuration)".

- [ ] **Step 4: Run the full suite**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -q`
Expected: all pass (the existing `stored_services`/`stack_status` tests use `httpx.MockTransport`, which intercepts any URL, so the port change is transparent to them).

- [ ] **Step 5: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server && uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/app/stack.py tests/mcp-server/test_stack.py
git commit -m "feat(mcp): derive stack ports and URLs from the global configuration

Refs #59

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: run_args config ports + stack_up port-mismatch guard

**Files:**
- Modify: `src/mcp-server/app/stack.py`
- Test: `tests/mcp-server/test_stack.py` (add two tests; patch existing `stack_up` tests)

**Interfaces:**
- Consumes: Task 3's `local_ports()`, `CONTAINER_PORTS`, `config.CONFIG_PATH` monkeypatching.
- Produces: `_container_host_ports() -> dict | None` — `{"grafana_port": int, "otlp_grpc_port": int, "otlp_http_port": int}` read from `docker inspect` of the existing container, `None` when the container is absent or unreadable. `stack_up` raises `RuntimeError` mentioning `odd_stack_reset` when the running/stopped container's host ports differ from the configuration.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/mcp-server/test_stack.py
def test_run_args_map_the_configured_host_ports(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        '{"local": {"grafana_port": 3300, "otlp_grpc_port": 4417, "otlp_http_port": 4418}}'
    )
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    args = run_args()

    for mapping in ("3300:3000", "4417:4317", "4418:4318"):
        assert mapping in args


def test_stack_up_fails_fast_on_port_mismatch(tmp_path, monkeypatch):
    # A hand-edited config while a container runs is the one path the
    # auto-reset of odd_config_set cannot close: fail immediately with
    # the remedy, not after a 120 s poll of dead URLs.
    path = tmp_path / "config.json"
    path.write_text('{"local": {"grafana_port": 3300}}')
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(
        stack,
        "_container_host_ports",
        lambda: {"grafana_port": 3000, "otlp_grpc_port": 4317, "otlp_http_port": 4318},
    )

    with pytest.raises(RuntimeError, match="odd_stack_reset"):
        stack.stack_up()
```

Patch the four existing `stack_up` tests (`test_stack_up_reports_env_not_applied_on_an_existing_container`, `test_stack_up_applies_env_when_it_creates_the_container`, `test_stack_up_reports_env_not_applied_on_a_stopped_container`, `test_stack_up_result_shape_is_unchanged_without_env`) by adding one monkeypatch line to each — the guard must see matching ports (or an absent container):

```python
    monkeypatch.setattr(stack, "_container_host_ports", lambda: None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_stack.py -q`
Expected: `test_run_args_map_the_configured_host_ports` PASSES already (Task 3 wired it — that is fine, it pins the behavior); `test_stack_up_fails_fast_on_port_mismatch` FAILS with `AttributeError: ... no attribute '_container_host_ports'`.

- [ ] **Step 3: Implement the guard**

In `src/mcp-server/app/stack.py`:

```python
def _container_host_ports() -> dict | None:
    """Host ports the existing container actually publishes, or None.

    Read from docker inspect so the guard in stack_up can compare them
    with the configuration - best-effort: unreadable means no guard,
    never a blocked start.
    """
    result = _docker(
        "inspect", "--format", "{{json .HostConfig.PortBindings}}", CONTAINER_NAME
    )
    if result.returncode != 0:
        return None
    try:
        bindings = json.loads(result.stdout.strip())
        return {
            key: int(bindings[f"{container_port}/tcp"][0]["HostPort"])
            for key, container_port in CONTAINER_PORTS.items()
        }
    except (ValueError, KeyError, IndexError, TypeError):
        return None
```

(Add `import json` to the module imports.) Then in `stack_up`, right after `state = _container_state()` and before the start/create branches:

```python
    if state != "absent":
        actual = _container_host_ports()
        configured = local_ports()
        if actual is not None and actual != configured:
            raise RuntimeError(
                f"container publishes host ports {actual} but the configuration "
                f"says {configured} - run odd_stack_reset to recreate it on the "
                "configured ports"
            )
```

- [ ] **Step 4: Run the full suite**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -q`
Expected: all pass (including the four patched env tests).

- [ ] **Step 5: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server && uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/app/stack.py tests/mcp-server/test_stack.py
git commit -m "feat(mcp): fail fast when the container ports diverge from the configuration

Refs #59

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: telemetry.py — export endpoint from the configuration at startup

**Files:**
- Modify: `src/mcp-server/app/telemetry.py:27-34` (the `_DEFAULT_ENV` block) and `setup_telemetry`
- Test: `tests/mcp-server/test_telemetry.py` (add one test)

**Interfaces:**
- Consumes: Task 1's `config.load()`.
- Produces: nothing new — behavior only. The exporter is built once at startup; a later port change reaches the server's own telemetry only after an MCP server restart (stated in Task 6's tool description).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/mcp-server/test_telemetry.py (it already imports os,
# telemetry, and uses monkeypatch fixtures - follow the file's existing
# setup/teardown pattern for OTEL_* env isolation)
def test_export_endpoint_follows_the_configured_otlp_port(tmp_path, monkeypatch):
    from oddyssey_mcp import config

    path = tmp_path / "config.json"
    path.write_text('{"local": {"otlp_http_port": 4418}}')
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    shutdown = telemetry.setup_telemetry()
    try:
        assert os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:4418"
    finally:
        shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_telemetry.py -q`
Expected: the new test FAILS — the endpoint is the hardcoded `http://localhost:4318`.

- [ ] **Step 3: Implement**

In `telemetry.py`, remove `"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",` from the module-level `_DEFAULT_ENV` dict, and inside `setup_telemetry`, just before the `for var, value in _DEFAULT_ENV.items():` loop, add:

```python
        from . import config

        # Resolved at startup because the exporter is built once: a
        # changed OTLP port reaches the server's own telemetry after
        # the next MCP server restart (odd_config_set says so).
        os.environ.setdefault(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            f"http://localhost:{config.load()['local']['otlp_http_port']}",
        )
```

(The import lives inside the function alongside the other lazy imports of `setup_telemetry` — module import order in `telemetry.py` is deliberate, everything heavy is deferred.)

- [ ] **Step 4: Run the full suite**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -q`
Expected: all pass.

- [ ] **Step 5: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server && uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/app/telemetry.py tests/mcp-server/test_telemetry.py
git commit -m "feat(mcp): server telemetry exports to the configured OTLP port

Refs #59

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: odd_config_get / odd_config_set tools

**Files:**
- Modify: `src/mcp-server/app/server.py`
- Modify: `README.md` (the MCP tools table — two new rows)
- Test: `tests/mcp-server/test_server.py`

**Interfaces:**
- Consumes: Task 2's `config.load()`/`config.save()`, `stack_ops._container_state()`, `stack_ops.stack_reset()`.
- Produces: tools `odd_config_get() -> dict` (the effective config) and `odd_config_set(config: dict) -> dict` returning `{"config": <effective>}` plus, when a port change hit an existing container, `"stack_reset": <stack_reset() result>` (which carries `services_wiped`).

- [ ] **Step 1: Write the failing tests**

```python
# in tests/mcp-server/test_server.py: add "odd_config_get", "odd_config_set"
# to EXPECTED_TOOLS, and append:
def test_config_set_resets_the_stack_only_on_port_change_with_container(monkeypatch, tmp_path):
    from oddyssey_mcp import config as config_module
    from oddyssey_mcp import server, stack

    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")
    resets: list[int] = []
    monkeypatch.setattr(
        stack, "stack_reset", lambda: resets.append(1) or {"running": True, "services_wiped": []}
    )
    monkeypatch.setattr(stack, "_container_state", lambda: "running")

    # stack change alone: no reset
    result = server.odd_config_set({"stack": "datadog"})
    assert result["config"]["stack"] == "datadog"
    assert "stack_reset" not in result
    assert resets == []

    # port change with a container present: reset embedded
    result = server.odd_config_set({"local": {"grafana_port": 3300}})
    assert result["config"]["local"]["grafana_port"] == 3300
    assert result["stack_reset"]["running"] is True
    assert resets == [1]

    # port change with no container: no reset
    monkeypatch.setattr(stack, "_container_state", lambda: "absent")
    result = server.odd_config_set({"local": {"grafana_port": 3400}})
    assert "stack_reset" not in result
    assert resets == [1]


def test_config_set_description_states_the_wipe_and_the_restart_note():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    description = tools["odd_config_set"].description
    assert "wipe" in description.lower()
    assert "restart" in description.lower()
```

Note for the implementer: `server.odd_config_set` is decorated by `@mcp.tool()`; call the underlying function the same way the existing tests call tools — if the decorator wraps it, use the module-level function reference produced in Step 3 (the `@telemetry.traced_tool`-wrapped callable is directly invocable).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_server.py -q`
Expected: `test_all_stack_tools_registered` FAILS (tool set mismatch) and the two new tests FAIL (`AttributeError: no attribute 'odd_config_set'`).

- [ ] **Step 3: Implement the tools**

In `server.py`, add `from . import config as config_ops` and `from . import stack` is already imported as `stack_ops`; append:

```python
@mcp.tool()
@telemetry.traced_tool
def odd_config_get() -> dict:
    """Read the global oddyssey configuration: stack backend and local stack host ports (defaults applied; invalid stored values are listed in invalid_ignored)."""
    return config_ops.load()


@mcp.tool()
@telemetry.traced_tool
def odd_config_set(config: dict) -> dict:
    """Update the global oddyssey configuration (partial merge).

    config example: {"stack": "datadog"} or {"local": {"grafana_port": 3300}}.
    stack is one of: grafana, azure-monitor, cloudwatch, datadog, dynatrace,
    splunk. Changing a port while a stack container exists RESETS the stack
    immediately so the configuration is always applied: this WIPES all stored
    telemetry machine-wide (the result embeds the reset outcome, including
    services_wiped). The MCP server's own telemetry export honors a changed
    OTLP port only after the MCP server restarts.
    """
    ports_before = config_ops.load()["local"]
    effective = config_ops.save(config)
    result: dict = {"config": effective}
    if (
        effective["local"] != ports_before
        and stack_ops._container_state() != "absent"
    ):
        result["stack_reset"] = stack_ops.stack_reset()
    return result
```

Add the two README rows to the MCP tools table (guide voice, matching the existing rows):

```markdown
| `odd_config_get` | Read the global configuration — stack backend and local host ports |
| `odd_config_set` | Update it — `config` (partial merge); a port change resets the stack to apply immediately |
```

- [ ] **Step 4: Run the full suite**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -q`
Expected: all pass.

- [ ] **Step 5: Lint, format, commit**

```bash
uvx ruff@0.16.4 format src/mcp-server tests/mcp-server && uvx ruff@0.16.4 check src/mcp-server tests/mcp-server
git add src/mcp-server/app/server.py tests/mcp-server/test_server.py README.md
git commit -m "feat(mcp): odd_config_get and odd_config_set tools

A port change while a container exists resets the stack immediately
(maintainer decision) - the destruction stays visible: the result
embeds the reset outcome with services_wiped.

Refs #59

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: integration test — configured port end to end

**Files:**
- Create: `integration-tests/mcp-server/test-stack-config.sh` (chmod +x)

**Interfaces:**
- Consumes: `lib.sh`'s `mcp_call <tool> [key=json-value]...`, `assert_result_contains`, `step`; the tools from Task 6.

- [ ] **Step 1: Write the test**

```bash
#!/usr/bin/env bash
# Global configuration end to end (#59): a port change through
# odd_config_set auto-resets the stack onto the new ports, Grafana and
# OTLP answer there, and defaults are restored afterwards. The config
# file is backed up/restored so a developer machine is left untouched.

source "$(dirname "$0")/lib.sh"

workdir=$(mktemp -d)
CONFIG_FILE="$HOME/.oddyssey/config.json"
restore() {
  rm -rf "$workdir"
  if [ -f "$workdir_backup_flag" ]; then
    mv "$workdir_backup" "$CONFIG_FILE" 2>/dev/null || true
  else
    rm -f "$CONFIG_FILE"
  fi
}
workdir_backup="$workdir/config.json.bak"
workdir_backup_flag="$workdir/had-config"
if [ -f "$CONFIG_FILE" ]; then
  cp "$CONFIG_FILE" "$workdir_backup" && touch "$workdir_backup_flag"
fi
trap restore EXIT

step "start the stack on default ports"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_stack_up > "$workdir/up.json"
assert_result_contains "$workdir/up.json" '"running": true'

step "odd_config_get returns the defaults"
mcp_call odd_config_get > "$workdir/get.json"
assert_result_contains "$workdir/get.json" '"grafana_port": 3000'
assert_result_contains "$workdir/get.json" '"stack": "grafana"'

step "changing the grafana port auto-resets onto the new port"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_config_set 'config={"local":{"grafana_port":3300}}' > "$workdir/set.json"
assert_result_contains "$workdir/set.json" '"grafana_port": 3300'
assert_result_contains "$workdir/set.json" 'services_wiped'
test "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3300/api/datasources/proxy/uid/prometheus/-/ready)" = "200"
test "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/api/datasources/proxy/uid/prometheus/-/ready)" != "200"

step "restore default ports (auto-resets back)"
MCP_SERVER_REQUEST_TIMEOUT="${MCP_SERVER_REQUEST_TIMEOUT:-420000}" \
  mcp_call odd_config_set 'config={"local":{"grafana_port":3000}}' > "$workdir/restore.json"
assert_result_contains "$workdir/restore.json" '"grafana_port": 3000'

step "tear down"
mcp_call odd_stack_down > "$workdir/down.json"
assert_result_contains "$workdir/down.json" '"running": false'

echo "stack config: OK"
```

- [ ] **Step 2: Verify locally what is non-destructive**

Run: `bash -n integration-tests/mcp-server/test-stack-config.sh` (syntax) and `chmod +x integration-tests/mcp-server/test-stack-config.sh`. Do NOT run the full script on a developer machine that has a live stack with data — CI's clean runner executes it (run.sh picks up `test-*.sh` automatically).

- [ ] **Step 3: Commit**

```bash
git add integration-tests/mcp-server/test-stack-config.sh
git commit -m "test(mcp): integration test for the global configuration port flow

Refs #59

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
