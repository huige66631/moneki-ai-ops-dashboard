from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import connection_dependency
from app.ai.contracts import AskRequest, ToolCallPlan
from app.ai.orchestrator import ask
from app.ai.providers.base import ProviderError
from app.db import connect
from app.main import app
from tests.test_api import api_client, build_fixture


@pytest.fixture(autouse=True)
def use_mock_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.api.routes.AI_PROVIDER", "mock")


def test_mock_assistant_uses_real_category_query(tmp_path: Path):
    db = tmp_path / "assistant.sqlite3"
    build_fixture(db)

    def dependency():
        connection = connect(db)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[connection_dependency] = dependency
    try:
        payload = TestClient(app).post(
            "/api/v1/assistant/ask",
            json={"question": "哪个品类的门店营业额最高？", "context": {"start_date": "2026-05-01", "end_date": "2026-05-03"}},
        ).json()
    finally:
        app.dependency_overrides.clear()

    assert payload["status"] == "answered"
    assert payload["tool_call"]["name"] == "get_category_store_revenue"
    assert payload["evidence"]["values"]["revenue"] == 38.0
    assert "38.00" in payload["answer"]


def test_mock_assistant_rejects_unsupported_without_evidence(api_client: TestClient):
    payload = api_client.post("/api/v1/assistant/ask", json={"question": "利润是多少？"}).json()
    assert payload["status"] == "unsupported"
    assert payload["evidence"] is None
    assert payload["tool_call"] is None


def test_assistant_validates_context_dates(api_client: TestClient):
    response = api_client.post(
        "/api/v1/assistant/ask",
        json={"question": "客单价最近是涨了还是跌了？", "context": {"start_date": "2026-05-03", "end_date": "2026-05-01"}},
    )
    assert response.status_code == 422


def test_product_query_keeps_negative_amount_and_date_boundary(api_client: TestClient):
    response = api_client.post(
        "/api/v1/assistant/ask",
        json={"question": "Beta 2026-05-01 至 2026-05-03 卖了多少钱？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "answered"
    assert payload["evidence"]["filters"]["start_date"] == "2026-05-01"
    assert payload["evidence"]["filters"]["end_date"] == "2026-05-03"
    assert payload["evidence"]["values"] == {"revenue": 13.0, "order_count": 2}
    assert "13.00" in payload["answer"]


def test_unknown_product_needs_clarification(api_client: TestClient):
    payload = api_client.post(
        "/api/v1/assistant/ask",
        json={"question": "Missing 2026年5月卖了多少钱？"},
    ).json()

    assert payload["status"] == "needs_clarification"
    assert payload["evidence"] is None
    assert payload["tool_call"] is None


def test_provider_failure_returns_safe_503(api_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def unavailable_provider():
        raise ProviderError("connection timeout")

    monkeypatch.setattr("app.api.routes._provider", unavailable_provider)
    response = api_client.post("/api/v1/assistant/ask", json={"question": "哪个品类的门店营业额最高？"})

    assert response.status_code == 503
    assert response.json()["detail"] == "AI 查询暂时不可用，请检查服务配置后重试。"


def test_unknown_tool_is_rejected_without_database_query(tmp_path: Path):
    class UnknownToolProvider:
        name = "fake"
        mode = "mock"

        def plan(self, *args, **kwargs):
            return ToolCallPlan(status="tool_call", name="drop_all_tables")

    db = tmp_path / "unknown-tool.sqlite3"
    build_fixture(db)
    connection = connect(db)
    try:
        with pytest.raises(ProviderError):
            ask(
                connection,
                request=AskRequest(question="测试"),
                provider=UnknownToolProvider(),
                bounds=(date(2026, 5, 1), date(2026, 5, 3)),
            )
    finally:
        connection.close()
