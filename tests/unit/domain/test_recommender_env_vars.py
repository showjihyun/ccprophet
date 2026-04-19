"""Unit tests for the three SET_ENV_VAR rules in Recommender.

Each rule is tested independently with:
  - no-trigger (below threshold)
  - trigger (at/above threshold) with expected target, confidence, rationale substring
  - est_savings_usd flows through when pricing is present
  - all three rules can fire simultaneously
"""

from __future__ import annotations

from datetime import datetime, timezone

from ccprophet.domain.entities import BloatReport
from ccprophet.domain.services.recommender import (
    _MCP_OUTPUT_CAP,
    _MCP_OUTPUT_TRIGGER,
    _SUBAGENT_TRIGGER,
    _THINKING_HIGH,
    _THINKING_TRIGGER,
    RecommendationContext,
    Recommender,
)
from ccprophet.domain.values import (
    BloatRatio,
    Confidence,
    Money,
    RecommendationKind,
    TokenCount,
)
from tests.fixtures.builders import PricingRateBuilder, SessionBuilder

NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
_EMPTY_REPORT = BloatReport(
    items=(),
    total_tokens=TokenCount(0),
    bloat_tokens=TokenCount(0),
    bloat_ratio=BloatRatio(0.0),
    used_sources=frozenset(),
)


def _ctx(**kwargs: object) -> RecommendationContext:
    return RecommendationContext(
        session=SessionBuilder().with_id("s-env").build(),
        bloat_report=_EMPTY_REPORT,
        **kwargs,  # type: ignore[arg-type]
    )


def _env_recs(ctx: RecommendationContext) -> list:
    return [
        r for r in Recommender.recommend(ctx, now=NOW) if r.kind == RecommendationKind.SET_ENV_VAR
    ]


# ─── Rule 1: MAX_THINKING_TOKENS ─────────────────────────────────────────────


def test_rule1_no_trigger_below_threshold() -> None:
    ctx = _ctx(thinking_tokens=_THINKING_TRIGGER - 1)
    assert _env_recs(ctx) == []


def test_rule1_triggers_at_threshold() -> None:
    ctx = _ctx(thinking_tokens=_THINKING_TRIGGER)
    recs = _env_recs(ctx)
    assert len(recs) == 1
    r = recs[0]
    assert r.target == "MAX_THINKING_TOKENS=10000"
    assert r.confidence == Confidence(0.7)
    assert "thinking tokens" in r.rationale
    assert "30-40%" in r.rationale
    assert r.est_savings_tokens == TokenCount(int(_THINKING_TRIGGER * 0.35))


def test_rule1_high_confidence_above_50k() -> None:
    ctx = _ctx(thinking_tokens=_THINKING_HIGH)
    [r] = _env_recs(ctx)
    assert r.confidence == Confidence(0.85)


def test_rule1_savings_tokens_are_35_percent() -> None:
    thinking = 100_000
    ctx = _ctx(thinking_tokens=thinking)
    [r] = _env_recs(ctx)
    assert r.est_savings_tokens == TokenCount(int(thinking * 0.35))


def test_rule1_usd_zero_without_pricing() -> None:
    ctx = _ctx(thinking_tokens=_THINKING_HIGH)
    [r] = _env_recs(ctx)
    assert r.est_savings_usd == Money.zero()


def test_rule1_usd_nonzero_with_pricing() -> None:
    pricing = PricingRateBuilder().for_model("claude-opus-4-6").build()
    ctx = _ctx(thinking_tokens=1_000_000, pricing=pricing)
    [r] = _env_recs(ctx)
    assert r.est_savings_usd.amount > 0


# ─── Rule 2: CLAUDE_CODE_SUBAGENT_MODEL=haiku ────────────────────────────────


def test_rule2_no_trigger_below_threshold() -> None:
    ctx = _ctx(subagent_context_tokens=_SUBAGENT_TRIGGER - 1)
    assert _env_recs(ctx) == []


def test_rule2_triggers_at_threshold() -> None:
    ctx = _ctx(subagent_context_tokens=_SUBAGENT_TRIGGER)
    recs = _env_recs(ctx)
    assert len(recs) == 1
    r = recs[0]
    assert r.target == "CLAUDE_CODE_SUBAGENT_MODEL=haiku"
    assert r.confidence == Confidence(0.8)
    assert "Subagents consumed" in r.rationale
    assert "~80%" in r.rationale
    assert r.est_savings_tokens == TokenCount(int(_SUBAGENT_TRIGGER * 0.8))


