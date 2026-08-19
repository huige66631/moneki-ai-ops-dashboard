from __future__ import annotations

import csv
import re
import sqlite3
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from app.config import DB_PATH, ROOT_DIR
from app.db import connect, ensure_schema

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y")
AMOUNT_RE = re.compile(
    r"^(?P<sign>[+-]?)(?:[\u00a5$\u20ac\u00a3]\s*)?"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"(?:\s*[\u00a5$\u20ac\u00a3])?$")


@contextmanager
def managed_connection(db_path: Path):
    connection = connect(db_path)
    try:
        ensure_schema(connection)
        with connection:
            yield connection
    finally:
        connection.close()


def normalize_text(value: str | None) -> str:
    return (value or "").strip()


def normalize_id(value: str | None) -> str:
    return normalize_text(value).upper()


def parse_date(value: str | None) -> str | None:
    raw = normalize_text(value)
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_amount_cents(value: str | None) -> tuple[int | None, bool]:
    raw = normalize_text(value)
    if not raw:
        return None, False
    match = AMOUNT_RE.fullmatch(raw)
    if not match:
        return None, False
    cleaned = f"{match.group('sign')}{match.group('number').replace(',', '')}"
    try:
        amount = Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None, False
    return int(amount * 100), True


def parse_quantity(value: str | None) -> tuple[int | None, bool]:
    raw = normalize_text(value)
    if not raw:
        return None, False
    try:
        quantity = int(raw)
    except ValueError:
        return None, False
    return quantity, quantity > 0


def load_data(
    db_path: Path = DB_PATH,
    raw_dir: Path = ROOT_DIR / "data" / "raw",
) -> dict[str, int | str]:
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    with managed_connection(db_path) as connection:
        # Rebuild inside the same transaction as the inserts so a bad source file
        # leaves the previous dataset intact instead of leaving a partial database.
        connection.execute("DELETE FROM stores")
        connection.execute("DELETE FROM products")
        connection.execute("DELETE FROM sales_facts")
        connection.execute("DELETE FROM data_quality_events")
        connection.execute("DELETE FROM data_quality_audit")
        stores = []
        with (raw_dir / "stores.csv").open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                stores.append(
                    (
                        normalize_id(row.get("store_id")),
                        normalize_text(row.get("store_name")),
                        normalize_text(row.get("category")),
                        normalize_text(row.get("district")),
                    )
                )
        connection.executemany(
            "INSERT INTO stores(store_id, store_name, category, district) VALUES (?, ?, ?, ?)",
            stores,
        )

        products = []
        with (raw_dir / "products.csv").open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                unit_price, _ = parse_amount_cents(row.get("unit_price"))
                products.append(
                    (
                        normalize_id(row.get("product_id")),
                        normalize_text(row.get("product_name")),
                        normalize_text(row.get("product_category")),
                        unit_price,
                    )
                )
        connection.executemany(
            "INSERT INTO products(product_id, product_name, product_category, unit_price_cents) "
            "VALUES (?, ?, ?, ?)",
            products,
        )

        store_ids = {row[0] for row in stores}
        product_ids = {row[0] for row in products}
        seen: set[tuple[object, ...]] = set()
        quality_counts: Counter[str] = Counter()
        facts = []
        events = []

        with (raw_dir / "sales.csv").open("r", encoding="utf-8-sig", newline="") as file:
            for source_line_number, row in enumerate(csv.DictReader(file), start=2):
                order_id = normalize_id(row.get("order_id"))
                sale_date = parse_date(row.get("date"))
                store_id = normalize_id(row.get("store_id"))
                product_id = normalize_id(row.get("product_id"))
                quantity, quantity_is_valid = parse_quantity(row.get("qty"))
                amount_cents, amount_is_valid = parse_amount_cents(row.get("amount"))
                payment = normalize_text(row.get("payment"))
                duplicate_key = (
                    order_id,
                    sale_date,
                    store_id,
                    product_id,
                    quantity,
                    amount_cents,
                    payment,
                )
                is_duplicate = duplicate_key in seen
                seen.add(duplicate_key)
                store_is_matched = store_id in store_ids
                product_is_matched = product_id in product_ids

                if is_duplicate:
                    quality_counts["duplicate"] += 1
                    events.append((run_id, source_line_number, sale_date, "duplicate", 1, now))
                    continue
                if sale_date is None:
                    quality_counts["invalid_date"] += 1
                    events.append((run_id, source_line_number, sale_date, "invalid_date", 1, now))
                if not amount_is_valid:
                    quality_counts["invalid_amount"] += 1
                    events.append((run_id, source_line_number, sale_date, "invalid_amount", 1, now))
                if not quantity_is_valid:
                    quality_counts["invalid_quantity"] += 1
                    events.append((run_id, source_line_number, sale_date, "invalid_quantity", 0, now))
                if not store_is_matched:
                    quality_counts["unmatched_store"] += 1
                    events.append((run_id, source_line_number, sale_date, "unmatched_store", 0, now))
                if not product_is_matched:
                    quality_counts["unmatched_product"] += 1
                    events.append((run_id, source_line_number, sale_date, "unmatched_product", 0, now))

                facts.append(
                    (
                        source_line_number,
                        order_id or None,
                        sale_date,
                        store_id or None,
                        product_id or None,
                        quantity,
                        amount_cents,
                        payment or None,
                        int(amount_is_valid),
                        int(quantity_is_valid),
                        int(store_is_matched),
                        int(product_is_matched),
                    )
                )

        connection.executemany(
            "INSERT INTO sales_facts(source_line_number, order_id, sale_date, store_id, product_id, "
            "quantity, amount_cents, payment, amount_is_valid, quantity_is_valid, store_is_matched, "
            "product_is_matched) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            facts,
        )
        connection.executemany(
            "INSERT INTO data_quality_events(run_id, source_line_number, sale_date, rule_name, "
            "is_excluded, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            events,
        )
        connection.executemany(
            "INSERT INTO data_quality_audit(run_id, rule_name, affected_rows, created_at) VALUES (?, ?, ?, ?)",
            [(run_id, rule, count, now) for rule, count in quality_counts.items()],
        )
    result: dict[str, int | str] = {"run_id": run_id, "fact_count": len(facts)}
    result.update({f"{key}_count": value for key, value in quality_counts.items()})
    return result


if __name__ == "__main__":
    print(load_data())
