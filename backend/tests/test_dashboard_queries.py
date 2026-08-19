from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.ai.tools.dashboard_queries import get_recent_average_order_value
from app.db import connect, ensure_schema


def test_average_order_value_uses_two_complete_seven_day_windows(tmp_path: Path):
    db = tmp_path / "aov.sqlite3"
    connection = connect(db)
    ensure_schema(connection)
    start = date(2026, 5, 1)
    rows = []
    for offset in range(14):
        rows.append((offset + 1, f"O{offset}", (start + timedelta(days=offset)).isoformat(), "S01", "P01", 1, 1000 if offset < 7 else 1500, 1, 1, 1, 1))
    connection.executemany(
        "INSERT INTO sales_facts(source_line_number, order_id, sale_date, store_id, product_id, quantity, amount_cents, amount_is_valid, quantity_is_valid, store_is_matched, product_is_matched) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    connection.commit()
    try:
        result = get_recent_average_order_value(connection, start, start + timedelta(days=13))
    finally:
        connection.close()

    assert result["previous"]["average_order_value"] == 10
    assert result["recent"]["average_order_value"] == 15
    assert result["difference"] == 5
    assert result["direction"] == "up"
