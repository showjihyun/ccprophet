"""Roll up recent sessions into per-model quality series + regression flags."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from ccprophet.domain.entities import RegressionReport
from ccprophet.domain.services.quality import (
    QualityInputs,
    QualityTracker,
    RegressionDetector,
)
from ccprophet.ports.clock import Clock
from ccprophet.ports.outcomes import OutcomeRepository
from ccprophet.ports.repositories import (
    SessionRepository,
    ToolCallRepository,
)


@dataclass(frozen=True)
class AssessQualityUseCase:
    sessions: SessionRepository
    tool_calls: ToolCallRepository
    outcomes: OutcomeRepository
    clock: Clock

    def execute(
        self,
        *,
        model: str | None = None,
        window_days: int = 7,
        baseline_days: int = 30,
        threshold_sigma: float = 2.0,
    ) -> list[RegressionReport]:
        now = self.clock.now()
        start = now - timedelta(days=window_days + baseline_days)
        sessions = list(self.sessions.list_in_range(start, now))
        if model is not None:
            sessions = [s for s in sessions if s.model == model]

        models = sorted({s.model for s in sessions})
        tool_calls_by_session = {
            s.session_id.value: list(
                self.tool_calls.list_for_session(s.session_id)
            )
            for s in sessions
        }
        outcomes_by_session = {}
        for s in sessions:
            label = self.outcomes.get_label(s.session_id)
            if label is not None:
                outcomes_by_session[s.session_id.value] = label

        reports: list[RegressionReport] = []
        for m in models:
            inputs = QualityInputs(
                model=m,
                sessions=[s for s in sessions if s.model == m],
                tool_calls_by_session=tool_calls_by_session,
                outcomes_by_session=outcomes_by_session,
            )
            series = QualityTracker.series_from_sessions(inputs)
            report = RegressionDetector.detect(
                series,
                window_days=window_days,
                baseline_days=baseline_days,
                threshold_sigma=threshold_sigma,
            )
            reports.append(report)
        return reports
