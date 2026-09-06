"""llmbench-mcp - the MCP server of the llms-benchmark demo.

Streamable HTTP transport: the agent runs in another container and reaches
the tools over the network.
"""

from __future__ import annotations

import logging
import os
import re

from mcp.server import MCPServer
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

from . import catalog, telemetry

LOG = logging.getLogger("llmbench.mcp")

mcp = MCPServer("llmbench-catalog")

# How many hits of a search get their full record attached to the answer.
DETAIL_FANOUT = int(os.environ.get("SEARCH_DETAIL_FANOUT", "25"))

# Searches repeat a lot across a conversation, and the catalog only changes
# when an order is placed, so the enriched result of a query is worth keeping.
_SEARCH_CACHE: dict[str, list] = {}

_tool_calls = None


def _highlight(text: str, term: str) -> str:
    """Wrap the searched term in the product name, so the model sees the match."""
    return re.compile(re.escape(term), re.IGNORECASE).sub(
        lambda m: f"[{m.group(0)}]", text
    )


@mcp.tool()
def search_products(query: str = "", category: str = "") -> dict:
    """Search the catalog by name fragment and/or category.

    Returns every matching product, the first ones with their full record
    (price, stock, description) so the answer needs no follow-up call.
    """
    cache_key = f"{category}::{query}"
    if cache_key in _SEARCH_CACHE:
        LOG.info("search served from cache key=%s", cache_key)
        return {
            "query": query,
            "category": category,
            "results": _SEARCH_CACHE[cache_key],
        }

    listing = catalog.get(
        "/products",
        params={k: v for k, v in (("q", query), ("category", category)) if v},
    )
    hits = listing.get("products", [])

    results = []
    for index, hit in enumerate(hits):
        record = dict(hit)
        if index < DETAIL_FANOUT:
            detail = catalog.get(f"/products/{hit['sku']}")
            record.update(detail)
        if query:
            record["name"] = _highlight(record["name"], query)
        results.append(record)

    _SEARCH_CACHE[cache_key] = results
    LOG.info("search done query=%r category=%r hits=%s", query, category, len(results))
    if _tool_calls is not None:
        _tool_calls.add(1, {"mcp.tool.name": "search_products"})
    return {"query": query, "category": category, "results": results}


@mcp.tool()
def get_product(sku: str) -> dict:
    """Fetch one product by SKU."""
    if _tool_calls is not None:
        _tool_calls.add(1, {"mcp.tool.name": "get_product"})
    return catalog.get(f"/products/{sku}")


@mcp.tool()
def get_order(order_ref: str) -> dict:
    """Fetch an order by its reference."""
    if _tool_calls is not None:
        _tool_calls.add(1, {"mcp.tool.name": "get_order"})
    order = None
    try:
        order = catalog.get(f"/orders/{order_ref}")
    except Exception:  # noqa: BLE001, S110 - an unknown reference is not an error
        pass
    return {"order_ref": order_ref, "order": order}


@mcp.tool()
def place_order(sku: str, quantity: int = 1, customer: str = "anonymous") -> dict:
    """Place an order for a SKU."""
    if _tool_calls is not None:
        _tool_calls.add(1, {"mcp.tool.name": "place_order"})
    result = catalog.post(
        "/orders", {"sku": sku, "quantity": quantity, "customer": customer}
    )
    LOG.info("order placed sku=%s quantity=%s result=%s", sku, quantity, result)
    return result


def main() -> None:
    global _tool_calls
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    telemetry.setup_telemetry()
    LoggingInstrumentor().instrument(set_logging_format=False, log_code_attributes=True)
    HTTPXClientInstrumentor().instrument()
    _tool_calls = telemetry.meter().create_counter(
        "mcp.tool.calls",
        unit="{call}",
        description="MCP tool invocations served",
    )
    try:
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",  # a container port, published deliberately
            port=int(os.environ.get("PORT", "8081")),
        )
    finally:
        telemetry.shutdown_telemetry()


if __name__ == "__main__":
    main()
