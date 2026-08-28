import json

import pytest
from oddyssey_mcp import config


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

    assert result["stack"] == "local"
    assert result["local"]["grafana_port"] == 3000
    assert sorted(result["invalid_ignored"]) == ["local.grafana_port", "stack"]


def test_load_tolerates_unparseable_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{broken")

    result = config.load(path)

    assert result["stack"] == "local"
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


def test_local_is_a_stack_value_and_the_default():
    # Issue #67: local is a first-class stack value and the default -
    # grafana then unambiguously means a remote Grafana. A fresh machine
    # targets the self-serve local stack.
    assert "local" in config.STACKS
    assert config.DEFAULTS["stack"] == "local"


def test_save_accepts_the_local_stack(tmp_path):
    path = tmp_path / "config.json"
    result = config.save({"stack": "local"}, path)
    assert result["stack"] == "local"


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
    # Values are identifiers, names, regions - flat scalars only. None is
    # NOT rejected: it is the deletion marker (issue #112).
    path = tmp_path / "config.json"
    for bad in ({"nested": {"a": 1}}, {"listed": [1, 2]}):
        with pytest.raises(ValueError, match="stack_config"):
            config.save({"stack_config": {"grafana": bad}}, path)
    assert not path.exists()


def test_save_null_key_deletes_it_and_the_last_deletion_leaves_the_entry(tmp_path):
    # Issue #112: the tool surface must be able to remove what it wrote -
    # hand-editing the file is exactly what it exists to make unnecessary.
    path = tmp_path / "config.json"
    config.save(
        {"stack_config": {"azure-monitor": {"workspace": "guid-123", "tenant": "t1"}}},
        path,
    )

    result = config.save({"stack_config": {"azure-monitor": {"workspace": None}}}, path)
    assert result["stack_config"]["azure-monitor"] == {"tenant": "t1"}

    result = config.save({"stack_config": {"azure-monitor": {"tenant": None}}}, path)
    # Present-but-empty already reads as "not configured" - not an error.
    assert result["stack_config"]["azure-monitor"] == {}


def test_save_null_entry_removes_the_stack_entry(tmp_path):
    path = tmp_path / "config.json"
    config.save({"stack_config": {"azure-monitor": {"workspace": "guid-123"}}}, path)
    config.save({"stack_config": {"cloudwatch": {"region": "eu-west-1"}}}, path)

    result = config.save({"stack_config": {"azure-monitor": None}}, path)

    assert result["stack_config"] == {"cloudwatch": {"region": "eu-west-1"}}
    assert "azure-monitor" not in json.loads(path.read_text())["stack_config"]


def test_save_mixes_deletion_and_set_in_one_write(tmp_path):
    path = tmp_path / "config.json"
    config.save({"stack_config": {"azure-monitor": {"workspace": "old"}}}, path)

    result = config.save(
        {"stack_config": {"azure-monitor": {"workspace": None, "tenant": "t1"}}},
        path,
    )

    assert result["stack_config"]["azure-monitor"] == {"tenant": "t1"}


def test_save_deletion_on_absent_targets_is_harmless(tmp_path):
    # Deleting what does not exist must converge, not error: a null key on
    # a missing entry leaves the present-but-empty entry, a null entry on
    # nothing stays nothing.
    path = tmp_path / "config.json"

    result = config.save({"stack_config": {"datadog": None}}, path)
    assert "datadog" not in result["stack_config"]

    result = config.save({"stack_config": {"grafana": {"context": None}}}, path)
    assert result["stack_config"]["grafana"] == {}


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
