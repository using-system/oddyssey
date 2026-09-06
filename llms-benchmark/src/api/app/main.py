"""llmbench-api - the catalog and orders API of the llms-benchmark demo."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from pydantic import BaseModel

from . import db, telemetry

LOG = logging.getLogger("llmbench.api")

app = FastAPI(title="llmbench-api", version="0.1.0")

_orders_counter = None


class OrderRequest(BaseModel):
    sku: str
    quantity: int = 1
    customer: str = "anonymous"


@app.on_event("startup")
def _startup() -> None:
    global _orders_counter
    db.init()
    _orders_counter = telemetry.meter().create_counter(
        "catalog.orders.created",
        unit="{order}",
        description="Orders accepted by the catalog API",
    )


@app.get("/health")
def health() -> dict:
    """Liveness for the container's healthcheck.

    Polled every few seconds by the orchestrator, so it is kept out of the
    traced surface: it would otherwise be the loudest endpoint of the
    service and drown the real traffic.
    """
    return {"status": "ok", "service": telemetry.SERVICE_NAME}


@app.get("/products")
def list_products(category: str | None = None, q: str | None = None) -> dict:
    """The catalog listing, filtered by category and/or a name fragment."""
    clauses, params = [], []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if q:
        clauses.append("name LIKE ?")
        params.append(f"%{q}%")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.query(
        f"SELECT sku, name, category, price_cents, stock FROM products{where}",
        tuple(params),
        op="list_products",
    )
    LOG.info("listed products category=%s q=%s matches=%s", category, q, len(rows))
    return {"count": len(rows), "products": [dict(row) for row in rows]}


@app.get("/products/{sku}")
def get_product(sku: str) -> dict:
    """One product by SKU - a primary-key read, the cheapest call of the API."""
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT sku, name, category, price_cents, stock, description"
            " FROM products WHERE sku = ?",
            (sku,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        LOG.warning("product not found sku=%s", sku)
        return {"error": "unknown sku", "sku": sku}
    return dict(row)


@app.get("/stats")
def stats() -> dict:
    """Catalog-wide aggregates: per-category counts, price bands, payload size."""
    rows = db.query(
        "SELECT sku, name, category, price_cents, stock, description FROM products",
        op="stats_scan",
    )
    catalog = [dict(row) for row in rows]

    per_category: dict[str, dict] = {}
    for item in catalog:
        bucket = per_category.setdefault(
            item["category"], {"count": 0, "stock": 0, "prices": []}
        )
        bucket["count"] += 1
        bucket["stock"] += item["stock"]
        bucket["prices"].append(item["price_cents"])

    summary = {}
    for name, bucket in per_category.items():
        prices = sorted(bucket["prices"])
        summary[name] = {
            "count": bucket["count"],
            "stock": bucket["stock"],
            "median_price_cents": prices[len(prices) // 2],
            "max_price_cents": prices[-1],
        }

    # What a client would have to download if it asked for everything - the
    # only honest way to measure it is to render it.
    payload_bytes = len(json.dumps(catalog))
    LOG.info(
        "stats computed categories=%s payload_bytes=%s", len(summary), payload_bytes
    )
    return {
        "products": len(catalog),
        "payload_bytes": payload_bytes,
        "categories": summary,
    }


@app.post("/orders")
def create_order(order: OrderRequest) -> dict:
    """Accept an order for a SKU."""
    conn = db.connect()
    try:
        (taken,) = conn.execute("SELECT COUNT(*) FROM orders").fetchone()
        order_ref = f"ORD-{taken + 1:06d}"

        product = conn.execute(
            "SELECT sku, name, price_cents, stock FROM products WHERE sku = ?",
            (order.sku,),
        ).fetchone()
        if product is None:
            LOG.warning(
                "order rejected ref=%s reason=unknown-sku sku=%s", order_ref, order.sku
            )
            return {"error": "unknown sku", "sku": order.sku, "order_ref": None}
        if product["stock"] < order.quantity:
            LOG.warning(
                "order rejected ref=%s reason=out-of-stock sku=%s wanted=%s stock=%s",
                order_ref,
                order.sku,
                order.quantity,
                product["stock"],
            )
            return {"error": "out of stock", "sku": order.sku, "order_ref": None}

        total = product["price_cents"] * order.quantity
        conn.execute(
            "INSERT INTO orders (order_ref, sku, quantity, customer, total_cents,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                order_ref,
                order.sku,
                order.quantity,
                order.customer,
                total,
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.execute(
            "UPDATE products SET stock = stock - ? WHERE sku = ?",
            (order.quantity, order.sku),
        )
        conn.commit()
    finally:
        conn.close()

    if _orders_counter is not None:
        _orders_counter.add(1, {"catalog.category": "unknown"})
    LOG.info(
        "order created ref=%s sku=%s quantity=%s total_cents=%s",
        order_ref,
        order.sku,
        order.quantity,
        total,
    )
    return {"order_ref": order_ref, "sku": order.sku, "total_cents": total}


@app.get("/orders/{order_ref}")
def get_order(order_ref: str) -> dict:
    rows = db.query(
        "SELECT order_ref, sku, quantity, customer, total_cents, created_at"
        " FROM orders WHERE order_ref = ?",
        (order_ref,),
        op="get_order",
    )
    if not rows:
        LOG.warning("order not found ref=%s", order_ref)
        return {"error": "unknown order", "order_ref": order_ref}
    return dict(rows[0])


def main() -> None:
    telemetry.setup_telemetry()
    LoggingInstrumentor().instrument(set_logging_format=False)
    # The healthcheck is polled far more often than the API is called; keeping
    # it off the traced surface keeps the traces readable.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",  # a container port, published deliberately
            port=int(os.environ.get("PORT", "8000")),
            log_config=None,
        )
    finally:
        telemetry.shutdown_telemetry()


if __name__ == "__main__":
    main()
