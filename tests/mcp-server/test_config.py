import json
import re
from importlib import metadata as importlib_metadata
from pathlib import Path

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
            "pyroscope_port": 4040,
        },
        "stack_config": {},
        "custom": {},
    }


def test_save_accepts_the_pyroscope_port(tmp_path):
    # Issue #224: Pyroscope's ingest port is a named local port like the
    # other three - pyroscope-io pushes over its own HTTP protocol, not
    # OTLP, so the port must be publishable and configurable.
    path = tmp_path / "config.json"

    result = config.save({"local": {"pyroscope_port": 4140}}, path)

    assert result["local"]["pyroscope_port"] == 4140
    assert result["local"]["grafana_port"] == 3000


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
    config.save({"stack": "dynatrace"}, path)
    assert json.loads(path.read_text())["stack"] == "dynatrace"


def test_local_is_a_stack_value_and_the_default():
    # Issue #67: local is a first-class stack value and the default -
    # grafana then unambiguously means a remote Grafana. A fresh machine
    # targets the self-serve local stack.
    assert "local" in config.STACKS
    assert config.DEFAULTS["stack"] == "local"


def test_builtin_stacks_reference_lists_exactly_the_stacks_values():
    # Issue #243: the observability-cli-guides skill's builtin-stacks.md
    # is what the stack-agnostic configuration skills and /odd-config read
    # to know which stacks exist; STACKS is what the server enforces. The
    # two must never drift - a stack added to one without the other is
    # either unknown to the agents or rejected by odd_config_set.
    reference = (
        Path(__file__).resolve().parents[2]
        / ".apm/skills/observability-cli-guides/references/builtin-stacks.md"
    )
    rows = re.findall(r"^\| `([a-z-]+)` \| \[", reference.read_text(), re.MULTILINE)
    assert rows == list(config.STACKS)


def test_every_stack_has_a_stack_config_fields_entry():
    # _stack_config_key_allowed fails OPEN on a missing entry (treats an
    # unmapped stack as unrestricted) - issue #196's whole point was to
    # stop silently accepting anything, so a stack added to STACKS without
    # a matching whitelist entry here must fail loudly, not slip back into
    # the bug this fix closes.
    assert set(config.STACK_CONFIG_FIELDS) == set(config.STACKS)


def test_save_accepts_cloudwatch_profile_and_separate_metrics_log_group(tmp_path):
    # Issue #207: SSO setups routinely have no default profile, and
    # metrics commonly arrive through a different log group than
    # application logs (Embedded Metric Format) - both need their own
    # field since a team may configure them distinctly.
    path = tmp_path / "config.json"
    result = config.save(
        {
            "stack_config": {
                "cloudwatch": {
                    "region": "eu-central-1",
                    "profile": "myteam",
                    "log_group": "/oddyssey-playground/logs",
                    "metrics_log_group": "/oddyssey-playground/metrics",
                }
            }
        },
        path,
    )
    assert result["stack_config"]["cloudwatch"] == {
        "region": "eu-central-1",
        "profile": "myteam",
        "log_group": "/oddyssey-playground/logs",
        "metrics_log_group": "/oddyssey-playground/metrics",
    }


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
        {
            "stack_config": {
                "azure-monitor": {
                    "workspace": "guid-123",
                    "app_insights_app": "guid-456",
                }
            }
        },
        path,
    )
    result = config.load(path)
    assert result["stack_config"] == {
        "azure-monitor": {"workspace": "guid-123", "app_insights_app": "guid-456"}
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
        {
            "stack_config": {
                "azure-monitor": {
                    "workspace": "guid-123",
                    "app_insights_app": "guid-456",
                }
            }
        },
        path,
    )

    result = config.save({"stack_config": {"azure-monitor": {"workspace": None}}}, path)
    assert result["stack_config"]["azure-monitor"] == {"app_insights_app": "guid-456"}

    result = config.save(
        {"stack_config": {"azure-monitor": {"app_insights_app": None}}}, path
    )
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
        {
            "stack_config": {
                "azure-monitor": {"workspace": None, "app_insights_app": "guid-456"}
            }
        },
        path,
    )

    assert result["stack_config"]["azure-monitor"] == {"app_insights_app": "guid-456"}


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


