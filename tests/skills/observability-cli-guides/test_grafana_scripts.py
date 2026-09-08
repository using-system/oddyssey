"""Tests for the observability-cli-guides skill's grafana-* scripts.

The scripts are loaded from their packaged location so the tests exercise the
very files the skill ships. Their contract is that every trap grafana.md
records about gcx output is absorbed once, in code: the hint preamble, the
multi-line JSON, the spill reference, the error object, the per-command
envelopes, the unpadded and base64 trace ids, the flamegraph quadruples. A
fake `gcx` on PATH answers with fixtures captured live on the local stack
(gcx 1.2.0), so the tests run without a stack and without the binary.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".apm/skills/observability-cli-guides/scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "grafana"


def load(name: str):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), SCRIPTS / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    sys.modules[spec.name] = module  # dataclasses resolves the module by name
    spec.loader.exec_module(module)
    return module


def fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


FAKE_GCX = r'''#!/usr/bin/env python3
"""A gcx that answers from fixtures, chosen by the subcommand and its arguments."""
import json, os, sys
F = os.environ["FAKE_FIXTURES"]
a = sys.argv[1:]
sys.stderr.write('{"class":"hint","summary":"use --json list"}\n')
def out(name, spill=False):
    text = open(os.path.join(F, name + ".json")).read()
    if spill:
        p = os.path.join(os.environ["FAKE_SPILL_DIR"], "spill.json")
        open(p, "w").write(text)
        print(json.dumps({"type": "gcx.spill_reference", "schema_version": "1", "spilled_to": p}))
    else:
        print(json.dumps(json.loads(text), indent=2))
    sys.exit(0)
def err():
    print(open(os.path.join(F, "m_err.json")).read()); sys.exit(1)
open(os.environ["FAKE_LOG"], "a").write(" ".join(a) + "\n")
if a[:2] == ["metrics", "query"]:
    q = a[2]
    if "no_such" in q: out("m_empty")
    if "sum by (" == q: err()
    if "--step" in a: out("m_range")
    if "histogram_quantile" in q: out("m_hist")
    out("m_instant")
if a[:2] == ["metrics", "series"]: out("m_series")
if a[:2] == ["traces", "query"]:
    out("t_empty" if "nope" in a[2] else "t_query")
if a[:2] == ["traces", "get"]: out("t_get", spill=os.environ.get("FAKE_SPILL") == "1")
if a[:2] == ["traces", "metrics"]: out("t_metrics")
if a[:2] == ["logs", "query"]: out("l_query")
if a[:2] == ["profiles", "list-profile-types"]: out("p_types")
if a[:2] == ["profiles", "labels"]: print(json.dumps({"names": ["llmbench-api", "llmbench-mcp"]})); sys.exit(0)
if a[:2] == ["profiles", "query"]: out("p_zero" if "nope" in a[2] else "p_query")
if a[:2] == ["datasources", "list"]: out("ds_list")
if a[:2] == ["config", "view"]: print(json.dumps({"current-context": "prod"})); sys.exit(0)
if a[:2] == ["config", "check"]: print("connected"); sys.exit(0)
sys.stderr.write("unknown command\n"); sys.exit(2)
'''


@pytest.fixture
def fake_gcx(tmp_path, monkeypatch):
    binary = tmp_path / "bin" / "gcx"
    binary.parent.mkdir()
    binary.write_text(FAKE_GCX, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.log"
    log.write_text("")
    monkeypatch.setenv("PATH", f"{binary.parent}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_FIXTURES", str(FIXTURES))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("FAKE_SPILL_DIR", str(tmp_path))
    monkeypatch.delenv("FAKE_SPILL", raising=False)
    return log


def run(
    script: str, *args: str, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{script}.py"), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


WIN = ("--from", "2026-09-08T16:40:53Z", "--to", "2026-09-08T16:42:55Z")


# --- the shared module -------------------------------------------------------


def test_hex_trace_id_pads_and_decodes():
    g = load("grafana_gcx")
    assert (
        g.hex_trace_id("9ed9a7b6ce4b233f8c6cf373c079811")
        == "09ed9a7b6ce4b233f8c6cf373c079811"
    )
    assert (
        g.hex_trace_id("Ce2ae2zksjP4xs83PAeYEQ==") == "09ed9a7b6ce4b233f8c6cf373c079811"
    )
    assert (
        g.short_trace_id("09ed9a7b6ce4b233f8c6cf373c079811")
        == "9ed9a7b6ce4b233f8c6cf373c079811"
    )


def test_envelopes_are_read_at_their_data_field():
    g = load("grafana_gcx")
    assert len(g.prom_result(fixture("m_instant"))) == 14
    assert g.prom_result(fixture("m_empty")) == []
    assert g.prom_value(fixture("m_empty")) is None
    assert len(g.prom_series(fixture("m_series"))) == 20
    assert len(g.traces_list(fixture("t_query"))) == 5
    assert g.traces_list(fixture("t_empty")) == []
    lines = g.logs_lines(fixture("l_query"))
    assert lines and "line" in lines[0] and lines[0]["meta"].get("code_function_name")
    assert "process_cpu:cpu:nanoseconds:cpu:nanoseconds" in g.profile_types(
        fixture("p_types")
    )


def test_flatten_trace_carries_service_parent_duration_and_attrs():
    g = load("grafana_gcx")
    spans = g.flatten_trace(fixture("t_get"))
    assert spans and spans[0]["service"] == "llmbench-api"
    assert all(len(s["trace_id"]) == 32 for s in spans)
    root = [s for s in spans if not s["parent_id"]]
    assert len(root) == 1 and root[0]["name"] == "GET /stats"
    scan = next(s for s in spans if s["name"] == "catalog stats_scan")
    assert scan["parent_id"] == root[0]["span_id"]
    assert scan["attrs"]["db.response.returned_rows"] == 5000
    assert 0 < scan["duration_ms"] <= root[0]["duration_ms"]
    summary = g.trace_summary(spans)
    assert summary["root"] == "llmbench-api GET /stats" and summary["spans"] == len(
        spans
    )


def test_flame_frames_sum_self_across_levels_and_drop_the_total_frame():
    g = load("grafana_gcx")
    total, frames = g.flame_frames(fixture("p_query"))
    assert total == 76510000000
    assert "total" not in frames
    assert all(set(e) == {"self", "total_max", "total_sum"} for e in frames.values())
    zero_total, zero_frames = g.flame_frames(fixture("p_zero"))
    assert zero_total == 0 and zero_frames == {}


def test_percentiles_on_truncated_integer_durations():
    g = load("grafana_gcx")
    p = g.percentiles([0, 0, 1, 2, 5, 9, 250])
    assert p["count"] == 7 and p["max"] == 250 and p["p50"] == 2
    assert g.percentiles([])["p50"] is None


def test_run_gcx_strips_the_hint_follows_a_spill_and_surfaces_an_error(
    fake_gcx, tmp_path, monkeypatch
):
    g = load("grafana_gcx")
    ok = g.run_gcx(["metrics", "query", "up"])
    assert ok.ok and g.prom_result(ok.data)
    monkeypatch.setenv("FAKE_SPILL", "1")
    spilled = g.run_gcx(["traces", "get", "abc"])
    assert spilled.ok and spilled.spilled_from and "trace" in spilled.data
    monkeypatch.delenv("FAKE_SPILL")
    bad = g.run_gcx(["metrics", "query", "sum by ("])
    assert not bad.ok and "Invalid PromQL" in bad.error
    missing = g.run_gcx(["metrics", "query", "up"], env={"PATH": str(tmp_path)})
    assert not missing.ok and missing.exit_code == 127


# --- the scripts -------------------------------------------------------------


def test_discover_reports_presence_and_absence_per_service(fake_gcx):
    r = run("grafana-discover", "llmbench-api", "nope-svc", *WIN, "--json")
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    api = o["services"]["llmbench-api"]
    expected_names = len({s["__name__"] for s in fixture("m_series")["data"]})
    assert api["metrics"]["names"] == expected_names and api["traces"]["roots"] == 5
    assert api["logs"]["lines"] > 0 and api["profile_cpu"]["present"]
    assert (
        o["services"]["nope-svc"]["traces"]["roots"] == 0
        and not o["services"]["nope-svc"]["profile_cpu"]["present"]
    )
    calls = fake_gcx.read_text().splitlines()
    assert sum(1 for c in calls if c.startswith("profiles labels")) == 1
    assert all("--limit 1000" in c for c in calls if c.startswith("traces query"))
    r = run("grafana-discover", "svc", *WIN, "--label-key", "job", "--json")
    assert r.returncode == 0, r.stderr
    calls = fake_gcx.read_text().splitlines()
    assert any(c.startswith('metrics series {job="svc"}') for c in calls)
    assert any(c.startswith('logs query {job="svc"}') for c in calls)
    assert any(c.startswith("profiles labels --label job") for c in calls)
    assert any('resource.service.name = "svc"' in c for c in calls)


def test_metrics_subcommands_compose_the_documented_queries(fake_gcx):
    r = run(
        "grafana-metrics", "instant", "sum(x)", "--at", "2026-09-08T16:42:55Z", "--json"
    )
    assert r.returncode == 0 and len(json.loads(r.stdout)["rows"]) == 14
    r = run(
        "grafana-metrics",
        "histogram",
        "http_server_duration_milliseconds",
        "--by",
        "http_target",
        "--selector",
        'service_name="svc"',
        *WIN[:4],
        "--json",
    )
    assert r.returncode == 0, r.stderr
    calls = fake_gcx.read_text()
    assert (
        'histogram_quantile(0.5, sum by (le, http_target) (rate(http_server_duration_milliseconds_bucket{service_name="svc"}[212s])))'
        in calls
    )
    assert "--time 2026-09-08T16:44:25Z" in calls  # --to + the 90s settle
    assert "increase(http_server_duration_milliseconds_count" in calls
    r = run("grafana-metrics", "counter", "orders_total", *WIN[:4], "--json")
    o = json.loads(r.stdout)
    row = next(iter(o["rows"].values()))
    assert r.returncode == 0 and {
        "at_start",
        "at_end",
        "settled",
        "increase",
        "delta",
    } <= set(row)
    assert "--time 2026-09-08T16:40:53Z" in fake_gcx.read_text()
    r = run(
        "grafana-metrics", "names", "--match", '{service_name="svc"}', *WIN, "--json"
    )
    assert (
        r.returncode == 0
        and "http_server_active_requests" in json.loads(r.stdout)["names"]
    )
    r = run("grafana-metrics", "instant", "sum by (", "--json")
    assert r.returncode == 1 and "Invalid PromQL" in json.loads(r.stdout)["error"]


def test_traces_ops_ranks_root_operations_with_exemplars_and_fetches_them(
    fake_gcx, tmp_path
):
    r = run(
        "grafana-traces",
        "ops",
        "--service",
        "llmbench-api",
        *WIN,
        "--fetch",
        str(tmp_path / "ex"),
        "--json",
    )
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    op = o["operations"]["llmbench-api GET /stats"]
    assert op["rooted_traces"] == 5 and op["containing_traces"] == 5
    assert len(op["p50_trace"]) == 32 and len(op["worst_rooted_trace"]) == 32
    assert op["span_p50_ms"] is not None and op["span_calls"] is not None
    assert o["exemplars"] and list(tmp_path.joinpath("ex").glob("trace-*.json"))
    calls = fake_gcx.read_text().splitlines()
    assert any('name = "GET /stats"' in c for c in calls)


def test_traces_get_summarises_and_count_deduplicates_bins(fake_gcx):
    r = run("grafana-traces", "get", "9ed9a7b6ce4b233f8c6cf373c079811", "--json")
    assert r.returncode == 0
    s = json.loads(r.stdout)["traces"][0]["summary"]
    assert s["root"] == "llmbench-api GET /stats" and s["errors"] == 0
    r = run(
        "grafana-traces",
        "count",
        '{ resource.service.name = "llmbench-api" }',
        *WIN[:4],
        "--bin",
        "60s",
        "--json",
    )
    o = json.loads(r.stdout)
    assert r.returncode == 0 and len(o["bins"]) == 3 and o["total"] == 5
    assert o["bins"][1]["new"] == 0


def test_logs_read_severity_and_trace_id_from_structured_metadata(fake_gcx):
    r = run("grafana-logs", "severity", '{service_name="llmbench-api"}', *WIN, "--json")
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert o["lines"] > 0 and "WARN" in o["severity"]
    r = run(
        "grafana-logs", "correlate", '{service_name="llmbench-api"}', *WIN, "--json"
    )
    assert r.returncode == 0 and '| trace_id != ""' in fake_gcx.read_text()
    r = run(
        "grafana-logs",
        "sample",
        '{service_name="llmbench-api"}',
        "--contains",
        "rejected",
        "--severity",
        "WARN.*",
        *WIN,
        "--json",
    )
    assert r.returncode == 0
    assert '|= "rejected" | severity_text =~ "WARN.*"' in fake_gcx.read_text()


def test_profiles_top_prints_self_and_total_and_check_tells_a_bad_label_from_no_data(
    fake_gcx,
):
    r = run(
        "grafana-profiles",
        "top",
        '{service_name="llmbench-api"}',
        *WIN,
        "-n",
        "3",
        "--json",
    )
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert o["total_seconds"] == 76.51 and len(o["top_self"]) == 3 and o["top_total"]
    r = run(
        "grafana-profiles",
        "check",
        '{service_name="nope-svc", "process.runtime.version"="3.12"}',
        *WIN,
        "--json",
    )
    o = json.loads(r.stdout)
    assert r.returncode == 0 and len(o["rows"]) == 3 and o["rows"][0]["total"] == 0
    r = run("grafana-profiles", "types", "--json")
    assert (
        r.returncode == 0
        and "process_cpu:cpu:nanoseconds:cpu:nanoseconds"
        in json.loads(r.stdout)["types"]
    )


def test_context_copies_the_config_sets_datasources_and_never_edits_the_original(
    fake_gcx, tmp_path, monkeypatch
):
    src = tmp_path / "config.yaml"
    src.write_text(
        "version: 1\nstacks:\n  prod:\n    grafana:\n      server: https://example.grafana.net\n      token: not-a-real-token\ncontexts:\n  prod:\n    stack: prod\ncurrent-context: prod\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GCX_CONFIG", str(src))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    before = src.read_text()
    r = run("grafana-context", "--stack", "prod", "--json")
    assert r.returncode == 0, r.stderr + r.stdout
    o = json.loads(r.stdout)
    assert o["ok"] and o["config"] != str(src) and o["datasources"]["tempo"] == "tempo"
    assert src.read_text() == before
    copy = Path(o["config"]).read_text()
    assert (
        "    datasources:\n      prometheus: prometheus\n" in copy
        and "not-a-real-token" in copy
    )
