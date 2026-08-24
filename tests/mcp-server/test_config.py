import json

import pytest
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
    for bad in (
        {"grafana_port": 0},
        {"grafana_port": "3000"},
        {"otlp_http_port": 70000},
    ):
        with pytest.raises(ValueError, match="port"):
            config.save({"local": bad}, path)
    assert not path.exists()


def test_save_rejects_colliding_ports(tmp_path):
    # Two signals cannot share one host port; catching it at write time
    # beats a cryptic docker error at the next reset.
    with pytest.raises(ValueError, match="distinct"):
        config.save({"local": {"grafana_port": 4317}}, tmp_path / "config.json")


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
