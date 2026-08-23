import httpx
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


def test_stack_status_all_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status == {"running": True, "prometheus": True, "tempo": True}


def test_stack_status_down_is_not_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    status = stack_status(transport=httpx.MockTransport(handler))
    assert status == {"running": False, "prometheus": False, "tempo": False}


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


def test_stack_reset_reports_the_services_it_wiped(monkeypatch):
    monkeypatch.setattr(stack, "stored_services", lambda: ["billing", "checkout"])
    monkeypatch.setattr(stack, "stack_down", lambda: {"running": False})
    monkeypatch.setattr(
        stack,
        "stack_up",
        lambda: {
            "running": True,
            "grafana_url": "http://localhost:3000",
            "otlp_endpoint": "http://localhost:4317",
        },
    )

    result = stack.stack_reset()

    assert result["services_wiped"] == ["billing", "checkout"]
    assert result["running"] is True
    assert result["grafana_url"] == "http://localhost:3000"
