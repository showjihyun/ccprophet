from __future__ import annotations

import json
from datetime import datetime, timezone

from ccprophet.adapters.cli.mark import run_mark_command
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import OutcomeLabelValue, SessionId
from ccprophet.use_cases.mark_outcome import MarkOutcomeUseCase
from tests.fixtures.builders import SessionBuilder


def _wire():  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("s-1").build())
    uc = MarkOutcomeUseCase(
        sessions=repos.sessions,
        outcomes=repos.outcomes,
        clock=FrozenClock(datetime(2026, 4, 17, tzinfo=timezone.utc)),
    )
    return repos, uc


def test_mark_success_json(capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc = _wire()
    code = run_mark_command(
        uc, session_id="s-1", outcome="success", task_type="refactor", as_json=True
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["label"] == "success"
    assert payload["task_type"] == "refactor"


def test_mark_invalid_outcome_returns_2(capsys) -> None:  # type: ignore[no-untyped-def]
    _, uc = _wire()
    code = run_mark_command(uc, session_id="s-1", outcome="nope", as_json=True)
    assert code == 2


def test_mark_unknown_session_returns_2(capsys) -> None:  # type: ignore[no-untyped-def]
    _, uc = _wire()
    code = run_mark_command(
        uc, session_id="missing", outcome="success", as_json=True
    )
    assert code == 2
