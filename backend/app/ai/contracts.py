from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Intent = Literal["category_store_revenue", "product_revenue", "recent_average_order_value"]
AnswerStatus = Literal["answered", "unsupported", "needs_clarification", "error"]


class AskContext(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def valid_range(self) -> "AskContext":
        if self.start_date > self.end_date:
            raise ValueError("context.start_date 不能晚于 context.end_date。")
        return self


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    context: AskContext | None = None
    session_id: UUID | None = None

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question 不能为空。")
        return value


class ToolCallPlan(BaseModel):
    status: Literal["tool_call", "unsupported", "needs_clarification"]
    intent: Intent | None = None
    name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]


class Evidence(BaseModel):
    metric: str
    unit: str = "CNY"
    filters: dict[str, Any]
    values: dict[str, Any]
    summary: str


class ProviderInfo(BaseModel):
    name: str
    mode: Literal["mock", "live"]


class Navigation(BaseModel):
    start_date: date
    end_date: date
    store_id: str | None = None
    reason: Literal["answer_query_range"] = "answer_query_range"


class AssistantResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: AnswerStatus
    answer: str
    intent: Intent | None = None
    session_id: UUID
    tool_call: ToolCall | None = None
    evidence: Evidence | None = None
    navigation: Navigation | None = None
    provider: ProviderInfo
