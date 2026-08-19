from __future__ import annotations

from datetime import date
from typing import Protocol

from app.ai.contracts import ToolCallPlan


class ProviderError(Exception):
    """A provider could not return a safe structured plan."""


class Provider(Protocol):
    name: str
    mode: str

    def plan(self, question: str, context: tuple[date, date] | None, bounds: tuple[date, date]) -> ToolCallPlan:
        ...

