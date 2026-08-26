# /odd-config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user-facing `/odd-config` prompt that displays the effective backend configuration and guides backend changes, backed by a per-stack `stack_config` persisted in the global MCP configuration.

**Architecture:** Four layers, built bottom-up: (1) the MCP `config.py` gains a `stack_config` per-stack payload with the same tolerant-read / strict-write contract as the rest of the file (#59); (2) `observability-cli-guides` references each name their CLI binary, its detection procedure, and install steps; (3) `check-backend-configuration` gains per-backend display references and the new `update-backend-configuration` skill owns the backend switch; (4) the `/odd-config` prompt composes both skills into the user entry point.

**Tech Stack:** Python 3.12 (`src/mcp-server`, package `oddyssey_mcp` mapped from `app/`), pytest, ruff 0.16.4, APM markdown skills/prompts under `.apm/`.

**Spec:** GitHub issue #70 (https://github.com/using-system/oddyssey/issues/70) — this plan restates every contract it implements; when in doubt the issue wins.

## Global Constraints

- All committed text is English (skills, prompts, comments, commit messages).
- Conventional Commits; no breaking markers (`!`) on any commit or title.
- `marketplace/` is a build artifact — never edit it; author only in `.apm/`.
- No secret values anywhere: `stack_config` holds identifiers, names, regions — credentials stay in the CLI's own auth store, referenced by name only.
- Lint/format must pass: `uvx ruff@0.16.4 check src/mcp-server tests/mcp-server` and `uvx ruff@0.16.4 format --check src/mcp-server tests/mcp-server`.
- Unit tests run as: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v` (verified working from the repo root).
- Prose style of `.apm/` files: plain hyphens, ~72-column wrap, terse contract prose like the existing skills.
- The seven stack values are exactly: `local`, `grafana`, `azure-monitor`, `cloudwatch`, `datadog`, `dynatrace`, `splunk` (constant `STACKS` in `app/config.py`).

---

### Task 1: `stack_config` in the MCP configuration (TDD)

**Files:**
- Modify: `src/mcp-server/app/config.py`
- Modify: `src/mcp-server/app/server.py:88-117` (the two config tool docstrings only)
- Test: `tests/mcp-server/test_config.py`

**Interfaces:**
- Consumes: existing `config.load(path) -> dict`, `config.save(partial, path) -> dict`, `STACKS`, `DEFAULTS`.
- Produces: `load()` result always carries `"stack_config": dict` (empty `{}` when nothing stored); `save()` accepts a third top-level key `"stack_config"`: `{<stack value>: {<key>: str|int|float|bool}}`, shallow-merged **per stack** so writing one stack's payload never touches another stack's. Tasks 3-5 rely on `odd_config_get` returning `stack_config` and `odd_config_set` persisting `{"stack_config": {...}}`.

**Contract being implemented (from the issue):** `odd_config_set` accepts and persists a per-stack `stack_config` payload keyed by stack value so switching back and forth does not lose the other stack's config; `odd_config_get` returns it; tolerant-read / strict-write like the rest of `config.py` — a broken stored value degrades visibly (`invalid_ignored`), a rejected partial writes nothing. `stack_config` changes never boot or reset the stack container (only `local` port changes do — the existing `will_change_ports` logic in `server.py` reads only `config.get("local")` and must stay that way).

- [ ] **Step 1: Write the failing tests**

Append to `tests/mcp-server/test_config.py` (style mirrors the existing tests — bare functions, `tmp_path`, exact asserts):

```python
def test_load_returns_empty_stack_config_by_default(tmp_path):
    result = config.load(tmp_path / "config.json")
    assert result["stack_config"] == {}


def test_save_persists_stack_config_and_load_returns_it(tmp_path):
    path = tmp_path / "config.json"
    config.save(
        {"stack_config": {"azure-monitor": {"workspace": "guid-123", "port": 443}}},
        path,
    )
    result = config.load(path)
    assert result["stack_config"] == {
        "azure-monitor": {"workspace": "guid-123", "port": 443}
    }


def test_save_stack_config_is_non_destructive_across_stacks(tmp_path):
    # Switching back and forth must not lose the other stack's config.
    path = tmp_path / "config.json"
    config.save({"stack_config": {"azure-monitor": {"workspace": "guid-123"}}}, path)
    config.save({"stack_config": {"cloudwatch": {"region": "eu-west-1"}}}, path)
    result = config.save(
        {"stack_config": {"azure-monitor": {"resource_group": "rg-obs"}}}, path
    )
    assert result["stack_config"] == {
        "azure-monitor": {"workspace": "guid-123", "resource_group": "rg-obs"},
        "cloudwatch": {"region": "eu-west-1"},
    }


def test_save_rejects_stack_config_for_unknown_stack(tmp_path):
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="stack_config"):
        config.save({"stack_config": {"nagios": {"url": "x"}}}, path)
    assert not path.exists()


