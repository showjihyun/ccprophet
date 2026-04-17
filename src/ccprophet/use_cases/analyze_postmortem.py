from __future__ import annotations

from dataclasses import dataclass

from ccprophet.domain.entities import PostmortemReport
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.services.postmortem import (
    PostmortemAnalyzer,
    PostmortemInputs,
)
from ccprophet.domain.values import OutcomeLabelValue, SessionId
from ccprophet.ports.outcomes import OutcomeRepository
from ccprophet.ports.repositories import (
    SessionRepository,
    ToolCallRepository,
    ToolDefRepository,
)


@dataclass(frozen=True)
class AnalyzePostmortemUseCase:
    sessions: SessionRepository
    outcomes: OutcomeRepository
    tool_calls: ToolCallRepository
    tool_defs: ToolDefRepository

    def execute(self, session_id: SessionId) -> PostmortemReport:
        failed = self.sessions.get(session_id)
        if failed is None:
            raise SessionNotFound(session_id)

        failed_label = self.outcomes.get_label(session_id)
        task_type = failed_label.task_type if failed_label else None

        success_sessions = (
            list(self.outcomes.list_sessions_by_label(
                OutcomeLabelValue.SUCCESS, task_type
            ))
            if task_type is not None
            else []
        )

        return PostmortemAnalyzer.analyze(
            PostmortemInputs(
                failed_session=failed,
                task_type=task_type,
                failed_tool_calls=list(self.tool_calls.list_for_session(session_id)),
                failed_tool_defs=list(self.tool_defs.list_for_session(session_id)),
                success_sessions=success_sessions,
                success_tool_calls={
                    s.session_id.value: list(
                        self.tool_calls.list_for_session(s.session_id)
                    )
                    for s in success_sessions
                },
                success_tool_defs={
                    s.session_id.value: list(
                        self.tool_defs.list_for_session(s.session_id)
                    )
                    for s in success_sessions
                },
            )
        )
