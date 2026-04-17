from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from ccprophet.domain.entities import CostBreakdown, Session
from ccprophet.domain.services.cost import CostCalculator
from ccprophet.domain.values import (
    Confidence,
    Money,
    RecommendationKind,
    SessionId,
    TokenCount,
)
from tests.fixtures.builders import (
    PricingRateBuilder,
    RecommendationBuilder,
    SessionBuilder,
)


def _session_with_tokens(sid: str, input_tok: int, output_tok: int) -> Session:
    s = SessionBuilder().with_id(sid).build()
    # SessionBuilder doesn't expose token setters — use dataclass.replace
    from dataclasses import replace

    return replace(
        s,
        total_input_tokens=TokenCount(input_tok),
        total_output_tokens=TokenCount(output_tok),
    )


def test_session_cost_uses_rate() -> None:
    session = _session_with_tokens("s-1", 1_000_000, 500_000)
    rate = PricingRateBuilder().build()  # in 15.0, out 75.0 per 1M
    cost = CostCalculator.session_cost(session, rate)
    assert cost.input_cost == Money(Decimal("15.0"))
    assert cost.output_cost == Money(Decimal("37.5"))
    assert cost.total_cost == Money(Decimal("52.5"))
    assert cost.rate_id == rate.rate_id


def test_session_cost_zero_tokens_is_zero() -> None:
    session = _session_with_tokens("s-0", 0, 0)
    rate = PricingRateBuilder().build()
    cost = CostCalculator.session_cost(session, rate)
    assert cost.total_cost == Money.zero()


def test_realized_savings_sums_matching_currency() -> None:
    recs = [
        RecommendationBuilder().build(),  # default 0.021 USD
        RecommendationBuilder().build(),
    ]
    total = CostCalculator.realized_savings(recs, currency="USD")
    assert total.amount == Decimal("0.042")


def test_realized_savings_skips_foreign_currency() -> None:
    recs = [
        RecommendationBuilder().build(),
    ]
    total = CostCalculator.realized_savings(recs, currency="EUR")
    assert total == Money.zero("EUR")


def test_monthly_summary_aggregates_by_model() -> None:
    session_a = _session_with_tokens("a", 1_000_000, 0)
    session_b = _session_with_tokens("b", 2_000_000, 0)
    # second session uses a different model
    from dataclasses import replace

    session_b = replace(session_b, model="claude-sonnet-4-6")

    rate_opus = PricingRateBuilder().for_model("claude-opus-4-6").build()
    rate_sonnet = PricingRateBuilder().for_model("claude-sonnet-4-6").build()
    breakdowns = [
        CostCalculator.session_cost(session_a, rate_opus),
        CostCalculator.session_cost(session_b, rate_sonnet),
    ]

    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    end = datetime(2026, 4, 1, tzinfo=timezone.utc)
    summary = CostCalculator.monthly_summary(
        month_start=start,
        month_end=end,
        breakdowns=breakdowns,
        sessions_by_id={"a": session_a, "b": session_b},
        applied_recs=[],
    )

    assert summary.session_count == 2
    assert summary.total_cost == Money(Decimal("45.0"))  # 15 + 30
    assert {m.model for m in summary.by_model} == {
        "claude-opus-4-6",
        "claude-sonnet-4-6",
    }


def test_avg_session_cost_divides_total() -> None:
    session_a = _session_with_tokens("a", 1_000_000, 0)
    rate = PricingRateBuilder().for_model("claude-opus-4-6").build()
    breakdown = CostCalculator.session_cost(session_a, rate)
    summary = CostCalculator.monthly_summary(
        month_start=datetime(2026, 3, 1, tzinfo=timezone.utc),
        month_end=datetime(2026, 4, 1, tzinfo=timezone.utc),
        breakdowns=[breakdown, breakdown],
        sessions_by_id={"a": session_a},
        applied_recs=[],
    )
    assert summary.avg_session_cost.amount == Decimal("15.0")


def test_monthly_summary_empty_is_zero() -> None:
    summary = CostCalculator.monthly_summary(
        month_start=datetime(2026, 3, 1, tzinfo=timezone.utc),
        month_end=datetime(2026, 4, 1, tzinfo=timezone.utc),
        breakdowns=[],
        sessions_by_id={},
        applied_recs=[],
    )
    assert summary.session_count == 0
    assert summary.total_cost == Money.zero()
    assert summary.avg_session_cost == Money.zero()
