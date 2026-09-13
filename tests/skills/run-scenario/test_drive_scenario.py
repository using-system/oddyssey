"""Tests for the run-scenario skill's ad-hoc drive.

The script is loaded from its packaged location so the tests exercise the
very file the skill ships. Its contract: the identity headers on every
request, the warmup suffix, one run-wide sequence from 1, t0 after the
warmup, failures recorded never retried, the record block printed
verbatim, and a detached mode for a scenario longer than a tool call.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".apm/skills/run-scenario/scripts/drive_scenario.py"
)


def load():
    spec = importlib.util.spec_from_file_location("drive_scenario", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def drive():
    return load()


class Recorder(BaseHTTPRequestHandler):
    """A service that records what it was sent and answers by route."""

    seen: ClassVar[list[dict]] = []
    lock = threading.Lock()

    def _record(self, body: bytes):
        with Recorder.lock:
            Recorder.seen.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": body.decode(),
                    "at": time.time(),
                }
            )

    def _answer(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self._record(body)
        if self.path.startswith("/fail"):
            status = 500
        elif self.path.startswith("/slow"):
            time.sleep(0.3)
            status = 200
        elif self.command == "POST":
            status = 201
        else:
            status = 200
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    do_GET = _answer
    do_POST = _answer
    do_PUT = _answer
    do_DELETE = _answer

    def log_message(self, *_):  # keep pytest's output clean
        pass


@pytest.fixture
def server():
    Recorder.seen = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    yield f"http://127.0.0.1:{port}", port
    httpd.shutdown()
    httpd.server_close()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_cli(*args: str, env: dict | None = None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=e,
        check=False,
    )


def base_args(base: str, out: Path, *ops: str, **extra: str) -> list[str]:
    args = [
        base,
        "--run-slug",
        "run-0913",
        "--prompt",
        "observe",
        "--out",
        str(out),
        "--wait-for",
        "none",
    ]
    for op in ops:
        args += ["--op", op]
    for k, v in extra.items():
        args += [f"--{k.replace('_', '-')}", v]
    return args


# --- the identity every request carries -----------------------------------------


def test_every_request_carries_both_headers_and_the_warmup_suffix(server, tmp_path):
    base, _ = server
    p = run_cli(
        *base_args(
            base,
            tmp_path / "run",
            "GET /ok",
            'POST /orders {"sku": "A1"}',
            count="3",
            warmup="2",
        )
    )
    assert p.returncode == 0, p.stderr
    seen = Recorder.seen
    # 2 ops x (2 warmup + 3 load)
    assert len(seen) == 10
    for r in seen:
        assert "traceparent" in r["headers"], r
        assert r["headers"]["user-agent"].startswith("odd-observe/run-0913"), r
    warm = [r for r in seen if r["headers"]["user-agent"].endswith("-warmup")]
    load = [r for r in seen if not r["headers"]["user-agent"].endswith("-warmup")]
    assert len(warm) == 4 and len(load) == 6
    assert all(r["headers"]["user-agent"] == "odd-observe/run-0913" for r in load)
    # the warmup goes out first: t0 is after it by construction
    assert all(r["headers"]["user-agent"].endswith("-warmup") for r in seen[:4])
    posts = [r for r in seen if r["method"] == "POST"]
    assert len(posts) == 5
    assert all(json.loads(r["body"]) == {"sku": "A1"} for r in posts)
    assert all(r["headers"]["content-type"] == "application/json" for r in posts)


def test_the_sequence_is_one_run_wide_counter_from_1(server, tmp_path):
    base, _ = server
    p = run_cli(
        *base_args(
            base, tmp_path / "run", "GET /ok", "GET /ok?x=1", count="4", warmup="1"
        )
    )
    assert p.returncode == 0, p.stderr
    run8 = hashlib.sha256(b"run-0913").hexdigest()[:8]
    seqs = []
    for r in Recorder.seen:
        m = re.fullmatch(
            r"00-0ddc0ffe([0-9a-f]{8})([0-9a-f]{16})-([0-9a-f]{16})-01",
            r["headers"]["traceparent"],
        )
        assert m, r["headers"]["traceparent"]
        assert m.group(1) == run8
        assert m.group(2) == m.group(3)
        seqs.append(int(m.group(2), 16))
    assert sorted(seqs) == list(range(1, 11))
    assert seqs == list(range(1, 11)), "sequential by default: sent in order"


def test_concurrency_keeps_the_sequence_disjoint(server, tmp_path):
    base, _ = server
    p = run_cli(
        *base_args(
            base, tmp_path / "run", "GET /ok", count="20", warmup="0", concurrency="4"
        )
    )
    assert p.returncode == 0, p.stderr
    seqs = sorted(int(r["headers"]["traceparent"][19:35], 16) for r in Recorder.seen)
    assert seqs == list(range(1, 21))
    assert "Load:     20 requests per operation, concurrency 4" in p.stdout


def test_another_prefix_and_prompt_land_in_the_headers(server, tmp_path):
    base, _ = server
    p = run_cli(
        *base_args(
            base,
            tmp_path / "run",
            "GET /ok",
            count="1",
            warmup="0",
            prefix="deadbeef",
            prompt="verify",
        )
    )
    assert p.returncode == 0, p.stderr
    r = Recorder.seen[0]
    assert r["headers"]["user-agent"] == "odd-verify/run-0913"
    assert r["headers"]["traceparent"].startswith("00-deadbeef")


# --- the record ------------------------------------------------------------------


def test_the_record_block_is_printed_verbatim(server, tmp_path):
    base, _ = server
    out = tmp_path / "run"
    p = run_cli(
        *base_args(base, out, "GET /ok", 'POST /orders {"a": 1}', count="2", warmup="1")
    )
    assert p.returncode == 0, p.stderr
    lines = p.stdout.splitlines()
    heads = [ln.split(":")[0] for ln in lines if ln and not ln.startswith(" ")]
    assert heads == [
        "Scenario",
        "Base URL",
        "Listeners",
        "Backend",
        "Instance",
        "Identity",
        "Warmup",
        "Load",
        "Started (UTC)",
        "Ended   (UTC)",
        "Query points",
        "Commands",
        "Requests",
        "Not reproducible",
    ]
    text = p.stdout
    assert f"Base URL: {base}\n" in text
    assert "Warmup:   1 request per operation (discarded; seq 1-2)\n" in text
    assert "Load:     2 requests per operation, sequential (seq 3-6)\n" in text
    assert "Query points: 1 (after Ended; no flush wait, --wait-for none)\n" in text
    run8 = hashlib.sha256(b"run-0913").hexdigest()[:8]
    assert f"trace ids start 0ddc0ffe{run8}" in text
    assert 'User-Agent "odd-observe/run-0913" (+ "-warmup" on the warmup)' in text
    started = re.search(r"Started \(UTC\): (\S+)", text).group(1)
    ended = re.search(r"Ended   \(UTC\): (\S+)", text).group(1)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", started) and started < ended
    assert f"  GET {base}/ok x2 (seq 3-4) -> 200:2\n" in text
    assert f'  POST {base}/orders {{"a": 1}} x2 (seq 5-6) -> 201:2\n' in text
    # the three lines the caller fills are placeholders, never guesses
    assert "Backend:  <yours: " in text and "Instance: <yours: " in text
    assert "Not reproducible: <yours: " in text
    # the Commands line is the invocation, re-runnable unchanged
    cmd = next(ln for ln in lines if ln.startswith("  python3 "))
    argv = shlex.split(cmd)[1:]
    assert argv[0] == str(SCRIPT)
    assert "--count 2" in cmd and "--warmup 1" in cmd and "--out" in cmd
    again = run_cli(*argv[1:], "--dry-run")
    assert again.returncode == 0, again.stderr
    # the files the run keeps, in the directory it alone owns
    record = json.loads((out / "drive-record.json").read_text())
    assert record["run_slug"] == "run-0913" and record["finished"] is True
    assert record["start_utc"] == started and record["end_utc"] == ended
    rows = [json.loads(ln) for ln in (out / "requests.jsonl").read_text().splitlines()]
    assert [r["seq"] for r in rows] == [1, 2, 3, 4, 5, 6]
    assert rows[0]["phase"] == "warmup" and rows[-1]["phase"] == "load"
    assert all(r["status"] in (200, 201) and r["ms"] >= 0 for r in rows)


def to_epoch(stamp: str) -> float:
    return (
        datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
        .replace(tzinfo=datetime.timezone.utc)
        .timestamp()
    )


def test_the_window_is_never_empty_and_holds_the_last_request(server, tmp_path):
    """Ended is ceiled to the whole second: floored, a fast drive read
    Ended = Started and every drive left its last partial second outside
    the window the queries use."""
    base, _ = server
    p = run_cli(*base_args(base, tmp_path / "run", "GET /ok", count="30", warmup="0"))
    assert p.returncode == 0, p.stderr
    started = re.search(r"Started \(UTC\): (\S+)", p.stdout).group(1)
    ended = re.search(r"Ended   \(UTC\): (\S+)", p.stdout).group(1)
    assert to_epoch(ended) > to_epoch(started)
    first = min(r["at"] for r in Recorder.seen)
    last = max(r["at"] for r in Recorder.seen)
    assert to_epoch(started) <= first
    assert to_epoch(ended) >= last
    assert to_epoch(ended) - last < 2


def test_the_load_line_states_the_operations_counts(server, tmp_path):
    base, _ = server
    p = run_cli(
        *base_args(
            base, tmp_path / "run", "GET /ok 4", "GET /ok?x=1", count="6", warmup="0"
        )
    )
    assert p.returncode == 0, p.stderr
    assert "Load:     as listed per operation, sequential (seq 1-10)\n" in p.stdout
    assert f"  GET {base}/ok x4 (seq 1-4) -> 200:4\n" in p.stdout
    p = run_cli(
        *base_args(
            base, tmp_path / "run", "GET /ok 6", "GET /ok?x=1", count="6", warmup="0"
        )
    )
    assert "Load:     6 requests per operation, sequential (seq 1-12)\n" in p.stdout


@pytest.mark.parametrize("url", ["http://127.0.0.1:abc", "http://127.0.0.1:70000"])
def test_a_malformed_port_exits_with_a_message(url, tmp_path):
    p = run_cli(*base_args(url, tmp_path / "run", "GET /ok"), "--dry-run")
    assert p.returncode == 1
    assert "Traceback" not in p.stderr and "port of 1-65535" in p.stderr


@pytest.mark.parametrize(
    "extra",
    [
        ["--run-slug", "run-\u2192"],
        ["-H", "X-Note: \U0001f680"],
        ["--op", "GET /caf\u00e9"],
    ],
)
def test_a_value_no_header_can_carry_is_refused_before_the_drive(
    server, tmp_path, extra
):
    base, _ = server
    args = base_args(base, tmp_path / "run", "GET /ok", count="1", warmup="0")
    if extra[0] == "--run-slug":
        args[args.index("--run-slug") + 1] = extra[1]
        extra = []
    p = run_cli(*args, *extra)
    assert p.returncode == 1, p.stdout
    assert "Traceback" not in p.stderr and "got" in p.stderr
    assert Recorder.seen == []
    assert not (tmp_path / "run" / "requests.jsonl").exists()


def test_the_listeners_line_carries_the_probes_fields_without_the_user(
    server, tmp_path, drive
):
    _, port = server
    if drive.shutil.which("lsof") is None:
        pytest.skip("lsof not installed")
    line = drive.listeners_line(port)
    assert line.startswith(f":{port} served by {os.getpid()} ")
    assert "(127.0.0.1)" in line
    assert os.environ.get("USER", "\0") not in line


def test_the_listeners_line_says_when_lsof_is_absent_or_finds_nothing(
    drive, monkeypatch
):
    monkeypatch.setattr(drive.shutil, "which", lambda _: None)
    assert drive.listeners_line(1) == "lsof not found - probe the port by hand"
    monkeypatch.setattr(drive.shutil, "which", lambda _: "/usr/bin/lsof")
    monkeypatch.setattr(
        drive.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, "", ""),
    )
    assert drive.listeners_line(1) == "none"


def test_lsof_field_output_is_parsed(drive):
    out = "p41234\ncuvicorn\nn127.0.0.1:8000\np51022\nccom.docker.backend\nn*:8000\n"
    assert drive.parse_lsof(out, 8000) == [
        {"pid": 41234, "command": "uvicorn", "bind": "127.0.0.1"},
        {"pid": 51022, "command": "com.docker.backend", "bind": "*"},
    ]


def test_json_output_carries_the_record(server, tmp_path):
    base, _ = server
    p = run_cli(
        *base_args(base, tmp_path / "run", "GET /ok", count="2", warmup="1"), "--json"
    )
    assert p.returncode == 0, p.stderr
    record = json.loads(p.stdout)
    for key in (
        "scenario",
        "base_url",
        "listeners",
        "run_slug",
        "prompt",
        "user_agent",
        "trace_id_prefix",
        "warmup",
        "count",
        "concurrency",
        "operations",
        "start_utc",
        "end_utc",
        "wait_for",
        "wait_seconds",
        "command",
        "requests",
        "finished",
    ):
        assert key in record, key
    assert record["requests"] == [
        {
            "method": "GET",
            "path": "/ok",
            "count": 2,
            "seq_first": 2,
            "seq_last": 3,
            "statuses": {"200": 2},
            "failed": 0,
            "body": None,
        }
    ]


# --- failures are data -------------------------------------------------------------


def test_a_failing_request_is_recorded_and_never_retried(server, tmp_path):
    base, _ = server
    p = run_cli(*base_args(base, tmp_path / "run", "GET /fail", count="3", warmup="0"))
    assert p.returncode == 0, p.stderr
    assert len(Recorder.seen) == 3, "a 500 is data: sent once, never retried"
    assert f"  GET {base}/fail x3 (seq 1-3) -> 500:3\n" in p.stdout


def test_a_refused_connection_is_recorded_as_a_failure(tmp_path):
    base = f"http://127.0.0.1:{free_port()}"
    p = run_cli(
        *base_args(base, tmp_path / "run", "GET /ok", count="2", warmup="1"), "--json"
    )
    assert p.returncode == 0, p.stderr
    record = json.loads(p.stdout)
    assert record["requests"][0]["failed"] == 2
    assert record["requests"][0]["statuses"] == {"error": 2}
    rows = [
        json.loads(ln)
        for ln in (tmp_path / "run" / "requests.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 3 and all(r["status"] is None and r["error"] for r in rows)
    assert record["listeners"] == [] and record["listeners_line"] in (
        "none",
        "lsof not found - probe the port by hand",
    )


def test_a_slow_request_past_the_timeout_is_a_failure(server, tmp_path):
    base, _ = server
    p = run_cli(
        *base_args(
            base, tmp_path / "run", "GET /slow", count="1", warmup="0", timeout="0.05"
        ),
        "--json",
    )
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["requests"][0]["statuses"] == {"error": 1}


# --- the inputs ------------------------------------------------------------------


def test_an_operation_is_method_path_optional_count_and_body(drive):
    assert drive.parse_op("GET /api/users", 30) == {
        "method": "GET",
        "path": "/api/users",
        "count": 30,
        "body": None,
    }
    assert drive.parse_op('POST /api/orders {"sku": "A1"}', 30) == {
        "method": "POST",
        "path": "/api/orders",
        "count": 30,
        "body": '{"sku": "A1"}',
    }
    assert drive.parse_op("GET /api/users 100", 30)["count"] == 100
    assert drive.parse_op('PUT /api/users/1 100 {"n": 1}', 30) == {
        "method": "PUT",
        "path": "/api/users/1",
        "count": 100,
        "body": '{"n": 1}',
    }
    for bad in ("get /x", "GET x", "GET", "GET /x 0"):
        with pytest.raises(ValueError):
            drive.parse_op(bad, 30)


def test_operations_come_from_a_file_too(server, tmp_path):
    base, _ = server
    ops = tmp_path / "ops.txt"
    ops.write_text('# the read path\nGET /ok\n\nPOST /orders 2 {"a": 1}\n')
    p = run_cli(
        *base_args(base, tmp_path / "run", count="1", warmup="0"), "--ops", str(ops)
    )
    assert p.returncode == 0, p.stderr
    assert [(r["method"], r["path"]) for r in Recorder.seen] == [
        ("GET", "/ok"),
        ("POST", "/orders"),
        ("POST", "/orders"),
    ]


def test_an_extra_header_is_sent_and_a_credential_one_is_not_recorded(server, tmp_path):
    base, _ = server
    p = run_cli(
        *base_args(base, tmp_path / "run", "GET /ok", count="1", warmup="0"),
        "-H",
        "X-Tenant: contoso",
        "-H",
        "Authorization: Bearer not-a-real-token",
    )
    assert p.returncode == 0, p.stderr
    h = Recorder.seen[0]["headers"]
    assert (
        h["x-tenant"] == "contoso" and h["authorization"] == "Bearer not-a-real-token"
    )
    assert "not-a-real-token" not in p.stdout
    assert "X-Tenant: contoso" in p.stdout
    assert (
        "Not reproducible: header Authorization (value not recorded); <yours: "
        in p.stdout
    )
    assert (
        "not-a-real-token" not in (tmp_path / "run" / "drive-record.json").read_text()
    )


def test_localhost_is_refused_and_the_reason_named(tmp_path):
    p = run_cli(
        *base_args("http://localhost:8000", tmp_path / "run", "GET /ok"), "--dry-run"
    )
    assert p.returncode == 1
    assert "127.0.0.1" in p.stderr and "localhost" in p.stderr


def test_dry_run_prints_the_plan_and_sends_nothing(server, tmp_path):
    base, _ = server
    p = run_cli(
        *base_args(
            base,
            tmp_path / "run",
            "GET /ok",
            'POST /orders {"a": 1}',
            count="7",
            warmup="2",
        ),
        "--dry-run",
    )
    assert p.returncode == 0, p.stderr
    assert Recorder.seen == []
    assert f"GET {base}/ok x7" in p.stdout and "x2 warmup" in p.stdout
    assert not (tmp_path / "run").exists()
    # --out is the one input a dry run does without
    p = run_cli(
        base, "--run-slug", "s", "--prompt", "observe", "--op", "GET /ok", "--dry-run"
    )
    assert p.returncode == 0, p.stderr
    assert "--out '<dir>'" in p.stdout and "--timeout 60 " in p.stdout


def test_the_required_inputs_are_named(tmp_path, server):
    base, _ = server
    p = run_cli(
        base, "--run-slug", "s", "--prompt", "observe", "--out", str(tmp_path / "r")
    )
    assert p.returncode == 2 and "--op" in p.stderr
    p = run_cli(
        base, "--op", "GET /ok", "--prompt", "observe", "--out", str(tmp_path / "r")
    )
    assert p.returncode == 2 and "--run-slug" in p.stderr
    p = run_cli(base, "--op", "GET /ok", "--run-slug", "s", "--prompt", "observe")
    assert p.returncode == 2 and "--out" in p.stderr


def test_the_flush_wait_is_sized_by_the_slowest_signal(drive):
    assert drive.wait_seconds("metrics") == 10
    assert drive.wait_seconds("traces") == 60
    assert drive.wait_seconds("none") == 0


def test_two_drives_of_one_scenario_print_the_same_command(server, tmp_path):
    base, _ = server
    a = run_cli(
        *base_args(base, tmp_path / "a", "GET /ok", count="1", warmup="0"), "--json"
    )
    b = run_cli(
        *base_args(base, tmp_path / "a", "GET /ok", count="1", warmup="0"), "--json"
    )
    assert json.loads(a.stdout)["command"] == json.loads(b.stdout)["command"]


# --- a scenario longer than a tool call ------------------------------------------


def test_detach_returns_at_once_and_status_wait_blocks_until_finished(server, tmp_path):
    base, _ = server
    out = tmp_path / "detached"
    started = time.monotonic()
    p = run_cli(*base_args(base, out, "GET /slow", count="3", warmup="0"), "--detach")
    assert p.returncode == 0, p.stderr
    assert time.monotonic() - started < 5
    assert "detached" in p.stdout and "--status" in p.stdout
    record = json.loads((out / "drive-record.json").read_text())
    assert record["finished"] is False and record["detached_in"] == str(out)
    assert (out / "runner.pid").is_file()

    status = run_cli("--status", str(out), "--wait", "20s", "--json")
    assert status.returncode == 0, status.stderr
    record = json.loads(status.stdout)
    assert record["finished"] is True
    assert record["requests"][0]["statuses"] == {"200": 3}
    assert (out / "done").is_file()
    assert len(Recorder.seen) == 3

    text = run_cli("--status", str(out))
    assert text.returncode == 0
    assert "Scenario:" in text.stdout and f"  GET {base}/slow x3" in text.stdout


def test_status_wait_is_bounded_and_status_without_a_run_is_an_error(server, tmp_path):
    base, _ = server
    out = tmp_path / "detached"
    p = run_cli(*base_args(base, out, "GET /slow", count="8", warmup="0"), "--detach")
    assert p.returncode == 0, p.stderr
    bounded = run_cli("--status", str(out), "--wait", "1s")
    assert bounded.returncode == 3, bounded.stderr
    assert "still running" in bounded.stdout + bounded.stderr
    final = run_cli("--status", str(out), "--wait", "30s", "--json")
    assert final.returncode == 0 and json.loads(final.stdout)["finished"] is True

    missing = run_cli("--status", str(tmp_path / "nowhere"))
    assert missing.returncode == 1 and "no detached drive" in missing.stderr
    alone = run_cli("--wait", "1s")
    assert alone.returncode == 2 and "--wait goes with --status" in alone.stderr


def test_a_reused_directory_does_not_report_the_previous_drives_outcome(
    server, tmp_path
):
    base, _ = server
    out = tmp_path / "detached"
    first = run_cli(*base_args(base, out, "GET /ok", count="1", warmup="0"))
    assert first.returncode == 0 and (out / "drive-record.json").is_file()
    p = run_cli(*base_args(base, out, "GET /slow", count="4", warmup="0"), "--detach")
    assert p.returncode == 0, p.stderr
    status = json.loads(run_cli("--status", str(out), "--json").stdout)
    assert status["finished"] is False
    assert "requests" not in status or status["requests"] == []
    run_cli("--status", str(out), "--wait", "30s")
