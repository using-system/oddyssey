import asyncio
from importlib import metadata as importlib_metadata

from oddyssey_mcp import config as config_module
from oddyssey_mcp import server, stack

EXPECTED_TOOLS = {
    "odd_stack_up",
    "odd_stack_down",
    "odd_stack_status",
    "odd_stack_reset",
    "odd_config_get",
    "odd_config_set",
}


def test_all_stack_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


def test_tools_have_descriptions():
    tools = asyncio.run(server.mcp.list_tools())
    assert all(tool.description for tool in tools)


def test_reset_description_states_the_machine_wide_wipe():
    # Issue #35: the wipe is machine-wide (one shared stack per machine),
    # and the tool result names the services it destroyed. Both facts must
    # be visible to the calling agent through the tool description.
    tools = asyncio.run(server.mcp.list_tools())
    reset = next(tool for tool in tools if tool.name == "odd_stack_reset")
    assert "machine" in reset.description.lower()
    assert "services_wiped" in reset.description
    # Issue #35 side note: the server observes itself and the embedded
    # collector self-reports, so these two names are always listed - the
    # agent must not read them as another project's leftover state.
    assert "oddyssey-mcp" in reset.description
    assert "otelcol-contrib" in reset.description


def test_up_and_reset_expose_an_env_parameter():
    # Issue #34: the otel-lgtm image is configured exclusively through
    # environment variables; both creation paths must accept them.
    tools = {tool.name: tool for tool in asyncio.run(server.mcp.list_tools())}
    for name in ("odd_stack_up", "odd_stack_reset"):
        assert "env" in tools[name].input_schema["properties"], name


def test_sdk_otel_middleware_removed():
    # mcp 2.0 installs its own OpenTelemetryMiddleware by default, which
    # duplicated every tool span (observation report finding 1). The
    # branch's decorator span is canonical; the SDK middleware must be gone.
    assert not any(
        type(m).__name__ == "OpenTelemetryMiddleware" for m in server.mcp.middleware
    )


def test_config_set_resets_the_stack_only_on_port_change_with_container(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")
    resets: list[int] = []
    monkeypatch.setattr(
        stack,
        "stack_reset",
        lambda env=None, **kwargs: (
            resets.append(1) or {"running": True, "services_wiped": []}
        ),
    )
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "container_user_env", lambda: None, raising=False)

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


def test_config_set_boots_a_stopped_container_before_writing_ports(
    monkeypatch, tmp_path
):
    # A stopped container must be booted while the OLD ports are still
    # configured: written first, the new ports trip stack_up's mismatch
    # guard and the pre-wipe enumeration sees a dead container (#35).
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")
    events: list[str] = []
    real_save = config_module.save
    monkeypatch.setattr(stack, "_container_state", lambda: "stopped")
    monkeypatch.setattr(stack, "container_user_env", lambda: None, raising=False)
    monkeypatch.setattr(
        stack,
        "stack_up",
        lambda env=None, **kwargs: events.append("up") or {"running": True},
    )
    monkeypatch.setattr(
        config_module,
        "save",
        lambda partial, path=None: events.append("save") or real_save(partial, path),
    )
    monkeypatch.setattr(
        stack,
        "stack_reset",
        lambda env=None, **kwargs: (
            events.append("reset") or {"running": True, "services_wiped": []}
        ),
    )

    server.odd_config_set({"local": {"grafana_port": 3300}})

    assert events == ["up", "save", "reset"]


def test_config_set_preboot_skips_the_port_guard(monkeypatch, tmp_path):
    # #224 review: after an upgrade adds a named port, every pre-change
    # container mismatches the configuration - the enumeration pre-boot
    # must bypass stack_up's guard or the pre-wipe listing reads a dead
    # container and reports services_wiped: [] over real data (#35).
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(stack, "_container_state", lambda: "stopped")
    monkeypatch.setattr(stack, "container_user_env", lambda: None, raising=False)
    guard_flags: list[bool] = []
    monkeypatch.setattr(
        stack,
        "stack_up",
        lambda env=None, persist=True, check_ports=True: (
            guard_flags.append(check_ports) or {"running": True}
        ),
    )
    monkeypatch.setattr(
        stack,
        "stack_reset",
        lambda env=None, **kwargs: {"running": True, "services_wiped": []},
    )

    server.odd_config_set({"local": {"grafana_port": 3300}})

    assert guard_flags == [False]


def test_config_set_description_states_the_wipe_and_the_restart_note():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    description = tools["odd_config_set"].description
    assert "wipe" in description.lower()
    assert "restart" in description.lower()


