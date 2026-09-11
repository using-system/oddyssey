"""Tests for the observability-cli-guides skill's cloudwatch-* scripts.

The scripts are loaded from their packaged location so the tests exercise the
very files the skill ships. Their contract is that every trap cloudwatch.md
records about `aws` is absorbed once, in code: `--profile`/`--region` on every
call, `--output json` captured whole and filtered client-side (no `--query`
with `--output text` on a paginated command), the time units per command
(milliseconds for `filter-log-events`, seconds for Logs Insights and X-Ray),
the Logs Insights `start-query` -> `get-query-results` poll inside and bounded,
the EMF temporality read per series, one unfiltered X-Ray summaries call
split client-side, `batch-get-traces` chunked by five, the targeting values
masked in the commands the scripts print, the errors classified. A fake
``aws`` on PATH answers with fixtures captured live (aws-cli 2.36.37,
2026-09-11) against an account fed by an OpenTelemetry Collector, every
identifier masked (the X-Ray summaries trimmed to every eighth plus the
exemplars' ids), replayed by a key over the masked arguments with the epochs
and file paths normalised and a Logs Insights query id mapped back to the
query that started it - so the tests run without a login and without the
binary - and the flags the reference states are checked against the parsers
in both directions.
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
REFERENCE = ROOT / ".apm/skills/observability-cli-guides/references/cloudwatch.md"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cloudwatch"

# The placeholders the fixtures carry in place of the live account's values.
A = ["--profile", "contoso", "--region", "eu-central-1"]
LG = "/contoso/logs"
MG = "/contoso/metrics"
NS = "ContosoApp"
FROM = "2026-09-11T12:40:00Z"
TO = "2026-09-11T12:50:00Z"
WINDOW = ["--from", FROM, "--to", TO]
TRACE_IDS = [
    "1-a4e20ce7-5ade6e607427c8011f1331d8",
    "1-eb746786-655a25441531eccded44e5ad",
    "1-e40cdcb0-90886f1e918153c4710d3f5e",
    "1-a33ae5bf-dd09bb27f5d8d858da544fcd",
]


def load(name: str):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), SCRIPTS / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# A fake aws: it answers from the fixture whose key is the sha1 of the masked
# arguments with every timestamp, epoch and file path normalised - the same key
# the recording aws that captured the fixtures computed - a Logs Insights query
# id carrying the key of the query that started it; it logs every call.
FAKE_AWS = r"""#!/usr/bin/env python3
import hashlib, json, os, re, sys
F = os.environ["FAKE_FIXTURES"]
GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z")
EPOCH = re.compile(r"(?<![\w.])\d{10}(\d{3})?(?![\w.])")
FILE = re.compile(r"file://\S+")
def mask(s):
    seen = {}
    def g(m):
        v = m.group(0).lower()
        seen.setdefault(v, "%08d-0000-0000-0000-000000000000" % (len(seen) + 1))
        return seen[v]
    return GUID.sub(g, s)
def normalise(a):
    return FILE.sub("file://<file>", EPOCH.sub("<epoch>", TS.sub("<ts>", a)))
args = sys.argv[1:]
if args[:2] in (["logs", "get-query-results"], ["logs", "stop-query"]) and "--query-id" in args:
    qid = args[args.index("--query-id") + 1]
    k = qid[:8] + qid[9:13]
    key = hashlib.sha1(json.dumps([args[0], args[1], k]).encode()).hexdigest()[:12]
else:
    key = hashlib.sha1(json.dumps([normalise(mask(a)) for a in args]).encode()).hexdigest()[:12]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
path = os.path.join(F, key + ".json")
if not os.path.exists(path):
    sys.stderr.write("ERROR: no fixture " + key + " for " + json.dumps(args) + "\n")
    sys.exit(97)
