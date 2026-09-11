"""The harnessing kit's two scripts, on fixtures shaped like each CLI's own
lines: opencode's log and store, claude's transcripts, copilot's events
and stdout stream - the readers, the model id per CLI, the phase markers.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / ".claude" / "skills" / "test-plugin-harnessing" / "scripts"
ANALYZE = SCRIPTS / "analyze_run.py"
MEASURE = SCRIPTS / "measure_phase.py"
SESSION = "11111111-2222-4333-8444-555555555555"


def _load(name: str, path: Path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def measure():
    return _load("measure_phase", MEASURE)


def analyze(home: Path, *args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(ANALYZE), *args, "--json"],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def stamp(seconds: int) -> str:
    return f"2026-09-11T10:{seconds // 60:02d}:{seconds % 60:02d}.000Z"


# --- the model id, per CLI -----------------------------------------------------


def test_the_canonical_model_id_takes_each_clis_form(measure):
    assert measure.cli_model("opencode", "google/gemini-3.7-flash") == (
        "openrouter/google/gemini-3.7-flash"
    )
    assert (
        measure.cli_model("claude", "anthropic/claude-haiku-4.5") == "claude-haiku-4-5"
    )
    assert measure.cli_model("copilot", "openai/gpt-5.6-sol") == "gpt-5.6-sol"
    with pytest.raises(SystemExit):
        measure.cli_model("claude", "openai/gpt-5.6-sol")


def test_an_end_pattern_closes_the_phase_on_the_runs_own_lines(measure):
    lines = ['{"type":"assistant","x":"subagent_type\\":\\"observe-run"}\n']
    assert measure.phase_reached(
        "preflight", lines, 0, 'subagent_type\\\\":\\\\"observe-run'
    )
    assert not measure.phase_reached("preflight", [], 0, "observe-run")


# --- opencode: the log and the store -------------------------------------------


def opencode_fixture(home: Path) -> None:
    log = home / ".local/share/opencode/log"
    log.mkdir(parents=True)
    lines = [
        (
            f"timestamp={stamp(1)} level=INFO run=abc12345 message=created "
            "id=ses_root session.id=ses_root"
        ),
        (
            f"timestamp={stamp(2)} level=INFO run=abc12345 message=evaluated "
            'permission=bash pattern="python3 preflight.py --help" action=allow'
        ),
        (
            f"timestamp={stamp(5)} level=INFO run=abc12345 message=evaluated "
            "permission=task pattern=observe-run action=allow"
        ),
        (
            f"timestamp={stamp(70)} level=INFO run=abc12345 message=evaluated "
            'permission=bash pattern="ls -la" action=allow'
        ),
        (
            f"timestamp={stamp(3)} level=INFO run=other message=evaluated "
            'permission=bash pattern="rm -rf x" action=allow'
        ),
    ]
    (log / "opencode.log").write_text("\n".join(lines) + "\n")
    con = sqlite3.connect(home / ".local/share/opencode/opencode.db")
    con.execute(
        "CREATE TABLE session (id TEXT, parent_id TEXT, tokens_input INT, "
        "tokens_output INT, tokens_reasoning INT, tokens_cache_read INT, "
        "tokens_cache_write INT, cost REAL)"
    )
    con.execute("CREATE TABLE message (session_id TEXT, data TEXT)")
    con.execute(
        "INSERT INTO session VALUES ('ses_root', NULL, 100, 10, 5, 1000, 200, 0.01)"
    )
    con.execute(
        "INSERT INTO session VALUES ('ses_child', 'ses_root', 50, 20, 0, 3000, 0, 0.02)"
    )
    con.execute(
        "INSERT INTO session VALUES ('ses_alien', NULL, 999, 999, 0, 0, 0, 9.0)"
    )
    for sid, created, completed in (
        ("ses_root", 1000, 4000),
        ("ses_child", 1000, 3000),
        ("ses_child", 5000, 6000),
    ):
        con.execute(
            "INSERT INTO message VALUES (?, ?)",
            (
                sid,
                json.dumps(
                    {
                        "role": "assistant",
                        "time": {"created": created, "completed": completed},
                    }
                ),
            ),
        )
    con.execute(
        "INSERT INTO message VALUES ('ses_root', ?)", (json.dumps({"role": "user"}),)
    )
    con.commit()
    con.close()


def test_opencode_reads_its_own_run_from_the_log_and_sums_the_session_tree(tmp_path):
    opencode_fixture(tmp_path)
    report = analyze(tmp_path, "--cli", "opencode", "--run-id", "abc12345")
    assert report["commands"] == 2  # the bash permissions of this run alone
    assert report["help_calls_on_shipped_scripts"] == 1
    assert report["redundant_machine_questions"] == 1
    assert report["turns"] == 3 and report["generation_seconds"] == 6
    assert report["median_turn_seconds"] == 2.0
    # tokens: input + cache read + write; output + reasoning; the tree, not the alien
    assert report["input_tokens"] == 100 + 1000 + 200 + 50 + 3000
    assert report["output_tokens"] == 35 and report["cache_tokens"] == 4200
    assert report["cost_usd"] == 0.03
    assert report["gaps_over_threshold"][0]["seconds"] == 68


# --- claude: the transcripts ------------------------------------------------------


def claude_line(kind: str, seconds: int, request: str | None = None, **message) -> str:
    row = {"type": kind, "timestamp": stamp(seconds)}
    if request:
        row["requestId"] = request
    if message:
        row["message"] = message
    return json.dumps(row)


def claude_fixture(home: Path) -> Path:
    project = home / ".claude/projects/-tmp-any-encoding"
    sub = project / SESSION / "subagents"
    sub.mkdir(parents=True)

    def usage(out: int) -> dict:
        return {
            "input_tokens": 10,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 1000,
            "output_tokens": out,
        }

    root = [
        claude_line("user", 0),
        # one request, two content blocks: the usage repeats, output growing
        claude_line(
            "assistant",
            4,
            "req1",
            role="assistant",
            usage=usage(5),
            content=[{"type": "text", "text": "hi"}],
        ),
        claude_line(
            "assistant",
            5,
            "req1",
            role="assistant",
            usage=usage(20),
            content=[
                {"type": "tool_use", "name": "Bash", "input": {"command": "git status"}}
            ],
        ),
        claude_line("user", 6),
        claude_line(
            "assistant",
            9,
            "req2",
            role="assistant",
            usage=usage(7),
            content=[
                {
                    "type": "tool_use",
                    "name": "Agent",
                    "input": {"subagent_type": "observe-run"},
                }
            ],
        ),
    ]
    (project / f"{SESSION}.jsonl").write_text("\n".join(root) + "\n")
    agent = [
        claude_line("user", 10),
        claude_line(
            "assistant",
            12,
            "req3",
            role="assistant",
            usage=usage(3),
            content=[
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "cat > drive.sh <<'X'\nk6 run s.js\nX"},
                },
                {
                    "type": "tool_use",
                    "name": "mcp__oddyssey__odd_stack_reset",
                    "input": {},
                },
            ],
        ),
    ]
    (sub / "agent-abc.jsonl").write_text("\n".join(agent) + "\n")
    return project


def test_claude_reads_the_root_and_subagent_transcripts(tmp_path):
    claude_fixture(tmp_path)
    report = analyze(tmp_path, "--cli", "claude", "--run-id", SESSION)
    assert report["commands"] == 2
    assert report["authored_scripts"] == 1 and report["stack_resets"] == 1
    # req1 waited 4 s, req2 3 s, req3 2 s: three requests, not four blocks
    assert report["turns"] == 3 and report["generation_seconds"] == 9
    # a request's counters are their largest value, cache in the input
    assert report["output_tokens"] == 20 + 7 + 3
    assert report["input_tokens"] == 3 * (10 + 100 + 1000)
    assert report["cache_tokens"] == 3 * 1100
    assert report["cost_usd"] is None and "printed at exit" in report["cost_note"]


def test_claude_takes_the_cost_from_the_result_the_run_printed(tmp_path):
    claude_fixture(tmp_path)
    stdout = tmp_path / "run.json"
    stdout.write_text(json.dumps({"type": "result", "total_cost_usd": 0.1234}) + "\n")
    report = analyze(
        tmp_path, "--cli", "claude", "--run-id", SESSION, "--stdout", str(stdout)
    )
    assert report["cost_usd"] == 0.1234 and "cost_note" not in report


def test_claude_transcripts_are_found_whatever_the_directorys_encoding(
    tmp_path, measure
):
    claude_fixture(tmp_path)
    measure.HOMES[:] = [tmp_path]
    found = measure.claude_transcripts(SESSION)
    assert [p.name for p in found] == [f"{SESSION}.jsonl", "agent-abc.jsonl"]
    assert measure.claude_transcripts("nope") == []


# --- copilot: the events, the stream, the usage file --------------------------------


def copilot_fixture(home: Path) -> tuple[Path, Path]:
    session = home / ".copilot/session-state" / SESSION
    session.mkdir(parents=True)
    events = [
        {"type": "session.start", "timestamp": stamp(0), "data": {}},
        {
            "type": "tool.execution_start",
            "timestamp": stamp(3),
            "data": {"toolName": "bash", "arguments": {"command": "docker ps"}},
        },
        {
            "type": "tool.execution_start",
            "timestamp": stamp(4),
            "data": {"toolName": "view", "arguments": {"path": "x"}},
        },
        {
            "type": "tool.execution_start",
            "timestamp": stamp(8),
            "data": {"toolName": "oddyssey-odd_stack_reset", "arguments": {}},
        },
        {
            "type": "subagent.started",
            "timestamp": stamp(9),
            "data": {"agentName": "observe-run"},
        },
    ]
    (session / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n"
    )
    stream = [
        {
            "type": "assistant.turn_start",
            "timestamp": stamp(1),
            "data": {"turnId": "0"},
        },
        {"type": "model.call_start", "timestamp": stamp(1), "data": {"turnId": "0"}},
        {"type": "model.call_finished", "timestamp": stamp(3), "data": {"turnId": "0"}},
        {"type": "model.call_start", "timestamp": stamp(5), "data": {"turnId": "0"}},
        {"type": "model.call_finished", "timestamp": stamp(6), "data": {"turnId": "0"}},
        # the turn ends long after its model calls: tool time is not generation
        {"type": "assistant.turn_end", "timestamp": stamp(40), "data": {"turnId": "0"}},
    ]
    stdout = home / "run.jsonl"
    stdout.write_text("\n".join(json.dumps(e) for e in stream) + "\n")
    usage = home / "usage.json"
    usage.write_text(
        json.dumps(
            {
                "modelMetrics": {
                    "gpt-5.6-sol": {
                        "usage": {
                            "inputTokens": 5000,
                            "outputTokens": 300,
                            "cacheReadTokens": 4000,
                            "cacheWriteTokens": 500,
                        }
                    }
                }
            }
        )
    )
    return stdout, usage


def test_copilot_reads_the_events_and_the_model_calls_of_the_stream(tmp_path):
    stdout, usage = copilot_fixture(tmp_path)
    report = analyze(
        tmp_path, "--cli", "copilot", "--run-id", SESSION, "--stdout", str(stdout)
    )
    assert report["commands"] == 1 and report["stack_resets"] == 1
    assert report["redundant_machine_questions"] == 1
    assert report["turns"] == 2 and report["generation_seconds"] == 3
    assert report["input_tokens"] is None and "written at exit" in report["tokens_note"]
    assert report["cost_usd"] is None and "premium requests" in report["cost_note"]
    report = analyze(
        tmp_path,
        "--cli",
        "copilot",
        "--run-id",
        SESSION,
        "--stdout",
        str(stdout),
        "--usage",
        str(usage),
    )
    assert report["input_tokens"] == 5000 and report["output_tokens"] == 300
    assert report["cache_tokens"] == 4500 and "tokens_note" not in report


def test_a_record_names_the_cli_the_id_and_the_files(tmp_path):
    stdout, usage = copilot_fixture(tmp_path)
    record = tmp_path / "t.record.json"
    record.write_text(
        json.dumps(
            {
                "cli": "copilot",
                "run_id": SESSION,
                "stdout": str(stdout),
                "usage": str(usage),
            }
        )
    )
    report = analyze(tmp_path, "--record", str(record))
    assert report["cli"] == "copilot" and report["turns"] == 2
    assert report["input_tokens"] == 5000
