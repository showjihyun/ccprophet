from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import Money, SnapshotId, TokenCount
from ccprophet.use_cases.compute_monthly_cost import ComputeMonthlyCostUseCase
from tests.fixtures.builders import (
    PricingRateBuilder,
    RecommendationBuilder,
    SessionBuilder,
)


def _uc(repos: InMemoryRepositorySet) -> ComputeMonthlyCostUseCase:
    return ComputeMonthlyCostUseCase(
        sessions=repos.sessions,
        recommendations=repos.recommendations,
        pricing=repos.pricing,
    )


def _march(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 3, day, hour, 0, tzinfo=timezone.utc)


def test_empty_month_returns_zero_summary() -> None:
    repos = InMemoryRepositorySet()
    summary = _uc(repos).execute(month_start=_march(1), month_end=_march(31) + timedelta(days=1))
    assert summary.session_count == 0
    assert summary.total_cost == Money.zero()


def test_aggregates_sessions_and_savings() -> None:
    """Uses the current month for applied-rec timestamps (InMemory repo stamps
    them with datetime.now), so the session window must cover 'now'."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + timedelta(days=32)).replace(day=1)

    repos = InMemoryRepositorySet()
    in_month = replace(
        SessionBuilder().with_id("s-in").build(),
        model="claude-opus-4-6",
        started_at=month_start + timedelta(days=1),
        total_input_tokens=TokenCount(1_000_000),
        total_output_tokens=TokenCount(0),
    )
    out_of_range = replace(
        SessionBuilder().with_id("s-out").build(),
        started_at=month_start - timedelta(days=10),
    )
    repos.sessions.upsert(in_month)
    repos.sessions.upsert(out_of_range)
    repos.pricing.add(PricingRateBuilder().for_model("claude-opus-4-6").build())

    rec = RecommendationBuilder().in_session("s-in").build()
    repos.recommendations.save_all([rec])
    repos.recommendations.mark_applied([rec.rec_id], SnapshotId("snap-m"))

    summary = _uc(repos).execute(month_start=month_start, month_end=month_end)
    assert summary.session_count == 1
    assert summary.total_cost == Money(Decimal("15.0"))
    assert summary.realized_savings.amount > 0
    assert len(summary.by_model) == 1
    assert summary.by_model[0].model == "claude-opus-4-6"


def test_unknown_pricing_session_is_skipped() -> None:
    repos = InMemoryRepositorySet()
    weird = replace(
        SessionBuilder().with_id("s-weird").build(),
        model="claude-unknown",
        started_at=_march(5),
    )
    repos.sessions.upsert(weird)
    summary = _uc(repos).execute(month_start=_march(1), month_end=_march(31) + timedelta(days=1))
    assert summary.session_count == 0
