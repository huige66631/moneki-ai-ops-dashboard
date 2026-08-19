from pathlib import Path

from app.ingestion.load_data import parse_amount_cents, parse_date, parse_quantity


def test_parse_dates_and_amounts():
    assert parse_date("2026/05/02") == "2026-05-02"
    assert parse_date("02-05-2026") == "2026-05-02"
    assert parse_amount_cents("¥ 1,234.50") == (123450, True)
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
