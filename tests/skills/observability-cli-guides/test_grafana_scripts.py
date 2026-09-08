"""Tests for the observability-cli-guides skill's grafana-* scripts.

The scripts are loaded from their packaged location so the tests exercise the
very files the skill ships. Their contract is that every trap grafana.md
records about gcx output is absorbed once, in code: the hint preamble on
either stream, the multi-line JSON, the spill reference, the error object,
the per-command envelopes, the unpadded and base64 trace ids, the flamegraph
quadruples, the export lag, the Loki page cap, a counter reset. A fake `gcx`
on PATH answers with fixtures captured live on the local stack (gcx 1.2.0),
so the tests run without a stack and without the binary - and the flags the
reference states are checked against the parsers themselves.
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
REFERENCE = ROOT / ".apm/skills/observability-cli-guides/references/grafana.md"
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
hint = '{"class":"hint","summary":"use --json list"}'
if os.environ.get("FAKE_HINT_STDOUT") == "1":
    print(hint)
else:
    sys.stderr.write(hint + "\n")
open(os.environ["FAKE_LOG"], "a").write(" ".join(a) + "\n")
def out(obj, spill=False):
    if spill:
        p = os.path.join(os.environ["FAKE_SPILL_DIR"], "spill.json")
        open(p, "w").write(json.dumps(obj))
        print(json.dumps({"type": "gcx.spill_reference", "schema_version": "1", "spilled_to": p}))
    else:
        print(json.dumps(obj, indent=2))
    sys.exit(0)
def fx(name): return json.load(open(os.path.join(F, name + ".json")))
def err():
    print(open(os.path.join(F, "m_err.json")).read()); sys.exit(1)
def flag(name):
    return a[a.index(name) + 1] if name in a else None
if a[:2] == ["metrics", "query"]:
    q = a[2]
    if "no_such" in q: out(fx("m_empty"))
    if "sum by (" == q: err()
    if "--step" in a: out(fx("m_range"))
    if "histogram_quantile" in q: out(fx("m_hist"))
    d = fx("m_instant")
    if os.environ.get("FAKE_RESET") == "1" and flag("--time") != "2026-09-08T16:40:53Z":
        for r in d["data"]["result"]:
            r["value"][1] = str(float(r["value"][1]) * 0.5)
    out(d)
if a[:2] == ["metrics", "series"]: out(fx("m_series"))
if a[:2] == ["traces", "query"]:
    out(fx("t_empty") if "nope" in a[2] else fx("t_query"))
if a[:2] == ["traces", "get"]: out(fx("t_get"), spill=os.environ.get("FAKE_SPILL") == "1")
if a[:2] == ["traces", "metrics"]: out(fx("t_metrics"))
if a[:2] == ["logs", "query"]:
    if os.environ.get("FAKE_LOG_SAT") == "1":
        # exactly --limit lines, spread across the window asked for, so every
        # piece saturates and every piece carries lines of its own
        from datetime import datetime, timezone
        lim = int(flag("--limit")); f0 = datetime.fromisoformat(flag("--from").replace("Z", "+00:00")); t0 = datetime.fromisoformat(flag("--to").replace("Z", "+00:00"))
        span = (t0 - f0).total_seconds()
        vals = [{"timestamp": str(int((f0.timestamp() + span * (i + 0.5) / lim) * 1e9)), "line": f"line at +{span * (i + 0.5) / lim:.3f}s", "structuredMetadata": {"severity_text": "INFO"}} for i in range(lim)]
        out({"status": "success", "data": {"resultType": "streams", "result": [{"stream": {"service_name": "svc"}, "values": vals}]}})
    out(fx("l_query"))
if a[:2] == ["profiles", "list-profile-types"]: out(fx("p_types"))
if a[:2] == ["profiles", "labels"]: out({"names": ["llmbench-api", "llmbench-mcp"]})
if a[:2] == ["profiles", "query"]:
    if not (a[2].startswith("{") and a[2].endswith("}")): err()
    out(fx("p_zero") if "nope" in a[2] else fx("p_query"))
if a[:2] == ["datasources", "list"]: out(fx("ds_list"))
if a[:2] == ["config", "view"]: out({"current-context": "prod"})
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
    for var in ("FAKE_SPILL", "FAKE_HINT_STDOUT", "FAKE_RESET", "FAKE_LOG_SAT"):
        monkeypatch.delenv(var, raising=False)
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
SETTLED = "2026-09-08T16:44:25Z"  # --to + the 90 s default settle


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


def test_hint_is_dropped_on_either_stream_and_pretty_json_is_parsed_whole():
    g = load("grafana_gcx")
    payload = {"data": {"result": [{"metric": {}, "value": [1, "42"]}]}}
    pretty = json.dumps(payload, indent=2)
    assert g._parse_stdout(pretty) == payload
    assert g._parse_stdout('{"class":"hint","summary":"x"}\n' + pretty) == payload
    assert g._parse_stdout(pretty + '\n{"class":"hint","summary":"x"}') == payload
    assert g._parse_stdout("") is None


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
    assert all(set(e) == {"self", "total_max"} for e in frames.values())
    zero_total, zero_frames = g.flame_frames(fixture("p_zero"))
    assert zero_total == 0 and zero_frames == {}


def test_percentiles_and_exemplar_share_one_index():
    g = load("grafana_gcx")
    p = g.percentiles([0, 0, 1, 2, 5, 9, 250])
    assert p["count"] == 7 and p["max"] == 250 and p["p50"] == 2
    assert g.percentiles([])["p50"] is None
    v = [1, 2, 3, 4]
    assert v[g.percentile_index(len(v), 0.5)] == g.percentiles(v)["p50"]


def test_windows_and_durations_are_validated_not_tracebacked():
    g = load("grafana_gcx")
    assert g.parse_duration("90s") == 90 and g.parse_duration("2h") == 7200
    with pytest.raises(SystemExit, match="a duration is"):
        g.parse_duration("90")
    with pytest.raises(SystemExit, match="RFC3339"):
        g.parse_ts("yesterday")

    class NS:
        frm, to, since = WIN[1], WIN[3], None

    assert g.resolve_window(NS) == (WIN[1], WIN[3])
    NS.since = "30m"
    frm, to = g.resolve_window(NS)
    assert to.endswith("Z") and g.window_seconds(frm, to) == 1800


def test_run_gcx_strips_the_hint_follows_a_spill_and_surfaces_an_error(
    fake_gcx, tmp_path, monkeypatch
):
    g = load("grafana_gcx")
    ok = g.run_gcx(["metrics", "query", "up"])
    assert ok.ok and g.prom_result(ok.data)
    monkeypatch.setenv("FAKE_HINT_STDOUT", "1")
    on_stdout = g.run_gcx(["metrics", "query", "up"])
    assert on_stdout.ok and len(g.prom_result(on_stdout.data)) == 14
    monkeypatch.delenv("FAKE_HINT_STDOUT")
    monkeypatch.setenv("FAKE_SPILL", "1")
    spilled = g.run_gcx(["traces", "get", "abc"])
    assert spilled.ok and spilled.spilled_from and "trace" in spilled.data
    monkeypatch.delenv("FAKE_SPILL")
    bad = g.run_gcx(["metrics", "query", "sum by ("])
    assert not bad.ok and "Invalid PromQL" in bad.error
    missing = g.run_gcx(["metrics", "query", "up"], env={"PATH": str(tmp_path)})
    assert not missing.ok and missing.exit_code == 127


def test_logs_all_splits_a_saturated_window_and_deduplicates(fake_gcx, monkeypatch):
    g = load("grafana_gcx")
    monkeypatch.setenv("FAKE_LOG_SAT", "1")
    lines, results, truncated = g.logs_all(
        '{service_name="svc"}', WIN[1], WIN[3], limit=4
    )
    assert (
        len(results) > 1 and truncated
    )  # every piece saturated down to the depth limit
    assert len(lines) > 4 and len(
        {(ln["timestamp"], ln["line"]) for ln in lines}
    ) == len(lines)
    froms = {r.args[r.args.index("--from") + 1] for r in results}
    assert len(froms) > 1


# --- the scripts -------------------------------------------------------------


def test_discover_reports_presence_and_absence_and_attributes_roots_to_the_service(
    fake_gcx,
):
    r = run(
        "grafana-discover", "llmbench-api", "llmbench-mcp", "nope-svc", *WIN, "--json"
    )
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    api = o["services"]["llmbench-api"]
    assert api["metrics"]["names"] == len(
        {s["__name__"] for s in fixture("m_series")["data"]}
    )
    assert api["traces"]["matching"] == 5 and api["traces"]["rooted_here"] == 5
    assert api["logs"]["lines"] > 0 and api["profile_cpu"]["present"]
    mcp = o["services"]["llmbench-mcp"]
    assert (
        mcp["traces"]["matching"] == 5
        and mcp["traces"]["rooted_here"] == 0
        and mcp["traces"]["operations"] == {}
    )
    assert (
        o["services"]["nope-svc"]["traces"]["matching"] == 0
        and not o["services"]["nope-svc"]["profile_cpu"]["present"]
    )
    assert o["commands"] and all(c.startswith("gcx ") for c in o["commands"])
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


def test_metrics_subcommands_compose_the_documented_queries_and_print_them(fake_gcx):
    r = run(
        "grafana-metrics", "instant", "sum(x)", "--at", "2026-09-08T16:42:55Z", "--json"
    )
    o = json.loads(r.stdout)
    assert (
        r.returncode == 0
        and len(o["rows"]) == 14
        and o["commands"]
        == ["gcx metrics query 'sum(x)' --time 2026-09-08T16:42:55Z -o json"]
    )
    r = run(
        "grafana-metrics",
        "histogram",
        "http_server_duration_milliseconds",
        "--by",
        "http_target",
        "--selector",
        'service_name="svc"',
        *WIN,
        "--json",
    )
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    calls = fake_gcx.read_text()
    assert (
        'histogram_quantile(0.5, sum by (le, http_target) (rate(http_server_duration_milliseconds_bucket{service_name="svc"}[212s])))'
        in calls
    )
    assert f"--time {SETTLED}" in calls and f"--time {WIN[1]}" in calls
    row = next(e for e in o["rows"].values() if "count_settled" in e)
    assert row["count"] == 0 and "mean" not in row  # same fixture at both instants
    assert {
        "count_at_start",
        "count_settled",
        "count_increase",
        "count",
        "sum",
    } <= set(row) and not row.get("reset")
    assert any("last_over_time(" in c for c in o["commands"])
    assert len(o["commands"]) == 9
    r = run("grafana-metrics", "counter", "orders_total", *WIN, "--json")
    o = json.loads(r.stdout)
    row = next(iter(o["rows"].values()))
    assert (
        r.returncode == 0
        and {"at_start", "at_end", "settled", "increase", "delta"} <= set(row)
        and row["delta"] == 0
    )
    r = run(
        "grafana-metrics",
        "names",
        "--match",
        '{service_name="svc"}',
        "--since",
        "30m",
        "--json",
    )
    assert (
        r.returncode == 0
        and "http_server_active_requests" in json.loads(r.stdout)["names"]
    )
    r = run("grafana-metrics", "instant", "sum by (", "--json")
    assert r.returncode == 1 and "Invalid PromQL" in json.loads(r.stdout)["error"]
    r = run("grafana-metrics", "instant", "sum by (")
    assert (
        r.returncode == 1
        and r.stdout.strip().startswith("ERROR ")
        and len(r.stdout.strip().splitlines()) == 1
    )
    r = run("grafana-metrics", "counter", "orders_total", *WIN, "--settle", "90")
    assert (
        r.returncode != 0
        and "a duration is" in (r.stderr + r.stdout)
        and "Traceback" not in r.stderr
    )


def test_counter_reset_inside_the_window_withholds_the_delta(fake_gcx, monkeypatch):
    monkeypatch.setenv("FAKE_RESET", "1")
    r = run("grafana-metrics", "counter", "orders_total", *WIN, "--json")
    o = json.loads(r.stdout)
    row = next(iter(o["rows"].values()))
    assert (
        r.returncode == 0
        and row["reset"] is True
        and row["delta"] is None
        and row["settled"] < row["at_start"]
    )
    assert "RESET" in run("grafana-metrics", "counter", "orders_total", *WIN).stdout
    r = run("grafana-metrics", "histogram", "h", *WIN, "--json")
    rows = json.loads(r.stdout)["rows"].values()
    row = next(e for e in rows if "count_settled" in e)
    assert row.get("reset") is True and "mean" not in row


def test_traces_ops_ranks_root_operations_with_span_metrics_and_exemplars(
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
    assert (
        op["span_p50_ms"] is not None
        and op["span_calls"] == 0
        and o["span_metrics_present"]
    )
    assert o["exemplars"] and list(tmp_path.joinpath("ex").glob("trace-*.json"))
    calls = fake_gcx.read_text().splitlines()
    assert any('name = "GET /stats"' in c for c in calls)
    assert any(
        f"--time {SETTLED}" in c
        and "traces_spanmetrics_latency_bucket" in c
        and "[212s]" in c
        for c in calls
    )
    assert len(o["commands"]) == len([c for c in calls if c])
    r = run(
        "grafana-traces", "ops", "--service", "llmbench-api", "--since", "30m", "--json"
    )
    o = json.loads(r.stdout)
    assert (
        r.returncode == 0
        and o["span_metrics_present"]
        and o["operations"]["llmbench-api GET /stats"]["span_p50_ms"] is not None
    )


def test_traces_get_summarises_and_count_deduplicates_bins(fake_gcx):
    r = run("grafana-traces", "get", "9ed9a7b6ce4b233f8c6cf373c079811", "--json")
    assert r.returncode == 0
    o = json.loads(r.stdout)
    s = o["traces"][0]["summary"]
    assert s["root"] == "llmbench-api GET /stats" and s["errors"] == 0 and o["commands"]
    r = run(
        "grafana-traces",
        "count",
        '{ resource.service.name = "llmbench-api" }',
        *WIN,
        "--bin",
        "60s",
        "--json",
    )
    o = json.loads(r.stdout)
    assert r.returncode == 0 and len(o["bins"]) == 3 and o["total"] == 5
    assert o["bins"][1]["new"] == 0 and len(o["commands"]) == 3


def test_logs_read_metadata_split_saturated_windows_and_never_report_a_partial_ratio(
    fake_gcx, monkeypatch
):
    r = run("grafana-logs", "severity", '{service_name="llmbench-api"}', *WIN, "--json")
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert (
        o["lines"] > 0
        and "WARN" in o["severity"]
        and not o["truncated"]
        and o["commands"]
    )
    r = run(
        "grafana-logs", "correlate", '{service_name="llmbench-api"}', *WIN, "--json"
    )
    o = json.loads(r.stdout)
    assert r.returncode == 0 and '| trace_id != ""' in fake_gcx.read_text()
    assert (
        o["without"] == o["lines"] - o["with_trace_id"] == len(o["orphan_samples"]) == 0
    )
    r = run(
        "grafana-logs",
        "sample",
        '{service_name="llmbench-api"}',
        "--contains",
        'a "quoted" \\ path',
        "--severity",
        "WARN.*",
        *WIN,
        "--json",
    )
    assert r.returncode == 0
    assert (
        '|= "a \\"quoted\\" \\\\ path" | severity_text =~ "WARN.*"'
        in fake_gcx.read_text()
    )
    monkeypatch.setenv("FAKE_LOG_SAT", "1")
    r = run("grafana-logs", "correlate", '{service_name="svc"}', *WIN, "--json")
    o = json.loads(r.stdout)
    assert (
        r.returncode == 0
        and o["truncated"]
        and o["without"] is None
        and "no ratio" in o["note"]
    )
    assert run(
        "grafana-logs", "correlate", '{service_name="svc"}', *WIN
    ).stdout.startswith("at least ")


def test_profiles_top_prints_self_and_total_check_tells_a_bad_label_from_no_data_and_refuses_a_bare_selector(
    fake_gcx,
):
    r = run(
        "grafana-profiles",
        "top",
        '{service_name="llmbench-api"}',
        *WIN,
        "-n",
        "3",
        "--trace-id",
        "9ed9a7b6ce4b233f8c6cf373c079811",
        "--json",
    )
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert o["total_seconds"] == 76.51 and len(o["top_self"]) == 3 and o["top_total"]
    assert "--trace-id 09ed9a7b6ce4b233f8c6cf373c079811" in fake_gcx.read_text()
    r = run(
        "grafana-profiles",
        "check",
        '{service_name="nope-svc", "process.runtime.version"="3.12"}',
        *WIN,
        "--json",
    )
    o = json.loads(r.stdout)
    assert r.returncode == 0 and len(o["rows"]) == 3 and o["rows"][0]["total"] == 0
    r = run("grafana-profiles", "check", 'service_name="nope-svc"', *WIN)
    assert r.returncode != 0 and "inside braces" in (r.stderr + r.stdout)
    r = run("grafana-profiles", "types", "--json")
    assert (
        r.returncode == 0
        and "process_cpu:cpu:nanoseconds:cpu:nanoseconds"
        in json.loads(r.stdout)["types"]
    )


def test_context_makes_the_stack_current_in_a_private_copy_and_never_edits_the_original(
    fake_gcx, tmp_path, monkeypatch
):
    src = tmp_path / "config.yaml"
    src.write_text(
        "version: 1\nstacks:\n  local:\n    grafana:\n      server: http://localhost:3000\n  prod:\n    grafana:\n      server: https://example.grafana.net\n      token: not-a-real-token\n"
        "contexts:\n  local:\n    stack: local\n  prod:\n    stack: prod\ncurrent-context: local\n",
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
    assert "current-context: prod\n" in copy and "current-context: local" not in copy
    assert (
        "  prod:\n    stack: prod\n    datasources:\n      prometheus: prometheus\n"
        in copy
    )
    assert "not-a-real-token" in copy and copy.index("datasources:") > copy.index(
        "contexts:"
    )
    again = json.loads(run("grafana-context", "--stack", "prod", "--json").stdout)
    assert again["config"] != o["config"]


def test_context_refuses_a_name_that_is_a_stack_but_not_a_context(
    fake_gcx, tmp_path, monkeypatch
):
    src = tmp_path / "config.yaml"
    src.write_text(
        "contexts:\n  local:\n    stack: local\nstacks:\n  prod:\n    grafana:\n      server: https://x\n      password: keychain:x\ncurrent-context: local\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GCX_CONFIG", str(src))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    r = run("grafana-context", "--stack", "prod")
    assert r.returncode != 0 and "not found under contexts" in (r.stderr + r.stdout)
    assert "datasources" not in src.read_text()


# --- the reference states every flag ---------------------------------------


def _flags_of(help_text: str) -> set[str]:
    return {
        f
        for f in re.findall(r"(?<![\w-])(--[a-z][a-z-]*|-n)\b", help_text)
        if f not in ("--help",)
    }


def test_every_flag_a_script_accepts_is_stated_in_the_reference():
    reference = REFERENCE.read_text(encoding="utf-8")
    missing = []
    for script in (
        "grafana-discover",
        "grafana-metrics",
        "grafana-traces",
        "grafana-logs",
        "grafana-profiles",
        "grafana-context",
    ):
        top = run(script, "--help")
        assert top.returncode == 0, top.stderr
        subs = re.findall(r"\{([a-z,]+)\}", top.stdout)
        helps = [top.stdout] + [
            run(script, sub, "--help").stdout
            for sub in (subs[0].split(",") if subs else [])
        ]
        for flag in set().union(*(_flags_of(h) for h in helps)):
            if flag not in reference:
                missing.append(f"{script}: {flag}")
    assert not missing, "flags the reference does not state: " + ", ".join(
        sorted(missing)
    )
