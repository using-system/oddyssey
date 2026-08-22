import httpx
from oddyssey_mcp.stack import CONTAINER_NAME, IMAGE, PORTS, run_args, stack_status


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
