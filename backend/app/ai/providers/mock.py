from __future__ import annotations

import re
from datetime import date

from app.ai.contracts import ToolCallPlan
from app.ai.providers.base import Provider
from app.ai.tools.resolver import parse_date_range


class MockProvider:
    name = "mock"
    mode = "mock"

    def plan(self, question: str, context: tuple[date, date] | None, bounds: tuple[date, date]) -> ToolCallPlan:
        text = question.casefold()
        date_range = parse_date_range(question, bounds) or context or bounds
        dates = {"start_date": date_range[0].isoformat(), "end_date": date_range[1].isoformat()}
        if any(token in text for token in ("哪个品类", "品类", "门店营业额", "门店类别")):
            return ToolCallPlan(status="tool_call", intent="category_store_revenue", name="get_category_store_revenue", arguments=dates)
        if any(token in text for token in ("客单价", "涨了", "跌了", "趋势")):
            return ToolCallPlan(status="tool_call", intent="recent_average_order_value", name="get_recent_average_order_value", arguments=dates)
        if any(token in text for token in ("卖了多少钱", "营业额", "销售额", "卖了多少")):
            product_name = question
            product_name = re.sub(r"20\d{2}\s*[年/-]\s*\d{1,2}\s*[月/-]\s*\d{1,2}\s*[日号]?", "", product_name)
            product_name = re.sub(r"20\d{2}\s*[年/-]\s*\d{1,2}\s*月", "", product_name)
            product_name = re.sub(r"20\d{2}\s*[年/-]\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*[日号])?", "", product_name)
            product_name = re.sub(r"\d{1,2}\s*月(?:\s*\d{1,2}\s*[日号])?", "", product_name)
            product_name = re.sub(r"(?:十[一二]?|[一二三四五六七八九])月", "", product_name)
            product_name = re.sub(r"卖了多少钱|营业额|销售额|卖了多少|多少订单|至|到|期间|日期", "", product_name)
            product_name = product_name.strip(" ，,：:？?。")
            if not product_name:
                return ToolCallPlan(status="needs_clarification", intent="product_revenue", message="请提供要查询的商品名称。")
            return ToolCallPlan(status="tool_call", intent="product_revenue", name="get_product_revenue", arguments={"product_name": product_name, **dates})
        return ToolCallPlan(status="unsupported", message="我只能回答销售流水、门店、商品、营业额、订单数和客单价相关问题。")
