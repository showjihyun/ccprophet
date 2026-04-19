"""Auto-label finished sessions based on heuristic signals.

Skips any session that already has an OutcomeLabel — manual labels win. The
classifier returns `None` for ambiguous sessions; we leave those unlabeled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from ccprophet.domain.entities import OutcomeLabel
from ccprophet.domain.services.auto_label import classify
from ccprophet.domain.values import OutcomeLabelValue
from ccprophet.ports.clock import Clock
from ccprophet.ports.outcomes import OutcomeRepository
from ccprophet.ports.repositories import (
    SessionRepository,
    ToolCallRepository,
)

DEFAULT_LOOKBACK_DAYS = 30


@dataclass(frozen=True, slots=True)
class AutoLabelSummary:
    considered: int = 0
    labeled_success: int = 0
    labeled_fail: int = 0
    skipped_active: int = 0
    skipped_already_labeled: int = 0
    skipped_ambiguous: int = 0
    applied_session_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AutoLabelSessionsUseCase:
    sessions: SessionRepository
    tool_calls: ToolCallRepository
    outcomes: OutcomeRepository
    clock: Clock

    def execute(
        self,
        *,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        dry_run: bool = False,
    ) -> AutoLabelSummary:
        now = self.clock.now()
        start = now - timedelta(days=lookback_days)
        recent = list(self.sessions.list_in_range(start, now))

        considered = 0
        success = 0
        fail = 0
        skipped_active = 0
        skipped_labeled = 0
        skipped_ambiguous = 0
        applied: list[str] = []

        for session in recent:
            considered += 1
            if session.is_active:
                skipped_active += 1
                continue
            if self.outcomes.get_label(session.session_id) is not None:
                skipped_labeled += 1
                continue

            calls = list(self.tool_calls.list_for_session(session.session_id))
            label = classify(session, calls)
            if label is None:
                skipped_ambiguous += 1
                continue

            if label is OutcomeLabelValue.SUCCESS:
                success += 1
            elif label is OutcomeLabelValue.FAIL:
                fail += 1

            applied.append(session.session_id.value)
            if not dry_run:
                self.outcomes.set_label(
                    OutcomeLabel(
                        session_id=session.session_id,
                        label=label,
                        task_type=None,
                        source="auto",
                        reason=None,
                        labeled_at=now,
                    )
                )

        return AutoLabelSummary(
            considered=considered,
            labeled_success=success,
            labeled_fail=fail,
            skipped_active=skipped_active,
            skipped_already_labeled=skipped_labeled,
            skipped_ambiguous=skipped_ambiguous,
            applied_session_ids=tuple(applied),
        )
