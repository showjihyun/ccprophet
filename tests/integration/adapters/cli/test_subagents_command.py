from __future__ import annotations

import json
from datetime import datetime, timezone

from ccprophet.adapters.cli.subagents import run_subagents_command
from ccprophet.adapters.persistence.inmemory.repositories import (
    InMemoryRepositorySet,
)
from ccprophet.domain.entities import Subagent
from ccprophet.domain.values import SessionId, TokenCount
from ccprophet.use_cases.list_subagents import ListSubagentsUseCase
from tests.fixtures.builders import SessionBuilder


def _sub(sid: str, parent: str) -> Subagent:
    return Subagent(
        subagent_id=SessionId(sid),
        parent_session_id=SessionId(parent),
        started_at=datetime(2026, 4, 17, 9, 0, 0, tzinfo=timezone.utc),
        agent_type="Task",
        context_tokens=TokenCount(0),
        tool_call_count=2,
    )


def test_subagents_json_for_explicit_session(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("p1").build())
    repos.subagents.upsert(_sub("a", "p1"))
    repos.subagents.upsert(_sub("b", "p1"))

    uc = ListSubagentsUseCase(subagents=repos.subagents)
    code = run_subagents_command(uc, repos.sessions, session="p1", as_json=True)
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert code == 0
    assert payload["parent_session_id"] == "p1"
    assert {s["subagent_id"] for s in payload["subagents"]} == {"a", "b"}


def test_subagents_defaults_to_latest_when_no_session(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("latest").build())
    repos.subagents.upsert(_sub("sub-x", "latest"))

    uc = ListSubagentsUseCase(subagents=repos.subagents)
    code = run_subagents_command(uc, repos.sessions, as_json=True)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["parent_session_id"] == "latest"
    assert payload["subagents"][0]["subagent_id"] == "sub-x"


def test_subagents_empty_session_json(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("solo").build())

    uc = ListSubagentsUseCase(subagents=repos.subagents)
    code = run_subagents_command(uc, repos.sessions, as_json=True)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["subagents"] == []


def test_subagents_no_session_at_all_returns_1(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    uc = ListSubagentsUseCase(subagents=repos.subagents)
    code = run_subagents_command(uc, repos.sessions, as_json=True)
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["parent_session_id"] is None