case = json.load(open(path))
sys.stdout.write(case["stdout"])
sys.stderr.write(case["stderr"])
sys.exit(case["code"])
"""


@pytest.fixture
def fake(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    aws = bin_dir / "aws"
    aws.write_text(FAKE_AWS, encoding="utf-8")
    aws.chmod(aws.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "aws.log"
    log.write_text("")
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_FIXTURES"] = str(FIXTURES)
    env["FAKE_LOG"] = str(log)

    class Fake:
        def run(self, script: str, *args: str):
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / f"cloudwatch-{script}.py"), *args],
                capture_output=True,
                text=True,
                env=env,
                cwd=tmp_path,
                check=False,
            )
            assert "no fixture" not in result.stderr + result.stdout, (
                "the fake aws had no fixture for a call: "
                + result.stderr
                + result.stdout
            )
            return result

        def json(self, script: str, *args: str):
            result = self.run(script, *args, "--json")
            assert result.returncode in (0, 1), result.stderr
            return result.returncode, json.loads(result.stdout)

        def calls(self) -> list[list[str]]:
            return [json.loads(line) for line in log.read_text().splitlines()]

    return Fake()


# --- the shared module -------------------------------------------------------


def test_insights_rows_become_dicts_with_the_numbers_coerced():
    aws = load("cloudwatch_aws")
    data = {
        "status": "Complete",
        "results": [
            [
                {"field": "n", "value": "1150"},
                {"field": "resource.service.name", "value": "orders-api"},
                {"field": "mean", "value": "0.00125"},
                {"field": "@ptr", "value": "CmgKJwoj"},
            ]
        ],
    }
    (row,) = aws.insights_rows(data)
    assert row["n"] == 1150 and row["mean"] == 0.00125
    assert row["resource.service.name"] == "orders-api"


def test_the_errors_are_classified_off_stderr():
    aws = load("cloudwatch_aws")
    assert (
        aws.classify(
            "Error when retrieving token from sso: Token has expired and refresh failed\n",
            255,
        )[0]
        == "identity-expired"
    )
    assert (
        aws.classify(
            "aws: [ERROR]: The config profile (nope) could not be found\n", 255
        )[0]
        == "no-profile"
    )
    assert (
        aws.classify(
            'Unable to locate credentials. You can configure credentials by running "aws configure".\n',
            253,
        )[0]
        == "no-credentials"
    )
    kind, detail = aws.classify(
        "An error occurred (MalformedQueryException) when calling the StartQuery operation: "
        "unexpected symbol found ( at line 1 and position 115\n",
        254,
    )
    assert kind == "malformed-query" and "position 115" in detail
    assert (
        aws.classify(
            "An error occurred (InvalidRequestException) when calling the GetTraceSummaries operation: Invalid input symbol\n",
            254,
        )[0]
        == "invalid-request"
    )
    kind, detail = aws.classify(
        "An error occurred (ResourceNotFoundException) when calling the StartQuery operation: "
        "Log group '/x' does not exist for account ID '123456789012' (Service: AWSLogs; Status Code: 400)\n",
        254,
    )
    assert kind == "not-found" and "123456789012" not in detail, (
        "the account id is scrubbed"
    )
    assert (
        aws.classify(
            "An error occurred (AccessDeniedException) when calling the GetServiceGraph operation: User is not authorized\n",
            254,
        )[0]
        == "rights"
    )
    assert (
        aws.classify(
            "An error occurred (ThrottlingException) when calling the FilterLogEvents operation: Rate exceeded\n",
            254,
        )[0]
        == "throttled"
    )
    assert aws.classify("usage: aws [options]\n", 252)[0] == "usage"


def test_the_temporality_is_read_off_the_pushes_in_time_order():
    metrics = load("cloudwatch-metrics")
    assert metrics.classify_values([100, 120, 150, 180]) == ("cumulative", False, 80)
    assert metrics.classify_values([100, 120, 150, 180, 5, 12, 30]) == (
        "cumulative",
        True,
        80 + 5 + 25,
    ), "a drop to near zero then rising is a restart: the per-epoch deltas summed"
    assert metrics.classify_values([12, 35, 0, 20, 8])[0] == "delta"
    assert metrics.classify_values([7, 7, 7]) == ("flat", False, 0.0)
    assert metrics.classify_values([2, 9, 40])[0] == "ambiguous"
    assert metrics.classify_values([5])[0] == "undetermined"


def test_a_result_row_is_scrubbed_of_its_pointer_and_account_prefix():
    logs = load("cloudwatch-logs")
    row = {"@ptr": "CmgKJwoj", "@log": "123456789012:/contoso/logs", "n": 3}
    assert logs.scrub(row) == {"@log": "/contoso/logs", "n": 3}


def test_a_value_shared_by_two_fields_prints_under_the_first_field_registered():
    aws = load("cloudwatch_aws")
    aws.register_targets(log_group="/same/group", metrics_log_group="/same/group")
    assert aws._VALUE_MASKS["/same/group"] == "<log_group>"


def test_the_time_units_per_command():
    aws = load("cloudwatch_aws")
    from datetime import datetime, timezone

    dt = datetime(2026, 9, 11, 12, 40, tzinfo=timezone.utc)
    assert aws.epoch_s(dt) == 1789130400
    assert aws.epoch_ms(dt) == 1789130400000
    assert aws.iso(dt) == "2026-09-11T12:40:00Z"
    assert aws.parse_xray_ts("2026-09-11T14:49:26.123000+02:00") == datetime(
        2026, 9, 11, 12, 49, 26, 123000, tzinfo=timezone.utc
    )


def test_the_path_is_normalised_and_percentiles_are_nearest_rank():
    aws = load("cloudwatch_aws")
    assert (
        aws.normalize_path("http://localhost:8000/orders/5103/checkout")
        == "/orders/{id}/checkout"
    )
    assert (
        aws.normalize_path("http://h/orders/0e0bccfe-5551-4ce0-adc6-9eee15909af4")
        == "/orders/{id}"
    )
    assert aws.normalize_path("http://h/products") == "/products"
    assert aws.percentiles([1.0, 2.0, 3.0, 4.0, 100.0]) == {
        "p50": 3.0,
        "p95": 100.0,
        "p99": 100.0,
    }
    assert aws.percentiles([]) == {"p50": None, "p95": None, "p99": None}
    assert aws.chunks(list(range(12))) == [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [10, 11]]


def test_every_call_carries_the_profile_the_region_and_an_explicit_window(fake):
    fake.run("discover", *A, "--log-group", LG, "--metrics-log-group", MG, *WINDOW)
    fake.run(
        "logs",
        "filter",
        *A,
        "--log-group",
        LG,
        "--pattern",
        "{ $.severity_number >= 13 }",
        "--limit",
        "3",
        *WINDOW,
    )
    fake.run("traces", "operations", *A, "--service", "orders-api", *WINDOW)
    calls = fake.calls()
    assert len(calls) >= 12
    for call in calls:
        assert "--profile" in call and "--region" in call, call
        assert "--output" in call and call[call.index("--output") + 1] == "json", call
        assert "--query" not in call, (
            "never --query with a text output on a paginated command"
        )
    starts = [c for c in calls if c[:2] == ["logs", "start-query"]]
    assert starts, "Logs Insights queries ran"
    for call in starts:
        s, e = (
            int(call[call.index("--start-time") + 1]),
            int(call[call.index("--end-time") + 1]),
        )
        assert 1_000_000_000 < s < e < 10_000_000_000, "start-query takes epoch seconds"
    (fle,) = [c for c in calls if c[:2] == ["logs", "filter-log-events"]]
    s = int(fle[fle.index("--start-time") + 1])
    assert s > 1_000_000_000_000, "filter-log-events takes epoch milliseconds"
    assert "--max-items" not in fle, (
        "never beside --no-paginate; the command's own --limit caps"
    )
    assert "--limit" in fle
    (xray,) = [c for c in calls if c[:2] == ["xray", "get-trace-summaries"]]
    assert "--filter-expression" not in xray, "one unfiltered call, split client-side"
    assert 1_000_000_000 < int(xray[xray.index("--start-time") + 1]) < 10_000_000_000


def test_the_printed_commands_carry_field_names_never_the_values(fake):
    code, out = fake.json(
        "discover", *A, "--log-group", LG, "--metrics-log-group", MG, *WINDOW
    )
    assert code == 0
    for command in out["commands"]:
        assert (
            "contoso" not in command.lower() and LG not in command and MG not in command
        )
        assert "--profile <profile> --region <region>" in command
        assert (
            "<log_group>" in command
            or "<metrics_log_group>" in command
            or "xray" in command
            or "codeguru" in command
            or "cloudwatch" in command
        )
    code, out = fake.json(
        "metrics",
        "series",
        "http.server.request.duration",
        *A,
        "--namespace",
        NS,
        "--dimension",
        "http.request.method=GET",
        "--dimension",
        "http.route=/orders/{order_id}",
        "--dimension",
        "http.response.status_code=200",
        "--dimension",
        "OTelLib=opentelemetry.instrumentation.fastapi",
        "--dimension",
        "url.scheme=http",
        "--dimension",
        "network.protocol.version=1.1",
        *WINDOW,
    )
    assert code == 0
    assert "file://<queries.json>" in out["commands"][0]
    code, out = fake.json("metrics", "list", *A, "--namespace", NS)
    assert code == 0
    assert (
        NS not in out["commands"][0] and "--namespace <namespace>" in out["commands"][0]
    )


# --- context -----------------------------------------------------------------


def test_context_check_proves_identity_and_both_groups(fake):
    code, out = fake.json(
        "context", "check", *A, "--log-group", LG, "--metrics-log-group", MG
    )
    assert code == 0
    assert out["connected"] is True
    assert (
        out["identity"]["ok"] is True
        and out["identity"]["principal_type"] == "assumed-role"
    )
    assert (
        out["targeting"]["log_group"]["ok"]
        and out["targeting"]["log_group"]["retention_days"] == 7
    )
    assert out["targeting"]["metrics_log_group"]["ok"]
    assert out["failed"] == []
    assert out["commands"][0].startswith(
        "aws sts get-caller-identity --profile <profile> --region <region>"
    )
    text = fake.run(
        "context", "check", *A, "--log-group", LG, "--metrics-log-group", MG
    ).stdout
    assert "****9012" in text and "123456789012" not in text, (
        "the text form shows the last four digits only"
    )
    assert "arn:aws" not in text


def test_context_check_wrong_values_and_a_missing_profile_are_diagnosed(fake):
    result = fake.run("context", "check", *A, "--log-group", "/no/such/group")
    assert result.returncode == 3
    assert "FAILED [not-found] no log group of that exact name" in result.stdout
    assert "route to the switch to correct it" in result.stdout
    assert "metrics_log_group: skipped" in result.stdout
    result = fake.run(
        "context", "check", "--profile", "no-such-profile", "--region", "eu-central-1"
    )
    assert result.returncode == 1
    assert (
        "[no-profile]" in result.stdout
        and "aws configure list-profiles" in result.stdout
    )


def test_context_landing_proves_the_logs_and_states_the_other_two_signals(fake):
    code, out = fake.json(
        "context",
        "landing",
        *A,
        "--log-group",
        LG,
        "--metrics-log-group",
        MG,
        "--until",
        "2026-09-11T12:48:00Z",
        "--service",
        "orders-api",
    )
    assert code == 0
    assert out["landed"] is True and len(out["polls"]) == 1
    assert out["polls"][0]["newest"] >= "2026-09-11T12:48:00Z"
    assert out["metrics_log_group"]["lower_bound_only"] is True
    assert out["failed"] == []
    assert any("traces" in n and "no landing proof" in n for n in out["notes"])
    assert "stats max(@timestamp)" in out["commands"][0]
    result = fake.run(
        "context",
        "landing",
        *A,
        "--log-group",
        LG,
        "--until",
        "2026-09-11T14:00:00Z",
        "--every",
        "1",
        "--cap",
        "2s",
    )
    assert result.returncode == 1
    assert "NOT landed" in result.stdout or "not landed" in result.stdout.lower()


# --- discover ----------------------------------------------------------------


def test_discover_reads_the_three_signals_and_states_the_gaps(fake):
    code, out = fake.json(
        "discover", *A, "--log-group", LG, "--metrics-log-group", MG, *WINDOW
    )
    assert code == 0
    logs = out["logs"]
    assert logs["group"]["exists"] and logs["freshness"]["records"] == 1121
    assert {r["severity"] for r in logs["by_service_severity"]} == {"INFO", "WARN"}
    assert (
        logs["environment"][0]["environment"] == "dev"
        and logs["environment"][0]["version"] == "0.1.0"
    )
    metrics = out["metrics"]
    assert metrics["namespaces"] == [
        {"namespace": NS, "records": 280, "newest": metrics["namespaces"][0]["newest"]}
    ]
    assert (
        metrics["resource_fields"]["with_service_name"] == 0
        and "no resource fields" in metrics["resource_fields"]["note"]
    )
    by_name = {m["metric"]: m for m in metrics["by_namespace"][0]["metrics"]}
    assert by_name["http.server.request.duration"]["series"] == 35
    assert by_name["http.server.request.duration"]["dimension_sets"] == 10
    assert "http.route" in by_name["http.server.request.duration"]["full_dimension_set"]
    nodes = {n["name"]: n for n in out["traces"]["services"]}
    assert (
        nodes["orders-api"]["requests"] > 1000
        and nodes["payment-upstream"]["type"] == "remote"
    )
    assert out["profiles"]["gap"] is True
    assert out["failed"] == []
    assert sum(1 for c in out["commands"] if "start-query" in c) == 5, (
        "five Insights queries, one call each"
    )


def test_discover_text_names_the_gap_and_the_fan_out(fake):
    result = fake.run(
        "discover",
        *A,
        "--log-group",
        LG,
        "--metrics-log-group",
        MG,
        "--service",
        "orders-api",
        "--namespace",
        NS,
        "--since",
        "10m",
    )
    assert result.returncode == 0, result.stderr
    assert (
        "profiles  no CodeGuru Profiler profiling group: profiles are a telemetry gap"
        in result.stdout
    )
    assert re.search(
        r"http\.server\.request\.duration\s+35\s+10\s+OTelLib", result.stdout
    )
    assert "the EMF records carry no resource fields" in result.stdout
    assert "queries run (record these):" in result.stdout


# --- traces ------------------------------------------------------------------


def test_traces_operations_from_one_unfiltered_summaries_call(fake):
    code, out = fake.json(
        "traces",
        "operations",
        *A,
        "--service",
        "orders-api",
        *WINDOW,
        "--slow",
        "2",
        "--failed",
        "2",
    )
    assert code == 0
    assert out["traces"] == 146, "len(TraceSummaries), never TracesProcessedCount"
    assert out["traces_processed_count_per_page"] == 1139
    (identity,) = out["identities"]
    assert (
        identity["identity"].startswith("(null")
        and identity["t0"] == "2026-09-11T13:11:35Z"
    )
    ops = {o["operation"]: o for o in out["operations"]}
    assert set(ops) == {
        "GET /products",
        "POST /orders",
        "GET /orders/{id}",
        "POST /orders/{id}/checkout",
        "DELETE /orders/{id}",
    }
    assert ops["GET /products"]["n"] == 74 and ops["GET /products"]["statuses"] == {
        "200": 74
    }
    assert ops["POST /orders/{id}/checkout"]["p95_s"] > 0.7
    assert out["statuses"] == {"200": 112, "201": 28, "204": 2, "404": 4}
    assert out["exemplars"]["slowest"][0]["id"] == TRACE_IDS[0]
    assert (
        out["exemplars"]["failed"][0]["status"] == 404
        and out["exemplars"]["failed"][0]["error"] is True
    )
    assert len(out["commands"]) == 1
    assert any("root segment" in n for n in out["notes"])


def test_traces_operations_by_user_agent_and_the_range_bound(fake):
    result = fake.run(
        "traces", "operations", *A, "--user-agent", "odd-observe/none", *WINDOW
    )
    assert result.returncode == 0, result.stderr
    assert "identity odd-observe/none: 0 traces" in result.stdout
    result = fake.run("traces", "operations", *A, "--since", "25h")
    assert result.returncode == 2
    assert "an X-Ray range stays under 24 h" in result.stderr
    assert (
        fake.calls()[-1][:2] != ["xray", "get-trace-summaries"]
        or len(fake.calls()) == 1
    )


def test_traces_trace_batches_by_five_and_renders_the_tree(fake):
    code, out = fake.json("traces", "trace", *TRACE_IDS, *A)
    assert code == 0
    assert len(out["commands"]) == 1, "four ids fit one batch-get-traces call"
    assert "--trace-ids " + " ".join(TRACE_IDS) in out["commands"][0]
    traces = {t["id"]: t for t in out["traces"]}
    checkout = traces[TRACE_IDS[0]]
    assert checkout["duration_s"] == 0.803 and checkout["segments"] == 3
    root = checkout["tree"][0]
    assert root["name"] == "POST" and root["kind"] == "segment"
    server = root["children"][0]
    assert (
        server["name"] == "orders-api"
        and server["metadata"]["http.route"] == "/orders/{order_id}/checkout"
    )
    assert "otel.resource.service.name" in server["metadata_keys"]
    remote = server["children"][0]
    assert remote["name"] == "payment-upstream" and remote["kind"] == "subsegment"
    text = fake.run("traces", "trace", *TRACE_IDS, *A).stdout
    assert "metadata.default keys are flat dotted strings" in text
    assert len(re.findall(r"^trace 1-", text, re.MULTILINE)) == 4


def test_traces_graph_reads_the_histograms(fake):
    code, out = fake.json("traces", "graph", *A, "--service", "orders-api", *WINDOW)
    assert code == 0
    (node,) = out["nodes"]
    assert node["name"] == "orders-api" and node["requests"] == 1133
    assert node["errors"] == 17 and node["faults"] == 5
    assert node["p95"] == 0.485
    assert {e["from"] for e in out["edges"]} >= {"DELETE", "GET", "POST"}
    edge = next(e for e in out["edges"] if e["from"] == "DELETE")
    assert edge["to"] == "orders-api" and edge["faults"] == 3
    assert "--group-name" not in out["commands"][0]


# --- metrics -----------------------------------------------------------------


def test_metrics_list_counts_the_dimension_set_fan_out(fake):
    code, out = fake.json("metrics", "list", *A, "--namespace", NS)
    assert code == 0
    by_name = {m["metric"]: m for m in out["metrics"]}
    assert len(by_name) == 7
    assert by_name["http.server.request.duration"]["series"] == 35
    assert len(by_name["http.server.request.duration"]["dimension_sets"]) == 10
    assert by_name["orders.created"]["full_dimension_set"] == ["OTelLib", "product.id"]


def test_metrics_probe_reads_the_temporality_per_series(fake):
    code, out = fake.json(
        "metrics",
        "probe",
        "http.server.request.duration",
        *A,
        "--metrics-log-group",
        MG,
        "--namespace",
        NS,
        *WINDOW,
    )
    assert code == 0
    assert out["shape"] == "statset" and out["records"]["statset_records"] == 80
    assert out["qualified_by_instance"] is False
    assert len(out["series"]) == 16, (
        "eight series, two cumulative fields each (.Count and .Sum)"
    )
    counts = [s for s in out["series"] if s["field"].endswith(".Count")]
    assert all(s["temporality"] == "cumulative" for s in counts)
    assert all(s["edge_diff"] == s["latest"] - s["earliest"] for s in counts)
    assert all(s["reset_suspected"] is False for s in counts)
    assert "http.route" in counts[0]["dimensions"]
    assert any("list-metrics" in c for c in out["commands"]), (
        "the full dimension set comes from list-metrics"
    )


def test_metrics_window_reads_a_statistic_set_a_counter_and_a_gauge(fake):
    result = fake.run(
        "metrics",
        "window",
        "http.server.request.duration",
        *A,
        "--metrics-log-group",
        MG,
        "--namespace",
        NS,
        *WINDOW,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("cumulative") == 8
    assert re.search(
        r"http\.route=/orders/\{order_id\}/checkout, [^\n]*cumulative\s+10\s+\d+\s+[\d.]+\s+0\.[3-7]",
        result.stdout,
    )
    assert "percentiles are not computable from it" in result.stdout
    code, out = fake.json(
        "metrics",
        "window",
        "orders.created",
        *A,
        "--metrics-log-group",
        MG,
        "--by",
        "product.id",
        "--by",
        "OTelLib",
        *WINDOW,
    )
    assert code == 0
    assert out["shape"] == "scalar" and len(out["rows"]) == 10
    assert {r["temporality"] for r in out["rows"]} == {"delta"}
    assert all(isinstance(r["value"], int) and r["value"] > 0 for r in out["rows"])
    code, out = fake.json(
        "metrics",
        "window",
        "http.server.active_requests",
        *A,
        "--metrics-log-group",
        MG,
        "--namespace",
        NS,
        "--as",
        "gauge",
        *WINDOW,
    )
    assert out["as"] == "gauge"
    assert out["rows"][0]["value"] == {"min": 0, "max": 0, "mean_of_pushes": 0.0}
    assert any("gauge" in n for n in out["notes"])


def test_metrics_window_reads_a_restarted_cumulative_series_across_the_restart(fake):
    # crafted fixtures: product.id=1 pushes 100,120,150,180 then 5,12,30 (a restart);
    # product.id=2 pushes 10,13,9,20 (a per-push counter)
    code, out = fake.json(
        "metrics",
        "window",
        "synthetic.restart",
        *A,
        "--metrics-log-group",
        MG,
        "--by",
        "product.id",
        *WINDOW,
    )
    assert code == 0
    rows = {r["dimensions"]: r for r in out["rows"]}
    restarted = rows["product.id=1"]
    assert (
        restarted["temporality"] == "cumulative"
        and restarted["reset_suspected"] is True
    )
    assert restarted["value"] == 80 + 5 + 25, (
        "the per-epoch deltas summed across the restart, never the bare latest - earliest"
    )
    assert (
        rows["product.id=2"]["temporality"] == "delta"
        and rows["product.id=2"]["value"] == 52
    )
    assert any("reset_suspected" in n for n in out["notes"])
    code, out = fake.json(
        "metrics",
        "probe",
        "synthetic.restart",
        *A,
        "--metrics-log-group",
        MG,
        "--by",
        "product.id",
        *WINDOW,
    )
    series = {str(s["dimensions"]["product.id"]): s for s in out["series"]}
    assert series["1"]["reset_suspected"] is True and series["1"]["edge_diff"] == 110
    assert series["2"]["reset_suspected"] is False and series["2"]["edge_diff"] is None


def test_metrics_series_goes_through_a_queries_file(fake):
    code, out = fake.json(
        "metrics",
        "series",
        "http.server.request.duration",
        *A,
        "--namespace",
        NS,
        "--dimension",
        "http.request.method=GET",
        "--dimension",
        "http.route=/orders/{order_id}",
        "--dimension",
        "http.response.status_code=200",
        "--dimension",
        "OTelLib=opentelemetry.instrumentation.fastapi",
        "--dimension",
        "url.scheme=http",
        "--dimension",
        "network.protocol.version=1.1",
        *WINDOW,
    )
    assert code == 0
    assert [q["MetricStat"]["Stat"] for q in out["metric_data_queries"]] == [
        "SampleCount",
        "Sum",
        "Average",
        "Minimum",
        "Maximum",
    ]
    assert {"Name": "http.route", "Value": "/orders/{order_id}"} in out[
        "metric_data_queries"
    ][0]["MetricStat"]["Metric"]["Dimensions"]
    stats = {s["stat"]: s for s in out["stats"]}
    assert (
        stats["SampleCount"]["status"] == "Complete"
        and stats["SampleCount"]["datapoints"] == 10
    )
    assert stats["SampleCount"]["points"][0][0].endswith("Z"), (
        "UTC, never the machine's offset"
    )
    assert any("snapshot" in n for n in out["notes"])
    (call,) = [c for c in fake.calls() if c[:2] == ["cloudwatch", "get-metric-data"]]
    assert call[call.index("--metric-data-queries") + 1].startswith("file://")


# --- logs --------------------------------------------------------------------


def test_logs_count_sample_and_filter(fake):
    code, out = fake.json(
        "logs", "count", *A, "--log-group", LG, "--service", "orders-api", *WINDOW
    )
    assert code == 0
    assert out["total"] == 1141
    assert {(r["severity"], r["n"]) for r in out["rows"]} == {
        ("INFO", 1136),
        ("WARN", 5),
    }
    result = fake.run("logs", "count", *A, "--log-group", LG, "--bin", "5m", *WINDOW)
    assert result.returncode == 0 and "bin(5m)" in result.stdout
    code, out = fake.json(
        "logs",
        "sample",
        *A,
        "--log-group",
        LG,
        "--min-severity",
        "13",
        "--show",
        "5",
        *WINDOW,
    )
    assert code == 0 and len(out["records"]) == 5
    assert all(
        r["severity_number"] == 13 and r["severity_text"] == "WARN"
        for r in out["records"]
    )
    assert all(re.fullmatch(r"[0-9a-f]{32}", r["trace_id"]) for r in out["records"])
    assert out["records"][0]["scope.name"] == "app.orders"
    code, out = fake.json(
        "logs",
        "filter",
        *A,
        "--log-group",
        LG,
        "--pattern",
        "{ $.severity_number >= 13 }",
        "--limit",
        "3",
        *WINDOW,
    )
    assert code == 0
    assert 1 <= len(out["events"]) <= 3 and out["truncated"] is True
    assert out["events"][0]["stream"] == "otel-collector"


def test_logs_routes_is_the_chained_parse(fake):
    code, out = fake.json(
        "logs", "routes", *A, "--log-group", LG, "--service", "orders-api", *WINDOW
    )
    assert code == 0
    assert out["rows"][0] == {
        "method": "GET",
        "route": "/products",
        "status": 200,
        "n": 540,
    }
    assert any(
        r["route"] == "/orders" and r.get("tail") == "/checkout" for r in out["rows"]
    )
    assert out["not_access_lines"] == 5
    query = out["commands"][0]
    assert "parse" in query and "replace(" not in query and "| sort bin" not in query


def test_logs_query_is_the_escape_hatch_with_the_poll_inside(fake):
    code, out = fake.json(
        "logs",
        "query",
        *A,
        "--log-group",
        LG,
        "stats count() as n by `scope.name`, severity_text",
        *WINDOW,
    )
    assert code == 0
    assert out["status"] == "Complete" and out["rows_total"] == 2
    assert out["rows"][0] == {
        "scope.name": "uvicorn.access",
        "severity_text": "INFO",
        "n": 1139,
    }
    assert out["statistics"]["recordsMatched"] == 1144.0
    calls = fake.calls()
    assert [c[1] for c in calls if c[0] == "logs"][:2] == [
        "start-query",
        "get-query-results",
    ]
    result = fake.run(
        "logs",
        "query",
        *A,
        "--log-group",
        LG,
        "stats count() as n by bin(5m) | sort bin(5m)",
        *WINDOW,
    )
    assert result.returncode == 1
    assert (
        "[malformed-query] MalformedQueryException on StartQuery: unexpected symbol found ( at line 1 and position 115"
        in result.stdout
    )


def test_logs_filter_confirms_an_emf_group(fake):
    code, out = fake.json(
        "logs",
        "filter",
        *A,
        "--log-group",
        MG,
        "--pattern",
        '{ $._aws.CloudWatchMetrics[0].Namespace = "*" }',
        "--limit",
        "1",
        *WINDOW,
    )
    assert code == 0
    assert len(out["events"]) == 1 and out["events"][0]["stream"].startswith(
        "otel-stream-"
    )
    assert "_aws" in out["events"][0]["message"]
    assert "<log_group>" in out["commands"][0], (
        "the group given to --log-group prints as its own field"
    )


# --- usage errors ------------------------------------------------------------


def test_usage_errors_exit_two_before_any_aws_call(fake):
    result = fake.run(
        "discover", *A, "--log-group", LG, "--metrics-log-group", MG, "--since", "5x"
    )
    assert result.returncode == 2 and "a duration is <number><s|m|h|d>" in result.stderr
    result = fake.run(
        "logs", "count", *A, "--log-group", LG, "--from", TO, "--to", FROM
    )
    assert result.returncode == 2 and "--to must be after --from" in result.stderr
    result = fake.run("metrics", "list", *A)
    assert result.returncode == 2
    assert fake.calls() == []


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
                r"python3 <Skills>/observability-cli-guides/scripts/cloudwatch-(\w+)\.py(.*)",
                line,
            )
            if not m:
                continue
            script, rest = m.group(1), m.group(2).split()
            sub = rest[0] if rest and not rest[0].startswith(("--", "<", "'")) else None
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
            cmd = [sys.executable, str(SCRIPTS / f"cloudwatch-{script}.py")]
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
        "Connection proof": "context",
    }
    common = {"--help", "--profile", "--region", "--from", "--to", "--since", "--json"}
    aws_flags = {"--group-name", "--query", "--output", "--no-paginate", "--max-items"}
    checked = 0
    for section in sections:
        title = section.split("\n", 1)[0]
        script = next((s for key, s in scripts.items() if title.startswith(key)), None)
        if script is None:
            continue
        surface = re.search(r"Whole surface[^:]*:(.*?)(?:\n\n|\Z)", section, re.DOTALL)
        assert surface, title
        flags = set(re.findall(r"`(--[a-z-]+)", surface.group(1))) - aws_flags
        assert flags, title
        subs = {sub for s, sub, _ in reference_invocations(section) if s == script}
        accepted = ""
        for sub in subs or {None}:
            cmd = [
                sys.executable,
                str(SCRIPTS / f"cloudwatch-{script}.py"),
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
        stated = flags | common
        for flag in set(re.findall(r"(--[a-z-]+)", accepted)):
            assert flag in stated, (
                f"{script}: {flag} accepted by the script, not stated in the reference"
            )
        checked += 1
    assert checked == 6
