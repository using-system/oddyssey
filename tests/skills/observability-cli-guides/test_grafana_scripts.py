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
    rows = list(json.loads(r.stdout)["rows"].values())
    row = next(e for e in rows if "count_settled" in e)
    assert row.get("reset") is True and "mean" not in row
    assert row["count"] is None and row["sum"] is None
    assert row["count_increase"] > 0
    text = run("grafana-metrics", "histogram", "h", *WIN).stdout
    assert "RESET" in text and "count=-" not in text and "sum=-" not in text
    # the span-metrics counter behind `ops` is guarded the same way
    r = run("grafana-traces", "ops", "--service", "llmbench-api", *WIN, "--json")
    ops = json.loads(r.stdout)["operations"]
    assert r.returncode == 0 and ops
    assert all(
        e["span_calls"] is None and e.get("span_calls_reset") is True
        for e in ops.values()
    )
    assert (
        "RESET"
        in run("grafana-traces", "ops", "--service", "llmbench-api", *WIN).stdout
    )


def test_histogram_rows_sort_busiest_first_even_when_a_row_reset():
    metrics = load("grafana-metrics")
    rows = {
        "quiet": {"count": 3.0, "count_increase": 3.0},
        "reset": {"count": None, "reset": True, "count_increase": 500.0},
        "busy": {"count": 40.0, "count_increase": 41.0},
    }
    assert [k for k, _ in sorted(rows.items(), key=metrics.sort_key)] == [
        "reset",
        "busy",
        "quiet",
    ]


def test_metrics_labels_lists_values_and_names_from_verified_queries(fake_gcx):
    r = run("grafana-metrics", "labels", "--match", '{service_name="svc"}', *WIN)
    assert r.returncode == 0 and "series carry it" in r.stdout
    assert "metrics series" in fake_gcx.read_text()
    r = run(
        "grafana-metrics",
        "labels",
        "--match",
        '{service_name="svc"}',
        "--label",
        "http_route",
        *WIN,
        "--json",
    )
    o = json.loads(r.stdout)
    assert r.returncode == 0 and o["label"] == "http_route"
    assert "count by (http_route) (last_over_time(" in o["commands"][0]


def test_errors_are_one_per_fact_and_commands_fold_losslessly():
    gcx = load("grafana_gcx")
    bad = [
        gcx.Result(args=["c"], ok=False, error=f"parse error at 1:{n}: bad")
        for n in (58, 97, 98)
    ]
    assert gcx.errors(bad) == "parse error at 1:58: bad"
    cmds = [
        'gcx metrics query "histogram_quantile(0.5, x)" --time T',
        'gcx metrics query "histogram_quantile(0.95, x)" --time T',
        'gcx metrics query "histogram_quantile(0.99, x)" --time T',
        "gcx traces get 1",
        "gcx traces get 2",
        "gcx traces get 1",
        "gcx logs query x --limit 5000",
    ]
    assert gcx.collapse_commands(cmds) == [
        'gcx metrics query {"histogram_quantile(0.5,|"histogram_quantile(0.95,|"histogram_quantile(0.99,} x)" --time T',
        "gcx traces get {1|2}",
        "gcx logs query x --limit 5000",
    ]
    lines = gcx.render_commands({"commands": cmds})
    assert lines[0].startswith("queries run (record these; 7 calls")


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


def test_traces_ops_takes_a_never_rooted_services_operations_from_its_span_metrics(
    fake_gcx,
):
    # the fixture's traces are all rooted at llmbench-*: orders-api is never a
    # root, so its operations come from the span-metrics names, in one query
    r = run("grafana-traces", "ops", "--service", "orders-api", *WIN, "--json")
    o = json.loads(r.stdout)
    assert r.returncode == 0, r.stdout
    nr = o["never_rooted"]["orders-api"]
    assert nr["traces_seen"] > 0 and "llmbench-api" in nr["roots"]
    assert nr["operations_from_span_metrics"] and "rooted at llmbench-api" in nr["why"]
    row = next(iter(o["operations"].values()))
    assert row["rooted_traces"] == 0 and row["containing_traces"] > 0
    assert row["worst_containing_trace"] and "span_p50_ms" in row
    assert row["p50_exemplar_is_containing"] and len(row["p50_trace"]) == 32
    assert (
        "sum by (span_name) (last_over_time(traces_spanmetrics_calls_total"
        in fake_gcx.read_text()
    )
    text = run("grafana-traces", "ops", "--service", "orders-api", *WIN).stdout
    assert "never a trace's root" in text and "contain" in text.splitlines()[0]
    # --name adds an operation and never switches the discovery off
    r = run(
        "grafana-traces",
        "ops",
        "--service",
        "orders-api",
        "--name",
        "X",
        *WIN,
        "--json",
    )
    o = json.loads(r.stdout)
    assert "orders-api X" in o["operations"]
    assert o["never_rooted"]["orders-api"]["operations_from_span_metrics"]
    # --top caps the list by calls, and says so
    r = run(
        "grafana-traces", "ops", "--service", "orders-api", "--top", "1", *WIN, "--json"
    )
    nr = json.loads(r.stdout)["never_rooted"]["orders-api"]
    assert len(nr["operations_from_span_metrics"]) == 1 and "top 1 of" in nr["why"]