def test_save_rejects_undocumented_key_for_a_documented_stack(tmp_path):
    # Issue #196: a well-typed but undocumented key (a copy-paste from az
    # account show, a typo, ...) must be rejected like any other invalid
    # partial, not persisted silently.
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="stack_config"):
        config.save(
            {
                "stack_config": {
                    "azure-monitor": {"tenant": "11111111-1111-1111-1111-111111111111"}
                }
            },
            path,
        )
    assert not path.exists()


def test_save_rejects_any_key_for_a_stack_with_no_documented_fields(tmp_path):
    # grafana/datadog/dynatrace persist nothing (their CLI context
    # carries targeting) - any key is unknown for them.
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="stack_config"):
        config.save({"stack_config": {"grafana": {"context": "prod"}}}, path)
    assert not path.exists()


def test_save_allows_arbitrary_keys_for_the_local_stack(tmp_path):
    # local's keys are otel-lgtm container env var names - an open set
    # catalogued elsewhere (setup-local-stack), not a closed field list.
    path = tmp_path / "config.json"
    result = config.save({"stack_config": {"local": {"GF_LOG_LEVEL": "debug"}}}, path)
    assert result["stack_config"]["local"] == {"GF_LOG_LEVEL": "debug"}


def test_save_still_allows_deleting_an_undocumented_key(tmp_path):
    # The whitelist must not trap a stray key already on disk (an older
    # write, or a hand edit) with no way to clean it up.
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "stack_config": {
                    "azure-monitor": {"workspace": "guid-123", "tenant": "stray"}
                }
            }
        )
    )

    result = config.save({"stack_config": {"azure-monitor": {"tenant": None}}}, path)

    assert result["stack_config"]["azure-monitor"] == {"workspace": "guid-123"}


def test_load_flags_undocumented_key_as_invalid_ignored(tmp_path):
    # Issue #196 repro: odd_config_set previously accepted this silently,
    # and odd_config_get returned it back un-flagged, indefinitely.
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "stack_config": {
                    "azure-monitor": {
                        "subscription": "Contoso",
                        "tenant": "11111111-1111-1111-1111-111111111111",
                        "app_insights_app": "22222222-2222-2222-2222-222222222222",
                    }
                }
            }
        )
    )

    result = config.load(path)

    assert result["stack_config"] == {
        "azure-monitor": {
            "subscription": "Contoso",
            "app_insights_app": "22222222-2222-2222-2222-222222222222",
        }
    }
    assert result["invalid_ignored"] == ["stack_config.azure-monitor.tenant"]


def test_load_allows_arbitrary_keys_for_the_local_stack(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"stack_config": {"local": {"ENABLE_LOGS_GRAFANA": "true"}}})
    )
    result = config.load(path)
    assert result["stack_config"] == {"local": {"ENABLE_LOGS_GRAFANA": "true"}}
    assert "invalid_ignored" not in result


# --- Custom stacks (issue #228): a stack declared by the caller ---------


def _declare(name="seq", fields=("base_url",)):
    return {"custom": {name: {"stack_config_fields": list(fields)}}}


def test_load_returns_empty_custom_by_default(tmp_path):
    assert config.load(tmp_path / "config.json")["custom"] == {}


def test_save_accepts_a_custom_stack_declared_in_the_same_call(tmp_path):
    path = tmp_path / "config.json"
    result = config.save({"stack": "seq", **_declare()}, path)
    assert result["stack"] == "seq"
    assert result["custom"] == {"seq": {"stack_config_fields": ["base_url"]}}
    assert "invalid_ignored" not in result
    assert json.loads(path.read_text())["stack"] == "seq"


def test_save_accepts_a_custom_stack_declared_earlier(tmp_path):
    path = tmp_path / "config.json"
    config.save(_declare(), path)
    result = config.save({"stack": "seq"}, path)
    assert result["stack"] == "seq"


def test_save_rejects_an_undeclared_custom_stack_and_writes_nothing(tmp_path):
    # Without a declaration the door stays closed exactly as before: the
    # error names the built-in list, and now says how a custom stack gets in.
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="must be one of .* or a declared custom"):
        config.save({"stack": "seq"}, path)
    assert not path.exists()


@pytest.mark.parametrize("name", ["local", "grafana", "azure-monitor"])
def test_save_rejects_redeclaring_a_builtin_stack(tmp_path, name):
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="built-in"):
        config.save(_declare(name), path)
    assert not path.exists()


