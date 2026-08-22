"""Minimal Prometheus HTTP API client (instant queries)."""

from __future__ import annotations

import httpx

from .errors import StackUnreachableError

# Queries go through the Grafana datasource proxy: only Grafana's port is
# exposed, and the same path works against any Grafana that has a
# "prometheus" datasource (the otel-lgtm image provisions that UID).
DEFAULT_BASE_URL = "http://localhost:3000/api/datasources/proxy/uid/prometheus"

_UNREACHABLE_HINT = (
    "Is the otel-lgtm stack running? "
    "Try: docker compose -f docker-compose/docker-compose.yml up -d"
)


class PrometheusClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def query(self, promql: str, time: int) -> list[dict]:
        """Run an instant query evaluated at `time` (unix epoch seconds).

        Returns the result vector (possibly empty).
        """
        try:
            response = self._client.get("/api/v1/query", params={"query": promql, "time": time})
            response.raise_for_status()
        except httpx.TransportError as exc:
            raise StackUnreachableError(
                f"Prometheus is unreachable at {self._client.base_url}. {_UNREACHABLE_HINT}"
            ) from exc
        payload = response.json()
        if payload.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed: {payload}")
        return payload["data"]["result"]
