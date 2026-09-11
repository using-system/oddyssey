"""Tests for the observability-cli-guides skill's azure-monitor-* scripts.

The scripts are loaded from their packaged location so the tests exercise the
very files the skill ships. Their contract is that every trap azure-monitor.md
records about `az` is absorbed once, in code: the two output shapes (the
component's typed ``tables[0]``, the workspace's flat stringified row list),
``customDimensions`` double-encoded as a string, the first-use ``WARNING:``
noise on stderr, the exit codes with the ``ERROR:`` line read past the
traceback banner and classified, the explicit window on every query, the
targeting values masked in the commands the scripts print. A fake ``az`` on
PATH answers with fixtures captured live (azure-cli 2.89.1, 2026-09-11)
against an Application Insights component and a Log Analytics workspace fed
by an OpenTelemetry Collector, every identifier masked - so the tests run
without a login and without the binary - and the flags the reference states
are checked against the parsers themselves.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".apm/skills/observability-cli-guides/scripts"
REFERENCE = ROOT / ".apm/skills/observability-cli-guides/references/azure-monitor.md"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "azure-monitor"

# The placeholders the fixtures carry in place of the live account's values.
APP = "aaaaaaaa-0000-0000-0000-00000000000a"
WS = "bbbbbbbb-0000-0000-0000-00000000000b"
RG = "contoso-rg"
SUB = "Contoso"
RID = (
    "/subscriptions/dddddddd-0000-0000-0000-00000000000d/resourceGroups/"
    "contoso-rg/providers/Microsoft.App/containerApps/contoso-app"
)
FROM = "2026-09-11T11:05:27Z"
TO = "2026-09-11T11:20:27Z"
WINDOW = ["--from", FROM, "--to", TO]
OPID = "51fe548d6c6cdcdd8fa2a68820f34905"


def load(name: str):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), SCRIPTS / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# A fake az: it answers from the fixture whose key is the sha1 of the masked
# arguments with every timestamp normalised - the same key the recording az
# that captured the fixtures computed - and logs every call it received.
FAKE_AZ = r"""#!/usr/bin/env python3
import hashlib, json, os, re, sys
F = os.environ["FAKE_FIXTURES"]
GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z")
KEEP = {
    "aaaaaaaa-0000-0000-0000-00000000000a", "bbbbbbbb-0000-0000-0000-00000000000b",
    "cccccccc-0000-0000-0000-00000000000c", "dddddddd-0000-0000-0000-00000000000d",
}
def mask(s):
    seen = {}
    def g(m):
        v = m.group(0).lower()
        if v in KEEP:
            return m.group(0)
        seen.setdefault(v, "%08d-0000-0000-0000-000000000000" % (len(seen) + 1))
        return seen[v]
    return GUID.sub(g, s)
args = sys.argv[1:]
key = hashlib.sha1(json.dumps([TS.sub("<ts>", mask(a)) for a in args]).encode()).hexdigest()[:12]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
path = os.path.join(F, key + ".json")
if not os.path.exists(path):
    sys.stderr.write("ERROR: no fixture " + key + " for " + json.dumps(args) + "\n")
    sys.exit(97)
case = json.load(open(path))
if os.environ.get("FAKE_WARN") == "1":
    sys.stderr.write("WARNING: The installed extension 'application-insights' is in preview.\n")
    sys.stderr.write("WARNING: Command group 'monitor app-insights' is in preview and under development.\n")
