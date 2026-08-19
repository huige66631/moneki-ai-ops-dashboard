from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from typing import Any


ALLOWED_TOOLS = {"get_category_store_revenue", "get_product_revenue", "get_recent_average_order_value"}


def _money(cents: int | None) -> Decimal:
    return (Decimal(cents or 0) / Decimal(100)).quantize(Decimal("0.01"))


def _params(start_date: date, end_date: date) -> tuple[str, str]:
    if start_date > end_date:
        raise ValueError("日期范围无效。")
    return start_date.isoformat(), end_date.isoformat()


def get_category_store_revenue(connection: sqlite3.Connection, start_date: date, end_date: date) -> dict[str, Any]:
    params = _params(start_date, end_date)
    rows = connection.execute(
        "SELECT COALESCE(s.category, '未匹配门店') AS category, SUM(sf.amount_cents) AS revenue_cents, "
        "COUNT(DISTINCT sf.order_id) AS order_count, COUNT(DISTINCT sf.store_id) AS store_count "
        "FROM sales_facts sf LEFT JOIN stores s ON s.store_id = sf.store_id "
        "WHERE sf.sale_date BETWEEN ? AND ? AND sf.sale_date IS NOT NULL AND sf.order_id IS NOT NULL "
        "AND sf.amount_is_valid = 1 AND sf.amount_cents IS NOT NULL "
        "GROUP BY COALESCE(s.category, '未匹配门店') ORDER BY revenue_cents DESC, category ASC",
        params,
    ).fetchall()
    values = [{"category": row["category"], "revenue": _money(row["revenue_cents"]), "order_count": int(row["order_count"]), "store_count": int(row["store_count"])} for row in rows]
    return {"rows": values, "winner": values[0] if values else None, "filters": {"start_date": start_date, "end_date": end_date}}


def resolve_product(connection: sqlite3.Connection, product_name: str) -> list[sqlite3.Row]:
    from app.ai.tools.resolver import normalize_text
    needle = normalize_text(product_name)
    rows = connection.execute("SELECT product_id, product_name, product_category FROM products ORDER BY product_id").fetchall()
    return [row for row in rows if normalize_text(row["product_name"]) == needle]


def get_product_revenue(connection: sqlite3.Connection, product_id: str, start_date: date, end_date: date) -> dict[str, Any]:
    params = (*_params(start_date, end_date), product_id)
    product = connection.execute("SELECT product_id, product_name, product_category FROM products WHERE product_id = ?", (product_id,)).fetchone()
    if product is None:
        return {"product": {"product_id": product_id, "product_name": f"未匹配商品 ({product_id})", "product_category": None, "matched": False}, "revenue": None, "order_count": None, "filters": {"start_date": start_date, "end_date": end_date}}
    row = connection.execute(
        "SELECT COALESCE(SUM(sf.amount_cents), 0) AS revenue_cents, COUNT(DISTINCT sf.order_id) AS order_count "
        "FROM sales_facts sf JOIN products p ON p.product_id = sf.product_id "
        "WHERE sf.sale_date BETWEEN ? AND ? AND sf.sale_date IS NOT NULL AND sf.order_id IS NOT NULL "
        "AND sf.amount_is_valid = 1 AND sf.amount_cents IS NOT NULL AND p.product_id = ?",
        params,
    ).fetchone()
    return {"product": {"product_id": product["product_id"], "product_name": product["product_name"], "product_category": product["product_category"], "matched": True}, "revenue": _money(row["revenue_cents"]), "order_count": int(row["order_count"]), "filters": {"start_date": start_date, "end_date": end_date}}


def _window(connection: sqlite3.Connection, start: date, end: date) -> dict[str, Any]:
    row = connection.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) AS revenue_cents, COUNT(DISTINCT order_id) AS order_count "
        "FROM sales_facts WHERE sale_date BETWEEN ? AND ? AND sale_date IS NOT NULL AND order_id IS NOT NULL "
        "AND amount_is_valid = 1 AND amount_cents IS NOT NULL", (start.isoformat(), end.isoformat())
    ).fetchone()
    revenue = _money(row["revenue_cents"])
    count = int(row["order_count"])
    return {"start_date": start, "end_date": end, "revenue": revenue, "order_count": count, "average_order_value": (revenue / count).quantize(Decimal("0.01")) if count else None}


def get_recent_average_order_value(connection: sqlite3.Connection, start_date: date, end_date: date, window_days: int = 7) -> dict[str, Any]:
    _params(start_date, end_date)
    if (end_date - start_date).days + 1 < window_days * 2:
        return {"status": "insufficient_data", "recent": None, "previous": None, "difference": None, "change_percent": None, "direction": "insufficient_data", "filters": {"start_date": start_date, "end_date": end_date}, "window_days": window_days}
    recent_start = end_date - timedelta(days=window_days - 1)
    previous_end = recent_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=window_days - 1)
    recent = _window(connection, recent_start, end_date)
    previous = _window(connection, previous_start, previous_end)
    if not recent["order_count"] or not previous["order_count"]:
        direction = "insufficient_data"
        difference = change_percent = None
    else:
        difference = (recent["average_order_value"] - previous["average_order_value"]).quantize(Decimal("0.01"))
        change_percent = (difference / previous["average_order_value"] if previous["average_order_value"] else None)
        direction = "up" if difference > 0 else "down" if difference < 0 else "flat"
    return {"status": "ok" if direction != "insufficient_data" else "insufficient_data", "recent": recent, "previous": previous, "difference": difference, "change_percent": change_percent, "direction": direction, "filters": {"start_date": start_date, "end_date": end_date}, "window_days": window_days}