@pytest.mark.parametrize(
    "name", ["Seq", "seq_prod", "-seq", "1seq", "seq.md", "", "seq\n"]
)
def test_save_rejects_a_badly_shaped_custom_name(tmp_path, name):
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="kebab-case"):
        config.save(_declare(name), path)
    assert not path.exists()


@pytest.mark.parametrize(
    "declaration",
    [
        "base_url",
        [],
        {"fields": ["base_url"]},
        {"stack_config_fields": "base_url"},
        {"stack_config_fields": ["base_url", 3]},
        {"stack_config_fields": ["Base-URL"]},
        {"stack_config_fields": ["base_url\n"]},
        {"stack_config_fields": ["base_url", "base_url"]},
        {"stack_config_fields": ["base_url"], "extra": True},
    ],
)
def test_save_rejects_a_malformed_declaration(tmp_path, declaration):
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="custom.seq"):
        config.save({"custom": {"seq": declaration}}, path)
    assert not path.exists()


def test_save_accepts_an_empty_field_list(tmp_path):
    # A custom stack whose query surface carries its own targeting (a CLI
    # context) persists nothing, like the context-bearing built-ins.
    path = tmp_path / "config.json"
    result = config.save(_declare(fields=()), path)
    assert result["custom"] == {"seq": {"stack_config_fields": []}}
    with pytest.raises(ValueError, match="does not persist any fields"):
        config.save({"stack_config": {"seq": {"base_url": "x"}}}, path)


def test_save_validates_custom_stack_config_against_the_declaration(tmp_path):
    path = tmp_path / "config.json"
    config.save(_declare(fields=("base_url", "workspace")), path)
    result = config.save(
        {"stack_config": {"seq": {"base_url": "http://seq.example.test:5341"}}},
        path,
    )
    assert result["stack_config"] == {
        "seq": {"base_url": "http://seq.example.test:5341"}
    }
    with pytest.raises(ValueError, match=r"accepts only \['base_url', 'workspace'\]"):
        config.save({"stack_config": {"seq": {"api_key": "not-a-secret"}}}, path)
    assert "api_key" not in path.read_text()


def test_save_rejects_stack_config_for_an_undeclared_custom_stack(tmp_path):
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="stack_config keys must be one of"):
        config.save({"stack_config": {"seq": {"base_url": "x"}}}, path)
    assert not path.exists()


def test_save_declaration_and_stack_config_land_in_one_call(tmp_path):
    # The switch's write: declaration, switch and targeting values together.
    path = tmp_path / "config.json"
    result = config.save(
        {
            "stack": "seq",
            **_declare(),
            "stack_config": {"seq": {"base_url": "http://seq.example.test:5341"}},
        },
        path,
    )
    assert result["stack"] == "seq"
    assert result["stack_config"]["seq"] == {"base_url": "http://seq.example.test:5341"}


def test_custom_stack_survives_a_switch_to_a_builtin_and_back(tmp_path):
    path = tmp_path / "config.json"
    config.save(
        {"stack": "seq", **_declare(), "stack_config": {"seq": {"base_url": "u"}}},
        path,
    )
    config.save({"stack": "local"}, path)
    after = config.load(path)
    assert after["stack"] == "local"
    assert after["custom"] == {"seq": {"stack_config_fields": ["base_url"]}}
    assert after["stack_config"]["seq"] == {"base_url": "u"}
    assert config.save({"stack": "seq"}, path)["stack"] == "seq"


def test_save_redeclaring_replaces_the_field_list(tmp_path):
    # The file changed its declaration; the switch passes the new list and
    # the old one is gone - a value under a dropped field is now ignored.
    path = tmp_path / "config.json"
    config.save({**_declare(), "stack_config": {"seq": {"base_url": "u"}}}, path)
    result = config.save(_declare(fields=("workspace",)), path)
    assert result["custom"] == {"seq": {"stack_config_fields": ["workspace"]}}
    assert result["stack_config"]["seq"] == {}
    assert result["invalid_ignored"] == ["stack_config.seq.base_url"]


def test_save_null_removes_a_declaration_and_keeps_its_values(tmp_path):
    path = tmp_path / "config.json"
    config.save({**_declare(), "stack_config": {"seq": {"base_url": "u"}}}, path)
    result = config.save({"custom": {"seq": None}}, path)
    assert result["custom"] == {}
    # The values stay in the file for a later re-declaration; without one
    # they read as an unknown stack's entry, flagged, never surfaced.
    assert json.loads(path.read_text())["stack_config"]["seq"] == {"base_url": "u"}
    assert result["invalid_ignored"] == ["stack_config.seq"]
    assert result["custom"] == {}


