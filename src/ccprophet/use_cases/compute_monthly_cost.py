from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ccprophet.domain.entities import MonthlyCostSummary
from ccprophet.domain.errors import UnknownPricingModel
from ccprophet.domain.services.cost import CostCalculator
from ccprophet.ports.pricing import PricingProvider
from ccprophet.ports.recommendations import RecommendationRepository
from ccprophet.ports.repositories import SessionRepository


@dataclass(frozen=True)
class ComputeMonthlyCostUseCase:
    sessions: SessionRepository
    recommendations: RecommendationRepository
    pricing: PricingProvider

    def execute(
        self,
        *,
        month_start: datetime,
        month_end: datetime,
        currency: str = "USD",
    ) -> MonthlyCostSummary:
        sessions = list(self.sessions.list_in_range(month_start, month_end))
        breakdowns = []
        sessions_by_id: dict[str, object] = {}
        for session in sessions:
            sessions_by_id[session.session_id.value] = session
            try:
                rate = self.pricing.rate_for(session.model, session.started_at)
            except UnknownPricingModel:
                continue
            breakdowns.append(CostCalculator.session_cost(session, rate))

        applied_recs = list(self.recommendations.list_applied_in_range(month_start, month_end))

        return CostCalculator.monthly_summary(
            month_start=month_start,
            month_end=month_end,
            breakdowns=breakdowns,
            sessions_by_id=sessions_by_id,  # type: ignore[arg-type]
            applied_recs=applied_recs,
            currency=currency,
        )
