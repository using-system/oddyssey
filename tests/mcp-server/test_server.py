import asyncio

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
        lambda: resets.append(1) or {"running": True, "services_wiped": []},
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
    monkeypatch.setattr(
        stack, "stack_up", lambda env=None: events.append("up") or {"running": True}
    )
    monkeypatch.setattr(
        config_module,
        "save",
        lambda partial, path=None: events.append("save") or real_save(partial, path),
    )
    monkeypatch.setattr(
        stack,
        "stack_reset",
        lambda: events.append("reset") or {"running": True, "services_wiped": []},
    )

    server.odd_config_set({"local": {"grafana_port": 3300}})

    assert events == ["up", "save", "reset"]


def test_config_set_description_states_the_wipe_and_the_restart_note():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    description = tools["odd_config_set"].description
    assert "wipe" in description.lower()
    assert "restart" in description.lower()
