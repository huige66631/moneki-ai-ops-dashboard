from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal


def money(cents: int | None) -> Decimal:
    return Decimal(cents or 0) / Decimal(100)


def _average(revenue: Decimal, order_count: int) -> Decimal | None:
    return (revenue / order_count).quantize(Decimal("0.01")) if order_count else None


def get_date_bounds(connection: sqlite3.Connection) -> tuple[date, date] | None:
    row = connection.execute(
        "SELECT MIN(sale_date) AS start_date, MAX(sale_date) AS end_date "
        "FROM sales_facts WHERE sale_date IS NOT NULL"
    ).fetchone()
    if not row or not row["start_date"]:
        return None
    return date.fromisoformat(row["start_date"]), date.fromisoformat(row["end_date"])


def build_dashboard(connection: sqlite3.Connection, start_date: date, end_date: date) -> dict:
    params = (start_date.isoformat(), end_date.isoformat())
    summary_row = connection.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) AS revenue_cents, "
        "COUNT(DISTINCT order_id) AS order_count "
        "FROM sales_facts WHERE sale_date BETWEEN ? AND ? AND sale_date IS NOT NULL "
        "AND order_id IS NOT NULL AND amount_is_valid = 1",
        params,
    ).fetchone()
    summary_revenue = money(summary_row["revenue_cents"])
    summary_orders = int(summary_row["order_count"])

    daily_rows = connection.execute(
        "SELECT sale_date, COALESCE(SUM(amount_cents), 0) AS revenue_cents, "
        "COUNT(DISTINCT order_id) AS order_count FROM sales_facts "
        "WHERE sale_date BETWEEN ? AND ? AND sale_date IS NOT NULL AND order_id IS NOT NULL "
        "AND amount_is_valid = 1 GROUP BY sale_date ORDER BY sale_date",
        params,
    ).fetchall()
    daily_by_date = {row["sale_date"]: row for row in daily_rows}
    daily = []
    cursor = start_date
    while cursor <= end_date:
        key = cursor.isoformat()
        row = daily_by_date.get(key)
        revenue = money(row["revenue_cents"] if row else 0)
        order_count = int(row["order_count"]) if row else 0
        daily.append(
            {
                "date": cursor,
                "revenue": revenue,
                "order_count": order_count,
                "average_order_value": _average(revenue, order_count),
            }
        )
        cursor += timedelta(days=1)

    product_rows = connection.execute(
        "SELECT sf.product_id, COALESCE(p.product_name, '未匹配商品 (' || sf.product_id || ')') AS product_name, "
        "p.product_category, SUM(sf.amount_cents) AS revenue_cents, COUNT(DISTINCT sf.order_id) AS order_count "
        "FROM sales_facts sf LEFT JOIN products p ON p.product_id = sf.product_id "
        "WHERE sf.sale_date BETWEEN ? AND ? AND sf.sale_date IS NOT NULL AND sf.order_id IS NOT NULL "
        "AND sf.amount_is_valid = 1 GROUP BY sf.product_id, p.product_name, p.product_category "
        "ORDER BY revenue_cents DESC, sf.product_id ASC LIMIT 10",
        params,
    ).fetchall()
    top_products = []
    for index, row in enumerate(product_rows, start=1):
        revenue = money(row["revenue_cents"])
        top_products.append(
            {
                "rank": index,
                "product_id": row["product_id"] or "UNKNOWN",
                "product_name": row["product_name"] or "未匹配商品 (UNKNOWN)",
                "product_category": row["product_category"],
                "revenue": revenue,
                "order_count": int(row["order_count"]),
                "revenue_share": (revenue / summary_revenue).quantize(Decimal("0.0001"))
                if summary_revenue
                else Decimal("0"),
            }
        )

    average_daily_revenue = (
        (summary_revenue / Decimal((end_date - start_date).days + 1)).quantize(Decimal("0.01"))
        if end_date >= start_date
        else Decimal("0")
    )

    quality = connection.execute(
        "SELECT "
        "SUM(CASE WHEN order_id IS NOT NULL AND amount_is_valid = 1 THEN 1 ELSE 0 END) "
        "AS included_record_count, "
        "SUM(CASE WHEN store_is_matched = 0 THEN 1 ELSE 0 END) AS unmatched_store_count, "
        "SUM(CASE WHEN product_is_matched = 0 THEN 1 ELSE 0 END) AS unmatched_product_count "
        "FROM sales_facts WHERE sale_date BETWEEN ? AND ? AND sale_date IS NOT NULL",
        params,
    ).fetchone()
    duplicate_row = connection.execute(
        "SELECT COUNT(*) AS count FROM data_quality_events WHERE sale_date BETWEEN ? AND ? AND rule_name = 'duplicate'",
        params,
    ).fetchone()
    invalid_row = connection.execute(
        "SELECT COUNT(*) AS count FROM data_quality_events WHERE sale_date BETWEEN ? AND ? AND rule_name = 'invalid_amount'",
        params,
    ).fetchone()
    invalid_date_row = connection.execute(
        "SELECT COUNT(*) AS count FROM data_quality_events WHERE rule_name = 'invalid_date'",
    ).fetchone()

    return {
        "range": {"start_date": start_date, "end_date": end_date},
        "summary": {
            "revenue": summary_revenue,
            "order_count": summary_orders,
            "average_order_value": _average(summary_revenue, summary_orders),
            "average_daily_revenue": average_daily_revenue,
        },
        "daily": daily,
        "top_products": top_products,
        "data_quality": {
            "included_record_count": int(quality["included_record_count"] or 0),
            "excluded_duplicate_count": int(duplicate_row["count"]),
            "excluded_invalid_amount_count": int(invalid_row["count"]),
            "excluded_invalid_date_count": int(invalid_date_row["count"]),
            "unmatched_store_count": int(quality["unmatched_store_count"] or 0),
            "unmatched_product_count": int(quality["unmatched_product_count"] or 0),
        },
    }