def test_traces_ops_tells_no_traces_from_no_span_metrics_and_stays_quiet_when_rooted(
    fake_gcx,
):
    # "nope" in the selector -> the trace search answers nothing at all
    r = run("grafana-traces", "ops", "--service", "nope-svc", *WIN, "--json")
    nr = json.loads(r.stdout)["never_rooted"]["nope-svc"]
    assert nr["traces_seen"] == 0 and "check the service name" in nr["why"]
    assert "callers" not in nr["why"] and "rooted at" not in nr["why"]
    # traces rooted elsewhere but "no_such" -> the span-metrics query answers nothing
    r = run("grafana-traces", "ops", "--service", "no_such-svc", *WIN, "--json")
    nr = json.loads(r.stdout)["never_rooted"]["no_such-svc"]
    assert nr["traces_seen"] > 0 and "pass --name" in nr["why"]
    # a rooted service carries no never_rooted entry
    r = run("grafana-traces", "ops", "--service", "llmbench-api", *WIN, "--json")
    assert json.loads(r.stdout)["never_rooted"] == {}


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


def test_traces_breakdown_tables_each_root_operations_outcome_and_children(fake_gcx):
    """One call answers what the runs used to compose by fetching every trace
    and reading the documents: per root operation, the root's outcome, the
    status code it carries (or `absent`), its latency, and every child span
    with its count per trace and its attribute keys."""
    r = run("grafana-traces", "breakdown", "--service", "llmbench-api", *WIN, "--json")
    assert r.returncode == 0, r.stderr
    o = json.loads(r.stdout)
    assert o["listed"] == o["rooted"] == o["fetched"] == 5 and not o["truncated"]
    (key, op), *rest = o["breakdown"].items()
    assert key == "llmbench-api GET /stats" and not rest
    assert op["traces"] == 5 and op["root_status"] == {"UNSET": 5}
    # old semconv: the root carries http.status_code, read under either name
    assert op["http_status"] == {"200": 5} and "http.route" in op["root_attrs"]
    assert op["root_p50_ms"] == op["root_max_ms"] > 0
    scan = op["children"]["llmbench-api catalog stats_scan [INTERNAL]"]
    assert scan["per_trace"] == 1.0 and scan["in_traces"] == 5
    assert "db.system.name" in scan["attrs"] and scan["errors"] == 0
    send = op["children"]["llmbench-api GET /stats http send [INTERNAL]"]
    assert send["count"] == 10 and send["per_trace"] == 2.0
    # one search, then one get per trace, all recorded
    assert len(o["commands"]) == 6
    text = run("grafana-traces", "breakdown", "--service", "llmbench-api", *WIN).stdout
    assert "5 traces rooted at llmbench-api" in text and "http 200=5" in text
    assert "1.0/trace  llmbench-api catalog stats_scan [INTERNAL]" in text
    r = run("grafana-traces", "breakdown", "--service", "nobody", *WIN, "--json")
    o = json.loads(r.stdout)
    assert r.returncode == 0 and o["rooted"] == 0 and o["breakdown"] == {}


def test_traces_search_names_the_windows_edges_and_roots_and_get_prints_the_outcome(
    fake_gcx,
):
    """The two shapes the runs re-derived from --json by hand: the first and
    last trace of a search and its root operations, and a span's status and
    outcome attributes on its own line."""
    r = run(
        "grafana-traces",
        "search",
        '{ resource.service.name = "llmbench-api" }',
        *WIN,
        "--json",
    )
    o = json.loads(r.stdout)
    assert r.returncode == 0 and o["count"] == 5
    assert o["first"] <= o["last"] and o["first"].endswith("Z")
    assert o["roots"] == {"llmbench-api GET /stats": 5}
    text = run(
        "grafana-traces", "search", '{ resource.service.name = "llmbench-api" }', *WIN
    ).stdout
    assert f"first {o['first']} last {o['last']}" in text
    assert "     5  llmbench-api GET /stats" in text
    text = run(
        "grafana-traces", "get", "9ed9a7b6ce4b233f8c6cf373c079811", "--spans"
    ).stdout
    lines = [ln for ln in text.splitlines() if "[INTERNAL]" in ln and "http send" in ln]
    # the status code leads the attributes, whatever position the SDK gave it
    assert (
        lines
        and "parent=" in lines[0]
        and "http.status_code=200" in lines[0].split("parent=")[1]
    )
    assert lines[0].split("parent=")[1].startswith("jjirsd82e8U=  http.status_code=200")
    assert "status=" not in lines[0]  # UNSET is not printed


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