def test_rule2_savings_tokens_are_80_percent() -> None:
    sub_tokens = 200_000
    ctx = _ctx(subagent_context_tokens=sub_tokens)
    [r] = _env_recs(ctx)
    assert r.est_savings_tokens == TokenCount(int(sub_tokens * 0.8))


def test_rule2_usd_zero_without_pricing() -> None:
    ctx = _ctx(subagent_context_tokens=_SUBAGENT_TRIGGER)
    [r] = _env_recs(ctx)
    assert r.est_savings_usd == Money.zero()


def test_rule2_usd_nonzero_with_pricing() -> None:
    pricing = PricingRateBuilder().for_model("claude-opus-4-6").build()
    ctx = _ctx(subagent_context_tokens=1_000_000, pricing=pricing)
    [r] = _env_recs(ctx)
    assert r.est_savings_usd.amount > 0


# ─── Rule 3: MAX_MCP_OUTPUT_TOKENS ───────────────────────────────────────────


def test_rule3_no_trigger_below_threshold() -> None:
    ctx = _ctx(mcp_max_output_seen=_MCP_OUTPUT_TRIGGER - 1)
    assert _env_recs(ctx) == []


def test_rule3_triggers_at_threshold() -> None:
    ctx = _ctx(mcp_max_output_seen=_MCP_OUTPUT_TRIGGER)
    recs = _env_recs(ctx)
    assert len(recs) == 1
    r = recs[0]
    assert r.target == "MAX_MCP_OUTPUT_TOKENS=15000"
    assert r.confidence == Confidence(0.75)
    assert "MCP call returned" in r.rationale
    assert "15000" in r.rationale
    expected_savings = max(0, _MCP_OUTPUT_TRIGGER - _MCP_OUTPUT_CAP)
    assert r.est_savings_tokens == TokenCount(expected_savings)


def test_rule3_savings_is_excess_over_cap() -> None:
    seen = 50_000
    ctx = _ctx(mcp_max_output_seen=seen)
    [r] = _env_recs(ctx)
    assert r.est_savings_tokens == TokenCount(seen - _MCP_OUTPUT_CAP)


def test_rule3_usd_zero_without_pricing() -> None:
    ctx = _ctx(mcp_max_output_seen=_MCP_OUTPUT_TRIGGER)
    [r] = _env_recs(ctx)
    assert r.est_savings_usd == Money.zero()


def test_rule3_usd_nonzero_with_pricing() -> None:
    pricing = PricingRateBuilder().for_model("claude-opus-4-6").build()
    ctx = _ctx(mcp_max_output_seen=1_000_000, pricing=pricing)
    [r] = _env_recs(ctx)
    assert r.est_savings_usd.amount > 0


# ─── All three rules fire simultaneously ─────────────────────────────────────


def test_all_three_rules_fire_simultaneously() -> None:
    pricing = PricingRateBuilder().for_model("claude-opus-4-6").build()
    ctx = _ctx(
        thinking_tokens=_THINKING_HIGH,
        subagent_context_tokens=_SUBAGENT_TRIGGER,
        mcp_max_output_seen=_MCP_OUTPUT_TRIGGER,
        pricing=pricing,
    )
    env_r = _env_recs(ctx)
    assert len(env_r) == 3
    targets = {r.target for r in env_r}
    assert targets == {
        "MAX_THINKING_TOKENS=10000",
        "CLAUDE_CODE_SUBAGENT_MODEL=haiku",
        "MAX_MCP_OUTPUT_TOKENS=15000",
    }


def test_all_three_rules_usd_nonzero_when_pricing() -> None:
    pricing = PricingRateBuilder().for_model("claude-opus-4-6").build()
    ctx = _ctx(
        thinking_tokens=1_000_000,
        subagent_context_tokens=1_000_000,
        mcp_max_output_seen=100_000,
        pricing=pricing,
    )
    env_r = _env_recs(ctx)
    for r in env_r:
        assert r.est_savings_usd.amount > 0, f"expected USD > 0 for {r.target}"


# ─── Confidence is always in [0.0, 1.0] ─────────────────────────────────────


def test_confidence_bounds_all_rules() -> None:
    ctx = _ctx(
        thinking_tokens=_THINKING_HIGH,
        subagent_context_tokens=_SUBAGENT_TRIGGER,
        mcp_max_output_seen=_MCP_OUTPUT_TRIGGER,
    )
    for r in _env_recs(ctx):
        assert 0.0 <= r.confidence.value <= 1.0
