from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.ai.providers.base import ProviderError
from app.ai.providers.deepseek import DeepSeekProvider
from app.ai.tools.resolver import parse_date_range


def test_date_parser_keeps_explicit_date_range() -> None:
    bounds = (date(2026, 5, 1), date(2026, 7, 31))

    assert parse_date_range("2026-05-01 至 2026-05-03", bounds) == (
        date(2026, 5, 1),
        date(2026, 5, 3),
    )


def test_date_parser_honors_explicit_chinese_year() -> None:
    bounds = (date(2026, 5, 1), date(2026, 7, 31))

    assert parse_date_range("2025年六月", bounds) == (
        date(2025, 6, 1),
        date(2025, 6, 30),
    )


def test_deepseek_rejects_multiple_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [{
                    "message": {
                        "tool_calls": [
                            {"function": {"name": "get_category_store_revenue", "arguments": "{}"}},
                            {"function": {"name": "get_product_revenue", "arguments": "{}"}},
                        ]
                    }
                }]
            }

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: Response())
    provider = DeepSeekProvider("test-key", "https://example.test", "deepseek-chat", 1)

    with pytest.raises(ProviderError):
        provider.plan("测试", None, (date(2026, 5, 1), date(2026, 7, 31)))
