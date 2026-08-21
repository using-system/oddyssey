import httpx
import pytest

from oddyssey_summarize.errors import StackUnreachableError
from oddyssey_summarize.prometheus import PrometheusClient


def _success(result: list[dict]) -> dict:
    return {"status": "success", "data": {"resultType": "vector", "result": result}}


def test_query_returns_result_vector():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/query"
        assert request.url.params["query"] == "up"
        assert request.url.params["time"] == "123"
        return httpx.Response(200, json=_success([{"metric": {}, "value": [123, "1"]}]))

    client = PrometheusClient(transport=httpx.MockTransport(handler))
    assert client.query("up", time=123) == [{"metric": {}, "value": [123, "1"]}]


def test_failed_status_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "error": "bad query"})

    client = PrometheusClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="Prometheus query failed"):
        client.query("up", time=123)


def test_unreachable_raises_explicit_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = PrometheusClient(transport=httpx.MockTransport(handler))
    with pytest.raises(StackUnreachableError, match="Prometheus is unreachable"):
        client.query("up", time=123)
