from __future__ import annotations

from dataclasses import dataclass

from ccprophet.domain.entities import Recommendation
from ccprophet.domain.errors import SessionNotFound, UnknownPricingModel
from ccprophet.domain.services.bloat import BloatCalculator
from ccprophet.domain.services.recommender import (
    RecommendationContext,
    Recommender,
)
from ccprophet.domain.values import SessionId
from ccprophet.ports.clock import Clock
from ccprophet.ports.pricing import PricingProvider
from ccprophet.ports.recommendations import RecommendationRepository
from ccprophet.ports.repositories import (
    SessionRepository,
    ToolCallRepository,
    ToolDefRepository,
)


@dataclass(frozen=True)
class RecommendActionUseCase:
    sessions: SessionRepository
    tool_defs: ToolDefRepository
    tool_calls: ToolCallRepository
    recommendations: RecommendationRepository
    pricing: PricingProvider
    clock: Clock

    def execute(
        self, session_id: SessionId, *, persist: bool = True
    ) -> list[Recommendation]:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)

        loaded = list(self.tool_defs.list_for_session(session_id))
        called = list(self.tool_calls.list_for_session(session_id))
        report = BloatCalculator.calculate(loaded, called)

        try:
            pricing_rate = self.pricing.rate_for(session.model, session.started_at)
        except UnknownPricingModel:
            pricing_rate = None

        ctx = RecommendationContext(
            session=session, bloat_report=report, pricing=pricing_rate
        )
        recs = Recommender.recommend(ctx, now=self.clock.now())
        if persist and recs:
            self.recommendations.save_all(recs)
        return recs

    def execute_current(self, *, persist: bool = True) -> list[Recommendation]:
        session = self.sessions.latest_active()
        if session is None:
            raise SessionNotFound(SessionId("(no active session)"))
        return self.execute(session.session_id, persist=persist)
