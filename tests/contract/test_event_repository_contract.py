from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

import pytest

from ccprophet.domain.values import SessionId
from tests.fixtures.builders import EventBuilder


class EventRepositoryContract(ABC):
    @pytest.fixture
    @abstractmethod
    def repository(self):  # type: ignore[no-untyped-def]
        ...

    def test_append_then_list_returns_event(self, repository) -> None:  # type: ignore[no-untyped-def]
        event = EventBuilder().for_session("s1").build()
        repository.append(event)
        events = list(repository.list_by_session(SessionId("s1")))
        assert len(events) == 1
        assert events[0].event_id == event.event_id

    def test_dedup_hash_detected(self, repository) -> None:  # type: ignore[no-untyped-def]
        event = EventBuilder().with_hash("unique-hash-1").build()
        repository.append(event)
        assert repository.dedup_hash_exists(event.raw_hash) is True

    def test_dedup_prevents_double_insert(self, repository) -> None:  # type: ignore[no-untyped-def]
        e1 = EventBuilder().with_hash("same-hash").build()
        e2 = EventBuilder().with_hash("same-hash").build()
        repository.append(e1)
        repository.append(e2)
        events = list(repository.list_by_session(e1.session_id))
        assert len(events) == 1

    def test_unknown_session_returns_empty(self, repository) -> None:  # type: ignore[no-untyped-def]
        assert list(repository.list_by_session(SessionId("nope"))) == []

    def test_chronological_order(self, repository) -> None:  # type: ignore[no-untyped-def]
        e1 = EventBuilder().for_session("s1").at(datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)).with_hash("h1").build()
        e2 = EventBuilder().for_session("s1").at(datetime(2026, 1, 1, 9, 1, tzinfo=timezone.utc)).with_hash("h2").build()
        repository.append(e2)
        repository.append(e1)
        events = list(repository.list_by_session(SessionId("s1")))
        assert events[0].ts <= events[1].ts


class TestInMemoryEventRepository(EventRepositoryContract):
    @pytest.fixture
    def repository(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import InMemoryEventRepository
        return InMemoryEventRepository()
