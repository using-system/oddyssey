"""Tests for the k6-guides skill's benchmark replay.

The script is loaded from its packaged location so the tests exercise the
very file the skill ships. Its contract is that a replay adds no
judgement: the same stored benchmark yields the same command, and the
flags that would silently edit the benchmark are refused rather than
passed through.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".apm/skills/k6-guides/scripts/replay_benchmark.py"
)

MANIFEST = """\
name: demo-load
service: demo
run_slug_env: RUN_SLUG
target:
  base_url_env: API_URL
  base_url_default: http://localhost:8010
  mcp_base_url_env: MCP_BASE_URL
  mcp_base_url_default: http://localhost:8011/mcp
"""


def load():
    spec = importlib.util.spec_from_file_location("replay_benchmark", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def replay():
    return load()


@pytest.fixture
def benchmark(tmp_path: Path) -> Path:
    d = tmp_path / "demo-load"
    d.mkdir()
    (d / "manifest.yaml").write_text(MANIFEST)
    (d / "script.js").write_text("export default function () {}\n")
    return d


def run_cli(benchmark: Path, *args: str, env: dict | None = None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(benchmark), *args],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )


def test_a_scalar_field_is_read_off_the_manifest(replay):
    assert replay.manifest_field(MANIFEST, "name") == "demo-load"
    assert replay.manifest_field(MANIFEST, "run_slug_env") == "RUN_SLUG"
    assert replay.manifest_field(MANIFEST, "absent") is None


def test_every_base_url_pair_is_resolved(replay):
    assert replay.base_url_defaults(MANIFEST) == {
        "API_URL": "http://localhost:8010",
        "MCP_BASE_URL": "http://localhost:8011/mcp",
    }


def test_a_trailing_comment_is_not_part_of_the_default(replay):
    text = "  base_url_env: API_URL\n  base_url_default: http://x:1  # the api\n"
    assert replay.base_url_defaults(text) == {"API_URL": "http://x:1"}


@pytest.mark.parametrize(
    "flag",
    ["--vus", "--iterations", "--duration", "--stage", "--rps", "--no-thresholds"],
)
def test_a_flag_that_would_edit_the_benchmark_is_refused(benchmark, flag):
    p = run_cli(benchmark, "--run-slug", "s", "--dry-run", flag, "3")
    assert p.returncode != 0
    assert flag in (p.stderr + p.stdout)


def test_the_refused_set_is_the_documented_one(replay):
    assert replay.REFUSED >= {
        "--vus",
        "--iterations",
        "--duration",
        "--stage",
        "--rps",
        "--execution-segment",
        "--no-thresholds",
        "--no-setup",
        "--no-teardown",
    }


def test_dry_run_builds_the_command_and_runs_nothing(benchmark):
    p = run_cli(benchmark, "--run-slug", "harness-test", "--dry-run")
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert "k6 run" in out
    # the command runs from the benchmark's own directory, so the script is
    # named relatively - that is what makes two replays byte-identical
    assert "k6 run script.js" in out
    assert "-e API_URL=http://localhost:8010" in out
    assert "-e MCP_BASE_URL=http://localhost:8011/mcp" in out
    assert "-e RUN_SLUG=harness-test" in out


def test_the_slug_travels_through_the_manifests_own_variable(tmp_path):
    d = tmp_path / "b"
    d.mkdir()
    (d / "manifest.yaml").write_text("name: b\nrun_slug_env: INSTANCE_ID\n")
    (d / "script.js").write_text("export default function () {}\n")
    p = run_cli(d, "--run-slug", "s1", "--dry-run")
    assert "-e INSTANCE_ID=s1" in p.stdout


def test_an_explicit_env_overrides_the_manifest_default(benchmark):
    p = run_cli(
        benchmark, "--run-slug", "s", "--dry-run", "-e", "API_URL=http://other:9"
    )
    assert "-e API_URL=http://other:9" in p.stdout
    assert "-e API_URL=http://localhost:8010" not in p.stdout


def test_two_replays_of_one_benchmark_build_the_same_command(benchmark):
    first = run_cli(benchmark, "--run-slug", "s", "--dry-run").stdout
    second = run_cli(benchmark, "--run-slug", "s", "--dry-run").stdout
    line = lambda out: next(l for l in out.splitlines() if "k6 run" in l)
    assert line(first) == line(second)


def test_a_missing_benchmark_directory_is_named(tmp_path):
    p = run_cli(tmp_path / "nope", "--run-slug", "s", "--dry-run")
    assert p.returncode != 0
    assert "nope" in (p.stderr + p.stdout)


def test_json_output_carries_the_record(benchmark):
    p = run_cli(benchmark, "--run-slug", "s", "--dry-run", "--json")
    assert p.returncode == 0, p.stderr
    record = json.loads(p.stdout)
    assert record["benchmark"] == "demo-load"
    assert record["command"].startswith("k6 run script.js")
    assert "-e RUN_SLUG=s" in record["command"]


def test_status_without_a_detached_run_is_an_error_not_a_crash(tmp_path):
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--status", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 1
    assert "no detached replay" in p.stderr


def test_detach_returns_at_once_and_status_tracks_it(benchmark, tmp_path, monkeypatch):
    """The detached form is what a scenario longer than a tool call uses."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "k6"
    stub.write_text("#!/bin/sh\nsleep 5\n")
    stub.chmod(0o755)
    out = tmp_path / "detached"
    e = dict(os.environ)
    e["PATH"] = str(bin_dir) + os.pathsep + e["PATH"]
    p = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(benchmark),
            "--run-slug",
            "s",
            "--detach",
            str(out),
        ],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    assert (out / "replay-record.json").is_file()
    assert (out / "runner.pid").is_file()
    record = json.loads((out / "replay-record.json").read_text())
    assert record["start_utc"] and record["detached_in"] == str(out)
    assert "end_utc" not in record

    status = subprocess.run(
        [sys.executable, str(SCRIPT), "--status", str(out), "--json"],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["finished"] is False


def test_status_wait_blocks_until_finished_and_is_bounded(benchmark, tmp_path):
    """--status --wait is the wait the contracts describe, shipped: no poller
    to author. It returns 0 once the run finished, 3 at the bound."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "k6"
    stub.write_text("#!/bin/sh\nsleep 2\n")
    stub.chmod(0o755)
    out = tmp_path / "detached"
    e = dict(os.environ)
    e["PATH"] = str(bin_dir) + os.pathsep + e["PATH"]
    run = [sys.executable, str(SCRIPT)]
    p = subprocess.run(
        [*run, str(benchmark), "--run-slug", "s", "--detach", str(out)],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    bound = subprocess.run(
        [*run, "--status", str(out), "--wait", "1s"],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert bound.returncode == 3 and "still running" in bound.stdout
    assert "bounded on purpose" in bound.stderr
    done = subprocess.run(
        [*run, "--status", str(out), "--wait", "20s", "--json"],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    record = json.loads(done.stdout)
    assert record["finished"] is True and "exit_code" in record
    bare = subprocess.run(
        [*run, "--status", str(out), "--wait", "1"],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert bare.returncode == 0, bare.stderr  # a bare number is seconds
    alone = subprocess.run(
        [*run, "--wait", "1s"], capture_output=True, text=True, env=e, check=False
    )
    assert alone.returncode == 2 and "--wait goes with --status" in alone.stderr
    bad = subprocess.run(
        [*run, "--status", str(out), "--wait", "5x"],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert bad.returncode == 2 and "<number>[s|m|h]" in bad.stderr
    missing = subprocess.run(
        [*run, "--status", str(tmp_path / "nowhere"), "--wait", "1s"],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert missing.returncode == 1 and "no detached replay" in missing.stderr


def test_parse_wait_reads_every_unit(replay):
    assert replay.parse_wait("20m") == 1200
    assert replay.parse_wait("1h") == 3600
    assert replay.parse_wait("300s") == 300 and replay.parse_wait("7") == 7
    with pytest.raises(SystemExit):
        replay.parse_wait("5x")


def test_status_wait_stops_at_once_when_the_runner_is_gone(benchmark, tmp_path):
    """A killed run never writes `done`: the wait says so instead of
    sitting on the bound."""
    import signal
    import time as _time

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "k6"
    stub.write_text("#!/bin/sh\nsleep 30\n")
    stub.chmod(0o755)
    out = tmp_path / "detached"
    e = dict(os.environ)
    e["PATH"] = str(bin_dir) + os.pathsep + e["PATH"]
    run = [sys.executable, str(SCRIPT)]
    p = subprocess.run(
        [*run, str(benchmark), "--run-slug", "s", "--detach", str(out)],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    pid = int((out / "runner.pid").read_text())
    os.killpg(pid, signal.SIGKILL)
    _time.sleep(0.5)
    started = _time.monotonic()
    gone = subprocess.run(
        [*run, "--status", str(out), "--wait", "30s"],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert gone.returncode == 1 and "gone without a record" in gone.stderr
    assert _time.monotonic() - started < 10


def test_the_benchmark_is_still_required_for_a_replay(tmp_path):
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--run-slug", "s", "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode != 0
    assert "required" in (p.stderr + p.stdout)


def test_a_detached_run_records_k6s_real_exit_status(benchmark, tmp_path):
    """A threshold breach is a 99: a record that called it 0 would be
    worse than no record, since the replay's exit status is the evidence
    a report quotes."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "k6"
    stub.write_text("#!/bin/sh\necho '     checks_succeeded...: 12.00%'\nexit 99\n")
    stub.chmod(0o755)
    out = tmp_path / "detached"
    e = dict(os.environ)
    e["PATH"] = str(bin_dir) + os.pathsep + e["PATH"]
    p = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(benchmark),
            "--run-slug",
            "s",
            "--detach",
            str(out),
        ],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert p.returncode == 0, p.stderr

    for _ in range(100):
        if (out / "done").is_file():
            break
        time.sleep(0.1)
    assert (out / "done").is_file(), "the detached run never finished"

    # --status is how the record is read, and what finalises it
    status = subprocess.run(
        [sys.executable, str(SCRIPT), "--status", str(out), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert status.returncode == 0, status.stderr
    record = json.loads(status.stdout)
    assert record["exit_code"] == 99
    assert record["end_utc"]
    assert record["finished"] is True
    assert any("checks" in line for line in record["k6"])

    human = subprocess.run(
        [sys.executable, str(SCRIPT), "--status", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "exit 99" in human.stdout


def test_the_detached_record_carries_the_stated_shapes(benchmark, tmp_path):
    """An agent reading --json gets the same shapes every time: k6 a list of
    lines, stderr a string, exit_code an int, the window two instants."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "k6"
    stub.write_text(
        "#!/bin/sh\necho '     checks_succeeded...: 100.00%'\necho 'oops' >&2\nexit 0\n"
    )
    stub.chmod(0o755)
    e = dict(os.environ)
    e["PATH"] = str(bin_dir) + os.pathsep + e["PATH"]
    out = tmp_path / "d"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(benchmark),
            "--run-slug",
            "d",
            "--detach",
            str(out),
        ],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    for _ in range(100):
        if (out / "done").is_file():
            break
        time.sleep(0.1)
    bg = json.loads(
        subprocess.run(
            [sys.executable, str(SCRIPT), "--status", str(out), "--json"],
            capture_output=True,
            text=True,
            env=e,
            check=False,
        ).stdout
    )
    assert isinstance(bg["k6"], list) and bg["k6"] == ["checks_succeeded...: 100.00%"]
    assert isinstance(bg["stderr"], str) and bg["stderr"] == "oops"
    assert isinstance(bg["exit_code"], int) and bg["exit_code"] == 0
    assert isinstance(bg["start_utc"], str) and isinstance(bg["end_utc"], str)


def test_a_reused_directory_does_not_report_the_previous_runs_outcome(
    benchmark, tmp_path
):
    """A retry, or a verify replaying the baseline's slug, lands in a
    directory that already holds a finished run."""
    out = tmp_path / "reused"
    out.mkdir()
    for name, body in (
        ("done", "1"),
        ("k6-exit.code", "99"),
        ("k6-stdout.log", "     checks_succeeded...: 12.00%\n"),
        ("k6-stderr.log", "old failure\n"),
    ):
        (out / name).write_text(body)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "k6"
    stub.write_text("#!/bin/sh\nsleep 5\n")
    stub.chmod(0o755)
    e = dict(os.environ)
    e["PATH"] = str(bin_dir) + os.pathsep + e["PATH"]

    p = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(benchmark),
            "--run-slug",
            "s",
            "--detach",
            str(out),
        ],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )
    assert p.returncode == 0, p.stderr

    status = json.loads(
        subprocess.run(
            [sys.executable, str(SCRIPT), "--status", str(out), "--json"],
            capture_output=True,
            text=True,
            env=e,
            check=False,
        ).stdout
    )
    assert status["finished"] is False
    assert "exit_code" not in status


def test_otel_output_carries_what_the_exporter_needs(benchmark, tmp_path):
    """`-o opentelemetry` alone requires TLS the local stack does not
    serve, so the flag would connect to nothing and the series would
    silently never land."""
    p = run_cli(benchmark, "--run-slug", "s", "--otel", "--dry-run")
    assert p.returncode == 0, p.stderr
    assert "K6_OTEL_GRPC_EXPORTER_INSECURE=true" in p.stdout
    assert "-o opentelemetry" in p.stdout


def test_without_otel_no_exporter_environment_is_added(benchmark):
    p = run_cli(benchmark, "--run-slug", "s", "--dry-run")
    assert "K6_OTEL" not in p.stdout
    assert "opentelemetry" not in p.stdout


def test_a_configured_grpc_port_reaches_the_exporter(benchmark, tmp_path, monkeypatch):
    """The port is configurable, so a fixed endpoint would be right only
    on a machine that kept the default."""
    module = load()
    home = tmp_path / "home"
    (home / ".oddyssey").mkdir(parents=True)
    (home / ".oddyssey" / "config.json").write_text(
        json.dumps({"local": {"otlp_grpc_port": 4319}})
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    env = module.otel_env()
    assert env["K6_OTEL_GRPC_EXPORTER_INSECURE"] == "true"
    assert env["K6_OTEL_GRPC_EXPORTER_ENDPOINT"] == "localhost:4319"


# --- the stage boundaries a record needs, from the manifest and a first row ----

ROOT = Path(__file__).resolve().parents[3]
SPIKE = ROOT / ".odd/benchmarks/mcp-read-spike"
BREAKPOINT = ROOT / ".odd/benchmarks/mcp-read-breakpoint"
STORE_LOAD = ROOT / ".llms-benchmark/benchmark/llmbench-store-load"
FIRST_ROW = "2026-09-06T08:30:11Z"


def stages_cli(bench: Path, *args: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--stages", str(bench), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_stages_convert_the_manifests_offsets_from_the_first_request_row():
    """Block-style stages (the spike): every boundary laid out from the first
    row, the quoted stages named, t0 the first quoted stage's start."""
    p = stages_cli(SPIKE, "--first-row", FIRST_ROW, "--json")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["first_row"] == FIRST_ROW
    names = [s["name"] for s in out["stages"]]
    assert names == ["baseline", "ramp-up", "burst", "ramp-down", "recovery"]
    burst = out["stages"][2]
    assert burst["from"] == "2026-09-06T08:30:51Z"
    assert burst["to"] == "2026-09-06T08:31:21Z"
    assert burst["quote"] is True and burst["target"] == 100
    assert out["t0"] == "2026-09-06T08:30:51Z"
    assert out["stages"][0]["quote"] is False
    assert out["warmup"] == {"stages": ["baseline"], "seconds": 30}
    assert out["end"] == "2026-09-06T08:32:01Z"


def test_stages_print_the_records_lines_ready_to_paste():
    p = stages_cli(SPIKE, "--first-row", FIRST_ROW)
    assert p.returncode == 0, p.stderr
    text = p.stdout
    assert text.startswith(
        "Stages (UTC): offsets converted from the first request row 08:30:11"
    )
    assert "baseline 08:30:11–08:30:41 (excluded)" in text
    assert "burst 08:30:51–08:31:21" in text
    assert (
        "t0 (first measured request, where the quoted numbers start) 08:30:51" in text
    )
    assert "ramp-up 08:30:41–08:30:51 read in 30 s segments" in text
    assert "Warmup:    the manifest's baseline stage, 30 s (excluded" in text
    assert "t0:  2026-09-06T08:30:51Z" in text


def test_a_ramp_is_read_in_segments_with_the_rate_at_each_midpoint():
    """The breakpoint's one stage ramps 1 -> 200 over 10 minutes; segments of
    30 s from the stage's own start, the offered rate interpolated at the
    segment's midpoint - never its start or its end."""
    p = stages_cli(BREAKPOINT, "--first-row", "2026-09-06T08:54:02Z", "--json")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    ramp = out["stages"][0]
    assert ramp["ramp"] is True and ramp["start_target"] == 1 and ramp["target"] == 200
    segs = [s for s in out["segments"] if s["stage"] == "ramp"]
    assert len(segs) == 20
    assert segs[0]["from"] == "2026-09-06T08:54:02Z"
    assert segs[0]["to"] == "2026-09-06T08:54:32Z"
    # midpoint at 15 s of 600: 1 + 199 * 15 / 600
    assert segs[0]["midpoint_rate"] == pytest.approx(5.975)
    assert segs[-1]["midpoint_rate"] == pytest.approx(1 + 199 * 585 / 600)
    assert out["t0"] is None  # a breakpoint quotes no steady stage
    assert out["warmup"] == {"stages": [], "seconds": 0}
    p = stages_cli(
        BREAKPOINT, "--first-row", "2026-09-06T08:54:02Z", "--segment", "60s", "--json"
    )
    assert len(json.loads(p.stdout)["segments"]) == 10


def test_a_steady_stage_has_no_segments_and_a_flow_style_manifest_parses():
    """The store-load manifest writes its stages in flow style under two
    scenarios; each scenario's stages start at the first row."""
    p = stages_cli(STORE_LOAD, "--first-row", "2026-09-07T10:00:00Z", "--json")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert [(s["scenario"], s["name"]) for s in out["stages"]] == [
        ("catalog", "steady"),
        ("assistant", "steady"),
    ]
    assert out["stages"][0]["to"] == "2026-09-07T10:02:00Z"
    assert out["stages"][1]["target"] == "1 per 15s"
    assert out["segments"] == []
    assert out["t0"] == "2026-09-07T10:00:00Z"
    assert out["warmup"] == {"stages": [], "seconds": 0}
    assert "no warmup stage" in out["warmup_line"]


def test_a_ramp_before_the_quoted_stage_is_named_on_the_warmup_line_with_the_offset():
    """The stress ramps five minutes before its hold: no warmup stage, but
    the record must say how far t0 sits from the first row and why."""
    p = stages_cli(
        ROOT / ".odd/benchmarks/mcp-read-stress",
        "--first-row",
        "2026-09-06T10:00:00Z",
        "--json",
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["t0"] == "2026-09-06T10:05:00Z" and out["warmup"]["stages"] == []
    assert "t0 is 300 s after the first row" in out["warmup_line"]
    assert "before it the ramp stage ramp rather than warm up" in out["warmup_line"]


def test_stages_refuse_a_manifest_without_stages_and_a_bad_instant(tmp_path):
    d = tmp_path / "x"
    d.mkdir()
    (d / "manifest.yaml").write_text("name: x\nprofile:\n  executor: constant-vus\n")
    p = stages_cli(d, "--first-row", FIRST_ROW)
    assert p.returncode == 1 and "no stages" in p.stderr
    p = stages_cli(SPIKE, "--first-row", "yesterday")
    assert p.returncode == 1 and "RFC3339" in p.stderr
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--stages", str(SPIKE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode != 0 and "--first-row" in (p.stderr + p.stdout)


def test_a_replay_without_detach_is_refused_with_the_detached_invocation(benchmark):
    """The replay is always detached: a foreground run outlasts a tool
    call, gets cut, and gets relaunched (measured 2026-09-12 - one drive
    ran twice). The script refuses it and prints the two commands to run."""
    p = run_cli(benchmark, "--run-slug", "s1")
    assert p.returncode == 2
    assert "--detach" in p.stderr and "--status" in p.stderr and "--wait" in p.stderr
    assert "s1" in p.stderr  # the invocation carries the slug given
    p = run_cli(
        benchmark,
        "--run-slug",
        "s1",
        "-e",
        "BASE_URL=http://target.example:9",
        "--send-traceparent",
        "--otel",
    )
    assert p.returncode == 2
    line = next(ln for ln in p.stderr.splitlines() if "--detach" in ln)
    # every flag the caller gave survives on the printed invocation
    assert "-e BASE_URL=http://target.example:9" in line
    assert "--send-traceparent" in line and "--otel" in line
    p = run_cli(benchmark, "--run-slug", "s1", "--dry-run")
    assert p.returncode == 0, p.stderr