def test_save_rejects_non_dict_stack_config_shapes(tmp_path):
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="stack_config"):
        config.save({"stack_config": ["azure-monitor"]}, path)
    with pytest.raises(ValueError, match="stack_config"):
        config.save({"stack_config": {"grafana": "not-a-dict"}}, path)
    assert not path.exists()


def test_save_rejects_non_scalar_stack_config_values(tmp_path):
    # Values are identifiers, names, regions - flat scalars only.
    path = tmp_path / "config.json"
    for bad in ({"nested": {"a": 1}}, {"listed": [1, 2]}, {"none": None}):
        with pytest.raises(ValueError, match="stack_config"):
            config.save({"stack_config": {"grafana": bad}}, path)
    assert not path.exists()


def test_load_tolerates_broken_stack_config_and_flags_it(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "stack_config": {
                    "nagios": {"url": "x"},
                    "grafana": "not-a-dict",
                    "azure-monitor": {"workspace": "guid-123", "bad": None},
                }
            }
        )
    )
    result = config.load(path)
    assert result["stack_config"] == {"azure-monitor": {"workspace": "guid-123"}}
    assert sorted(result["invalid_ignored"]) == [
        "stack_config.azure-monitor.bad",
        "stack_config.grafana",
        "stack_config.nagios",
    ]


def test_load_tolerates_non_dict_stack_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"stack_config": "broken"}))
    result = config.load(path)
    assert result["stack_config"] == {}
    assert result["invalid_ignored"] == ["stack_config"]
