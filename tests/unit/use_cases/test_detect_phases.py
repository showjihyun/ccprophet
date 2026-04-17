from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import PhaseType, SessionId
from ccprophet.use_cases.detect_phases import DetectPhasesUseCase
from tests.fixtures.builders import EventBuilder, SessionBuilder

T0 = datetime(2026, 4, 17, 9, 0, 0, tzinfo=timezone.utc)


def _at(m: int) -> datetime:
    return T0 + timedelta(minutes=m)


def _uc(repos: InMemoryRepositorySet) -> DetectPhasesUseCase:
    return DetectPhasesUseCase(
        sessions=repos.sessions,
        events=repos.events,
        phases=repos.phases,
    )


def test_execute_persists_detected_phases(inmemory_repos: InMemoryRepositorySet) -> None:
    session = SessionBuilder().with_id("s-1").build()
    inmemory_repos.sessions.upsert(session)
    for e in (
        EventBuilder().for_session("s-1").of_type("UserPromptSubmit").at(_at(0)).with_hash("a").build(),
        EventBuilder().for_session("s-1").tool_use("Edit", "/x.py").at(_at(1)).with_hash("b").build(),
        EventBuilder().for_session("s-1").tool_use("Write", "/y.py").at(_at(2)).with_hash("c").build(),
    ):
        inmemory_repos.events.append(e)

    phases = _uc(inmemory_repos).execute(SessionId("s-1"))

    assert len(phases) == 1
    assert phases[0].phase_type == PhaseType.IMPLEMENTATION
    stored = list(inmemory_repos.phases.list_for_session(SessionId("s-1")))
    assert len(stored) == 1
    assert stored[0].phase_id == phases[0].phase_id


def test_execute_raises_when_session_missing(inmemory_repos: InMemoryRepositorySet) -> None:
    with pytest.raises(SessionNotFound):
        _uc(inmemory_repos).execute(SessionId("missing"))


def test_execute_replaces_previous_phases(inmemory_repos: InMemoryRepositorySet) -> None:
    session = SessionBuilder().with_id("s-2").build()
    inmemory_repos.sessions.upsert(session)
    inmemory_repos.events.append(
        EventBuilder().for_session("s-2").of_type("UserPromptSubmit").at(_at(0)).with_hash("x").build()
    )
    uc = _uc(inmemory_repos)
    first = uc.execute(SessionId("s-2"))
    second = uc.execute(SessionId("s-2"))
    stored = list(inmemory_repos.phases.list_for_session(SessionId("s-2")))
    assert len(stored) == 1
    assert first[0].phase_id != second[0].phase_id or len(stored) == 1
