import httpx
import pytest

from oddyssey.summarize.app.errors import StackUnreachableError
from oddyssey.summarize.app.tempo import TempoClient


def test_search_returns_parsed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/search"
        assert request.url.params["q"] == '{resource.service.name="demo"}'
        assert request.url.params["start"] == "100"
        assert request.url.params["end"] == "200"
        return httpx.Response(200, json={"traces": [], "metrics": {}})

    client = TempoClient(transport=httpx.MockTransport(handler))
    result = client.search('{resource.service.name="demo"}', start=100, end=200)
    assert result == {"traces": [], "metrics": {}}


def test_unreachable_raises_explicit_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = TempoClient(transport=httpx.MockTransport(handler))
    with pytest.raises(StackUnreachableError, match="Tempo is unreachable"):
        client.search("{}", start=0, end=1)
