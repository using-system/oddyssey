import json
import subprocess

import httpx
import pytest
from oddyssey_mcp import config, stack
from oddyssey_mcp.stack import (
    CONTAINER_NAME,
    IMAGE,
    _otlp_ingest_ready,
    run_args,
    stack_status,
    stored_services,
)


def test_run_args_build_the_pinned_container():
    args = run_args()

    assert args[:2] == ["docker", "run"]
    assert args[-1] == IMAGE
    assert IMAGE == "grafana/otel-lgtm:0.31.0"
    assert CONTAINER_NAME in args
    for mapping in ("3000:3000", "4317:4317", "4318:4318"):
        assert mapping in args


def test_urls_derive_from_the_configured_ports(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        '{"local": {"grafana_port": 3300, "otlp_grpc_port": 4417, "otlp_http_port": 4418}}'
    )
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    assert stack.grafana_base() == "http://localhost:3300"
    assert stack.otlp_endpoint() == "http://localhost:4417"
    assert stack.otlp_http_ingest() == "http://localhost:4418/v1/traces"


def test_run_args_enable_delta_to_cumulative_by_default():
    # Issue #34: CLI coding agents export claude_code.* metrics with delta
    # temporality, which Prometheus's OTLP receiver silently rejects unless
    # started with this feature flag. The stack targets those agents, so
    # storing their telemetry is part of the embedded definition.
    args = run_args()

    flag_index = args.index("-e")
    assert (
        args[flag_index + 1]
        == "PROMETHEUS_EXTRA_ARGS=--enable-feature=otlp-deltatocumulative"
    )


def _env_entries(args: list[str]) -> list[str]:
    return [args[i + 1] for i, flag in enumerate(args) if flag == "-e"]


def test_run_args_adds_user_env_after_the_defaults():
    entries = _env_entries(run_args({"GF_LOG_LEVEL": "debug"}))

    assert "PROMETHEUS_EXTRA_ARGS=--enable-feature=otlp-deltatocumulative" in entries
    assert "GF_LOG_LEVEL=debug" in entries


def test_run_args_lets_user_env_override_the_defaults():
    entries = _env_entries(run_args({"PROMETHEUS_EXTRA_ARGS": "--custom"}))

    assert entries.count("PROMETHEUS_EXTRA_ARGS=--custom") == 1
    assert not any(e.startswith("PROMETHEUS_EXTRA_ARGS=--enable") for e in entries)


def test_run_args_rejects_malformed_env_keys():
    with pytest.raises(ValueError, match="environment variable name"):
        run_args({"BAD=KEY": "x"})
    with pytest.raises(ValueError, match="environment variable name"):
        run_args({"": "x"})


def _no_container(monkeypatch) -> None:
    """Stub the identity reads away: readiness assertions must not need docker."""
    monkeypatch.setattr(stack, "_container_identity", lambda: None)
    monkeypatch.setattr(stack, "container_user_env", lambda: None)


