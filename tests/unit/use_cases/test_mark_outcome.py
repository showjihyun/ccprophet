from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import OutcomeLabelValue, SessionId, TaskType
from ccprophet.use_cases.mark_outcome import MarkOutcomeUseCase
from tests.fixtures.builders import SessionBuilder

FROZEN = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)


def _uc(repos: InMemoryRepositorySet) -> MarkOutcomeUseCase:
    return MarkOutcomeUseCase(
        sessions=repos.sessions,
        outcomes=repos.outcomes,
        clock=FrozenClock(FROZEN),
    )


def test_labels_a_known_session() -> None:
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-1").build())
    uc = _uc(repos)

    label = uc.execute(
        SessionId("s-1"),
        OutcomeLabelValue.SUCCESS,
        task_type=TaskType("refactor"),
        reason="clean run",
    )
    assert label.label == OutcomeLabelValue.SUCCESS
    assert label.task_type == TaskType("refactor")
    assert label.labeled_at == FROZEN

    got = repos.outcomes.get_label(SessionId("s-1"))
    assert got is not None and got.label == OutcomeLabelValue.SUCCESS


def test_unknown_session_raises() -> None:
    repos = InMemoryRepositorySet()
    with pytest.raises(SessionNotFound):
        _uc(repos).execute(SessionId("nope"), OutcomeLabelValue.FAIL)


def test_overwrites_previous_label() -> None:
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-2").build())
    uc = _uc(repos)
    uc.execute(SessionId("s-2"), OutcomeLabelValue.PARTIAL)
    uc.execute(
        SessionId("s-2"),
        OutcomeLabelValue.SUCCESS,
        task_type=TaskType("bugfix"),
    )
    got = repos.outcomes.get_label(SessionId("s-2"))
    assert got is not None
    assert got.label == OutcomeLabelValue.SUCCESS
    assert got.task_type == TaskType("bugfix")
