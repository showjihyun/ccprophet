from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import (
    InMemoryRepositorySet,
)
from ccprophet.domain.entities import OutcomeLabel
from ccprophet.domain.values import OutcomeLabelValue, SessionId
from ccprophet.use_cases.auto_label_sessions import AutoLabelSessionsUseCase
from tests.fixtures.builders import SessionBuilder, ToolCallBuilder

NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _wire() -> tuple[InMemoryRepositorySet, AutoLabelSessionsUseCase]:
    repos = InMemoryRepositorySet()
    uc = AutoLabelSessionsUseCase(
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        outcomes=repos.outcomes,
        clock=FrozenClock(NOW),
    )
    return repos, uc


def _seed_finished(
    repos: InMemoryRepositorySet,
    sid: str,
    *,
    success_ratio: float = 1.0,
    calls: int = 8,
    compacted: bool = False,
) -> None:
    session = (
        SessionBuilder()
        .with_id(sid)
        .ended(NOW.replace(hour=10))
        .build()
    )
    session = replace(
        session,
        started_at=NOW.replace(hour=9),
        compacted=compacted,
    )
    repos.sessions.upsert(session)
    successes = int(calls * success_ratio)
    for i in range(calls):
        tc = ToolCallBuilder().in_session(SessionId(sid)).for_tool("Bash").build()
        repos.tool_calls.append(replace(tc, success=(i < successes)))


def test_auto_label_success_session() -> None:
    repos, uc = _wire()
    _seed_finished(repos, "s-win")
    summary = uc.execute()
    assert summary.labeled_success == 1
    assert summary.labeled_fail == 0
    label = repos.outcomes.get_label(SessionId("s-win"))
    assert label is not None
    assert label.label is OutcomeLabelValue.SUCCESS
    assert label.source == "auto"


def test_auto_label_compacted_as_fail() -> None:
    repos, uc = _wire()
    _seed_finished(repos, "s-lose", compacted=True)
    summary = uc.execute()
    assert summary.labeled_fail == 1
    label = repos.outcomes.get_label(SessionId("s-lose"))
    assert label is not None and label.label is OutcomeLabelValue.FAIL


def test_auto_label_skips_already_labeled_sessions() -> None:
    repos, uc = _wire()
    _seed_finished(repos, "s-manual")
    repos.outcomes.set_label(
        OutcomeLabel(
            session_id=SessionId("s-manual"),
            label=OutcomeLabelValue.FAIL,  # pre-existing manual label
            task_type=None,
            source="manual",
            reason=None,
            labeled_at=NOW,
        )
    )
    summary = uc.execute()
    assert summary.skipped_already_labeled == 1
    assert summary.labeled_success == 0
    # manual label preserved
    label = repos.outcomes.get_label(SessionId("s-manual"))
    assert label is not None and label.source == "manual"


def test_dry_run_does_not_persist() -> None:
    repos, uc = _wire()
    _seed_finished(repos, "s-dry")
    summary = uc.execute(dry_run=True)
    assert summary.labeled_success == 1
    assert repos.outcomes.get_label(SessionId("s-dry")) is None
