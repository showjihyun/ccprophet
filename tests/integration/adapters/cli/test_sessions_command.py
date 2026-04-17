from __future__ import annotations

import json

from ccprophet.adapters.cli.sessions import run_sessions_command
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from tests.fixtures.builders import SessionBuilder


def test_sessions_command_empty_returns_1(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    code = run_sessions_command(repos.sessions)
    assert code == 1


def test_sessions_latest_id_only(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-old").build())
    repos.sessions.upsert(SessionBuilder().with_id("s-new").build())
    code = run_sessions_command(repos.sessions, latest=True, id_only=True)
    captured = capsys.readouterr()
    assert code == 0
    printed = captured.out.strip()
    assert printed in {"s-old", "s-new"}


def test_sessions_json_output(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-1").build())
    code = run_sessions_command(repos.sessions, as_json=True)
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload[0]["session_id"] == "s-1"
    assert payload[0]["project_slug"] == "test-project"
