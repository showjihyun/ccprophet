from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ccprophet.adapters.cli.live import run_live_command
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
from ccprophet.use_cases.detect_phases import DetectPhasesUseCase
from tests.fixtures.builders import EventBuilder, SessionBuilder


def _use_cases(repos: InMemoryRepositorySet):  # type: ignore[no-untyped-def]
    detect = DetectPhasesUseCase(
        sessions=repos.sessions,
        events=repos.events,
        phases=repos.phases,
    )
    analyze = AnalyzeBloatUseCase(
        sessions=repos.sessions,
        tool_defs=repos.tool_defs,
        tool_calls=repos.tool_calls,
    )
    return detect, analyze


def test_live_no_session_returns_2(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    detect, analyze = _use_cases(repos)
    code = run_live_command(detect, analyze, as_json=True)
    assert code == 2


def test_live_renders_phases(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    session = SessionBuilder().with_id("s-live").build()
    repos.sessions.upsert(session)
    t0 = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
    for i, ev in enumerate((
        EventBuilder().for_session("s-live").of_type("UserPromptSubmit")
            .at(t0).with_hash("a").build(),
        EventBuilder().for_session("s-live").tool_use("Edit", "/x.py")
            .at(t0 + timedelta(minutes=1)).with_hash("b").build(),
        EventBuilder().for_session("s-live").tool_use("Write", "/y.py")
            .at(t0 + timedelta(minutes=2)).with_hash("c").build(),
    )):
        repos.events.append(ev)

    detect, analyze = _use_cases(repos)
    code = run_live_command(detect, analyze, as_json=True)
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["session"]["session_id"] == "s-live"
    assert payload["phases"][0]["phase_type"] == "implementation"
