# odd_stack_status Identity Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `odd_stack_status` returns the container's identity — image
tag, created/started timestamps, user-set env (credential values
redacted to null) — alongside the unchanged readiness booleans, so a
report's `instance` identity needs no external `docker inspect`.

**Architecture:** One new best-effort helper reads identity in a
single inspect; `env` reuses `container_user_env()`; the probe-only
body splits into `_readiness()` so `stack_up`'s 2-second boot polling
never pays the inspects. TDD against the existing test style
(`httpx.MockTransport` for probes, `monkeypatch` on `_docker` /
`container_user_env` for docker).

**Tech Stack:** Python 3 (uv project `src/mcp-server`), pytest,
httpx MockTransport; docs in the repo's markdown register.

**Spec:** `docs/superpowers/specs/2026-08-29-stack-status-identity-design.md`
(implements issue #118 — the PR carries `Closes #118`).

## Global Constraints

- **stdout is the JSON-RPC wire** — nothing may print to stdout; all
  docker access through the existing `_docker()` helper.
- **Telemetry never breaks a tool; tool registration must not change**
  (instrumentation spec §2 — the unit tests assert the exact tool set).
- Identity reads are **best-effort**: unreadable inspect → `null`
  fields, never an exception out of `stack_status`.
- The five existing booleans keep their names and semantics.
- Redaction rule: a key matching the existing `_sensitive_env()`
  heuristic keeps its name, value becomes `None`. Absent container:
  `image`/`created`/`started`/`env` all `None` (`env` is `None`, not
  `{}`).
- `created`/`started` are docker's strings verbatim — no parsing.
- English everywhere; Conventional Commits; no `!` marker; run what CI
  runs before handing back (`uv run --project src/mcp-server pytest -c
  src/mcp-server/pyproject.toml tests/mcp-server -v`, then
  `uvx ruff@0.16.4 check src/mcp-server tests/mcp-server` and
  `uvx ruff@0.16.4 format --check src/mcp-server tests/mcp-server`).
- `marketplace/`, `.claude-plugin/`, `.agents/plugins/` untouched.

---

### Task 1: identity fields in `stack_status` (code + unit tests, TDD)

**Files:**
- Modify: `src/mcp-server/app/stack.py` (the `stack_status` region,
  lines ~301-315 pre-change)
- Test: `tests/mcp-server/test_stack.py`

**Interfaces:**
- Consumes: existing `_docker()`, `container_user_env()`,
  `_sensitive_env()` — all unchanged.
- Produces: `_readiness(transport) -> dict` (the five booleans),
  `_container_identity() -> dict | None` (keys `image`, `created`,
  `started`, or `None` when unreadable/absent), and the enriched
  public `stack_status(transport) -> dict`. `stack_up`'s wait loop
  and its initial probe switch to `_readiness()`.

- [ ] **Step 1: Read the existing tests** for `stack_status`
  (`tests/mcp-server/test_stack.py:78-120`) and the monkeypatch style
  used elsewhere in the file — new tests must match it.

- [ ] **Step 2: Write the failing tests** (add to
  `tests/mcp-server/test_stack.py`; adapt fixture names to the file's
  conventions — the bodies below are the required assertions):

```python
def _identity_docker(monkeypatch, *, inspect_json=None, returncode=0):
    """Route stack._docker: identity inspect answers inspect_json."""
    def fake_docker(*args):
        return subprocess.CompletedProcess(
            args, returncode, stdout=inspect_json or "", stderr=""
        )
    monkeypatch.setattr(stack, "_docker", fake_docker)


def test_stack_status_carries_container_identity(monkeypatch):
    _identity_docker(
        monkeypatch,
        inspect_json='{"image": "grafana/otel-lgtm:0.31.0",'
        ' "created": "2026-08-29T08:12:03.1Z",'
        ' "started": "2026-08-29T08:12:04.5Z"}',
    )
    monkeypatch.setattr(
        stack, "container_user_env", lambda: {"GF_LOG_LEVEL": "debug"}
    )
    handler = lambda request: httpx.Response(200)
    status = stack_status(transport=httpx.MockTransport(handler))
    assert status["running"] is True
    assert status["image"] == "grafana/otel-lgtm:0.31.0"
    assert status["created"] == "2026-08-29T08:12:03.1Z"
    assert status["started"] == "2026-08-29T08:12:04.5Z"
    assert status["env"] == {"GF_LOG_LEVEL": "debug"}


def test_stack_status_absent_container_yields_null_identity(monkeypatch):
    _identity_docker(monkeypatch, returncode=1)
    monkeypatch.setattr(stack, "container_user_env", lambda: None)
    handler = lambda request: httpx.Response(500)
    status = stack_status(transport=httpx.MockTransport(handler))
    assert status["running"] is False
    assert status["image"] is None
    assert status["created"] is None
    assert status["started"] is None
    assert status["env"] is None


def test_stack_status_redacts_credential_named_env_values(monkeypatch):
    _identity_docker(
        monkeypatch,
        inspect_json='{"image": "i", "created": "c", "started": "s"}',
    )
    monkeypatch.setattr(
        stack,
        "container_user_env",
        lambda: {"GF_LOG_LEVEL": "debug", "X_DEMO_TOKEN": "fake"},
    )
    handler = lambda request: httpx.Response(200)
    status = stack_status(transport=httpx.MockTransport(handler))
    assert status["env"] == {"GF_LOG_LEVEL": "debug", "X_DEMO_TOKEN": None}


def test_stack_status_survives_malformed_inspect_output(monkeypatch):
    _identity_docker(monkeypatch, inspect_json="not json")
    monkeypatch.setattr(stack, "container_user_env", lambda: None)
    handler = lambda request: httpx.Response(200)
    status = stack_status(transport=httpx.MockTransport(handler))
    assert status["running"] is True
    assert status["image"] is None and status["env"] is None


def test_stack_up_boot_polling_never_reads_identity(monkeypatch):
    """The wait loop uses the probe-only readiness, not the enriched status."""
    calls = []
    monkeypatch.setattr(
        stack,
        "_docker",
        lambda *a: calls.append(a)
        or subprocess.CompletedProcess(a, 1, stdout="", stderr=""),
    )
    # _readiness must not touch docker at all:
    handler = lambda request: httpx.Response(200)
    ready = stack._readiness(transport=httpx.MockTransport(handler))
    assert ready == {
        "running": True,
        "prometheus": True,
        "tempo": True,
        "loki": True,
        "pyroscope": True,
    }
    assert calls == []
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_stack.py -v -k "identity or redacts or malformed or boot_polling"`
Expected: FAIL (`stack_status` has no identity fields; `_readiness`
does not exist).

- [ ] **Step 4: Implement in `src/mcp-server/app/stack.py`:**

```python
def _container_identity() -> dict | None:
    """Image tag and lifecycle timestamps of the existing container, or None.

    One inspect, best-effort like container_user_env: an absent
    container or unreadable output yields None, never an error - a
    status call must not fail because docker hiccupped.
    """
    result = _docker(
        "inspect",
        "--format",
        '{"image": {{json .Config.Image}}, "created": {{json .Created}},'
        ' "started": {{json .State.StartedAt}}}',
        CONTAINER_NAME,
    )
    if result.returncode != 0:
        return None
    try:
        parsed = json.loads(result.stdout.strip())
    except ValueError:
        return None
    if not all(isinstance(parsed.get(k), str) for k in ("image", "created", "started")):
        return None
    return {k: parsed[k] for k in ("image", "created", "started")}


def _readiness(transport: httpx.BaseTransport | None = None) -> dict:
    """Probe readiness endpoints; a down stack is a status, not an error.

    All four signal backends are probed (issue #36): gating on a subset
    only covers the others by boot-timing coincidence. Probe-only on
    purpose: stack_up polls this every 2 s, and the identity inspects of
    the full status would tax every boot trace for data the loop never
    reads.
    """
    with httpx.Client(timeout=3.0, transport=transport) as client:
        signals = {
            "prometheus": _probe(client, _proxy("prometheus", "/-/ready")),
            "tempo": _probe(client, _proxy("tempo", "/ready")),
            "loki": _probe(client, _proxy("loki", "/ready")),
            "pyroscope": _probe(client, _proxy("pyroscope", "/ready")),
        }
    return {"running": all(signals.values()), **signals}


def stack_status(transport: httpx.BaseTransport | None = None) -> dict:
    """Readiness plus the container's identity (issue #118).

    image/created/started come from one inspect, env from
    container_user_env() with credential-named values redacted to None
    (the name closes the visibility gap - observation finding N3 - the
    value never leaves the server). Absent or unreadable container:
    all four identity fields are None (env included - "no container"
    and "no user env" are different facts).
    """
    identity = _container_identity()
    user_env = container_user_env()
    env = (
        {k: (None if _sensitive_env(k) else v) for k, v in user_env.items()}
        if user_env is not None
        else None
    )
    return {
        **_readiness(transport),
        "image": identity["image"] if identity else None,
        "created": identity["created"] if identity else None,
        "started": identity["started"] if identity else None,
        "env": env,
    }
```

  Then switch `stack_up`'s two status uses to the probe-only helper:
  line ~383 `status = stack_status()` → `status = _readiness()` and
  line ~413 likewise (the loop only reads `status["running"]`; the
  timeout error message keeps working — it formats the readiness
  dict). `stack_reset`'s "stopped" boot path calls `stack_up()` and
  needs no change.

- [ ] **Step 5: Run the new tests to verify they pass**

Run: the Step 3 command. Expected: PASS.

- [ ] **Step 6: Run the whole suite + lint like CI**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v`
then `uvx ruff@0.16.4 check src/mcp-server tests/mcp-server` and
`uvx ruff@0.16.4 format --check src/mcp-server tests/mcp-server`.
Expected: all pass, output pristine. Existing `stack_status` tests
(`test_stack.py:78-120`) will now hit docker paths — if they fail
because `_docker` is unmocked, patch THOSE tests minimally (add the
identity monkeypatches) rather than weakening the implementation;
their boolean assertions must stay untouched.

- [ ] **Step 7: Check the integration driver** — read
  `integration-tests/mcp-server/run.sh` and any script it invokes for
  assertions on the `odd_stack_status` result shape; extend the
  assertion (not the scenario) if it pins exact keys. If nothing pins
  the shape, state so in your report and change nothing.

- [ ] **Step 8: Commit**

```bash
git add src/mcp-server/app/stack.py tests/mcp-server/test_stack.py
git commit -m "feat(mcp): odd_stack_status returns the container identity - image, timestamps, and redacted user env"
```

(Include `integration-tests/` in the add only if Step 7 changed it.)

### Task 2: tool docstring + docs sync

**Files:**
- Modify: `src/mcp-server/app/server.py` (the `odd_stack_status`
  docstring only)
- Modify: `README.md` (MCP tools table row for `odd_stack_status`,
  line ~292)

**Interfaces:**
- Consumes: Task 1's shipped result shape.

- [ ] **Step 1: Update the tool docstring** — it is the tool's
  user-facing description; keep it one line in the file's style, e.g.:
  `"""Check whether the local LGTM stack is up (Prometheus, Tempo, Loki, and Pyroscope ready) - plus the container's identity: image tag, created/started timestamps, and user-set env (credential-named values redacted)."""`

- [ ] **Step 2: Update the README MCP tools row** — from
  `| `odd_stack_status` | Probe whether it is up | — |` to a
  register-matched description mentioning the identity fields, e.g.
  `Probe whether it is up; returns the container identity too (image, created/started, user-set env - credential values redacted)`.
  Check `docs/guide/dependencies.md` needs nothing: the tool nodes
  carry names only, no behavior text (verified at planning — restate
  the check in your report).

- [ ] **Step 3: Run the unit suite once** (the docstring lives in
  asserted-tool-set territory — prove nothing broke):
  `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v`. Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/mcp-server/app/server.py README.md
git commit -m "docs(readme): odd_stack_status row and docstring say what the identity fields carry"
```
