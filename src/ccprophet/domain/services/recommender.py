"""Recommender domain service — turns BloatReport + PricingRate into actionable
Recommendations. Pure; no IO. See ARCHITECT.md §4.6 and PRD.md §6.7 (F7).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ccprophet.domain.entities import (
    BloatItem,
    BloatReport,
    PricingRate,
    Recommendation,
    Session,
)
from ccprophet.domain.values import (
    Confidence,
    Money,
    RecommendationKind,
    TokenCount,
)

DEFAULT_MIN_TOKENS = 100


@dataclass(frozen=True, slots=True)
class RecommendationContext:
    session: Session
    bloat_report: BloatReport
    pricing: PricingRate | None = None
    min_tokens: int = DEFAULT_MIN_TOKENS


class Recommender:
    @staticmethod
    def recommend(
        ctx: RecommendationContext, *, now: datetime
    ) -> list[Recommendation]:
        recs = [
            _pruning_rec(ctx, item, now)
            for item in ctx.bloat_report.items
            if not item.used and item.tokens.value >= ctx.min_tokens
        ]
        recs.sort(
            key=lambda r: (r.est_savings_tokens.value, r.confidence.value),
            reverse=True,
        )
        return recs


def _pruning_rec(
    ctx: RecommendationContext, item: BloatItem, now: datetime
) -> Recommendation:
    is_mcp = item.source.startswith("mcp:")
    kind = RecommendationKind.PRUNE_MCP if is_mcp else RecommendationKind.PRUNE_TOOL
    usd = _estimate_usd(item.tokens, ctx.pricing)
    rationale = (
        f"{item.source} / {item.tool_name}: 세션 내 0회 호출, "
        f"제거 시 {item.tokens.value:,} 토큰 절감"
    )
    return Recommendation(
        rec_id=str(uuid.uuid4()),
        session_id=ctx.session.session_id,
        kind=kind,
        target=item.tool_name,
        est_savings_tokens=item.tokens,
        est_savings_usd=usd,
        confidence=_pick_confidence(item.tokens),
        rationale=rationale,
        created_at=now,
        provenance="recommend",
    )


def _estimate_usd(tokens: TokenCount, pricing: PricingRate | None) -> Money:
    if pricing is None or tokens.value == 0:
        return Money.zero()
    amount = (
        Decimal(str(pricing.input_per_mtok))
        * Decimal(tokens.value)
        / Decimal(1_000_000)
    )
    return Money(amount, pricing.currency)


def _pick_confidence(tokens: TokenCount) -> Confidence:
    n = tokens.value
    if n >= 2000:
        return Confidence(0.95)
    if n >= 500:
        return Confidence(0.8)
    return Confidence(0.5)
