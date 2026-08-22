import subprocess
import sys

import pytest
from oddyssey_mcp import telemetry


@pytest.fixture()
def clean_otel_env(monkeypatch):
    for var in (
        "OTEL_SDK_DISABLED",
        "OTEL_SERVICE_NAME",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_SEMCONV_STABILITY_OPT_IN",
    ):
        monkeypatch.delenv(var, raising=False)


def test_disabled_is_a_no_op(clean_otel_env, monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    shutdown = telemetry.setup_telemetry()
    shutdown()  # callable, does nothing, raises nothing
    # The disabled path must not install defaults into the environment.
    import os

    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in os.environ


def test_force_flush_without_setup_is_safe():
    telemetry.force_flush()  # no provider installed: must not raise


def test_enabled_setup_writes_nothing_to_stdout():
    # Full real bootstrap + shutdown in a subprocess (global providers are
    # set-once per process; a subprocess keeps this test hermetic). The
    # stack is down, so exports fail: that is the NORMAL state and must
    # stay silent on stdout.
    code = (
        "from oddyssey_mcp import telemetry; "
        "shutdown = telemetry.setup_telemetry(); "
        "shutdown()"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