def test_config_set_description_states_the_stack_config_field_whitelist():
    # Issue #196: an agent must learn the per-stack field rule from the
    # tool description, not only by hitting the raised error.
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    description = tools["odd_config_set"].description
    assert "app_insights_app" in description
    assert "documented field set" in description


def test_config_set_carries_the_container_env_through_the_auto_reset(
    monkeypatch, tmp_path
):
    # Issue #62: the auto-reset recreates the container - the env the user
    # applied through odd_stack_up/odd_stack_reset must be read from the
    # doomed container BEFORE it is destroyed and passed to the reset.
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")
    events: list[str] = []
    captured: dict = {}
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(
        stack,
        "container_user_env",
        lambda: events.append("read_env") or {"GF_LOG_LEVEL": "debug"},
    )

    def fake_reset(env=None, *, persist=True):
        events.append("reset")
        captured["env"] = env
        captured["persist"] = persist
        return {"running": True, "services_wiped": []}

    monkeypatch.setattr(stack, "stack_reset", fake_reset)

    result = server.odd_config_set({"local": {"grafana_port": 3300}})

    assert events == ["read_env", "reset"]
    assert captured["env"] == {"GF_LOG_LEVEL": "debug"}
    # Key names only: values may hold secrets and the result is logged.
    assert result["env_preserved"] == ["GF_LOG_LEVEL"]


def test_config_set_reset_survives_an_unreadable_container_env(monkeypatch, tmp_path):
    # Best-effort like everything on that path: an unreadable inspect
    # preserves nothing and never blocks the reset.
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")
    captured: dict = {}
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "container_user_env", lambda: None)

    def fake_reset(env=None, *, persist=True):
        captured["env"] = env
        return {"running": True, "services_wiped": []}

    monkeypatch.setattr(stack, "stack_reset", fake_reset)

    result = server.odd_config_set({"local": {"grafana_port": 3300}})

    assert captured["env"] is None
    assert result["env_preserved"] == []


def test_config_set_auto_reset_never_re_persists_the_carried_env(monkeypatch, tmp_path):
    # The carried env is the container's current state, not a caller
    # choice: re-persisting it would rewrite a variable this very call
    # deleted with null, resurrecting it on the next recreation.
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "config.json")
    captured: dict = {}
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "container_user_env", lambda: {"GF_LOG_LEVEL": "debug"})

    def fake_reset(env=None, *, persist=True):
        captured["persist"] = persist
        return {"running": True, "services_wiped": []}

    monkeypatch.setattr(stack, "stack_reset", fake_reset)

    server.odd_config_set({"local": {"grafana_port": 3300}})

    assert captured["persist"] is False


def test_config_set_description_states_the_env_carry_over():
    # The carried env is part of the tool contract: the calling agent
    # learns about env_preserved from the description, nowhere else.
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert "env_preserved" in tools["odd_config_set"].description


def test_config_set_description_states_the_custom_stack_declaration():
    # Issue #228: an agent must learn from the tool description that a
    # stack outside the built-in list needs a declaration, and its shape.
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    description = tools["odd_config_set"].description
    assert "custom" in description
    assert "stack_config_fields" in description


def test_config_get_returns_the_installed_version():
    # Issue #395: the server is the one component that knows the installed
    # oddyssey version for certain - read from the distribution metadata,
    # never from a constant, exactly like the telemetry resource does.
    result = server.odd_config_get()

    assert result["version"] == importlib_metadata.version("oddyssey-mcp")
    assert result["stack"] == "local"


def test_config_get_version_is_null_when_the_distribution_is_absent(monkeypatch):
    # A source checkout not installed as a distribution: the field is null
    # and the tool answers all the same - a version never breaks a tool.
    def missing(name):
        raise importlib_metadata.PackageNotFoundError(name)

    monkeypatch.setattr(config_module.importlib_metadata, "version", missing)

    result = server.odd_config_get()

    assert result["version"] is None
    assert result["stack"] == "local"
    assert result["stack_config"] == {}


def test_config_get_description_states_the_version():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}

    assert "version" in tools["odd_config_get"].description


def test_config_set_config_block_carries_no_version(monkeypatch):
    # The version is not configuration: odd_config_set echoes the effective
    # configuration it wrote (what config.load returns), and only
    # odd_config_get carries the installed version next to it.
    monkeypatch.setattr(stack, "_container_state", lambda: "absent")

    result = server.odd_config_set({"stack": "datadog"})

    assert result["config"]["stack"] == "datadog"
    assert "version" not in result["config"]
