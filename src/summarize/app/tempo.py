"""Minimal Tempo HTTP API client (TraceQL search)."""

from __future__ import annotations

import httpx

from oddyssey.summarize.app.errors import StackUnreachableError

DEFAULT_BASE_URL = "http://localhost:3200"

_UNREACHABLE_HINT = (
    "Is the otel-lgtm stack running? "
    "Try: docker compose -f docker-compose/docker-compose.yml up -d"
)


class TempoClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def search(
        self,
        query: str,
        start: int,
        end: int,
        limit: int = 500,
        spans_per_spanset: int = 100,
    ) -> dict:
        """Run a TraceQL search; start/end are unix epoch seconds."""
        params = {
            "q": query,
            "start": start,
            "end": end,
            "limit": limit,
            "spss": spans_per_spanset,
        }
        try:
            response = self._client.get("/api/search", params=params)
            response.raise_for_status()
        except httpx.TransportError as exc:
            raise StackUnreachableError(
                f"Tempo is unreachable at {self._client.base_url}. {_UNREACHABLE_HINT}"
            ) from exc
        return response.json()
