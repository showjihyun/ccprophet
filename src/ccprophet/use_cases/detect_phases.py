from __future__ import annotations

from dataclasses import dataclass

from ccprophet.domain.entities import Phase
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.services.phase import PhaseDetector
from ccprophet.domain.values import SessionId
from ccprophet.ports.repositories import (
    EventRepository,
    PhaseRepository,
    SessionRepository,
)


@dataclass(frozen=True)
class DetectPhasesUseCase:
    sessions: SessionRepository
    events: EventRepository
    phases: PhaseRepository

    def execute(self, session_id: SessionId) -> list[Phase]:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        evs = list(self.events.list_by_session(session_id))
        detected = PhaseDetector.detect(evs)
        self.phases.replace_for_session(session_id, detected)
        return detected

    def execute_current(self) -> list[Phase]:
        session = self.sessions.latest_active()
        if session is None:
            raise SessionNotFound(SessionId("(no active session)"))
        return self.execute(session.session_id)
