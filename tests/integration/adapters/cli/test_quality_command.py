from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ccprophet.adapters.cli.quality import run_quality_command
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import TokenCount
from ccprophet.use_cases.assess_quality import AssessQualityUseCase
from tests.fixtures.builders import SessionBuilder


NOW = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)


def _wire(days: int, baseline_output: int, recent_output: int):  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    for d in range(days):
        day_back = days - d - 1
        output = recent_output if day_back < 2 else baseline_output
        session = replace(
            SessionBuilder().with_id(f"s-{d}").build(),
            model="claude-opus-4-7",
            started_at=NOW - timedelta(days=day_back, hours=1),
            total_output_tokens=TokenCount(output),
            total_input_tokens=TokenCount(output * 4),
        )
        repos.sessions.upsert(session)
    return AssessQualityUseCase(
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        outcomes=repos.outcomes,
        clock=FrozenClock(NOW),
    )


def test_regression_detected_returns_1(capsys) -> None:  # type: ignore[no-untyped-def]
    uc = _wire(days=10, baseline_output=2000, recent_output=200)
    code = run_quality_command(
        uc, window_days=2, baseline_days=8, threshold_sigma=1.0, as_json=True
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload[0]["has_regression"] is True
    metrics = {flag["metric"] for flag in payload[0]["flags"]}
    assert "avg_output_tokens" in metrics


def test_stable_returns_0(capsys) -> None:  # type: ignore[no-untyped-def]
    uc = _wire(days=10, baseline_output=1000, recent_output=1000)
    code = run_quality_command(
        uc, window_days=2, baseline_days=8, threshold_sigma=2.0, as_json=True
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload[0]["has_regression"] is False
