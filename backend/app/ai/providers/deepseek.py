from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx

from app.ai.contracts import ToolCallPlan
from app.ai.prompts import SYSTEM_PROMPT, TOOL_DEFINITIONS
from app.ai.providers.base import ProviderError


class DeepSeekProvider:
    name = "deepseek"
    mode = "live"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float) -> None:
        self.api_key = api_key
        self.url = f"{base_url}/chat/completions"
        self.model = model
        self.timeout = timeout

    def plan(self, question: str, context: tuple[date, date] | None, bounds: tuple[date, date]) -> ToolCallPlan:
        context_text = {"start_date": context[0].isoformat(), "end_date": context[1].isoformat()} if context else None
        payload = {"model": self.model, "temperature": 0, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": json.dumps({"question": question, "dashboard_context": context_text, "data_bounds": {"start_date": bounds[0].isoformat(), "end_date": bounds[1].isoformat()}}, ensure_ascii=False)}], "tools": TOOL_DEFINITIONS, "tool_choice": "auto"}
        try:
            response = httpx.post(self.url, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=payload, timeout=self.timeout)
            response.raise_for_status()
            body = response.json()
            message = body.get("choices", [{}])[0].get("message", {})
            calls = message.get("tool_calls") or []
            if not calls:
                return ToolCallPlan(status="unsupported", message="当前问题不属于已支持的数据查询。")
            if len(calls) != 1:
                raise ProviderError("provider returned multiple tool calls")
            call = calls[0].get("function", {})
            arguments = json.loads(call.get("arguments", "{}"))
            return ToolCallPlan(status="tool_call", name=call.get("name"), arguments=arguments, intent=None)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError("provider request failed") from exc
