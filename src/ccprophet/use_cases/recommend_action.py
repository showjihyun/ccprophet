from __future__ import annotations

import os
from dataclasses import dataclass, field

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
from ccprophet.ports.subagents import SubagentRepository


@dataclass(frozen=True)
class RecommendActionUseCase:
    sessions: SessionRepository
    tool_defs: ToolDefRepository
    tool_calls: ToolCallRepository
    recommendations: RecommendationRepository
    pricing: PricingProvider
    clock: Clock
    # Optional: if absent, subagent_context_tokens will be 0 (Rule 2 won't fire)
    subagents: SubagentRepository | None = field(default=None)

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

        # --- env-var signal derivation ---

        # Rule 1: thinking_tokens.
        # A real signal requires per-event tracking of the `thinking` block
        # token count (Phase 3 work). Until that exists we keep this at 0 and
        # skip the rec — the previous "Opus output_tokens is a proxy" shortcut
        # over-triggered on any Opus session doing heavy work and eroded trust.
        # Set CCPROPHET_EXPERIMENTAL_THINKING_PROXY=1 to re-enable the old
        # heuristic for your own dogfooding.
        thinking_tokens = 0
        if (
            os.environ.get("CCPROPHET_EXPERIMENTAL_THINKING_PROXY") == "1"
            and session.model.startswith("claude-opus")
        ):
            thinking_tokens = session.total_output_tokens.value

        # Rule 2: subagent_context_tokens — sum across child subagents.
        subagent_context_tokens = 0
        if self.subagents is not None:
            for sub in self.subagents.list_for_parent(session_id):
                subagent_context_tokens += sub.context_tokens.value

        # Rule 3: mcp_max_output_seen — largest output_tokens on an mcp__ tool call.
        mcp_max_output_seen = max(
            (
                tc.output_tokens.value
                for tc in called
                if tc.tool_name.startswith("mcp__")
            ),
            default=0,
        )

        ctx = RecommendationContext(
            session=session,
            bloat_report=report,
            pricing=pricing_rate,
            thinking_tokens=thinking_tokens,
            subagent_context_tokens=subagent_context_tokens,
            mcp_max_output_seen=mcp_max_output_seen,
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
