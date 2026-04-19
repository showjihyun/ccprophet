from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ccprophet.domain.values import SessionId
from tests.fixtures.builders import SubagentBuilder


class SubagentRepositoryContract(ABC):
    @pytest.fixture
    @abstractmethod
    def repository(self):  # type: ignore[no-untyped-def]
        ...

    def test_upsert_roundtrip(self, repository) -> None:  # type: ignore[no-untyped-def]
        sub = SubagentBuilder().with_id("sub-A").with_parent("parent-1").build()
        repository.upsert(sub)

        got = repository.get(SessionId("sub-A"))
        assert got is not None
        assert got.subagent_id == SessionId("sub-A")
        assert got.parent_session_id == SessionId("parent-1")
        assert got.agent_type == "Task"

    def test_get_unknown_returns_none(self, repository) -> None:  # type: ignore[no-untyped-def]
        assert repository.get(SessionId("does-not-exist")) is None

    def test_list_for_parent_filters_and_orders(self, repository) -> None:  # type: ignore[no-untyped-def]
        early = datetime(2026, 4, 17, 9, 0, 0, tzinfo=timezone.utc)
        late = datetime(2026, 4, 17, 9, 5, 0, tzinfo=timezone.utc)
        repository.upsert(
            SubagentBuilder().with_id("sub-late").with_parent("p1").started(late).build()
        )
        repository.upsert(
            SubagentBuilder().with_id("sub-early").with_parent("p1").started(early).build()
        )
        repository.upsert(SubagentBuilder().with_id("sub-other").with_parent("p2").build())

        listed = list(repository.list_for_parent(SessionId("p1")))
        assert [s.subagent_id.value for s in listed] == ["sub-early", "sub-late"]

        other = list(repository.list_for_parent(SessionId("p2")))
        assert [s.subagent_id.value for s in other] == ["sub-other"]

        empty = list(repository.list_for_parent(SessionId("nope")))
        assert empty == []

    def test_upsert_updates_ended_at_idempotently(self, repository) -> None:  # type: ignore[no-untyped-def]
        start = datetime(2026, 4, 17, 9, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 4, 17, 9, 10, 0, tzinfo=timezone.utc)
        original = (
            SubagentBuilder().with_id("sub-end").with_parent("parent-1").started(start).build()
        )
        repository.upsert(original)
        repository.upsert(replace(original, ended_at=end, tool_call_count=5))
        # Second idempotent upsert with the same ended values must not change
        # state.
        repository.upsert(replace(original, ended_at=end, tool_call_count=5))

        got = repository.get(SessionId("sub-end"))
        assert got is not None
        assert got.ended_at is not None
        assert got.tool_call_count == 5


class TestInMemorySubagentRepository(SubagentRepositoryContract):
    @pytest.fixture
    def repository(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import (
            InMemorySubagentRepository,
        )

        return InMemorySubagentRepository()
