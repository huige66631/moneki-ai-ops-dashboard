from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    store_id TEXT PRIMARY KEY,
    store_name TEXT NOT NULL,
    category TEXT,
    district TEXT
);
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    product_category TEXT,
    unit_price_cents INTEGER
);
CREATE TABLE IF NOT EXISTS sales_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_line_number INTEGER NOT NULL,
    order_id TEXT,
    sale_date TEXT,
    store_id TEXT,
    product_id TEXT,
    quantity INTEGER,
    amount_cents INTEGER,
    payment TEXT,
    amount_is_valid INTEGER NOT NULL,
    quantity_is_valid INTEGER NOT NULL,
    store_is_matched INTEGER NOT NULL,
    product_is_matched INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sales_facts_date ON sales_facts(sale_date);
CREATE TABLE IF NOT EXISTS data_quality_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_line_number INTEGER NOT NULL,
    sale_date TEXT,
    rule_name TEXT NOT NULL,
    is_excluded INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quality_events_date ON data_quality_events(sale_date);
CREATE TABLE IF NOT EXISTS data_quality_audit (
    run_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    affected_rows INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, rule_name)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # FastAPI may enter a generator dependency and its sync route on different
    # worker threads; each request still owns its connection, so thread checks
    # only add a false failure here.
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    connection.commit()


def get_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(db_path)
    try:
        yield connection
    finally:
        connection.close()
