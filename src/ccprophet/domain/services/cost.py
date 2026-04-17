"""Pure cost calculations.

Tokens → Money conversion + realized-savings aggregation. No IO; PricingRate
is passed in by the use case that knows which rate was active when.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal

from ccprophet.domain.entities import (
    CostBreakdown,
    ModelCostSummary,
    MonthlyCostSummary,
    PricingRate,
    Recommendation,
    Session,
)
from ccprophet.domain.values import Money, TokenCount


class CostCalculator:
    @staticmethod
    def session_cost(session: Session, rate: PricingRate) -> CostBreakdown:
        currency = rate.currency
        input_cost = _tokens_to_money(
            session.total_input_tokens, rate.input_per_mtok, currency
        )
        output_cost = _tokens_to_money(
            session.total_output_tokens, rate.output_per_mtok, currency
        )
        cache_write_cost = _tokens_to_money(
            session.total_cache_creation_tokens,
            rate.cache_write_per_mtok,
            currency,
        )
        cache_read_cost = _tokens_to_money(
            session.total_cache_read_tokens, rate.cache_read_per_mtok, currency
        )
        cache_cost = cache_write_cost + cache_read_cost
        total = input_cost + output_cost + cache_cost
        return CostBreakdown(
            session_id=session.session_id,
            model=session.model,
            input_cost=input_cost,
            output_cost=output_cost,
            cache_cost=cache_cost,
            total_cost=total,
            rate_id=rate.rate_id,
        )

    @staticmethod
    def realized_savings(
        applied: Iterable[Recommendation], currency: str = "USD"
    ) -> Money:
        total = Money.zero(currency)
        for rec in applied:
            if rec.est_savings_usd.currency != currency:
                continue
            total = total + rec.est_savings_usd
        return total

    @staticmethod
    def monthly_summary(
        *,
        month_start: datetime,
        month_end: datetime,
        breakdowns: Sequence[CostBreakdown],
        sessions_by_id: dict[str, Session],
        applied_recs: Sequence[Recommendation],
        currency: str = "USD",
    ) -> MonthlyCostSummary:
        by_model: dict[str, ModelCostSummary] = {}
        total = Money.zero(currency)
        for bd in breakdowns:
            session = sessions_by_id.get(bd.session_id.value)
            if session is None:
                continue
            prev = by_model.get(bd.model)
            if prev is None:
                by_model[bd.model] = ModelCostSummary(
                    model=bd.model,
                    session_count=1,
                    total_input_tokens=session.total_input_tokens,
                    total_output_tokens=session.total_output_tokens,
                    total_cost=bd.total_cost,
                )
            else:
                by_model[bd.model] = ModelCostSummary(
                    model=bd.model,
                    session_count=prev.session_count + 1,
                    total_input_tokens=TokenCount(
                        prev.total_input_tokens.value + session.total_input_tokens.value
                    ),
                    total_output_tokens=TokenCount(
                        prev.total_output_tokens.value
                        + session.total_output_tokens.value
                    ),
                    total_cost=prev.total_cost + bd.total_cost,
                )
            total = total + bd.total_cost

        realized = CostCalculator.realized_savings(applied_recs, currency=currency)
        return MonthlyCostSummary(
            month_start=month_start,
            month_end=month_end,
            session_count=len(breakdowns),
            total_cost=total,
            realized_savings=realized,
            by_model=tuple(
                sorted(by_model.values(), key=lambda m: m.total_cost.amount, reverse=True)
            ),
        )


def _tokens_to_money(tokens: TokenCount, rate_per_mtok: float, currency: str) -> Money:
    if tokens.value == 0:
        return Money.zero(currency)
    amount = Decimal(str(rate_per_mtok)) * Decimal(tokens.value) / Decimal(1_000_000)
    return Money(amount, currency)
