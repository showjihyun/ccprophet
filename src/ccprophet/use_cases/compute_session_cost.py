from __future__ import annotations

from dataclasses import dataclass

from ccprophet.domain.entities import CostBreakdown
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.services.cost import CostCalculator
from ccprophet.domain.values import SessionId
from ccprophet.ports.pricing import PricingProvider
from ccprophet.ports.repositories import SessionRepository


@dataclass(frozen=True)
class ComputeSessionCostUseCase:
    sessions: SessionRepository
    pricing: PricingProvider

    def execute(self, session_id: SessionId) -> CostBreakdown:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        rate = self.pricing.rate_for(session.model, session.started_at)
        return CostCalculator.session_cost(session, rate)
