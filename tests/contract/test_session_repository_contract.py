from __future__ import annotations

from abc import ABC, abstractmethod

import pytest

from ccprophet.domain.values import SessionId
from tests.fixtures.builders import SessionBuilder


class SessionRepositoryContract(ABC):
    @pytest.fixture
    @abstractmethod
    def repository(self):  # type: ignore[no-untyped-def]
        ...

    def test_upsert_then_get(self, repository) -> None:  # type: ignore[no-untyped-def]
        session = SessionBuilder().with_id("s1").build()
        repository.upsert(session)
        got = repository.get(SessionId("s1"))
        assert got is not None
        assert got.session_id == SessionId("s1")

    def test_get_unknown_returns_none(self, repository) -> None:  # type: ignore[no-untyped-def]
        assert repository.get(SessionId("nope")) is None

    def test_latest_active_returns_most_recent(self, repository) -> None:  # type: ignore[no-untyped-def]
        s1 = SessionBuilder().with_id("s1").build()
        s2 = SessionBuilder().with_id("s2").build()
        repository.upsert(s1)
        repository.upsert(s2)
        latest = repository.latest_active()
        assert latest is not None

    def test_latest_active_returns_none_when_empty(self, repository) -> None:  # type: ignore[no-untyped-def]
        assert repository.latest_active() is None


class TestInMemorySessionRepository(SessionRepositoryContract):
    @pytest.fixture
    def repository(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import InMemorySessionRepository
        return InMemorySessionRepository()
