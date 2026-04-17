from __future__ import annotations

from datetime import datetime, timezone

from ccprophet.adapters.persistence.inmemory.repositories import (
    InMemoryRepositorySet,
)
from ccprophet.domain.entities import Subagent
from ccprophet.domain.values import SessionId, TokenCount
from ccprophet.use_cases.list_subagents import ListSubagentsUseCase


def _sub(sid: str, parent: str, started_h: int) -> Subagent:
    return Subagent(
        subagent_id=SessionId(sid),
        parent_session_id=SessionId(parent),
        started_at=datetime(2026, 4, 17, started_h, 0, 0, tzinfo=timezone.utc),
        agent_type="Task",
        context_tokens=TokenCount(0),
    )


def test_returns_only_subagents_of_given_parent() -> None:
    repos = InMemoryRepositorySet()
    repos.subagents.upsert(_sub("a", "parent-1", 9))
    repos.subagents.upsert(_sub("b", "parent-2", 10))
    repos.subagents.upsert(_sub("c", "parent-1", 11))

    uc = ListSubagentsUseCase(subagents=repos.subagents)
    result = list(uc.execute_for_parent(SessionId("parent-1")))

    assert [s.subagent_id.value for s in result] == ["a", "c"]


def test_returns_empty_list_for_unknown_parent() -> None:
    repos = InMemoryRepositorySet()
    uc = ListSubagentsUseCase(subagents=repos.subagents)
    assert list(uc.execute_for_parent(SessionId("none"))) == []