def test_save_null_entry_cleans_up_the_values_of_an_undeclared_stack(tmp_path):
    # The declaration is gone (or never existed on this machine) and the
    # values linger, flagged: the null entry is the tool-surface cleanup,
    # accepted for any name, in the same call as the removal or later.
    path = tmp_path / "config.json"
    config.save({**_declare(), "stack_config": {"seq": {"base_url": "u"}}}, path)
    result = config.save({"custom": {"seq": None}, "stack_config": {"seq": None}}, path)
    assert result["custom"] == {}
    assert result["stack_config"] == {}
    assert "invalid_ignored" not in result
    assert "seq" not in path.read_text()


def test_save_refuses_removing_the_declaration_of_the_configured_stack(tmp_path):
    path = tmp_path / "config.json"
    config.save({"stack": "seq", **_declare()}, path)
    with pytest.raises(ValueError, match="configured stack"):
        config.save({"custom": {"seq": None}}, path)
    assert config.load(path)["custom"] == {"seq": {"stack_config_fields": ["base_url"]}}
    # Switching away in the same call is the one way to remove it at once.
    result = config.save({"stack": "local", "custom": {"seq": None}}, path)
    assert result["stack"] == "local"
    assert result["custom"] == {}


def test_save_rejects_switching_to_a_stack_removed_in_the_same_call(tmp_path):
    path = tmp_path / "config.json"
    config.save(_declare(), path)
    with pytest.raises(ValueError, match="configured stack"):
        config.save({"stack": "seq", "custom": {"seq": None}}, path)


def test_save_removing_an_absent_declaration_is_harmless(tmp_path):
    path = tmp_path / "config.json"
    result = config.save({"custom": {"seq": None}}, path)
    assert result["custom"] == {}
    assert "invalid_ignored" not in result


def test_save_rejects_a_non_dict_custom(tmp_path):
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="custom must be an object"):
        config.save({"custom": ["seq"]}, path)
    assert not path.exists()


def test_load_tolerates_a_malformed_stored_declaration(tmp_path):
    # A hand edit broke the declaration: the stack it declared falls back
    # to the default like any invalid stored stack, its stack_config entry
    # is dropped like an unknown stack's, and every drop is listed.
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "stack": "seq",
                "custom": {
                    "seq": {"stack_config_fields": "base_url"},
                    "local": {"stack_config_fields": []},
                    "uptrace": {"stack_config_fields": ["dsn_name"]},
                },
                "stack_config": {
                    "seq": {"base_url": "u"},
                    "uptrace": {"dsn_name": "d"},
                },
            }
        )
    )
    result = config.load(path)
    assert result["stack"] == "local"
    assert result["custom"] == {"uptrace": {"stack_config_fields": ["dsn_name"]}}
    assert result["stack_config"] == {"uptrace": {"dsn_name": "d"}}
    assert result["invalid_ignored"] == [
        "custom.seq",
        "custom.local",
        "stack",
        "stack_config.seq",
    ]


def test_load_tolerates_a_non_dict_custom(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"custom": ["seq"]}))
    result = config.load(path)
    assert result["custom"] == {}
    assert result["invalid_ignored"] == ["custom"]


def test_load_flags_an_undeclared_key_of_a_custom_stack(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "custom": {"seq": {"stack_config_fields": ["base_url"]}},
                "stack_config": {"seq": {"base_url": "u", "api_key": "k"}},
            }
        )
    )
    result = config.load(path)
    assert result["stack_config"] == {"seq": {"base_url": "u"}}
    assert result["invalid_ignored"] == ["stack_config.seq.api_key"]


def test_installed_version_reads_the_distribution_metadata():
    # Issue #395: the distribution's version, never a constant.
    assert config.installed_version() == importlib_metadata.version("oddyssey-mcp")


def test_installed_version_is_none_when_the_distribution_is_absent(monkeypatch):
    def missing(name):
        raise importlib_metadata.PackageNotFoundError(name)

    monkeypatch.setattr(config.importlib_metadata, "version", missing)

    assert config.installed_version() is None


def test_load_carries_no_version(tmp_path):
    # The version is not configuration: load stays the file's effective
    # shape, odd_config_get adds the installed version next to it.
    assert "version" not in config.load(tmp_path / "config.json")