```

Also update the existing defaults test — the effective shape gains the key:

```python
def test_load_returns_defaults_when_file_is_missing(tmp_path):
    result = config.load(tmp_path / "config.json")

    assert result == {
        "stack": "local",
        "local": {
            "grafana_port": 3000,
            "otlp_grpc_port": 4317,
            "otlp_http_port": 4318,
        },
        "stack_config": {},
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server/test_config.py -v`
Expected: the new tests FAIL (KeyError `stack_config` / no ValueError raised); the untouched old tests still pass.

- [ ] **Step 3: Implement in `app/config.py`**

Add to `DEFAULTS`:

```python
DEFAULTS = {
    "stack": "local",
    "local": {"grafana_port": 3000, "otlp_grpc_port": 4317, "otlp_http_port": 4318},
    "stack_config": {},
}
```

Add the scalar predicate next to `_valid_port`:

```python
def _valid_config_value(value: object) -> bool:
    # Identifiers, names, regions, ports - flat scalars only, and never
    # secrets (credentials stay in the CLI's own auth store, by name).
    return isinstance(value, (str, int, float, bool))
```

In `load()`, initialize `effective` with `"stack_config": {}` and after the `local` block add the tolerant read:

```python
    raw_sc = stored.get("stack_config", {})
    if isinstance(raw_sc, dict):
        for stack_key, payload in raw_sc.items():
            if stack_key not in STACKS or not isinstance(payload, dict):
                invalid.append(f"stack_config.{stack_key}")
                continue
            clean = {}
            for key, value in payload.items():
                if _valid_config_value(value):
                    clean[key] = value
                else:
                    invalid.append(f"stack_config.{stack_key}.{key}")
            effective["stack_config"][stack_key] = clean
    elif "stack_config" in stored:
        invalid.append("stack_config")
```

In `save()`, extend the unknown-keys guard to `{"stack", "local", "stack_config"}`, validate strictly before any write:

```python
    sc_partial = partial.get("stack_config", {})
    if not isinstance(sc_partial, dict):
        raise ValueError("stack_config must be an object keyed by stack")  # noqa: TRY004
    for stack_key, payload in sc_partial.items():
        if stack_key not in STACKS:
            raise ValueError(
                f"stack_config keys must be one of {list(STACKS)}, got {stack_key!r}"
            )
        if not isinstance(payload, dict):
            raise ValueError(  # noqa: TRY004
                f"stack_config.{stack_key} must be an object of scalar values"
            )
        for key, value in payload.items():
            if not _valid_config_value(value):
                raise ValueError(
                    f"stack_config.{stack_key}.{key} must be a string, number,"
                    f" or boolean, got {value!r}"
                )
```

and merge per stack into `stored` (after the existing `local` merge):

```python
    if sc_partial:
        stored_sc = stored.get("stack_config")
        stored_sc = stored_sc if isinstance(stored_sc, dict) else {}
        for stack_key, payload in sc_partial.items():
            existing = stored_sc.get(stack_key)
            stored_sc[stack_key] = {
                **(existing if isinstance(existing, dict) else {}),
                **payload,
            }
        stored["stack_config"] = stored_sc
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v`
Expected: ALL tests pass (the full file, not only test_config.py — `test_server.py` asserts tool behavior that must not drift).

- [ ] **Step 5: Update the two tool docstrings in `app/server.py`**

`odd_config_get` (line 91): append to the one-line docstring: `Also returns stack_config: per-stack non-secret targeting values (identifiers, names, regions) persisted for each backend.`

`odd_config_set` (lines 98-117): in the `config example` sentence add `or {"stack_config": {"azure-monitor": {"workspace": "<guid>"}}}` and append one sentence: `stack_config is merged per stack (other stacks' payloads are untouched) and never boots or resets the stack container; values must be non-secret scalars - credentials stay in the CLI's own auth store, referenced by name only.`

No behavioral change in `odd_config_set`'s body: `will_change_ports` reads `config.get("local")` only and already ignores `stack_config`.

- [ ] **Step 6: Lint, format, full test run**

Run: `uvx ruff@0.16.4 check src/mcp-server tests/mcp-server && uvx ruff@0.16.4 format --check src/mcp-server tests/mcp-server && uv run --project src/mcp-server pytest -c src/mcp-server/pyproject.toml tests/mcp-server -v`
Expected: clean lint, clean format, all tests pass. If `format --check` fails, run `uvx ruff@0.16.4 format src/mcp-server tests/mcp-server` and re-check.

- [ ] **Step 7: Commit**

```bash
git add src/mcp-server/app/config.py src/mcp-server/app/server.py tests/mcp-server/test_config.py
git commit -m "feat(mcp): per-stack stack_config in the global configuration

odd_config_set persists a stack_config payload keyed by stack value -
shallow-merged per stack so switching backends never loses another
stack's config - and odd_config_get returns it. Same contract as the
rest of config.py (#59): tolerant read (broken entries degrade visibly
into invalid_ignored), strict write (a rejected partial writes
nothing). Values are flat non-secret scalars; stack_config changes
never touch the stack container."
```

---

### Task 2: CLI binary, detection, and install steps in every `observability-cli-guides` reference

**Files:**
- Modify: `.apm/skills/observability-cli-guides/references/grafana.md`
- Modify: `.apm/skills/observability-cli-guides/references/datadog.md`
- Modify: `.apm/skills/observability-cli-guides/references/dynatrace.md`
- Modify: `.apm/skills/observability-cli-guides/references/azure-monitor.md`
- Modify: `.apm/skills/observability-cli-guides/references/cloudwatch.md`
- Modify: `.apm/skills/observability-cli-guides/references/splunk.md`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: each reference opens with a `## CLI binary` section that Task 4's `update-backend-configuration` skill relies on for its presence preflight. Fixed section shape (three bold entries): **Binary** (the executable name), **Detect** (the exact shell test), **Install** (the commands or the linked install doc already present in the file).

Insert the section right after the reference's title/intro block, before its Setup table. Exact content per file (keep each file's existing prose untouched; where an Install row already exists in the Setup table, the new section cites the same methods in one line and the table row stays):

`grafana.md`:

```markdown
## CLI binary

- **Binary**: `gcx`
- **Detect**: `command -v gcx` (non-empty path = installed; `which -a gcx`
  flags duplicate installs)
- **Install**: `brew install gcx`, or the official install script /
  prebuilt binaries — see the Install row below (installation.md link).
```

`datadog.md`:

```markdown
## CLI binary

- **Binary**: `pup`
- **Detect**: `command -v pup`
- **Install**: `brew tap datadog-labs/pack && brew install
  datadog-labs/pack/pup`, a prebuilt release binary, or `cargo build
  --release` from source — see the Install row below (pup README link).
```

`dynatrace.md`:

```markdown
## CLI binary

- **Binary**: `dtctl`
- **Detect**: `command -v dtctl`
- **Install**: `brew install dynatrace-oss/tap/dtctl`, or the install.sh
  script, or a release binary — see the install row below
  (INSTALLATION.md link). Raw DQL over curl is the documented no-CLI
  fallback for queries, but the skills below still require the binary.
```

`azure-monitor.md`:

```markdown
## CLI binary

- **Binary**: `az`
- **Detect**: `command -v az`
- **Install**: `brew install azure-cli` (macOS) or the official installer
  per platform: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
  — the `log-analytics`/`application-insights` extensions auto-install on
  first use.
```

`cloudwatch.md`:

```markdown
## CLI binary

- **Binary**: `aws`
- **Detect**: `command -v aws`
- **Install**: `brew install awscli` (macOS) or the official AWS CLI v2
  installer per platform:
  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
```

`splunk.md`:

```markdown
## CLI binary

- **Binary**: `splunk` — ships WITH the Splunk Enterprise/Cloud instance
  (`$SPLUNK_HOME/bin/splunk`), it is not separately installable.
- **Detect**: `command -v splunk || test -x "$SPLUNK_HOME/bin/splunk"`
- **Install**: installing Splunk Enterprise provides it:
  https://help.splunk.com/en/data-management/splunk-enterprise-admin-manual —
  for a remote instance, run the CLI on the instance or remotely with
  `-uri`; there is no standalone client package.
```

- [ ] **Step 1: Insert the six sections exactly as above** (adjust only line wrapping to the file's column width; do not touch existing content).
- [ ] **Step 2: Verify** — `grep -l "## CLI binary" .apm/skills/observability-cli-guides/references/*.md` lists all six files; read each diff hunk to confirm placement after the intro, before Setup.
- [ ] **Step 3: Commit**

```bash
git add .apm/skills/observability-cli-guides/references
git commit -m "feat(skill): name each backend CLI binary with its detection and install steps

update-backend-configuration's presence preflight needs a mechanical
answer to 'is this backend's CLI installed' - each reference now opens
with the binary name, the exact detect command, and the install path,
sourced from the install links the references already carry."
```

---

### Task 3: per-backend display references in `check-backend-configuration`

**Files:**
- Create: `.apm/skills/check-backend-configuration/references/local.md`
- Create: `.apm/skills/check-backend-configuration/references/grafana.md`
- Create: `.apm/skills/check-backend-configuration/references/azure-monitor.md`
- Create: `.apm/skills/check-backend-configuration/references/cloudwatch.md`
- Create: `.apm/skills/check-backend-configuration/references/datadog.md`
- Create: `.apm/skills/check-backend-configuration/references/dynatrace.md`
- Create: `.apm/skills/check-backend-configuration/references/splunk.md`
- Modify: `.apm/skills/check-backend-configuration/SKILL.md`

**Interfaces:**
- Consumes: `odd_config_get` returning `stack`, `local` ports, and `stack_config` (Task 1); the `## CLI binary` sections (Task 2).
- Produces: a display contract per backend that Task 5's `/odd-config` prompt invokes through this skill. Each reference answers: what to display, where each value comes from, the connection proof, and one example change-request phrasing.

Each reference follows this fixed skeleton (SKILL.md step 2 will point here):

```markdown
# <Backend> — configuration display

## Display

<what to show and the exact source of each value>

## Connection proof

<the cheapest probe command and what success looks like>

## Change-request phrasing

<one or two literal example sentences the user can say>
```

Exact content decisions per file (write full prose in the skeleton, house style):

- `local.md` — Display: the configured host ports from `odd_config_get` (`local.grafana_port`, `local.otlp_grpc_port`, `local.otlp_http_port`), rendered as the Grafana URL (`http://localhost:<grafana_port>`) and both OTLP endpoints — **all resolved via `odd_config_get`, never hardcoded**; plus `stack_config.local` when present (the container env to reapply on reset, names shown, values only if non-secret by the stored contract) and any `invalid_ignored` degradations. Connection proof: `gcx config check` against the isolated context of the `setup-local-stack` skill (that skill owns the local method). Change-request phrasing: `"set the local Grafana port to 3001"` / `"change otlp_http_port to 4319"`.
- `grafana.md` — Display: `gcx config list-contexts` and the active context's server/org from `gcx config view` (which instance the queries will hit); `stack_config.grafana` is expected empty — the gcx context already names the instance, say so instead of inventing values. Proof: `gcx config check`. Phrasing: `"switch gcx to context <name>"` / `"change backend to local"`.
- `azure-monitor.md` — Display: `az account show` (subscription, tenant) plus the persisted targeting values from `stack_config.azure-monitor` (`subscription`, `resource_group`, `workspace` — the Log Analytics *customer ID* GUID, `app_insights_app` when used); each stored value shown next to where it came from, missing ones listed as "not persisted — the mission will ask". Proof: `az account show` succeeding. Phrasing: `"persist workspace <guid> for azure-monitor"` / `"change backend to azure-monitor"`.
- `cloudwatch.md` — Display: `aws sts get-caller-identity` (account) and `aws configure list` (region, profile) plus `stack_config.cloudwatch` (`region`, `log_group`, `xray` context values). Proof: `aws sts get-caller-identity`. Phrasing: `"persist log group <name> for cloudwatch"`.
- `datadog.md` — Display: the Pup CLI's site/org context (per the observability-cli-guides datadog reference: `DD_SITE`/keys are env/config — show names, never values); `stack_config.datadog` expected empty — the CLI context already names the site/org. Proof: the datadog reference's cheapest query probe. Phrasing: `"change backend to datadog"`.
- `dynatrace.md` — Display: the active `dtctl` context/environment (per its reference); `stack_config.dynatrace` expected empty. Proof: the reference's cheapest probe. Phrasing: `"change backend to dynatrace"`.
- `splunk.md` — Display: the instance targeted (`-uri` or `$SPLUNK_HOME`); `stack_config.splunk` expected empty. Proof: the reference's cheapest probe (a trivial SPL search or `splunk status` on-instance). Phrasing: `"change backend to splunk"`.

SKILL.md modifications:
- Step 2 gains: `Then open this skill's own reference for the stack (references/<stack>.md) - it says exactly what to display for that backend and where each value comes from, including the persisted stack_config values from odd_config_get.` and `Every display ends with the reference's change-request phrasing example, so the user knows how to ask for a change.`
- The Local specificity section points to `references/local.md` for the display shape (ports and endpoints from `odd_config_get`, never hardcoded) while `setup-local-stack` keeps owning the method.

- [ ] **Step 1: Write the seven reference files** per the skeleton and content decisions above.
- [ ] **Step 2: Update SKILL.md** (step 2 routing + Local specificity pointer).
- [ ] **Step 3: Verify** — every file exists, each carries the three skeleton sections, `grep -L "Change-request" .apm/skills/check-backend-configuration/references/*.md` returns nothing.
- [ ] **Step 4: Commit**

```bash
git add .apm/skills/check-backend-configuration
git commit -m "feat(skill): per-backend display references for check-backend-configuration

The display was generic prose; each backend now has a reference saying
exactly what to show and where each value comes from - the local stack
renders its Grafana URL and OTLP endpoints from odd_config_get, never
hardcoded - plus the persisted stack_config values, the connection
proof, and an example change-request phrasing so the user knows what
to ask."
```

---

### Task 4: the `update-backend-configuration` skill

**Files:**
- Create: `.apm/skills/update-backend-configuration/SKILL.md`
- Create: `.apm/skills/update-backend-configuration/references/local.md`
- Create: `.apm/skills/update-backend-configuration/references/azure-monitor.md`
- Create: `.apm/skills/update-backend-configuration/references/cloudwatch.md`
- Create: `.apm/skills/update-backend-configuration/references/grafana.md`
- Create: `.apm/skills/update-backend-configuration/references/datadog.md`
- Create: `.apm/skills/update-backend-configuration/references/dynatrace.md`
- Create: `.apm/skills/update-backend-configuration/references/splunk.md`

**Interfaces:**
- Consumes: `odd_config_set({"stack": ...})` and `odd_config_set({"stack_config": {...}})` (Task 1); the `## CLI binary` detect/install sections (Task 2); `check-backend-configuration` for the post-switch verification.
- Produces: the switch procedure Task 5 routes "Change backend?" to.

SKILL.md frontmatter description: `Own the backend switch of the global oddyssey configuration: verify the target backend's CLI is installed (offer a guided install when missing), persist the switch via odd_config_set, persist the per-stack stack_config values the missions will need, and hand back to check-backend-configuration for the connection proof. Use when the user asks to change the configured stack/backend or to persist backend targeting values. Never installs silently, never authenticates on the user's behalf, never stores secrets.`

SKILL.md body sections (write in house style):
1. **Resolve the target stack** — one of the seven `STACKS` values; anything else is an error naming the valid list.
2. **CLI presence preflight** — open the target's `observability-cli-guides` reference, run its `## CLI binary` Detect command; when missing, OFFER the Install steps (guided, never silent — the user runs or approves the install); `local` needs gcx like `grafana` (the local stack's mandatory query CLI), and a missing gcx on local is still self-serve to install.
3. **Persist the switch** — `odd_config_set {"stack": "<target>"}`; state what the result reports (including any embedded stack_reset outcome when local ports were also changed — port changes stay the caller's explicit ask, this skill never changes ports on its own).
4. **Persist the stack_config** — open this skill's `references/<stack>.md`; it says what to persist for that stack, where each value comes from, and what to ask the user for; write via `odd_config_set {"stack_config": {"<stack>": {...}}}`. Values are identifiers/names/regions only — never secrets (credentials stay in the CLI's auth store, referenced by name).
5. **Verify** — run `check-backend-configuration` against the new stack: display + connection proof is the exit criterion.

Per-stack reference content (each file: `## What stack_config holds`, `## Where each value comes from`, `## What to ask the user`):

- `local.md` — holds the **container environment variables** applied to the otel-lgtm container (the env surface catalogued by `setup-local-stack`), e.g. `{"GF_LOG_LEVEL": "debug"}` — what was applied and should be reapplied on the next reset; comes from the user's own `odd_stack_up`/`odd_stack_reset` env choices; ask nothing unless the user wants persistent container env.
- `azure-monitor.md` — holds the extra targeting info the missions need because `az` is general-purpose and its context does NOT say where the telemetry lives: `subscription`, `resource_group`, `workspace` (Log Analytics **customer ID** GUID — from `az monitor log-analytics workspace show`, not the resource name), optional `app_insights_app`; ask the user for each value not derivable from `az account show`.
- `cloudwatch.md` — same rationale for `aws`: `region`, `log_group` (or the naming pattern), the X-Ray group/context when used; from `aws configure list` and the user.
- `grafana.md` / `datadog.md` / `dynatrace.md` / `splunk.md` — **little to nothing beyond the switch**: their CLI context (gcx context, Datadog site/org, dtctl config, splunk target) already names the instance; the reference says exactly that so the skill knows NOT to ask — an empty `stack_config.<stack>` is the correct state.

- [ ] **Step 1: Write SKILL.md** per the five sections above.
- [ ] **Step 2: Write the seven per-stack references** per the content decisions.
- [ ] **Step 3: Verify** — the skill never says "install" without "offer/propose/ask", never asks for a credential value; `grep -ri "password\|api.key\|token" .apm/skills/update-backend-configuration/` only matches by-name mentions.
- [ ] **Step 4: Commit**

```bash
git add .apm/skills/update-backend-configuration
git commit -m "feat(skill): update-backend-configuration owns the backend switch

Verifies the target CLI is installed via the observability-cli-guides
binary sections (guided install offer, never silent), persists the
switch through odd_config_set, and carries one reference per stack
saying what stack_config must hold - the local container env, the
azure-monitor/cloudwatch targeting info the general-purpose CLIs do
not carry, and explicitly nothing for the context-bearing CLIs - so
missions stop re-asking every run. Verification is handed back to
check-backend-configuration."
```

---

### Task 5: the `/odd-config` prompt and README

**Files:**
- Create: `.apm/prompts/odd-config.prompt.md`
- Modify: `README.md` (primitives table + Miscellaneous prompts subsection)

**Interfaces:**
- Consumes: `check-backend-configuration` (display + proof), `update-backend-configuration` (switch), both via their skill names.
- Produces: the user entry point; nothing downstream.

Prompt frontmatter description: `Display the current oddyssey backend configuration - configured stack, targeted instance, connection proof - then offer to change it: pick a backend from the full list and route the switch to the update-backend-configuration skill`

Prompt body (house style, mirrors odd-observe's structure):
- Arguments: `$ARGUMENTS` — optional; when they already name a target backend or a persist request (e.g. `switch to datadog`, `persist workspace <guid>`), skip the display-first flow and route straight to `update-backend-configuration`.
- No arguments: run the `check-backend-configuration` skill for the configured stack — display the effective configuration (per its backend reference), the targeted instance, and the connection proof. Show any `invalid_ignored` degradations.
- Then propose the next choices, starting with **"Change backend?"** — list the seven backends (`local`, `grafana`, `azure-monitor`, `cloudwatch`, `datadog`, `dynatrace`, `splunk`), current one marked; on a pick, route to the `update-backend-configuration` skill which owns the switch (CLI presence preflight, persist, stack_config, re-verify).
- Read-only until the user picks a change: displaying never writes configuration.

README:
- Primitives table, after the `/odd-status` row: `| [`/odd-config`](.apm/prompts/odd-config.prompt.md) (prompt) | Show the configured backend - stack, targeted instance, connection proof - and guide a backend switch through the update-backend-configuration skill |`
- Miscellaneous prompts subsection (after the `/odd-status` sub-subsection): a `#### /odd-config` block with the example lines ` /odd-config ` and ` /odd-config switch to datadog ` in one ```text fence, then one short paragraph: displays the effective configuration (stack, instance, connection proof) via check-backend-configuration, then offers "Change backend?" across the seven stacks; switches are guided (CLI presence checked, install offered, targeting values persisted in the per-stack stack_config) and nothing is written until the user picks a change.

- [ ] **Step 1: Write the prompt** per the structure above.
- [ ] **Step 2: Update README** (table row + subsection).
- [ ] **Step 3: Verify** — the prompt names both skills exactly; the backend list matches `STACKS` verbatim; README links resolve (`ls .apm/prompts/odd-config.prompt.md`).
- [ ] **Step 4: Commit**

```bash
git add .apm/prompts/odd-config.prompt.md README.md
git commit -m "feat(apm): /odd-config - display the backend configuration and guide changes

The global configuration had no user-facing entry point: a wrong
target was only caught once a mission was already dispatching.
/odd-config shows the effective configuration - stack, targeted
instance, connection proof, degradations - through
check-backend-configuration, then offers the backend switch across
the seven stacks, routed to update-backend-configuration. Read-only
until the user picks a change."
```
