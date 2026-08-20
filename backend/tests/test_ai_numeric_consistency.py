from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.routes import connection_dependency
from app.db import connect
from app.main import app
from tests.test_api import build_fixture


@contextmanager
def verified_client(db: Path) -> Iterator[TestClient]:
    def dependency():
        connection = connect(db)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[connection_dependency] = dependency
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _money(cents: int) -> float:
    return float((Decimal(cents) / Decimal(100)).quantize(Decimal("0.01")))


def _seed_aov_days(db: Path) -> None:
    connection = connect(db)
    try:
        rows = []
        for offset in range(3, 14):
            current = date(2026, 5, 1) + timedelta(days=offset)
            rows.append((100 + offset, f"AOV-{offset}", current.isoformat(), "S01", "P01", 1, 1000 + offset * 100, 1, 1, 1, 1))
        connection.executemany(
            "INSERT INTO sales_facts(source_line_number, order_id, sale_date, store_id, product_id, quantity, amount_cents, "
            "amount_is_valid, quantity_is_valid, store_is_matched, product_is_matched) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def consistency_db(tmp_path: Path) -> Path:
    db = tmp_path / "consistency.sqlite3"
    build_fixture(db)
    _seed_aov_days(db)
    return db


def test_category_answer_matches_independent_join(consistency_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.api.routes.AI_PROVIDER", "mock")
    connection = connect(consistency_db)
    try:
        expected = connection.execute(
            "SELECT COALESCE(s.category, '未匹配门店') AS category, SUM(sf.amount_cents) AS revenue_cents, "
            "COUNT(DISTINCT sf.order_id) AS order_count FROM sales_facts sf LEFT JOIN stores s ON s.store_id = sf.store_id "
            "WHERE sf.sale_date BETWEEN ? AND ? AND sf.sale_date IS NOT NULL AND sf.order_id IS NOT NULL "
            "AND sf.amount_is_valid = 1 AND sf.amount_cents IS NOT NULL GROUP BY COALESCE(s.category, '未匹配门店') "
            "ORDER BY revenue_cents DESC, category ASC LIMIT 1",
            ("2026-05-01", "2026-05-14"),
        ).fetchone()
    finally:
        connection.close()
    with verified_client(consistency_db) as client:
        payload = client.post("/api/v1/assistant/ask", json={"question": "哪个品类的门店营业额最高？", "context": {"start_date": "2026-05-01", "end_date": "2026-05-14"}}).json()

    assert payload["status"] == "answered"
    assert payload["evidence"]["filters"]["category"] == expected["category"]
    assert payload["evidence"]["values"]["revenue"] == _money(expected["revenue_cents"])
    assert payload["evidence"]["values"]["order_count"] == expected["order_count"]
    assert f"{_money(expected['revenue_cents']):,.2f}" in payload["answer"]


def test_product_and_refund_answer_match_independent_join(consistency_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.api.routes.AI_PROVIDER", "mock")
    connection = connect(consistency_db)
    try:
        expected = connection.execute(
            "SELECT SUM(sf.amount_cents) AS revenue_cents, COUNT(DISTINCT sf.order_id) AS order_count, "
            "MIN(sf.amount_cents) AS minimum_amount_cents FROM sales_facts sf JOIN products p ON p.product_id = sf.product_id "
            "WHERE p.product_name = ? AND sf.sale_date BETWEEN ? AND ? AND sf.sale_date IS NOT NULL "
            "AND sf.order_id IS NOT NULL AND sf.amount_is_valid = 1 AND sf.amount_cents IS NOT NULL",
            ("Beta", "2026-05-01", "2026-05-03"),
        ).fetchone()
    finally:
        connection.close()
    with verified_client(consistency_db) as client:
        payload = client.post("/api/v1/assistant/ask", json={"question": "Beta 2026年5月1日到2026年5月3日卖了多少钱？"}).json()

    assert expected["minimum_amount_cents"] < 0
    assert payload["status"] == "answered"
    assert payload["evidence"]["values"] == {"revenue": _money(expected["revenue_cents"]), "order_count": expected["order_count"]}
    assert f"{_money(expected['revenue_cents']):,.2f}" in payload["answer"]


def test_recent_aov_answer_matches_independent_windows(consistency_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.api.routes.AI_PROVIDER", "mock")
    connection = connect(consistency_db)
    try:
        windows = []
        for start, end in (("2026-05-08", "2026-05-14"), ("2026-05-01", "2026-05-07")):
            row = connection.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) AS revenue_cents, COUNT(DISTINCT order_id) AS order_count "
                "FROM sales_facts WHERE sale_date BETWEEN ? AND ? AND sale_date IS NOT NULL AND order_id IS NOT NULL "
                "AND amount_is_valid = 1 AND amount_cents IS NOT NULL",
                (start, end),
            ).fetchone()
            windows.append(_money(row["revenue_cents"]) / row["order_count"])
    finally:
        connection.close()
    with verified_client(consistency_db) as client:
        payload = client.post("/api/v1/assistant/ask", json={"question": "客单价最近是涨了还是跌了？", "context": {"start_date": "2026-05-01", "end_date": "2026-05-14"}}).json()

    values = payload["evidence"]["values"]
    assert payload["status"] == "answered"
    assert values["recent"]["average_order_value"] == pytest.approx(windows[0], abs=0.01)
    assert values["previous"]["average_order_value"] == pytest.approx(windows[1], abs=0.01)
    assert values["difference"] == pytest.approx(windows[0] - windows[1], abs=0.01)
    assert f"{windows[0]:,.2f}" in payload["answer"]


def test_empty_product_range_reports_verified_zero_without_navigation_guess(consistency_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.api.routes.AI_PROVIDER", "mock")
    connection = connect(consistency_db)
    try:
        expected = connection.execute(
            "SELECT COALESCE(SUM(sf.amount_cents), 0) AS revenue_cents FROM sales_facts sf JOIN products p ON p.product_id = sf.product_id "
            "WHERE p.product_name = ? AND sf.sale_date BETWEEN ? AND ? AND sf.sale_date IS NOT NULL "
            "AND sf.order_id IS NOT NULL AND sf.amount_is_valid = 1 AND sf.amount_cents IS NOT NULL",
            ("Alpha", "2026-05-02", "2026-05-03"),
        ).fetchone()
    finally:
        connection.close()
    with verified_client(consistency_db) as client:
        payload = client.post("/api/v1/assistant/ask", json={"question": "Alpha 2026年5月2日到2026年5月3日卖了多少钱？"}).json()

    assert expected["revenue_cents"] == 0
    assert payload["status"] == "answered"
    assert payload["evidence"]["values"]["revenue"] == 0.0
    assert "0.00" in payload["answer"]
    assert payload["navigation"] == {"start_date": "2026-05-02", "end_date": "2026-05-03", "store_id": None, "reason": "answer_query_range"}
