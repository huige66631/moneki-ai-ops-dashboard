from __future__ import annotations

from datetime import date

from app.ai.contracts import AskContext, ToolCallPlan
from app.ai.session_store import ConversationState
from app.ai.tools.dashboard_queries import ALLOWED_TOOLS
from app.ai.tools.resolver import parse_date_range


_NEW_INTENT_MARKERS = ("哪个品类", "品类", "门店", "客单价", "涨了", "跌了", "趋势")


def resolve_turn(
    question: str,
    request_context: AskContext | None,
    previous_state: ConversationState | None,
    bounds: tuple[date, date],
) -> ToolCallPlan | None:
    """Resolve only date-replacement follow-ups; let the provider plan every other turn."""
    del request_context
    dates = parse_date_range(question, bounds)
    compact_question = question.strip()
    is_follow_up = (
        dates is not None
        and not any(marker in compact_question.casefold() for marker in _NEW_INTENT_MARKERS)
        and ("那" in compact_question or compact_question.rstrip("？?").endswith("呢"))
    )
    if not is_follow_up:
        return None
    if (
        previous_state is None
        or previous_state.last_successful_intent is None
        or previous_state.last_tool_name not in ALLOWED_TOOLS
        or not previous_state.last_tool_arguments
    ):
        return ToolCallPlan(
            status="needs_clarification",
            message="请先说明要查询的商品、门店品类或指标，再指定日期范围。",
        )
    arguments = dict(previous_state.last_tool_arguments)
    arguments["start_date"], arguments["end_date"] = dates
    return ToolCallPlan(
        status="tool_call",
        intent=previous_state.last_successful_intent,
        name=previous_state.last_tool_name,
        arguments=arguments,
    )
