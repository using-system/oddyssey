import httpx
import pytest
from oddyssey_mcp import stack
from oddyssey_mcp.stack import (
    CONTAINER_NAME,
    IMAGE,
    PORTS,
    _otlp_ingest_ready,
    run_args,
    stack_status,
    stored_services,
)


def test_run_args_build_the_pinned_container():
    args = run_args()

    assert args[:2] == ["docker", "run"]
    assert args[-1] == IMAGE
    assert IMAGE == "grafana/otel-lgtm:0.30.2"
    assert CONTAINER_NAME in args
    for mapping in PORTS:
        assert mapping in args
    assert {"3000:3000", "4317:4317", "4318:4318"} == set(PORTS)


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


def test_stack_status_all_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status == {
        "running": True,
        "prometheus": True,
        "tempo": True,
        "loki": True,
        "pyroscope": True,
    }


def test_stack_status_down_is_not_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status == {
        "running": False,
        "prometheus": False,
        "tempo": False,
        "loki": False,
        "pyroscope": False,
    }


def test_stack_status_is_not_running_until_every_signal_is_ready():
    # Issue #36: readiness must cover all four signals the tool claims to
    # make ready - a stack whose logs backend is still booting is not up.
    # A booting backend behind the Grafana proxy answers 503 (the proxy
    # relays it), not a transport error - the down-stack test covers that.
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
        stack, "stack_down", lambda: calls.append("stack_down") or {"running": False}
    )
    monkeypatch.setattr(
        stack,
        "stack_up",
        up or (lambda env=None: calls.append("stack_up") or UP_RESULT),
    )
    return calls, stack.stack_reset()


def test_stack_up_reports_env_not_applied_on_an_existing_container(monkeypatch):
    # Docker env only applies at container creation: an up on an existing
    # container must say so instead of letting the caller believe the
    # configuration landed (issue #34 / #43 family).
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "stack_status", lambda: {"running": True})
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
    monkeypatch.setattr(stack.subprocess, "run", fake_run)
    monkeypatch.setattr(stack, "stack_status", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    result = stack.stack_up(env={"GF_LOG_LEVEL": "debug"})

    assert "GF_LOG_LEVEL=debug" in _env_entries(captured["args"])
    assert result["env_applied"] is True


def test_stack_up_reports_env_not_applied_on_a_stopped_container(monkeypatch):
    # docker start brings a stopped container up without applying env -
    # created must stay False on that path (e.g. after a host reboot).
    class StartOk:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(stack, "_container_state", lambda: "stopped")
    monkeypatch.setattr(stack, "_docker", lambda *args: StartOk())
    monkeypatch.setattr(stack, "stack_status", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    result = stack.stack_up(env={"GF_LOG_LEVEL": "debug"})

    assert result["env_applied"] is False


def test_stack_up_rejects_malformed_env_before_doing_anything(monkeypatch):
    # A malformed env must fail up front, not silently report
    # env_applied: false and steer the caller toward a doomed reset.
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "stack_status", lambda: {"running": True})
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
        stack, "stack_down", lambda: calls.append("stack_down") or {"running": False}
    )
    monkeypatch.setattr(stack, "stack_status", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    with pytest.raises(ValueError, match="environment variable name"):
        stack.stack_reset(env={"BAD=KEY": "x"})

    assert calls == []


def test_stack_up_result_shape_is_unchanged_without_env(monkeypatch):
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "stack_status", lambda: {"running": True})
    monkeypatch.setattr(stack, "_otlp_ingest_ready", lambda client: True)

    assert "env_applied" not in stack.stack_up()


def test_stack_reset_passes_env_to_the_new_container(monkeypatch):
    seen: dict[str, object] = {}
    monkeypatch.setattr(stack, "_container_state", lambda: "running")
    monkeypatch.setattr(stack, "stored_services", list)
    monkeypatch.setattr(stack, "stack_down", lambda: {"running": False})

    def fake_up(env=None):
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

    def up(env=None):
        boots.append(1)
        if len(boots) == 1:
            raise RuntimeError("container will not start")
        return UP_RESULT

    _, result = _trace_reset(monkeypatch, "stopped", up=up)

    assert result["running"] is True
    assert result["services_wiped"] == ["billing", "checkout"]
