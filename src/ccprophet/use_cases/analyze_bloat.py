from __future__ import annotations

from dataclasses import dataclass

from ccprophet.domain.entities import BloatReport
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.services.bloat import BloatCalculator
from ccprophet.domain.values import SessionId
from ccprophet.ports.repositories import (
    SessionRepository,
    ToolCallRepository,
    ToolDefRepository,
)


@dataclass(frozen=True)
class AnalyzeBloatUseCase:
    sessions: SessionRepository
    tool_defs: ToolDefRepository
    tool_calls: ToolCallRepository

    def execute(self, session_id: SessionId) -> BloatReport:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        loaded = list(self.tool_defs.list_for_session(session_id))
        called = list(self.tool_calls.list_for_session(session_id))
        return BloatCalculator.calculate(loaded, called)

    def execute_current(self) -> BloatReport:
        session = self.sessions.latest_active()
        if session is None:
            raise SessionNotFound(SessionId("(no active session)"))
        return self.execute(session.session_id)
