from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import TokenCount
from ccprophet.use_cases.assess_quality import AssessQualityUseCase
from tests.fixtures.builders import SessionBuilder

NOW = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)


def _uc(repos: InMemoryRepositorySet) -> AssessQualityUseCase:
    return AssessQualityUseCase(
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        outcomes=repos.outcomes,
        clock=FrozenClock(NOW),
    )


def _seed_over_days(
    repos: InMemoryRepositorySet,
    days: int,
    baseline_output: int,
    recent_output: int,
    recent_window: int = 2,
) -> None:
    for d in range(days):
        day_back = days - d - 1
        started_at = NOW - timedelta(days=day_back, hours=1)
        output = recent_output if day_back < recent_window else baseline_output
        session = replace(
            SessionBuilder().with_id(f"s-{d}").build(),
            model="claude-opus-4-7",
            started_at=started_at,
            total_input_tokens=TokenCount(output * 4),
            total_output_tokens=TokenCount(output),
        )
        repos.sessions.upsert(session)


def test_returns_reports_per_model() -> None:
    repos = InMemoryRepositorySet()
    _seed_over_days(repos, days=10, baseline_output=1000, recent_output=200, recent_window=2)
    reports = _uc(repos).execute(window_days=2, baseline_days=8, threshold_sigma=1.5)
    assert len(reports) == 1
    r = reports[0]
    assert r.model == "claude-opus-4-7"
    metric_names = {f.metric_name for f in r.flags}
    assert "avg_output_tokens" in metric_names


def test_filters_by_model() -> None:
    repos = InMemoryRepositorySet()
    _seed_over_days(repos, days=5, baseline_output=1000, recent_output=1000)
    other = replace(
        SessionBuilder().with_id("other").build(),
        model="claude-haiku-4-5",
        started_at=NOW - timedelta(hours=3),
    )
    repos.sessions.upsert(other)

    reports = _uc(repos).execute(model="claude-haiku-4-5")
    assert len(reports) == 1
    assert reports[0].model == "claude-haiku-4-5"


def test_no_sessions_returns_empty() -> None:
    repos = InMemoryRepositorySet()
    reports = _uc(repos).execute()
    assert reports == []
