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


def test_both_forms_of_the_record_carry_the_same_shapes(benchmark, tmp_path):
    """An agent reading --json must not get a string here and a list there."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "k6"
    stub.write_text(
        "#!/bin/sh\necho '     checks_succeeded...: 100.00%'\necho 'oops' >&2\nexit 0\n"
    )
    stub.chmod(0o755)
    e = dict(os.environ)
    e["PATH"] = str(bin_dir) + os.pathsep + e["PATH"]

    fg = json.loads(
        subprocess.run(
            [sys.executable, str(SCRIPT), str(benchmark), "--run-slug", "f", "--json"],
            capture_output=True,
            text=True,
            env=e,
            check=False,
        ).stdout
    )
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
    for key in ("k6", "stderr", "exit_code", "start_utc", "end_utc"):
        assert type(fg[key]) is type(bg[key]), key
    assert fg["k6"] and fg["k6"] == bg["k6"]


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
