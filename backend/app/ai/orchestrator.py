from __future__ import annotations

import sqlite3
import re
from datetime import date
from decimal import Decimal
from typing import Any

from app.ai.contracts import AssistantResponse, AskRequest, Evidence, ProviderInfo, ToolCall, ToolCallPlan
from app.ai.providers.base import ProviderError
from app.ai.tools.dashboard_queries import ALLOWED_TOOLS, get_category_store_revenue, get_product_revenue, get_recent_average_order_value, resolve_product
from app.ai.tools.resolver import parse_date_range


def _display_money(value: Decimal | float | int | None) -> str:
    if value is None:
        return "—"
    return f"¥{float(value):,.2f}"


def _json_number(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_number(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_number(item) for item in value]
    return value


def _dates(arguments: dict[str, Any], request: AskRequest, bounds: tuple[date, date]) -> tuple[date, date] | None:
    parsed = parse_date_range(request.question, bounds)
    if parsed is None:
        if re.search(r"(?:20\d{2}\s*[年/-]|\d{1,2}\s*月|[一二三四五六七八九十]+月|日期)", request.question):
            return None
        parsed = (request.context.start_date, request.context.end_date) if request.context else bounds
    if parsed[0] > parsed[1]:
        raise ValueError("日期范围无效。")
    return parsed


def _intent_for_name(name: str) -> str:
    return {"get_category_store_revenue": "category_store_revenue", "get_product_revenue": "product_revenue", "get_recent_average_order_value": "recent_average_order_value"}[name]


def ask(connection: sqlite3.Connection, request: AskRequest, provider, bounds: tuple[date, date]) -> AssistantResponse:
    try:
        plan: ToolCallPlan = provider.plan(request.question, (request.context.start_date, request.context.end_date) if request.context else None, bounds)
    except ProviderError:
        raise
    provider_info = ProviderInfo(name=provider.name, mode=provider.mode)
    if plan.status != "tool_call":
        return AssistantResponse(status=plan.status, answer=plan.message or "当前问题需要更多信息。", intent=plan.intent, provider=provider_info)
    if plan.name not in ALLOWED_TOOLS:
        raise ProviderError("unknown tool")
    try:
        dates = _dates(plan.arguments, request, bounds)
        if dates is None:
            return AssistantResponse(status="needs_clarification", answer="这个日期涉及多个年份或格式不完整，请提供明确的起止日期或年份。", intent=_intent_for_name(plan.name), provider=provider_info)
        start_date, end_date = dates
        if plan.name == "get_category_store_revenue":
            result = get_category_store_revenue(connection, start_date, end_date)
            if not result["winner"]:
                return AssistantResponse(status="needs_clarification", answer="这个日期范围没有可用的销售记录，请换一个日期范围。", intent="category_store_revenue", provider=provider_info)
            winner = result["winner"]
            answer = f"在 {start_date} 至 {end_date}，门店品类“{winner['category']}”的净营业额最高，为 {_display_money(winner['revenue'])}，涉及 {winner['order_count']} 个订单。"
            evidence = Evidence(metric="revenue", filters={"start_date": start_date, "end_date": end_date, "category": winner["category"]}, values=_json_number({"revenue": winner["revenue"], "order_count": winner["order_count"], "store_count": winner["store_count"]}), summary=f"共返回 {len(result['rows'])} 个门店品类，按净营业额降序。")
        elif plan.name == "get_product_revenue":
            product_name = str(plan.arguments.get("product_name", "")).strip()
            matches = resolve_product(connection, product_name)
            if len(matches) != 1:
                detail = "、".join(row["product_name"] for row in matches) if matches else "未找到匹配商品"
                return AssistantResponse(status="needs_clarification", answer=f"我没有找到唯一的商品“{product_name}”（{detail}），请提供 products 表中的准确商品名称。", intent="product_revenue", provider=provider_info)
            result = get_product_revenue(connection, matches[0]["product_id"], start_date, end_date)
            answer = f"{start_date} 至 {end_date}，{result['product']['product_name']}的净营业额是 {_display_money(result['revenue'])}，共涉及 {result['order_count']} 个订单。"
            evidence = Evidence(metric="revenue", filters={"product_id": result["product"]["product_id"], "product_name": result["product"]["product_name"], "start_date": start_date, "end_date": end_date}, values=_json_number({"revenue": result["revenue"], "order_count": result["order_count"]}), summary="商品名称通过 products 表规范化匹配，查询使用商品 JOIN。")
        else:
            result = get_recent_average_order_value(connection, start_date, end_date)
            if result["direction"] == "insufficient_data":
                return AssistantResponse(status="needs_clarification", answer="当前范围不足以比较两个完整的 7 天客单价窗口，或其中一个窗口没有订单。请扩大日期范围。", intent="recent_average_order_value", provider=provider_info)
            direction = {"up": "上涨", "down": "下跌", "flat": "持平"}[result["direction"]]
            answer = f"最近 7 天（{result['recent']['start_date']} 至 {result['recent']['end_date']}）客单价为 {_display_money(result['recent']['average_order_value'])}；此前 7 天（{result['previous']['start_date']} 至 {result['previous']['end_date']}）为 {_display_money(result['previous']['average_order_value'])}，整体{direction} {_display_money(abs(result['difference']))}。"
            evidence = Evidence(metric="average_order_value", filters=result["filters"], values=_json_number({"recent": result["recent"], "previous": result["previous"], "difference": result["difference"], "change_percent": result["change_percent"], "direction": result["direction"]}), summary="两个窗口均按净营业额除以去重订单数计算。")
        return AssistantResponse(status="answered", answer=answer, intent=_intent_for_name(plan.name), tool_call=ToolCall(name=plan.name, arguments={**plan.arguments, "start_date": start_date, "end_date": end_date}), evidence=evidence, provider=provider_info)
    except (ValueError, sqlite3.Error, KeyError, TypeError) as exc:
        raise ProviderError("unsafe tool execution") from exc
