"""The demo catalog: a SQLite file, seeded once at startup.

The store is deliberately small enough to fit in a container and large
enough that a query over it is worth measuring.
"""

from __future__ import annotations

import logging
import os
import random
import sqlite3
import time

from . import telemetry

LOG = logging.getLogger(__name__)

DB_PATH = os.environ.get("CATALOG_DB_PATH", "./catalog.db")
CATALOG_SIZE = int(os.environ.get("CATALOG_SIZE", "5000"))

CATEGORIES = (
    "audio",
    "bikes",
    "cameras",
    "climbing",
    "coffee",
    "desks",
    "kitchen",
    "lighting",
    "outdoor",
    "running",
    "storage",
    "tools",
)

_ADJECTIVES = ("compact", "rugged", "featherweight", "insulated", "modular", "quiet")
_NOUNS = ("frame", "grinder", "harness", "lantern", "pannier", "riser", "sleeve")


def connect() -> sqlite3.Connection:
    """Open the catalog.

    A request-scoped connection: SQLite is a file, opening it is cheap, and
    a per-request handle keeps the routes free of any shared-state locking.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql: str, params: tuple = (), *, op: str) -> list[sqlite3.Row]:
    """Run a read under its own span, so the time it costs is attributed."""
    with telemetry.tracer().start_as_current_span(
        f"catalog {op}",
        attributes={"db.system.name": "sqlite", "db.operation.name": op},
    ) as span:
        conn = connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        span.set_attribute("db.response.returned_rows", len(rows))
        return rows


def _seed_rows(rng: random.Random) -> list[tuple]:
    rows = []
    for index in range(CATALOG_SIZE):
        category = CATEGORIES[index % len(CATEGORIES)]
        name = f"{rng.choice(_ADJECTIVES)} {category} {rng.choice(_NOUNS)}"
        rows.append(
            (
                f"SKU-{index:05d}",
                name,
                category,
                rng.randrange(900, 240000),
                rng.randrange(0, 40),
                # A description long enough that shipping every row of a
                # category is a payload rather than a rounding error.
                f"{name}. " + ("Field tested across three seasons. " * 6),
            )
        )
    return rows


def init() -> None:
    """Create the schema and seed it, once, at startup."""
    started = time.monotonic()
    conn = connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                sku          TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                category     TEXT NOT NULL,
                price_cents  INTEGER NOT NULL,
                stock        INTEGER NOT NULL,
                description  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                order_ref  TEXT NOT NULL,
                sku        TEXT NOT NULL,
                quantity   INTEGER NOT NULL,
                customer   TEXT NOT NULL,
                total_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # The catalog is read by SKU on the hot path, and the primary key
        # already covers that lookup.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")

        (count,) = conn.execute("SELECT COUNT(*) FROM products").fetchone()
        if count == 0:
            conn.executemany(
                "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)",
                _seed_rows(random.Random(1789)),
            )
            conn.commit()
        conn.commit()
    finally:
        conn.close()
    LOG.info(
        "catalog ready path=%s products=%s seed_ms=%.1f",
        DB_PATH,
        CATALOG_SIZE,
        (time.monotonic() - started) * 1000,
    )
