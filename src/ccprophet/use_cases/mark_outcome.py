from __future__ import annotations

from dataclasses import dataclass

from ccprophet.domain.entities import OutcomeLabel
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import OutcomeLabelValue, SessionId, TaskType
from ccprophet.ports.clock import Clock
from ccprophet.ports.outcomes import OutcomeRepository
from ccprophet.ports.repositories import SessionRepository


@dataclass(frozen=True)
class MarkOutcomeUseCase:
    sessions: SessionRepository
    outcomes: OutcomeRepository
    clock: Clock

    def execute(
        self,
        session_id: SessionId,
        label: OutcomeLabelValue,
        *,
        task_type: TaskType | None = None,
        reason: str | None = None,
        source: str = "manual",
    ) -> OutcomeLabel:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)

        outcome = OutcomeLabel(
            session_id=session_id,
            label=label,
            task_type=task_type,
            source=source,
            reason=reason,
            labeled_at=self.clock.now(),
        )
        self.outcomes.set_label(outcome)
        return outcome