sys.stdout.write(case["stdout"])
sys.stderr.write(case["stderr"])
sys.exit(case["code"])
"""


@pytest.fixture
def fake(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    az = bin_dir / "az"
    az.write_text(FAKE_AZ, encoding="utf-8")
    az.chmod(az.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "az.log"
    log.write_text("")
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_FIXTURES"] = str(FIXTURES)
    env["FAKE_LOG"] = str(log)
    env.pop("FAKE_WARN", None)

    class Fake:
        def run(self, script: str, *args: str, warn: bool = False):
            e = dict(env)
            if warn:
                e["FAKE_WARN"] = "1"
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / f"azure-monitor-{script}.py"), *args],
                capture_output=True,
                text=True,
                env=e,
                cwd=tmp_path,
                check=False,
            )
            assert "no fixture" not in result.stderr + result.stdout, (
                "the fake az had no fixture for a call: "
                + result.stderr
                + result.stdout
            )
            return result

        def json(self, script: str, *args: str, **kw):
            result = self.run(script, *args, "--json", **kw)
            assert result.returncode in (0, 1), result.stderr
            return result.returncode, json.loads(result.stdout)

        def calls(self) -> list[list[str]]:
            return [json.loads(line) for line in log.read_text().splitlines()]

    return Fake()


# --- the shared module -------------------------------------------------------


def test_the_two_output_shapes_have_one_parser_each():
    az = load("azure_monitor_az")
    typed = {
        "tables": [
            {
                "columns": [
                    {"name": "n", "type": "long"},
                    {"name": "name", "type": "string"},
                ],
                "rows": [[3, "GET /products"]],
            }
        ]
    }
    assert az.ai_rows(typed) == [{"n": 3, "name": "GET /products"}]
    flat = [
        {"TableName": "PrimaryResult", "n": "484782", "latest": "2026-09-11T11:23:29Z"}
    ]
    rows = az.la_rows(flat)
    assert rows[0]["n"] == 484782, (
        "the workspace's stringified numbers are coerced back"
    )
    assert rows[0]["latest"] == "2026-09-11T11:23:29Z"
    assert "TableName" not in rows[0]


def test_custom_dimensions_are_decoded_from_their_double_encoding():
    az = load("azure_monitor_az")
    encoded = json.dumps({"service.version": "0.1.0", "http.route": "/orders"})
    assert az.dims(encoded) == {"service.version": "0.1.0", "http.route": "/orders"}
    assert az.dims({"already": "an object"}) == {"already": "an object"}
    assert az.dims("") == {}


def test_the_error_line_is_read_past_the_traceback_banner_and_classified():
    az = load("azure_monitor_az")
    banner = (
        "ERROR: The command failed with an unexpected error. Here is the traceback:\n"
        "ERROR: The Application Insight is not found. Please check the app id again.\n"
        "Traceback (most recent call last):\n  File x, line 1\nValueError: nope\n"
    )
    kind, _ = az.classify(banner, 1)
    assert kind == "not-an-appid"
    assert (
        az.classify("ERROR: ApplicationNotFoundError: not found\n", 3)[0] == "not-found"
    )
    kind, why = az.classify(
        "ERROR: BadArgumentError: The request had some invalid properties\n", 1
    )
    assert kind == "kql" and "percentileif" in why
    kind, why = az.classify(
        "ERROR: (BadArgumentError) The request had some invalid properties\n"
        "Code: BadArgumentError\nMessage: The request had some invalid properties\n"
        'Inner error: {\n    "code": "SemanticError",\n'
        '    "message": "A semantic error occurred.",\n'
        '    "innererror": {\n        "code": "SEM0100",\n'
        '        "message": "\'summarize\' operator: Failed to resolve scalar '
        "expression named 'NoSuchColumn_s'\"\n    }\n}\n",
        1,
    )
    assert kind == "kql" and "NoSuchColumn_s" in why
    assert (
        az.classify("ERROR: AADSTS700082: The refresh token has expired\n", 1)[0]
        == "identity"
    )
    assert (
        az.classify("ERROR: (AuthorizationFailed) does not have authorization\n", 1)[0]
        == "rights"
    )
    assert az.classify("ERROR: unrecognized arguments: --nope\n", 2)[0] == "usage"


def test_every_query_carries_an_explicit_window(fake):
    fake.run("discover", "--app", APP, "--workspace", WS, *WINDOW)
    fake.run("logs", "count", "--workspace", WS, "--since", "24h")
    queries = [
        c
        for c in fake.calls()
        if c[:2] == ["monitor", "app-insights"] or c[:2] == ["monitor", "log-analytics"]
    ]
    assert len(queries) >= 9
    for call in queries:
        if call[1] == "app-insights":
            assert "--start-time" in call and "--end-time" in call, call
            assert "--offset" not in call
        else:
            assert "--timespan" in call, call
            span = call[call.index("--timespan") + 1]
            assert re.fullmatch(r"\S+Z/\S+Z", span), span


def test_the_printed_commands_carry_field_names_never_the_values(fake):
    code, out = fake.json("discover", "--app", APP, "--workspace", WS, *WINDOW)
    assert code == 0
    for command in out["commands"]:
        assert APP not in command and WS not in command
        assert (
            "--app <app_insights_app>" in command
            or "--workspace <workspace>" in command
        )
    code, out = fake.json(
        "metrics",
        "platform",
        "--resource",
        RID,
        "--metric",
        "Requests",
        "RestartCount",
        "--aggregation",
        "Total",
        "--interval",
        "PT1M",
        *WINDOW,
    )
    assert code == 0
    assert (
        RID not in out["commands"][0] and "--resource <resource>" in out["commands"][0]
    )
    code, out = fake.json(
        "metrics", "resources", "--resource-group", RG, "--subscription", SUB
    )
    assert "--resource-group <resource_group>" in out["commands"][0]
    assert "--subscription <subscription>" in out["commands"][0]


def test_first_use_warning_noise_on_stderr_is_not_a_failure(fake):
    code, out = fake.json(
        "discover", "--app", APP, "--workspace", WS, *WINDOW, warn=True
    )
    assert code == 0
    assert out["failed"] == []
    assert out["component"]["services"]["orders-api"]["tables"]["request"] == 1702


# --- discover ----------------------------------------------------------------


def test_discover_reads_both_sides_and_the_environment(fake):
    code, out = fake.json("discover", "--app", APP, "--workspace", WS, *WINDOW)
    assert code == 0
    svc = out["component"]["services"]["orders-api"]
    assert svc["tables"] == {
        "trace": 1719,
        "dependency": 163,
        "request": 1702,
        "customMetric": 588,
    }
    assert svc["environment"] == "dev"
    assert svc["environment_read_from"] == "deployment.environment.name"
    assert svc["operations"][0] == {"name": "GET /products", "n": 824, "failed": 0}
    assert {o["name"]: o["failed"] for o in svc["operations"]}[
        "DELETE /orders/{order_id}"
    ] == 8
    assert [m["name"] for m in svc["metrics"] if m["aggregated"]] == [
        "http.server.request.body.size",
        "http.server.request.duration",
        "http.server.response.body.size",
    ]
    assert svc["severities"] == {"information": 1704, "warning": 15}
    assert svc["exceptions"] == []
    assert out["component"]["gap"] is None
    assert out["workspace"]["cl_tables"] == [
        {"table": "ContainerAppConsoleLogs_CL", "n": 7281}
    ]
    assert [c["container"] for c in out["workspace"]["containers"]] == [
        "orders-api",
        "load-generator",
    ]
    assert out["profiles"].startswith("not served")
    assert len(out["commands"]) == 8, "six component and two workspace queries"


def test_discover_states_a_missing_side_as_a_gap(fake):
    result = fake.run(
        "discover", "--app", APP, "--service", "orders-api", "--since", "15m"
    )
    assert result.returncode == 0, result.stderr
    assert "GAP: no workspace" in result.stdout
    assert "load-generator" not in result.stdout, (
        "--service scopes the component queries"
    )
    result = fake.run("discover", "--workspace", WS, "--since", "15m")
    assert result.returncode == 0, result.stderr
    assert "GAP: no app_insights_app" in result.stdout
    assert "distributed tracing is a telemetry gap" in result.stdout
    assert "ContainerAppConsoleLogs_CL=7281" in result.stdout


def test_discover_needs_one_side_at_least(fake):
    result = fake.run("discover", "--since", "15m")
    assert result.returncode == 2


# --- traces ------------------------------------------------------------------


def test_traces_operations_from_requests_with_percentiles_in_one_query(fake):
    code, out = fake.json(
        "traces",
        "operations",
        "--app",
        APP,
        "--service",
        "orders-api",
        *WINDOW,
        "--bin",
        "5m",
    )
    assert code == 0
    ops = {o["name"]: o for o in out["operations"]}
    assert out["total_operations"] == 5
    checkout = ops["POST /orders/{order_id}/checkout"]
    assert checkout["n"] == 109 and checkout["failed"] == 7
    assert checkout["failed_codes"] == {"502": 7}
    assert checkout["p50"] == 546.667 and checkout["p99"] == 790.852
    assert ops["DELETE /orders/{order_id}"]["failed_codes"] == {"500": 8}
    assert ops["GET /orders/{order_id}"]["failed_codes"] == {"404": 46}
    assert [b["n"] for b in out["bins"]] == [223, 574, 575, 344]
    assert (
        "percentile(duration, 95)" in out["commands"][0]
        and "percentileif" not in out["commands"][0]
    )
    assert len(out["commands"]) == 3


def test_traces_dependencies_are_joined_on_operation_id(fake):
    result = fake.run(
        "traces", "dependencies", "--app", APP, "--service", "orders-api", *WINDOW
    )
    assert result.returncode == 0, result.stderr
    assert "joined on operation_Id" in result.stdout
    assert re.search(
        r"POST /orders/\{order_id\}/checkout\s+Other\s+payment\.authorize\s+109\s+7",
        result.stdout,
    )
    assert re.search(
        r"DELETE /orders/\{order_id\}\s+Other\s+storage\.delete\s+54\s+8", result.stdout
    )
    assert "join kind=inner (requests" in result.stdout


def test_traces_exemplars_carry_their_dependencies_and_logs(fake):
    code, out = fake.json(
        "traces",
        "exemplars",
        "--app",
        APP,
        "--service",
        "orders-api",
        "--slow",
        "2",
        "--failed",
        "2",
        *WINDOW,
    )
    assert code == 0
    slow = out["slow"]
    assert len(slow) == 2 and slow[0]["duration"] == 796.709
    assert slow[0]["operation_Id"] == OPID
    assert [d["name"] for d in slow[0]["dependencies"]] == ["POST", "payment.authorize"]
    failed = slow[1]
    assert failed["resultCode"] == "502"
    assert failed["logs"] == [
        {
            "severity": "warn",
            "message": "payment upstream unavailable, checkout failed for order 2273",
        }
    ]
    assert [r["resultCode"] for r in out["failed_requests"]] == ["404", "404"]
    assert "union dependencies, exceptions, traces" in out["commands"][2]
    assert len(out["commands"]) == 3, (
        "one union over the picked ids, never one call per exemplar"
    )


def test_traces_trace_prints_the_tree_rooted_at_the_parentless_span(fake):
    result = fake.run("traces", "trace", OPID, "--app", APP, *WINDOW)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].startswith(
        f"trace {OPID}: root load-generator POST 798.255 ms, 3 spans (0 failed), 1 logs, 0 exceptions"
    )
    assert lines[1].startswith("  dependency") and "load-generator POST" in lines[1]
    assert (
        lines[2].startswith("    request")
        and "orders-api POST /orders/{order_id}/checkout" in lines[2]
    )
    assert lines[3].startswith("      dependency") and "payment.authorize" in lines[3]
    assert lines[4].startswith("      log")


def test_traces_trace_unknown_id_is_no_rows_not_an_error(fake):
    result = fake.run("traces", "trace", "0" * 32, "--app", APP, *WINDOW)
    assert result.returncode == 0
    assert (
        "(no rows: an unknown operation_Id, or one outside the window" in result.stdout
    )


# --- metrics -----------------------------------------------------------------


def test_metrics_list_names_the_dimensions_query_takes(fake):
    code, out = fake.json(
        "metrics", "list", "--app", APP, "--service", "orders-api", *WINDOW
    )
    assert code == 0
    by_name = {m["name"]: m for m in out["metrics"]}
    assert by_name["orders.created"]["dimensions"] == ["product.id"]
    assert by_name["orders.created"]["aggregated"] is False
    assert by_name["http.server.request.duration"]["aggregated"] is True
    assert "http.route" in by_name["http.server.request.duration"]["dimensions"]
    assert by_name["http.server.request.duration"]["points"] == 1734


def test_metrics_query_probes_the_temporality_before_reading(fake):
    code, out = fake.json(
        "metrics",
        "query",
        "orders.created",
        "--app",
        APP,
        "--by",
        "product.id",
        *WINDOW,
    )
    assert code == 0
    assert out["temporality"]["verdict"] == "delta"
    assert out["temporality"]["decreases"] == 52 and out["temporality"]["pushes"] == 150
    assert "delta" in out["readings"]
    assert {r["product.id"]: r["total"] for r in out["readings"]["delta"]}["1"] == 48
    assert "prev(value)" in out["commands"][0], "the probe runs first"
    assert "sum(value)" in out["commands"][1], "a delta pipeline is read as sum(value)"


def test_metrics_query_reads_a_histogram_export_and_a_told_gauge(fake):
    result = fake.run(
        "metrics",
        "query",
        "http.server.request.duration",
        "--app",
        APP,
        "--by",
        "http.route",
        "--by",
        "http.response.status_code",
        *WINDOW,
    )
    assert result.returncode == 0, result.stderr
    assert "histogram - rows carry several points" in result.stdout
    assert re.search(
        r"/orders/\{order_id\}/checkout\s+200\s+102\s+55\.4", result.stdout
    )
    _, out = fake.json(
        "metrics",
        "query",
        "http.server.active_requests",
        "--app",
        APP,
        "--as",
        "gauge",
        *WINDOW,
    )
    assert (
        out["temporality"]["verdict"] == "gauge"
        and out["temporality"]["why"] == "told by --as"
    )
    assert out["readings"]["gauge"][0]["avg"] == 0


def test_metrics_query_unknown_name_is_none_with_exit_zero(fake):
    result = fake.run("metrics", "query", "no.such.metric", "--app", APP, *WINDOW)
    assert result.returncode == 0
    assert ": none - no rows for this name in the window" in result.stdout


def test_metrics_resources_and_definitions(fake):
    code, out = fake.json(
        "metrics", "resources", "--resource-group", RG, "--subscription", SUB
    )
    assert code == 0
    assert [r["name"] for r in out["resources"]] == ["contoso-collector", "contoso-app"]
    assert out["resources"][1]["id"] == RID
    result = fake.run("metrics", "definitions", "--resource", RID)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("31 metric definitions")
    assert re.search(
        r"Requests\s+Count\s+Total\s+Average, Total, Maximum, Minimum\s+revisionName, podName, statusCodeCategory, statusCode",
        result.stdout,
    )


def test_metrics_platform_reads_values_and_states_the_two_absences(fake):
    code, out = fake.json(
        "metrics",
        "platform",
        "--resource",
        RID,
        "--metric",
        "Requests",
        "RestartCount",
        "--aggregation",
        "Total",
        "--interval",
        "PT1M",
        *WINDOW,
    )
    assert code == 0
    assert [m["name"] for m in out["metrics"]] == ["Requests", "RestartCount"]
    series = out["metrics"][1]["series"][0]
    assert series["points"] == 15 and series["of"] == 15
    assert series["stats"]["total"]["max"] == 0.0, (
        "a published idle metric answers zeros, which are values"
    )
    assert out["metrics"][1]["absence"] is None
    result = fake.run(
        "metrics",
        "platform",
        "--resource",
        RID,
        "--metric",
        "GpuUtilizationPercentage",
        *WINDOW,
    )
    assert result.returncode == 0
    assert "ABSENT - no point carries a value" in result.stdout
    assert "0 of 15 points carry a value" in result.stdout
    code, out = fake.json(
        "metrics",
        "platform",
        "--resource",
        "contoso-app",
        "--resource-group",
        RG,
        "--resource-type",
        "Microsoft.App/containerApps",
        "--metric",
        "Requests",
        "--dimension",
        "statusCodeCategory",
        "--since",
        "15m",
    )
    assert code == 0
    assert out["metrics"][0]["series"] == []
    assert out["metrics"][0]["absence"] == (
        "empty timeseries: no series matched (a --dimension split or a --filter with no match)"
    )


def test_metrics_platform_failures_are_classified_in_the_output(fake):
    result = fake.run(
        "metrics", "platform", "--resource", RID, "--metric", "NoSuchMetric", *WINDOW
    )
    assert result.returncode == 1
    assert "[unknown-metric] unknown metric; valid: UsageNanoCores," in result.stdout
    before = len(fake.calls())
    result = fake.run(
        "metrics",
        "platform",
        "--resource",
        RID,
        "--metric",
        "Requests",
        "--dimension",
        "statusCodeCategory",
        "--filter",
        "statusCodeCategory eq 'nope'",
        *WINDOW,
    )
    assert result.returncode == 2
    assert "--dimension and --filter are mutually exclusive" in result.stderr
    assert len(fake.calls()) == before, "refused before any az call"


# --- logs --------------------------------------------------------------------


def test_logs_tables_and_schema(fake):
    result = fake.run("logs", "tables", "--workspace", WS, "--since", "24h")
    assert result.returncode == 0, result.stderr
    assert re.search(r"ContainerAppConsoleLogs_CL\s+687392", result.stdout)
    assert re.search(r"ContainerAppSystemLogs_CL\s+109", result.stdout)
    code, out = fake.json(
        "logs", "schema", "--workspace", WS, "--table", "ContainerAppSystemLogs_CL"
    )
    assert code == 0
    assert out["table"] == "ContainerAppSystemLogs_CL"
    assert {"name": "Log_s", "type": "string"} in out["columns"]
    assert len(out["columns"]) == 26
    assert "getschema" in out["commands"][0]


def test_logs_count_extracts_the_level_and_names_a_regex_that_matches_nothing(fake):
    code, out = fake.json("logs", "count", "--workspace", WS, "--since", "24h")
    assert code == 0
    assert out["level_regex"] == r"^\S+\s+(\w+)\s"
    collector = {
        r["level"]: r["n"] for r in out["rows"] if r["container"] == "otel-collector"
    }
    assert collector == {"info": 18, "warn": 10}
    no_match = [r for r in out["rows"] if r["level"] == "(no match)"]
    assert {r["container"] for r in no_match} == {"load-generator", "orders-api"}
    assert "extract(" in out["commands"][0]


def test_logs_sample_counts_the_matching_lines_exactly(fake):
    result = fake.run(
        "logs",
        "sample",
        "--workspace",
        WS,
        "--container",
        "otel-collector",
        "--level",
        "info",
        "--since",
        "24h",
        "--show",
        "3",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("ContainerAppConsoleLogs_CL: 18 matching lines")
    assert result.stdout.count("otel-collector info stderr") == 3
    assert "lvl =~ 'info'" in result.stdout.replace("'\\''", "'")


def test_logs_traces_reads_the_component_log_table_by_severity(fake):
    code, out = fake.json(
        "logs",
        "traces",
        "--app",
        APP,
        "--service",
        "orders-api",
        "--min-severity",
        "2",
        *WINDOW,
    )
    assert code == 0
    assert out["severities"] == [
        {"cloud_RoleName": "orders-api", "severity": "information", "n": 1716},
        {"cloud_RoleName": "orders-api", "severity": "warning", "n": 15},
    ]
    assert out["matching"] == 15 and len(out["samples"]) == 15
    sample = out["samples"][0]
    assert sample["severity"] == "warning" and sample["library"] == "app.orders"
    assert re.fullmatch(r"[0-9a-f]{32}", sample["operation_Id"])
    assert re.fullmatch(r"[0-9a-f]{16}", sample["span_id"])


def test_logs_kql_runs_through_the_same_transport_and_classifies_both_error_shapes(
    fake,
):
    code, out = fake.json(
        "logs",
        "kql",
        "--app",
        APP,
        "requests | summarize n=count() by name | take 3",
        *WINDOW,
    )
    assert code == 0
    assert out["total_rows"] == 3 and out["rows"][0] == {
        "name": "GET /products",
        "n": 830,
    }
    result = fake.run(
        "logs",
        "kql",
        "--workspace",
        WS,
        "ContainerAppSystemLogs_CL | summarize n=count() by NoSuchColumn_s",
        "--since",
        "24h",
    )
    assert result.returncode == 1
    assert (
        "[kql] SEM0100: 'summarize' operator: Failed to resolve scalar expression named 'NoSuchColumn_s'"
        in result.stdout
    )
    result = fake.run(
        "logs",
        "kql",
        "--app",
        APP,
        "requests | summarize first=min(timestamp)",
        *WINDOW,
    )
    assert result.returncode == 1
    assert "[kql] BadArgumentError (the component names no token)" in result.stdout
    result = fake.run(
        "logs", "kql", "--app", APP, "--workspace", WS, "print 1", *WINDOW
    )
    assert result.returncode == 2, "exactly one of --workspace or --app"


# --- context -----------------------------------------------------------------


def test_context_check_proves_identity_and_both_targets(fake):
    code, out = fake.json("context", "check", "--app", APP, "--workspace", WS)
    assert code == 0
    assert out["connected"] is True
    assert out["identity"]["ok"] is True and out["identity"]["user_type"] == "user"
    assert "user_name" not in out["identity"] and "example-user" not in json.dumps(out)
    assert out["targeting"]["component"]["ok"] and out["targeting"]["workspace"]["ok"]
    assert out["failed"] == []
    assert out["commands"][0] == "az account show -o json"
    assert "print 1" in out["commands"][1] and "-g" not in out["commands"][1]
    assert "--subscription" not in out["commands"][1]


def test_context_check_wrong_values_exit_three_with_the_diagnosis(fake):
    result = fake.run(
        "context", "check", "--app", "12345678-1234-1234-1234-123456789abc"
    )
    assert result.returncode == 3
    assert "FAILED [not-found] ApplicationNotFoundError" in result.stdout
    assert "route to the switch to correct it" in result.stdout
    assert "NOT connected" in result.stdout
    result = fake.run("context", "check", "--app", "contoso-appinsights")
    assert result.returncode == 3
    assert "FAILED [not-an-appid]" in result.stdout
    assert "typically the component's resource name" in result.stdout


def test_context_check_a_workspace_value_that_is_not_the_customer_id_exits_three(fake):
    result = fake.run("context", "check", "--app", APP, "--workspace", "contoso-logs")
    assert result.returncode == 3
    assert "FAILED [not-a-workspace-id]" in result.stdout
    assert "route to the switch to persist the customer ID" in result.stdout
    result = fake.run(
        "context",
        "check",
        "--app",
        APP,
        "--workspace",
        "12345678-1234-1234-1234-123456789abc",
    )
    assert result.returncode == 3
    assert "FAILED [not-found] (WorkspaceNotFoundError)" in result.stdout


def test_usage_errors_exit_two_before_any_az_call(fake):
    result = fake.run("discover", "--app", APP, "--since", "5x")
    assert result.returncode == 2 and "a duration is <number><s|m|h|d>" in result.stderr
    result = fake.run("traces", "operations", "--app", APP, "--from", TO, "--to", FROM)
    assert result.returncode == 2 and "--to must be after --from" in result.stderr
    result = fake.run(
        "metrics", "list", "--app", APP, "--from", "yesterday", "--to", TO
    )
    assert result.returncode == 2 and "a timestamp is RFC3339 UTC" in result.stderr
    result = fake.run("logs", "traces", "--app", APP)
    assert result.returncode == 2 and "a window is required" in result.stderr
    assert fake.calls() == []


def test_context_landing_polls_the_identity_count_and_is_bounded(fake):
    code, out = fake.json(
        "context",
        "landing",
        "--app",
        APP,
        "--identity",
        "python-httpx/0.28.1",
        "--expect",
        "10",
        *WINDOW,
    )
    assert code == 0
    assert out["landed"] is True and out["count"] == 1716
    assert len(out["polls"]) == 1
    assert "user_agent.original" in out["commands"][0]
    result = fake.run(
        "context",
        "landing",
        "--app",
        APP,
        "--identity",
        "no-such-agent/0",
        "--expect",
        "1",
        "--every",
        "1",
        "--cap",
        "2s",
        *WINDOW,
    )
    assert result.returncode == 1
    assert "NOT landed within the cap: 0 of 1" in result.stdout
    assert "exact repeats folded" in result.stdout
    assert result.stdout.count("az monitor app-insights query") == 1


# --- the reference states what the parsers accept ----------------------------


def reference_invocations(
    text: str | None = None,
) -> list[tuple[str, str | None, list[str]]]:
    """(script, subcommand, flags) per invocation line of the fenced blocks of the
    reference, or of the section given."""
    found = []
    text = REFERENCE.read_text(encoding="utf-8") if text is None else text
    for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
        for line in block.splitlines():
            m = re.match(
                r"python3 <Skills>/observability-cli-guides/scripts/azure-monitor-(\w+)\.py(.*)",
                line,
            )
            if not m:
                continue
            script, rest = m.group(1), m.group(2).split()
            sub = rest[0] if rest and not rest[0].startswith(("--", "<")) else None
            flags = [t for t in rest if t.startswith("--")]
            found.append((script, sub, flags))
    return found


def test_the_reference_invocations_name_flags_the_scripts_accept():
    invocations = reference_invocations()
    assert len(invocations) >= 20
    assert {s for s, _, _ in invocations} == {
        "discover",
        "traces",
        "metrics",
        "logs",
        "context",
    }
    helps: dict[tuple[str, str | None], str] = {}
    for script, sub, flags in invocations:
        if (script, sub) not in helps:
            cmd = [sys.executable, str(SCRIPTS / f"azure-monitor-{script}.py")]
            if sub:
                cmd.append(sub)
            helps[(script, sub)] = subprocess.run(
                [*cmd, "--help"], capture_output=True, text=True, check=False
            ).stdout
        for flag in flags:
            assert flag in helps[(script, sub)], (
                f"{script} {sub or ''}: {flag} is not a flag of the script"
            )


def test_the_reference_whole_surface_paragraphs_match_the_parsers():
    text = REFERENCE.read_text(encoding="utf-8")
    sections = re.split(r"\n### ", text)
    scripts = {
        "First, in one call": "discover",
        "Traces": "traces",
        "Metrics": "metrics",
        "Logs": "logs",
        "The landing of a driven run": "context",
    }
    for section in sections:
        title = section.split("\n", 1)[0]
        script = next((s for key, s in scripts.items() if title.startswith(key)), None)
        if script is None:
            continue
        surface = re.search(r"Whole surface:(.*?)(?:\n\n|\Z)", section, re.DOTALL)
        assert surface, title
        flags = set(re.findall(r"`(--[a-z-]+)", surface.group(1)))
        assert flags, title
        subs = {sub for s, sub, _ in reference_invocations(section) if s == script}
        accepted = ""
        for sub in subs or {None}:
            cmd = [
                sys.executable,
                str(SCRIPTS / f"azure-monitor-{script}.py"),
                *([sub] if sub else []),
                "--help",
            ]
            accepted += subprocess.run(
                cmd, capture_output=True, text=True, check=False
            ).stdout
        for flag in flags:
            assert flag in accepted, (
                f"{script}: {flag} stated in the reference, not accepted by the script"
            )
        stated = flags | {"--help", "--from", "--to", "--since", "--json"}
        for flag in set(re.findall(r"(--[a-z-]+)", accepted)):
            assert flag in stated, (
                f"{script}: {flag} accepted by the script, not stated in the reference"
            )
