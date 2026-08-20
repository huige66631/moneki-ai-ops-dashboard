from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from app.ai.contracts import Intent


@dataclass
class ConversationState:
    session_id: str
    last_successful_intent: Intent | None = None
    last_tool_name: str | None = None
    last_tool_arguments: dict[str, Any] | None = None
    updated_at: datetime | None = None
    expires_at: datetime | None = None


class ConversationStore:
    """Short-lived, process-local context for verified assistant turns."""

    def __init__(self, capacity: int = 100, ttl: timedelta = timedelta(minutes=30)) -> None:
        self.capacity = capacity
        self.ttl = ttl
        self._states: OrderedDict[str, ConversationState] = OrderedDict()
        self._lock = Lock()

    @staticmethod
    def _now(now: datetime | None) -> datetime:
        return now or datetime.now(timezone.utc)

    def _remove_expired(self, now: datetime) -> None:
        expired = [session_id for session_id, state in self._states.items() if state.expires_at and state.expires_at <= now]
        for session_id in expired:
            self._states.pop(session_id, None)

    def _refresh(self, state: ConversationState, now: datetime) -> ConversationState:
        state.updated_at = now
        state.expires_at = now + self.ttl
        self._states.move_to_end(state.session_id)
        return state

    def touch(self, session_id: str, now: datetime | None = None) -> ConversationState | None:
        current = self._now(now)
        with self._lock:
            self._remove_expired(current)
            state = self._states.get(session_id)
            return self._refresh(state, current) if state else None

    def get_or_create(self, session_id: str | None, now: datetime | None = None) -> ConversationState:
        current = self._now(now)
        with self._lock:
            self._remove_expired(current)
            state = self._states.get(session_id) if session_id else None
            if state:
                return self._refresh(state, current)
            while len(self._states) >= self.capacity:
                self._states.popitem(last=False)
            state = ConversationState(session_id=str(uuid4()))
            self._states[state.session_id] = state
            return self._refresh(state, current)

    def record_answered(
        self,
        session_id: str,
        intent: Intent,
        tool_name: str,
        arguments: dict[str, Any],
        now: datetime | None = None,
    ) -> ConversationState:
        current = self._now(now)
        with self._lock:
            self._remove_expired(current)
            state = self._states.get(session_id)
            if state is None:
                while len(self._states) >= self.capacity:
                    self._states.popitem(last=False)
                state = ConversationState(session_id=session_id)
                self._states[session_id] = state
            state.last_successful_intent = intent
            state.last_tool_name = tool_name
            state.last_tool_arguments = dict(arguments)
            return self._refresh(state, current)
