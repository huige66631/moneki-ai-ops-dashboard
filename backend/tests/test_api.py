from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import connection_dependency
from app.db import connect, ensure_schema
from app.main import app


def build_fixture(db: Path) -> None:
    connection = connect(db)
    ensure_schema(connection)
    connection.executemany(
        "INSERT INTO stores(store_id, store_name, category, district) VALUES (?, ?, ?, ?)",
        [("S01", "Main", "Food", "East")],
    )
    connection.executemany(
        "INSERT INTO products(product_id, product_name, product_category, unit_price_cents) "
        "VALUES (?, ?, ?, ?)",
        [("P01", "Alpha", "Main", 1000), ("P02", "Beta", "Side", 500)],
    )
    connection.executemany(
        "INSERT INTO sales_facts("
        "source_line_number, order_id, sale_date, store_id, product_id, quantity, amount_cents, "
        "amount_is_valid, quantity_is_valid, store_is_matched, product_is_matched) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "O1", "2026-05-01", "S01", "P01", 1, 1000, 1, 1, 1, 1),
            (2, "O2", "2026-05-01", "S01", "P01", 1, 500, 1, 1, 1, 1),
            (3, "O3", "2026-05-01", "S01", "P02", 1, 1500, 1, 1, 1, 1),
            (4, "O4", "2026-05-02", "S01", "P02", 1, -200, 1, 1, 1, 1),
            (5, "O5", "2026-05-02", "S01", "P03", 1, 1000, 1, 1, 1, 0),
            (6, "O6", "2026-05-02", "S01", "P01", 1, None, 0, 1, 1, 1),
            (7, "O7", "2026-05-03", "S99", "P03", 1, 500, 1, 1, 0, 0),
        ],
    )
    connection.executemany(
        "INSERT INTO data_quality_events(run_id, source_line_number, sale_date, rule_name, "
        "is_excluded, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("run-1", 8, "2026-05-01", "duplicate", 1, "2026-05-04T00:00:00+00:00"),
            ("run-1", 9, "2026-05-02", "invalid_amount", 1, "2026-05-04T00:00:00+00:00"),
        ],
    )
    connection.commit()
    connection.close()


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "api.sqlite3"
    build_fixture(db)
    app.dependency_overrides[connection_dependency] = lambda: connect(db)
    monkeypatch.setattr("app.api.routes.DB_PATH", db)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_dashboard_summary_daily_and_quality(api_client: TestClient):
    response = api_client.get(
        "/api/v1/dashboard?start_date=2026-05-01&end_date=2026-05-03"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "revenue": 43.0,
        "order_count": 6,
        "average_order_value": 7.17,
    }
    assert [point["revenue"] for point in payload["daily"]] == [30.0, 8.0, 5.0]
    assert [point["order_count"] for point in payload["daily"]] == [3, 2, 1]
    assert sum(point["revenue"] for point in payload["daily"]) == payload["summary"]["revenue"]
    assert sum(point["order_count"] for point in payload["daily"]) == payload["summary"]["order_count"]
    assert payload["data_quality"] == {
        "included_record_count": 6,
        "excluded_duplicate_count": 1,
        "excluded_invalid_amount_count": 1,
        "unmatched_store_count": 1,
        "unmatched_product_count": 2,
    }


def test_top_products_sort_ties_and_fallback_name(api_client: TestClient):
    payload = api_client.get(
        "/api/v1/dashboard?start_date=2026-05-01&end_date=2026-05-03"
    ).json()

    assert [(row["product_id"], row["revenue"]) for row in payload["top_products"]] == [
        ("P01", 15.0),
        ("P03", 15.0),
        ("P02", 13.0),
    ]
    assert payload["top_products"][1]["product_name"] == "未匹配商品 (P03)"
    assert payload["top_products"][0]["revenue_share"] == pytest.approx(15 / 43, abs=0.00005)


def test_empty_range_has_continuous_zero_points(api_client: TestClient):
    response = api_client.get(
        "/api/v1/dashboard?start_date=2026-08-01&end_date=2026-08-03"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "revenue": 0.0,
        "order_count": 0,
        "average_order_value": None,
    }
    assert [point["date"] for point in payload["daily"]] == [
        "2026-08-01",
        "2026-08-02",
        "2026-08-03",
    ]
    assert all(point["revenue"] == 0.0 and point["order_count"] == 0 for point in payload["daily"])
    assert payload["top_products"] == []


def test_default_range_and_health(api_client: TestClient):
    response = api_client.get("/api/v1/dashboard")
    assert response.status_code == 200
    assert response.json()["range"] == {"start_date": "2026-05-01", "end_date": "2026-05-03"}

    health = api_client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "database_ready": True}


def test_dashboard_validation(api_client: TestClient):
    assert api_client.get("/api/v1/dashboard?start_date=2026-05-01").status_code == 422
    assert api_client.get("/api/v1/dashboard?start_date=2026-05-02&end_date=2026-05-01").status_code == 422