def test_stack_status_all_ready(monkeypatch):
    _no_container(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status == {
        "running": True,
        "prometheus": True,
        "tempo": True,
        "loki": True,
        "pyroscope": True,
        "image": None,
        "created": None,
        "started": None,
        "env": None,
    }


def test_stack_status_down_is_not_an_error(monkeypatch):
    _no_container(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status == {
        "running": False,
        "prometheus": False,
        "tempo": False,
        "loki": False,
        "pyroscope": False,
        "image": None,
        "created": None,
        "started": None,
        "env": None,
    }


def test_stack_status_is_not_running_until_every_signal_is_ready(monkeypatch):
    # Issue #36: readiness must cover all four signals the tool claims to
    # make ready - a stack whose logs backend is still booting is not up.
    # A booting backend behind the Grafana proxy answers 503 (the proxy
    # relays it), not a transport error - the down-stack test covers that.
    _no_container(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if "uid/loki" in str(request.url):
            return httpx.Response(503)
        return httpx.Response(200)

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status["running"] is False
    assert status["loki"] is False
    assert status["prometheus"] is True
    assert status["tempo"] is True
    assert status["pyroscope"] is True


def _identity_docker(monkeypatch, *, inspect_json=None, returncode=0):
    """Route stack._docker: identity inspect answers inspect_json."""

    def fake_docker(*args):
        return subprocess.CompletedProcess(
            args, returncode, stdout=inspect_json or "", stderr=""
        )

    monkeypatch.setattr(stack, "_docker", fake_docker)


def test_stack_status_carries_container_identity(monkeypatch):
    # Issue #118: a report's instance identity (image tag, lifecycle
    # timestamps, effective env) must be fillable from the tool alone -
    # no docker inspect on the caller's side.
    _identity_docker(
        monkeypatch,
        inspect_json='{"image": "grafana/otel-lgtm:0.31.0",'
        ' "created": "2026-08-29T08:12:03.1Z",'
        ' "started": "2026-08-29T08:12:04.5Z"}',
    )
    monkeypatch.setattr(stack, "container_user_env", lambda: {"GF_LOG_LEVEL": "debug"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status["running"] is True
    assert status["image"] == "grafana/otel-lgtm:0.31.0"
    assert status["created"] == "2026-08-29T08:12:03.1Z"
    assert status["started"] == "2026-08-29T08:12:04.5Z"
    assert status["env"] == {"GF_LOG_LEVEL": "debug"}


def test_stack_status_absent_container_yields_null_identity(monkeypatch):
    # No container: every identity field is null - env included, because
    # "no container" and "container with no user env" are different facts.
    _identity_docker(monkeypatch, returncode=1)
    monkeypatch.setattr(stack, "container_user_env", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status["running"] is False
    assert status["image"] is None
    assert status["created"] is None
    assert status["started"] is None
    assert status["env"] is None


def test_stack_status_redacts_credential_named_env_values(monkeypatch):
    # The NAME closes the visibility gap (observation finding N3: an
    # applied-but-not-persisted variable is invisible without docker
    # access); the VALUE never leaves the server.
    _identity_docker(
        monkeypatch,
        inspect_json='{"image": "i", "created": "c", "started": "s"}',
    )
    monkeypatch.setattr(
        stack,
        "container_user_env",
        lambda: {"GF_LOG_LEVEL": "debug", "X_DEMO_TOKEN": "fake"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status["env"] == {"GF_LOG_LEVEL": "debug", "X_DEMO_TOKEN": None}


def test_stack_status_survives_malformed_inspect_output(monkeypatch):
    # Best-effort by contract: a status call must never fail because
    # docker hiccupped - unreadable identity degrades to nulls.
    _identity_docker(monkeypatch, inspect_json="not json")
    monkeypatch.setattr(stack, "container_user_env", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status["running"] is True
    assert status["image"] is None and status["env"] is None


def test_stack_status_survives_non_object_inspect_output(monkeypatch):
    # Valid JSON that is not an object still has to degrade to nulls: the
    # identity read is best-effort, so "never an exception" covers every
    # shape docker could hand back, not just unparseable bytes.
    _identity_docker(monkeypatch, inspect_json="null")
    monkeypatch.setattr(stack, "container_user_env", lambda: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status["running"] is True
    assert status["image"] is None and status["env"] is None


def test_readiness_never_touches_docker(monkeypatch):
    """Probe-only: the boot loop polls it every 2 s, so it must not inspect.

    Half of the boot-loop contract - that _readiness is cheap. The other
    half, that stack_up actually consumes it, is pinned by
    test_stack_up_polls_readiness_not_the_enriched_status.
    """
    calls = []
    monkeypatch.setattr(
        stack,
        "_docker",
        lambda *a: (
            calls.append(a) or subprocess.CompletedProcess(a, 1, stdout="", stderr="")
        ),
    )

    # _readiness must not touch docker at all:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    ready = stack._readiness(transport=httpx.MockTransport(handler))
    assert ready == {
        "running": True,
        "prometheus": True,
        "tempo": True,
        "loki": True,
        "pyroscope": True,
    }
    assert calls == []


def test_otlp_ingest_ready_true_on_any_http_response():
    # Any HTTP response (even 4xx) proves the OTLP listener accepts
    # connections; only transport errors mean not-ready.
    transport = httpx.MockTransport(lambda request: httpx.Response(415))
    with httpx.Client(transport=transport) as client:
        assert _otlp_ingest_ready(client) is True


def test_otlp_ingest_ready_false_on_transport_error():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    transport = httpx.MockTransport(refuse)
    with httpx.Client(transport=transport) as client:
        assert _otlp_ingest_ready(client) is False


def test_stored_services_unions_tempo_prometheus_and_loki():
    # A service may have emitted only one signal, so all three queryable
    # backends contribute. Prometheus OTLP ingestion maps service.name onto
    # the job label, prefixed by service.namespace/ when one is set - the
    # prefix must be stripped so backends report the same service.name values.
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "uid/tempo" in url:
            return httpx.Response(200, json={"tagValues": ["checkout", "oddyssey-mcp"]})
        if "uid/loki" in url:
            return httpx.Response(
                200, json={"status": "success", "data": ["logs-only"]}
            )
        return httpx.Response(
            200, json={"status": "success", "data": ["shop/checkout", "billing"]}
        )

    services = stored_services(transport=httpx.MockTransport(handler))
    assert services == ["billing", "checkout", "logs-only", "oddyssey-mcp"]


def test_stored_services_queries_tempo_and_loki_with_their_widest_time_range():
    # Without explicit start/end, Tempo's tag-values endpoint only reads the
    # live store (flushed blocks are invisible) and Loki defaults to a 6-hour
    # lookback - a day-old project would be wiped without ever being listed.
    # Both cap the queryable range (Tempo max_duration 168h, Loki
    # max_query_length 30d1h) and reject wider requests outright, so the
    # window must sit just under each cap, not at epoch 0.
    seen: dict[str, httpx.URL] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "uid/tempo" in url:
            seen["tempo"] = request.url
            return httpx.Response(200, json={"tagValues": []})
        if "uid/loki" in url:
            seen["loki"] = request.url
            return httpx.Response(200, json={"status": "success", "data": []})
        return httpx.Response(200, json={"status": "success", "data": []})

    stored_services(transport=httpx.MockTransport(handler))

    tempo_start = int(seen["tempo"].params["start"])
    tempo_end = int(seen["tempo"].params["end"])
    assert tempo_start > 0
    assert tempo_end - tempo_start == stack.TEMPO_SEARCH_WINDOW_S

    loki_start = int(seen["loki"].params["start"])
    loki_end = int(seen["loki"].params["end"])
    assert loki_start > 0
    assert loki_end - loki_start == stack.LOKI_SEARCH_WINDOW_S * 1_000_000_000


def test_stored_services_strips_only_the_namespace_prefix():
    # job is "<service.namespace>/<service.name>" with a single namespace
    # segment; a service.name containing "/" must survive intact.
    def handler(request: httpx.Request) -> httpx.Response:
        if "uid/prometheus" in str(request.url):
            return httpx.Response(
                200, json={"status": "success", "data": ["eu/shop/checkout"]}
            )
        return httpx.Response(200, json={"tagValues": []})

    assert stored_services(transport=httpx.MockTransport(handler)) == ["shop/checkout"]


def test_stored_services_ignores_wrong_typed_json_fields():
    # A string-typed field must not be iterated char-by-char, and a null
    # field must not raise: both degrade to fewer names per the contract.
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "uid/tempo" in url:
            return httpx.Response(200, json={"tagValues": "checkout"})
        if "uid/loki" in url:
            return httpx.Response(200, json={"status": "success", "data": None})
        return httpx.Response(200, json={"status": "success", "data": ["billing"]})

    assert stored_services(transport=httpx.MockTransport(handler)) == ["billing"]


def test_stored_services_is_empty_when_stack_is_down():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    assert stored_services(transport=httpx.MockTransport(handler)) == []


def test_stored_services_survives_a_malformed_backend_payload():
    # The list warns before a wipe; a broken backend answer must degrade
    # to fewer names, never to an exception that blocks the reset.
    def handler(request: httpx.Request) -> httpx.Response:
        if "uid/tempo" in str(request.url):
            return httpx.Response(200, content=b"not json")
        return httpx.Response(200, json={"status": "success", "data": ["billing"]})

    assert stored_services(transport=httpx.MockTransport(handler)) == ["billing"]


def _recording_transport(seen: list[int | None]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.port)
        if "uid/tempo" in str(request.url):
            return httpx.Response(200, json={"tagValues": []})
        return httpx.Response(200, json={"status": "success", "data": []})

    return httpx.MockTransport(handler)


def _config_with_grafana_port_3300(tmp_path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        '{"local": {"grafana_port": 3300, "otlp_grpc_port": 4417, "otlp_http_port": 4418}}'
    )
    monkeypatch.setattr(config, "CONFIG_PATH", path)


def test_stored_services_targets_the_actual_container_ports(tmp_path, monkeypatch):
    # odd_config_set writes the new ports and then resets: the container
    # about to be wiped still publishes the OLD ones. Enumerating against
    # the new configuration would hit dead URLs and report services_wiped
    # [] while destroying real data (issue #35's visibility contract).
    _config_with_grafana_port_3300(tmp_path, monkeypatch)
    monkeypatch.setattr(
        stack,
        "_container_host_ports",
        lambda: {"grafana_port": 3000, "otlp_grpc_port": 4317, "otlp_http_port": 4318},
    )
    seen: list[int | None] = []

    stored_services(transport=_recording_transport(seen))

    assert seen
    assert all(port == 3000 for port in seen)


def test_stored_services_falls_back_to_configured_ports_without_a_container(
    tmp_path, monkeypatch
):
    # No container to inspect (or an unreadable one): the configuration is
    # the only truth left, and the enumeration must still be attempted.
    _config_with_grafana_port_3300(tmp_path, monkeypatch)
    seen: list[int | None] = []

    stored_services(transport=_recording_transport(seen))

    assert seen
    assert all(port == 3300 for port in seen)


UP_RESULT = {
    "running": True,
    "grafana_url": "http://localhost:3000",
    "otlp_endpoint": "http://localhost:4317",
}


def _trace_reset(monkeypatch, state: str, up=None) -> tuple[list[str], dict]:
    """Run stack_reset with docker/backends stubbed; return (call order, result)."""
    calls: list[str] = []
    monkeypatch.setattr(stack, "_container_state", lambda: state)
    monkeypatch.setattr(
        stack,
        "stored_services",
        lambda: calls.append("stored_services") or ["billing", "checkout"],
    )
    monkeypatch.setattr(
        stack,
        "stack_down",
        lambda flush=True: calls.append("stack_down") or {"running": False},
    )
    monkeypatch.setattr(
        stack,
        "stack_up",
        up or (lambda env=None, **kwargs: calls.append("stack_up") or UP_RESULT),
    )
    return calls, stack.stack_reset()


def test_stack_up_polls_readiness_not_the_enriched_status(monkeypatch):
    # The wiring half of the boot-loop contract (issue #118): the wait loop
    # must consume the probe-only _readiness. Reading the enriched status
    # instead would add three docker inspects to every 2 s poll, taxing
    # every boot trace for identity data the loop never looks at.
    calls: list[str] = []
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "_container_host_ports", lambda: None)
    monkeypatch.setattr(
        stack,
        "_readiness",
        lambda: calls.append("_readiness") or {"running": True},
    )
    monkeypatch.setattr(
        stack,
        "stack_status",
        lambda *args, **kwargs: pytest.fail("stack_up read the enriched status"),
    )
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    assert stack.stack_up()["running"] is True
    assert calls == ["_readiness"]


def test_stack_up_reports_env_not_applied_on_an_existing_container(monkeypatch):
    # Docker env only applies at container creation: an up on an existing
    # container must say so instead of letting the caller believe the
    # configuration landed (issue #34 / #43 family).
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "_container_host_ports", lambda: None)
    monkeypatch.setattr(stack, "_readiness", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    result = stack.stack_up(env={"GF_LOG_LEVEL": "debug"})

    assert result["env_applied"] is False
    assert result["running"] is True


def test_stack_up_applies_env_when_it_creates_the_container(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr(stack, "_container_state", lambda: "absent")
    monkeypatch.setattr(stack, "_container_host_ports", lambda: None)
    monkeypatch.setattr(stack.subprocess, "run", fake_run)
    monkeypatch.setattr(stack, "_readiness", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    result = stack.stack_up(env={"GF_LOG_LEVEL": "debug"})

    assert "GF_LOG_LEVEL=debug" in _env_entries(captured["args"])
    assert result["env_applied"] is True


def _create_container(monkeypatch) -> dict:
    """Stub docker so stack_up hits its creation branch; capture run args."""
    captured: dict[str, list[str]] = {}

    def fake_run(args, **kwargs):
        captured["args"] = args

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr(stack, "_container_state", lambda: "absent")
    monkeypatch.setattr(stack, "_container_host_ports", lambda: None)
    monkeypatch.setattr(stack.subprocess, "run", fake_run)
    monkeypatch.setattr(stack, "_readiness", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)
    return captured


def test_stack_up_persists_the_env_it_applies(monkeypatch):
    # Issue #117: a creation-time env choice must survive later
    # recreations - the applied env is written to stack_config.local.
    _create_container(monkeypatch)

    result = stack.stack_up(env={"GF_LOG_LEVEL": "debug"})

    assert config.load()["stack_config"]["local"] == {"GF_LOG_LEVEL": "debug"}
    assert result["env_persisted"] == ["GF_LOG_LEVEL"]


def test_stack_up_reapplies_the_persisted_env_when_called_without_env(monkeypatch):
    config.save({"stack_config": {"local": {"GF_LOG_LEVEL": "debug"}}})
    captured = _create_container(monkeypatch)

    result = stack.stack_up()

    assert "GF_LOG_LEVEL=debug" in _env_entries(captured["args"])
    assert result["env_reapplied"] == ["GF_LOG_LEVEL"]
    assert "env_applied" not in result


def test_stack_up_explicit_env_wins_over_the_persisted_one(monkeypatch):
    config.save({"stack_config": {"local": {"GF_LOG_LEVEL": "info", "OBI": "on"}}})
    captured = _create_container(monkeypatch)

    result = stack.stack_up(env={"GF_LOG_LEVEL": "debug"})

    entries = _env_entries(captured["args"])
    assert entries.count("GF_LOG_LEVEL=debug") == 1
    assert "GF_LOG_LEVEL=info" not in entries
    # Non-colliding persisted entries still apply alongside.
    assert "OBI=on" in entries
    # The explicit value is what stack_config.local now holds.
    assert config.load()["stack_config"]["local"]["GF_LOG_LEVEL"] == "debug"
    assert result["env_persisted"] == ["GF_LOG_LEVEL"]
    # The overridden name came from env, not from the configuration:
    # only the untouched persisted entry is reported as reapplied.
    assert result["env_reapplied"] == ["OBI"]


def test_stack_up_never_persists_credential_named_env(monkeypatch):
    # Applied to the container, excluded from the configuration: the
    # stored contract holds no secret, and the caller is told what to
    # repeat on the next recreation.
    captured = _create_container(monkeypatch)

    result = stack.stack_up(
        env={"OTEL_EXPORTER_OTLP_HEADERS": "authorization=Bearer x", "OBI": "on"}
    )

    assert "OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer x" in _env_entries(
        captured["args"]
    )
    assert config.load()["stack_config"]["local"] == {"OBI": "on"}
    assert result["env_not_persisted"] == ["OTEL_EXPORTER_OTLP_HEADERS"]
    assert result["env_persisted"] == ["OBI"]


def test_stack_up_never_persists_an_api_key_named_env(monkeypatch):
    # The credential heuristic covers API keys too: applied to the
    # container, kept out of the configuration.
    captured = _create_container(monkeypatch)

    result = stack.stack_up(env={"MY_BACKEND_API_KEY": "s3cr3t", "OBI": "on"})

    assert "MY_BACKEND_API_KEY=s3cr3t" in _env_entries(captured["args"])
    assert config.load()["stack_config"]["local"] == {"OBI": "on"}
    assert result["env_not_persisted"] == ["MY_BACKEND_API_KEY"]


def test_stack_up_reports_env_it_could_not_persist(monkeypatch):
    # The container already took the env when the write fails: the
    # result must not claim a persistence that never happened, or the
    # caller drops the variable from the next recreation.
    _create_container(monkeypatch)

    def failing_save(partial):
        raise OSError("read-only configuration")

    monkeypatch.setattr(stack.config, "save", failing_save)

    result = stack.stack_up(env={"GF_LOG_LEVEL": "debug", "OBI": "on"})

    assert result["env_not_persisted"] == ["GF_LOG_LEVEL", "OBI"]
    assert "env_persisted" not in result


def test_stack_up_without_persist_applies_env_but_stores_nothing(monkeypatch):
    # The odd_config_set auto-reset path: the live env is carried onto
    # the new container without being written back to the configuration,
    # so a just-deleted variable is not resurrected.
    captured = _create_container(monkeypatch)

    result = stack.stack_up(env={"GF_LOG_LEVEL": "debug"}, persist=False)

    assert "GF_LOG_LEVEL=debug" in _env_entries(captured["args"])
    assert result["env_applied"] is True
    assert config.load()["stack_config"] == {}
    assert "env_persisted" not in result
    assert "env_not_persisted" not in result


def test_stack_reset_passes_persist_through_to_the_creation(monkeypatch):
    captured: dict = {}

    def fake_up(env=None, *, persist=True):
        captured["persist"] = persist
        return {"running": True}

    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "stored_services", list)
    monkeypatch.setattr(stack, "stack_down", lambda flush=True: {"running": False})
    monkeypatch.setattr(stack, "stack_up", fake_up)

    stack.stack_reset({"GF_LOG_LEVEL": "debug"}, persist=False)

    assert captured["persist"] is False


def test_stack_up_does_not_persist_env_it_did_not_apply(monkeypatch):
    # An existing container means env_applied: false - persisting it
    # would make the configuration diverge from the live container.
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "_container_host_ports", lambda: None)
    monkeypatch.setattr(stack, "_readiness", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    result = stack.stack_up(env={"GF_LOG_LEVEL": "debug"})

    assert result["env_applied"] is False
    assert config.load()["stack_config"] == {}
    assert "env_persisted" not in result


def test_persisted_env_coerces_scalars_to_docker_strings():
    # The stored contract holds flat scalars; docker takes strings.
    config.save(
        {"stack_config": {"local": {"OBI": True, "GF_PORT_QUOTA": 3, "OFF": False}}}
    )

    assert stack.persisted_env() == {
        "OBI": "true",
        "GF_PORT_QUOTA": "3",
        "OFF": "false",
    }


def test_stack_up_reports_env_not_applied_on_a_stopped_container(monkeypatch):
    # docker start brings a stopped container up without applying env -
    # created must stay False on that path (e.g. after a host reboot).
    class StartOk:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(stack, "_container_state", lambda: "stopped")
    monkeypatch.setattr(stack, "_container_host_ports", lambda: None)
    monkeypatch.setattr(stack, "_docker", lambda *args: StartOk())
    monkeypatch.setattr(stack, "_readiness", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    result = stack.stack_up(env={"GF_LOG_LEVEL": "debug"})

    assert result["env_applied"] is False


def test_stack_up_rejects_malformed_env_before_doing_anything(monkeypatch):
    # A malformed env must fail up front, not silently report
    # env_applied: false and steer the caller toward a doomed reset.
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "_readiness", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    with pytest.raises(ValueError, match="environment variable name"):
        stack.stack_up(env={"BAD=KEY": "x"})


def test_stack_reset_rejects_malformed_env_before_wiping(monkeypatch):
    # The validation is pure and free: it must run before the machine-wide
    # wipe, never after it (a rejected request must destroy nothing).
    calls: list[str] = []
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(
        stack, "stored_services", lambda: calls.append("stored_services") or []
    )
    monkeypatch.setattr(
        stack,
        "stack_down",
        lambda flush=True: calls.append("stack_down") or {"running": False},
    )
    monkeypatch.setattr(stack, "_readiness", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    with pytest.raises(ValueError, match="environment variable name"):
        stack.stack_reset(env={"BAD=KEY": "x"})

    assert calls == []


def test_stack_up_result_shape_is_unchanged_without_env(monkeypatch):
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "_container_host_ports", lambda: None)
    monkeypatch.setattr(stack, "_readiness", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    assert "env_applied" not in stack.stack_up()


def test_stack_reset_passes_env_to_the_new_container(monkeypatch):
    seen: dict[str, object] = {}
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "stored_services", list)
    monkeypatch.setattr(stack, "stack_down", lambda flush=True: {"running": False})

    def fake_up(env=None, **kwargs):
        seen["env"] = env
        return {**UP_RESULT, "env_applied": env is not None}

    monkeypatch.setattr(stack, "stack_up", fake_up)

    result = stack.stack_reset(env={"GF_LOG_LEVEL": "debug"})

    assert seen["env"] == {"GF_LOG_LEVEL": "debug"}
    assert result["env_applied"] is True


def test_stack_reset_reports_the_services_it_wiped(monkeypatch):
    calls, result = _trace_reset(monkeypatch, "running")

    assert result["services_wiped"] == ["billing", "checkout"]
    assert result["running"] is True
    assert result["grafana_url"] == "http://localhost:3000"
    # The query must happen before the wipe, or the list is always empty.
    assert calls == ["stored_services", "stack_down", "stack_up"]


def test_stack_reset_boots_a_stopped_container_before_querying(monkeypatch):
    # A stopped container (normal after a host reboot) still holds telemetry
    # but answers nothing on :3000 - querying it directly would report
    # services_wiped: [] while destroying real data.
    calls, result = _trace_reset(monkeypatch, "stopped")

    assert calls == ["stack_up", "stored_services", "stack_down", "stack_up"]
    assert result["services_wiped"] == ["billing", "checkout"]


def test_stack_reset_still_wipes_a_stopped_container_that_cannot_boot(monkeypatch):
    # Recovering a broken stack is part of reset's job: if the pre-query
    # boot fails, the wipe must proceed rather than error out.
    boots: list[int] = []

    def up(env=None, **kwargs):
        boots.append(1)
        if len(boots) == 1:
            raise RuntimeError("container will not start")
        return UP_RESULT

    _, result = _trace_reset(monkeypatch, "stopped", up=up)

    assert result["running"] is True
    assert result["services_wiped"] == ["billing", "checkout"]


def test_run_args_map_the_configured_host_ports(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        '{"local": {"grafana_port": 3300, "otlp_grpc_port": 4417, "otlp_http_port": 4418}}'
    )
    monkeypatch.setattr(config, "CONFIG_PATH", path)

    args = run_args()

    for mapping in ("3300:3000", "4417:4317", "4418:4318"):
        assert mapping in args


def test_stack_up_fails_fast_on_port_mismatch(tmp_path, monkeypatch):
    # A hand-edited config while a container runs is the one path the
    # auto-reset of odd_config_set cannot close: fail immediately with
    # the remedy, not after a 120 s poll of dead URLs.
    path = tmp_path / "config.json"
    path.write_text('{"local": {"grafana_port": 3300}}')
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(
        stack,
        "_container_host_ports",
        lambda: {"grafana_port": 3000, "otlp_grpc_port": 4317, "otlp_http_port": 4318},
    )

    with pytest.raises(RuntimeError, match="odd_stack_reset"):
        stack.stack_up()


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_env_inspects(
    monkeypatch, container, image, container_image="sha256:cafe", seen=None
):
    """Stub _docker for the env inspects; None = failing call.

    container/image are .Config.Env lists; container_image is the .Image
    ID the container inspect reports; seen records the ref the image
    inspect was actually queried with.
    """

    def fake_docker(*args):
        if args[0] == "image":
            if seen is not None:
                seen["ref"] = args[-1]
            if image is None:
                return _Proc(returncode=1, stderr="no such object")
            return _Proc(stdout=json.dumps(image))
        if container is None:
            return _Proc(returncode=1, stderr="no such object")
        return _Proc(stdout=json.dumps({"env": container, "image": container_image}))

    monkeypatch.setattr(stack, "_docker", fake_docker)


def test_container_user_env_keeps_only_user_set_entries(monkeypatch):
    # Issue #62: the auto-reset must carry forward what the USER set - the
    # image's own env and the embedded defaults are recreated anyway.
    _fake_env_inspects(
        monkeypatch,
        container=[
            "PATH=/usr/bin",
            *stack.DEFAULT_ENV,
            "GF_LOG_LEVEL=debug",
            "LOKI_EXTRA_ARGS=-a=b",
        ],
        image=["PATH=/usr/bin"],
    )
    assert stack.container_user_env() == {
        "GF_LOG_LEVEL": "debug",
        # a value containing '=' splits on the first one only
        "LOKI_EXTRA_ARGS": "-a=b",
    }


def test_container_user_env_keeps_an_overridden_default(monkeypatch):
    # PROMETHEUS_EXTRA_ARGS set to a NON-default value is a user choice:
    # only the exact embedded default entry is dropped.
    _fake_env_inspects(
        monkeypatch,
        container=["PATH=/usr/bin", "PROMETHEUS_EXTRA_ARGS=--custom"],
        image=["PATH=/usr/bin"],
    )
    assert stack.container_user_env() == {"PROMETHEUS_EXTRA_ARGS": "--custom"}


def test_container_user_env_is_none_when_an_inspect_fails(monkeypatch):
    # Best-effort by contract: unreadable preserves nothing, never raises.
    _fake_env_inspects(monkeypatch, container=None, image=["PATH=/usr/bin"])
    assert stack.container_user_env() is None
    _fake_env_inspects(monkeypatch, container=["PATH=/usr/bin"], image=None)
    assert stack.container_user_env() is None


def test_container_user_env_is_none_on_malformed_inspect_output(monkeypatch):
    monkeypatch.setattr(stack, "_docker", lambda *args: _Proc(stdout="not json"))
    assert stack.container_user_env() is None


def test_container_user_env_inspects_the_container_own_image(monkeypatch):
    # Issue #83 (review of #62): diffing against the currently pinned
    # IMAGE misclassifies image-baked env when the pin was bumped while
    # the old container survived - old-image entries whose value changed
    # would be carried as "user env" into the new container. The diff
    # must target the image the container was created from (.Image ID).
    seen: dict = {}
    _fake_env_inspects(
        monkeypatch,
        container=["PATH=/from-old-image", "GF_LOG_LEVEL=debug"],
        image=["PATH=/from-old-image"],
        container_image="sha256:0ld",
        seen=seen,
    )
    assert stack.container_user_env() == {"GF_LOG_LEVEL": "debug"}
    assert seen["ref"] == "sha256:0ld"


def test_container_user_env_drops_a_superseded_default(monkeypatch):
    # When a DEFAULT_ENV entry changes across server versions, the old
    # container still carries the OLD default - it must not be carried
    # forward as a user choice (it would suppress the new default), while
    # a genuinely custom value for the same key stays a user choice.
    monkeypatch.setattr(
        stack,
        "SUPERSEDED_DEFAULT_ENV",
        ("PROMETHEUS_EXTRA_ARGS=--old-default",),
        raising=False,
    )
    _fake_env_inspects(
        monkeypatch,
        container=["PATH=/usr/bin", "PROMETHEUS_EXTRA_ARGS=--old-default"],
        image=["PATH=/usr/bin"],
    )
    assert stack.container_user_env() == {}
    _fake_env_inspects(
        monkeypatch,
        container=["PATH=/usr/bin", "PROMETHEUS_EXTRA_ARGS=--custom"],
        image=["PATH=/usr/bin"],
    )
    assert stack.container_user_env() == {"PROMETHEUS_EXTRA_ARGS": "--custom"}


def test_stack_down_flushes_queued_telemetry_before_the_rm(monkeypatch):
    # Standalone down keeps its flush, and BEFORE the destruction: the
    # export target may be a remote store that survives the local
    # container - a shared order sink pins the sequence, not just the call.
    order: list[str] = []
    monkeypatch.setattr(stack.telemetry, "force_flush", lambda: order.append("flush"))
    monkeypatch.setattr(stack, "_docker", lambda *args: order.append("rm") or _Proc())

    stack.stack_down()

    assert order == ["flush", "rm"]


def test_stack_up_flushes_after_readiness(monkeypatch):
    # stack_reset(flush=False) relies on THIS flush as the delivery
    # backstop for the deferred pre-rm spans (F3 review, finding F-1):
    # pin it so a stack_up simplification cannot silently remove the
    # reset path's delivery point.
    order: list[str] = []
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "_container_host_ports", lambda: None)
    monkeypatch.setattr(stack, "_readiness", lambda: {"running": True})
    monkeypatch.setattr(
        stack, "_otlp_ingest_ready", lambda client: order.append("ready") or True
    )
    monkeypatch.setattr(stack.telemetry, "force_flush", lambda: order.append("flush"))

    stack.stack_up()

    assert order == ["ready", "flush"]


def test_stack_reset_defers_the_flush_to_the_recreated_store(monkeypatch):
    # F3 (observation report 2026-08-26): stack_down's flush delivered the
    # pre-rm spans (the #62 env reads, the pre-wipe enumeration) into the
    # very store the next line destroys - deterministic loss. From reset,
    # spans must stay queued so stack_up's post-readiness flush lands them
    # in the recreated store.
    flushes: list[int] = []
    monkeypatch.setattr(stack.telemetry, "force_flush", lambda: flushes.append(1))
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "stored_services", list)
    monkeypatch.setattr(stack, "_docker", lambda *args: _Proc())
    monkeypatch.setattr(stack, "stack_up", lambda env=None, **kwargs: {"running": True})

    stack.stack_reset()

    assert flushes == []
