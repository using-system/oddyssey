import httpx
from oddyssey_mcp.stack import (
    CONTAINER_NAME,
    IMAGE,
    PORTS,
    _otlp_ingest_ready,
    run_args,
    stack_status,
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
