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

# Env-var rule thresholds
_THINKING_TRIGGER = 20_000
_THINKING_HIGH = 50_000
_SUBAGENT_TRIGGER = 50_000
_MCP_OUTPUT_TRIGGER = 20_000
_MCP_OUTPUT_CAP = 15_000


@dataclass(frozen=True, slots=True)
class RecommendationContext:
    session: Session
    bloat_report: BloatReport
    pricing: PricingRate | None = None
    min_tokens: int = DEFAULT_MIN_TOKENS
    # NEW: env-var signal fields populated by the use case layer
    thinking_tokens: int = 0            # extended-thinking output tokens this session
    subagent_context_tokens: int = 0    # sum of subagent context_tokens for this session
    mcp_max_output_seen: int = 0        # max output_tokens from any mcp__ tool call


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
        recs.extend(_env_var_recs(ctx, now))
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
        f"{item.source} / {item.tool_name}: 0 calls in session — "
        f"removing saves ~{item.tokens.value:,} tokens"
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


def _estimate_output_usd(tokens: int, pricing: PricingRate | None) -> Money:
    """Estimate USD savings using the output token rate (for thinking/subagent tokens)."""
    if pricing is None or tokens == 0:
        return Money.zero()
    amount = (
        Decimal(str(pricing.output_per_mtok))
        * Decimal(tokens)
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


def _env_var_recs(ctx: RecommendationContext, now: datetime) -> list[Recommendation]:
    """Emit SET_ENV_VAR recommendations based on env-var signal fields.

    Each rule fires independently when its threshold is exceeded. Rules are
    advisory only; the CLI renders them with a copy-paste hint.
    """
    recs: list[Recommendation] = []

    # Rule 1 — MAX_THINKING_TOKENS
    if ctx.thinking_tokens >= _THINKING_TRIGGER:
        conf = Confidence(0.85) if ctx.thinking_tokens >= _THINKING_HIGH else Confidence(0.7)
        rationale = (
            f"Observed {ctx.thinking_tokens:,} thinking tokens — capping at 10000 "
            f"typically saves 30-40% per session"
        )
        savings = int(ctx.thinking_tokens * 0.35)
        usd = _estimate_output_usd(savings, ctx.pricing)
        recs.append(
            Recommendation(
                rec_id=str(uuid.uuid4()),
                session_id=ctx.session.session_id,
                kind=RecommendationKind.SET_ENV_VAR,
                target="MAX_THINKING_TOKENS=10000",
                est_savings_tokens=TokenCount(savings),
                est_savings_usd=usd,
                confidence=conf,
                rationale=rationale,
                created_at=now,
                provenance="env_var_rule",
            )
        )

    # Rule 2 — CLAUDE_CODE_SUBAGENT_MODEL=haiku
    if ctx.subagent_context_tokens >= _SUBAGENT_TRIGGER:
        savings = int(ctx.subagent_context_tokens * 0.8)
        usd = _estimate_output_usd(savings, ctx.pricing)
        rationale = (
            f"Subagents consumed {ctx.subagent_context_tokens:,} tokens — "
            f"Haiku as subagent model saves ~80%"
        )
        recs.append(
            Recommendation(
                rec_id=str(uuid.uuid4()),
                session_id=ctx.session.session_id,
                kind=RecommendationKind.SET_ENV_VAR,
                target="CLAUDE_CODE_SUBAGENT_MODEL=haiku",
                est_savings_tokens=TokenCount(savings),
                est_savings_usd=usd,
                confidence=Confidence(0.8),
                rationale=rationale,
                created_at=now,
                provenance="env_var_rule",
            )
        )

    # Rule 3 — MAX_MCP_OUTPUT_TOKENS
    if ctx.mcp_max_output_seen >= _MCP_OUTPUT_TRIGGER:
        savings = max(0, ctx.mcp_max_output_seen - _MCP_OUTPUT_CAP)
        usd = _estimate_output_usd(savings, ctx.pricing)
        rationale = (
            f"An MCP call returned {ctx.mcp_max_output_seen:,} tokens — "
            f"capping at 15000 prevents runaway MCP output"
        )
        recs.append(
            Recommendation(
                rec_id=str(uuid.uuid4()),
                session_id=ctx.session.session_id,
                kind=RecommendationKind.SET_ENV_VAR,
                target="MAX_MCP_OUTPUT_TOKENS=15000",
                est_savings_tokens=TokenCount(savings),
                est_savings_usd=usd,
                confidence=Confidence(0.75),
                rationale=rationale,
                created_at=now,
                provenance="env_var_rule",
            )
        )

    return recs
