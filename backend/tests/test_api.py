from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.api.routes import connection_dependency


def test_dashboard_validation(monkeypatch, tmp_path):
    from app.db import connect, ensure_schema
    from app.config import DB_PATH

    db = tmp_path / "api.sqlite3"
    connection = connect(db)
    ensure_schema(connection)
    connection.execute("INSERT INTO sales_facts(source_line_number, order_id, sale_date, product_id, amount_cents, amount_is_valid, quantity_is_valid, store_is_matched, product_is_matched) VALUES (1, 'O1', '2026-05-01', 'P01', 1000, 1, 1, 1, 1)")
    connection.commit()
    connection.close()
    app.dependency_overrides[connection_dependency] = lambda: connect(db)
    try:
        client = TestClient(app)
        assert client.get("/api/v1/dashboard?start_date=2026-05-01").status_code == 422
        assert client.get("/api/v1/dashboard?start_date=2026-05-02&end_date=2026-05-01").status_code == 422
        response = client.get("/api/v1/dashboard?start_date=2026-05-01&end_date=2026-05-01")
        assert response.status_code == 200
        assert response.json()["summary"]["revenue"] == 10.0
    finally:
        app.dependency_overrides.clear()
