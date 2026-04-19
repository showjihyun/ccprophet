from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

from ccprophet.adapters.cli.mark import run_mark_auto_command, run_mark_command
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import OutcomeLabelValue, SessionId
from ccprophet.use_cases.auto_label_sessions import AutoLabelSessionsUseCase
from ccprophet.use_cases.mark_outcome import MarkOutcomeUseCase
from tests.fixtures.builders import SessionBuilder, ToolCallBuilder


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
    _repos, uc = _wire()
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


def _wire_auto() -> tuple[InMemoryRepositorySet, AutoLabelSessionsUseCase]:
    frozen = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
    repos = InMemoryRepositorySet()
    session = SessionBuilder().with_id("s-auto").ended(frozen.replace(hour=10)).build()
    session = replace(session, started_at=frozen.replace(hour=9))
    repos.sessions.upsert(session)
    for _ in range(6):
        tc = ToolCallBuilder().in_session(SessionId("s-auto")).for_tool("Bash").build()
        repos.tool_calls.append(tc)
    uc = AutoLabelSessionsUseCase(
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        outcomes=repos.outcomes,
        clock=FrozenClock(frozen),
    )
    return repos, uc


def test_mark_auto_json_reports_labels(capsys) -> None:  # type: ignore[no-untyped-def]
    _repos, uc = _wire_auto()
    code = run_mark_auto_command(uc, lookback_days=30, dry_run=False, as_json=True)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["considered"] == 1
    assert payload["labeled_success"] == 1
    assert payload["dry_run"] is False
    assert payload["applied_session_ids"] == ["s-auto"]


def test_mark_auto_dry_run_does_not_persist(capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc = _wire_auto()
    code = run_mark_auto_command(uc, lookback_days=30, dry_run=True, as_json=True)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["labeled_success"] == 1
    # Not persisted
    assert repos.outcomes.get_label(SessionId("s-auto")) is None
    _ = OutcomeLabelValue.SUCCESS  # import check
