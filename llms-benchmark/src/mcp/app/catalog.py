"""The HTTP client the MCP tools use to reach llmbench-api."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

LOG = logging.getLogger(__name__)

API_BASE_URL = os.environ.get("CATALOG_API_URL", "http://localhost:8000")
TIMEOUT_S = float(os.environ.get("CATALOG_API_TIMEOUT_S", "10"))
ATTEMPTS = int(os.environ.get("CATALOG_API_ATTEMPTS", "3"))


def get(path: str, params: dict | None = None) -> Any:
    """GET a catalog path, retrying a few times so a restarting API is survivable."""
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            # A per-call client keeps the tools stateless: nothing to open at
            # import time and nothing to close when a tool raises.
            with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT_S) as client:
                response = client.get(path, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as error:  # noqa: BLE001 - every failure is retried alike
            last_error = error
            LOG.warning(
                "catalog GET failed path=%s attempt=%s/%s error=%s",
                path,
                attempt,
                ATTEMPTS,
                error,
            )
    raise RuntimeError(
        f"catalog GET {path} failed after {ATTEMPTS} attempts: {last_error}"
    )


def post(path: str, payload: dict) -> Any:
    """POST to a catalog path, with the same retry policy as GET."""
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT_S) as client:
                response = client.post(path, json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as error:  # noqa: BLE001 - every failure is retried alike
            last_error = error
            LOG.warning(
                "catalog POST failed path=%s attempt=%s/%s error=%s",
                path,
                attempt,
                ATTEMPTS,
                error,
            )
    raise RuntimeError(
        f"catalog POST {path} failed after {ATTEMPTS} attempts: {last_error}"
    )
