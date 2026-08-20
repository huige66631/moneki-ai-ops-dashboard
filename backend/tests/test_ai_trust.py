from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from app.ai.contracts import AskRequest
from app.ai.orchestrator import ask
from app.ai.providers.mock import MockProvider
from app.ai.session_store import ConversationStore
from app.db import connect
from tests.test_api import api_client, build_fixture


@pytest.fixture(autouse=True)
def use_mock_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.api.routes.AI_PROVIDER", "mock")


def test_store_expires_idle_sessions_and_evicts_least_recently_used() -> None:
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    store = ConversationStore(capacity=2, ttl=timedelta(minutes=30))
    first = store.get_or_create(None, now)
    second = store.get_or_create(None, now + timedelta(minutes=1))
    assert store.touch(first.session_id, now + timedelta(minutes=2)) is not None
    third = store.get_or_create(None, now + timedelta(minutes=3))

    assert store.touch(second.session_id, now + timedelta(minutes=3)) is None
    assert store.touch(first.session_id, now + timedelta(minutes=3)) is not None
    assert store.touch(third.session_id, now + timedelta(minutes=3)) is not None
    assert store.touch(first.session_id, now + timedelta(minutes=33)) is None


def test_follow_up_replaces_month_and_keeps_verified_product(tmp_path: Path) -> None:
    db = tmp_path / "trust.sqlite3"
    build_fixture(db)
    connection = connect(db)
    store = ConversationStore()
    try:
        first = ask(
            connection,
            AskRequest(question="Alpha 2026年6月卖了多少钱？"),
            MockProvider(),
            (date(2026, 5, 1), date(2026, 6, 30)),
            store,
        )
        follow_up = ask(
            connection,
            AskRequest(question="那五月营业额是多少？", session_id=first.session_id),
            MockProvider(),
            (date(2026, 5, 1), date(2026, 6, 30)),
            store,
        )
    finally:
        connection.close()

    assert UUID(str(first.session_id))
    assert first.navigation is not None
    assert first.navigation.start_date == date(2026, 6, 1)
    assert first.navigation.end_date == date(2026, 6, 30)
    assert follow_up.status == "answered"
    assert follow_up.tool_call is not None
    assert follow_up.tool_call.name == "get_product_revenue"
    assert follow_up.tool_call.arguments["product_name"] == "Alpha"
    assert follow_up.tool_call.arguments["start_date"] == date(2026, 5, 1)
    assert follow_up.tool_call.arguments["end_date"] == date(2026, 5, 31)
    assert follow_up.navigation is not None
    assert follow_up.navigation.start_date == follow_up.tool_call.arguments["start_date"]
    assert follow_up.navigation.end_date == follow_up.tool_call.arguments["end_date"]


def test_follow_up_with_new_intent_does_not_inherit_previous_product(tmp_path: Path) -> None:
    db = tmp_path / "new-intent.sqlite3"
    build_fixture(db)
    connection = connect(db)
    store = ConversationStore()
    try:
        first = ask(connection, AskRequest(question="Alpha 2026年5月卖了多少钱？"), MockProvider(), (date(2026, 5, 1), date(2026, 5, 31)), store)
        second = ask(connection, AskRequest(question="那五月哪个品类营业额最高？", session_id=first.session_id), MockProvider(), (date(2026, 5, 1), date(2026, 5, 31)), store)
    finally:
        connection.close()

    assert second.status == "answered"
    assert second.intent == "category_store_revenue"
    assert second.tool_call is not None
    assert second.tool_call.name == "get_category_store_revenue"
    assert "product_name" not in second.tool_call.arguments


def test_follow_up_without_valid_context_needs_clarification(tmp_path: Path) -> None:
    db = tmp_path / "clarification.sqlite3"
    build_fixture(db)
    connection = connect(db)
    try:
        response = ask(
            connection,
            AskRequest(question="那五月呢？"),
            MockProvider(),
            (date(2026, 5, 1), date(2026, 5, 31)),
        )
    finally:
        connection.close()

    assert response.status == "needs_clarification"
    assert response.tool_call is None
    assert response.evidence is None
    assert response.navigation is None


def test_new_product_question_does_not_inherit_previous_product(tmp_path: Path) -> None:
    db = tmp_path / "new-product.sqlite3"
    build_fixture(db)
    connection = connect(db)
    store = ConversationStore()
    try:
        first = ask(connection, AskRequest(question="Alpha 2026年5月卖了多少钱？"), MockProvider(), (date(2026, 5, 1), date(2026, 5, 31)), store)
        second = ask(connection, AskRequest(question="Beta 2026年5月卖了多少钱？", session_id=first.session_id), MockProvider(), (date(2026, 5, 1), date(2026, 5, 31)), store)
    finally:
        connection.close()

    assert second.status == "answered"
    assert second.tool_call is not None
    assert second.tool_call.arguments["product_name"] == "Beta"


def test_legacy_request_without_session_id_remains_single_turn(api_client):
    response = api_client.post("/api/v1/assistant/ask", json={"question": "Alpha 2026年5月卖了多少钱？"})

    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["session_id"]


def test_invalid_session_id_is_rejected(api_client):
    response = api_client.post("/api/v1/assistant/ask", json={"question": "那五月呢？", "session_id": "not-a-uuid"})

    assert response.status_code == 422
