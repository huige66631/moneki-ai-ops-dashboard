from pathlib import Path

from app.ingestion.load_data import parse_amount_cents, parse_date, parse_quantity


def test_parse_dates_and_amounts():
    assert parse_date("2026/05/02") == "2026-05-02"
    assert parse_date("02-05-2026") == "2026-05-02"
    assert parse_date("2026-02-30") is None
    assert parse_amount_cents("¥ 1,234.50") == (123450, True)
    assert parse_amount_cents("-$12.35") == (-1235, True)
    assert parse_amount_cents("") == (None, False)
    assert parse_amount_cents("not-money") == (None, False)


def test_quantity_rules():
    assert parse_quantity("2") == (2, True)
    assert parse_quantity("0") == (0, False)
    assert parse_quantity("-1") == (-1, False)


def test_fixture_import_is_repeatable(tmp_path: Path):
    from app.ingestion.load_data import load_data
    from app.db import connect

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "stores.csv").write_text("store_id,store_name,category,district\ns01,Demo,Food,Test\n", encoding="utf-8")
    (raw / "products.csv").write_text("product_id,product_name,product_category,unit_price\np01,Noodles,Main,10\n", encoding="utf-8")
    (raw / "sales.csv").write_text(
        "order_id,date,store_id,product_id,qty,amount,payment\n"
        "o1,2026-05-01,s01,p01,1,$10.00,Cash\n"
        "o1,2026-05-01,s01,p01,1,$10.00,Cash\n",
        encoding="utf-8",
    )
    db = tmp_path / "test.sqlite3"
    first = load_data(db, raw)
    second = load_data(db, raw)
    assert first["fact_count"] == second["fact_count"] == 1
    connection = connect(db)
    assert connection.execute("SELECT COUNT(*) FROM sales_facts").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM data_quality_events").fetchone()[0] == 1
    connection.close()


def test_import_records_quality_events_and_keeps_dirty_facts(tmp_path: Path):
    from app.ingestion.load_data import load_data
    from app.db import connect

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "stores.csv").write_text(
        "store_id,store_name,category,district\nS01,Demo,Food,Test\n", encoding="utf-8"
    )
    (raw / "products.csv").write_text(
        "product_id,product_name,product_category,unit_price\nP01,Noodles,Main,10\n",
        encoding="utf-8",
    )
    (raw / "sales.csv").write_text(
        "order_id,date,store_id,product_id,qty,amount,payment\n"
        "o1,2026-05-01,s01,p01,0,$10.00,Cash\n"
        "o2,not-a-date,s99,p99,1,,Card\n"
        "o3,2026-05-02,s99,p99,1,-$2.50,Card\n",
        encoding="utf-8",
    )
    result = load_data(tmp_path / "test.sqlite3", raw)

    assert result["fact_count"] == 3
    assert result["invalid_amount_count"] == 1
    assert result["invalid_quantity_count"] == 1
    assert result["unmatched_store_count"] == 2
    assert result["unmatched_product_count"] == 2

    connection = connect(tmp_path / "test.sqlite3")
    facts = connection.execute(
        "SELECT sale_date, amount_cents, amount_is_valid, quantity_is_valid "
        "FROM sales_facts ORDER BY source_line_number"
    ).fetchall()
    assert facts[0]["sale_date"] == "2026-05-01"
    assert facts[0]["quantity_is_valid"] == 0
    assert facts[1]["sale_date"] is None
    assert facts[1]["amount_is_valid"] == 0
    assert facts[2]["amount_cents"] == -250
    audit = {
        row["rule_name"]: row["affected_rows"]
        for row in connection.execute(
            "SELECT rule_name, affected_rows FROM data_quality_audit"
        ).fetchall()
    }
    assert audit == {
        "invalid_amount": 1,
        "invalid_quantity": 1,
        "unmatched_store": 2,
        "unmatched_product": 2,
    }
    connection.close()