def test_context_uses_the_users_config_in_place_when_it_is_already_current(
    fake_gcx, tmp_path, monkeypatch
):
    src = tmp_path / "config.yaml"
    src.write_text(
        "stacks:\n  prod:\n    grafana:\n      server: https://example.grafana.net\n      oauth-token: keychain:not-a-real-ref\n"
        "contexts:\n  prod:\n    stack: prod\n    datasources:\n      loki: loki\ncurrent-context: prod\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GCX_CONFIG", str(src))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    before = src.read_text()
    for args in (("--stack", "prod"), ()):
        r = run("grafana-context", *args, "--json")
        o = json.loads(r.stdout)
        assert r.returncode == 0 and o["ok"] and o["in_place"], r.stdout
        assert o["config"] == str(src) and o["export"].endswith(str(src))
        assert o["datasources"]["tempo"] == "tempo"
    assert src.read_text() == before
    assert not list(tmp_path.glob("oddyssey/gcx-session-*"))
    text = run("grafana-context", "--stack", "prod").stdout
    assert "in place, nothing written" in text and "connected" in text
    assert "tempo=tempo (not a context default" in text and "loki=loki," in text
    assert json.loads(run("grafana-context", "--json").stdout)["context_defaults"] == [
        "loki"
    ]


def test_current_context_reads_quoted_commented_and_absent_values(tmp_path):
    context = load("grafana-context")
    for body, want in (
        ('current-context: "prod"\n', "prod"),
        ("current-context: 'prod' # the one\n", "prod"),
        ("current-context: prod   # comment\n", "prod"),
        ("contexts:\n  prod:\n    stack: prod\n", ""),
    ):
        f = tmp_path / "c.yaml"
        f.write_text(body, encoding="utf-8")
        assert context.current_context(str(f)) == want, body
    f = tmp_path / "d.yaml"
    f.write_text(
        "contexts:\n  prod:\n    stack: prod\n    datasources:\n      loki: l\n      prometheus: p\n  other:\n    datasources:\n      tempo: t\ncurrent-context: prod\n",
        encoding="utf-8",
    )
    assert context.context_defaults(str(f), "prod") == {"loki", "prometheus"}
    assert context.context_defaults(str(f), "other") == {"tempo"}
    g = tmp_path / "e.yaml"
    g.write_text(
        'contexts:\n  local:\n    stack: local\n    default-prometheus-datasource: prometheus\n    default-tempo-datasource: tempo\n  inline:\n    datasources: {loki: l, "pyroscope": p}\ncurrent-context: local\n',
        encoding="utf-8",
    )
    assert context.context_defaults(str(g), "local") == {"prometheus", "tempo"}
    assert context.context_defaults(str(g), "inline") == {"loki", "pyroscope"}


def test_session_paths_never_collide_inside_one_second(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    context = load("grafana-context")
    assert len({context.session_path("prod") for _ in range(20)}) == 20


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


SCRIPTS_STATED = (
    "grafana-discover",
    "grafana-metrics",
    "grafana-traces",
    "grafana-logs",
    "grafana-profiles",
    "grafana-context",
)


def _accepted_flags(script: str) -> tuple[set[str], list[str]]:
    """(every flag the script's parsers accept, its subcommand names)."""
    top = run(script, "--help")
    assert top.returncode == 0, top.stderr
    subs = re.findall(r"\{([a-z,]+)\}", top.stdout)
    names = subs[0].split(",") if subs else []
    helps = [top.stdout] + [run(script, sub, "--help").stdout for sub in names]
    return set().union(*(_flags_of(h) for h in helps)), names


def _reference_sections() -> dict[str, str]:
    """{script: the reference text that documents it} - each `###` under
    `## Query by signal` (and the remote-missions section) whose fenced
    block invokes one grafana-*.py script."""
    text = REFERENCE.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    for chunk in re.split(r"^##+ ", text, flags=re.MULTILINE):
        scripts = set(re.findall(r"scripts/(grafana-[a-z]+)\.py", chunk))
        if len(scripts) == 1:
            name = scripts.pop()
            sections[name] = sections.get(name, "") + "\n" + chunk
    return sections


def test_every_flag_a_script_accepts_is_stated_in_the_reference():
    reference = REFERENCE.read_text(encoding="utf-8")
    missing = []
    for script in SCRIPTS_STATED:
        flags, _ = _accepted_flags(script)
        for flag in flags:
            if flag not in reference:
                missing.append(f"{script}: {flag}")
    assert not missing, "flags the reference does not state: " + ", ".join(
        sorted(missing)
    )


def test_every_flag_and_subcommand_the_reference_states_exists():
    """The reverse guard: a flag or subcommand written in a script's section
    that no parser accepts is the defect a run meets as `unrecognized
    arguments` (the shape F14 had)."""
    sections = _reference_sections()
    assert set(sections) == set(SCRIPTS_STATED), sorted(sections)
    phantom = []
    for script, text in sections.items():
        flags, subs = _accepted_flags(script)
        # a gcx command quoted whole (`gcx login … --config <path>`) carries
        # gcx's flags, not the script's
        text = re.sub(r"`(gcx|config|metrics|traces|logs|profiles) [^`]*`", "", text)
        for flag in _flags_of(text):
            if flag not in flags:
                phantom.append(f"{script}: {flag}")
        for sub in re.findall(rf"{script}\.py ([a-z]+)", text):
            if sub not in subs and subs:
                phantom.append(f"{script}: subcommand {sub}")
    assert not phantom, "stated but not implemented: " + ", ".join(sorted(phantom))
