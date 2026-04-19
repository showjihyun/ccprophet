from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from ccprophet.domain.entities import BloatItem, BloatReport
from ccprophet.domain.services.recommender import (
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


def _report(*items: BloatItem) -> BloatReport:
    total = sum(i.tokens.value for i in items)
    bloat = sum(i.tokens.value for i in items if not i.used)
    ratio = bloat / total if total > 0 else 0.0
    return BloatReport(
        items=tuple(items),
        total_tokens=TokenCount(total),
        bloat_tokens=TokenCount(bloat),
        bloat_ratio=BloatRatio(ratio),
        used_sources=frozenset(i.source for i in items if i.used),
    )


def _ctx(report: BloatReport, pricing=None, min_tokens: int = 100):
    return RecommendationContext(
        session=SessionBuilder().with_id("s-1").build(),
        bloat_report=report,
        pricing=pricing,
        min_tokens=min_tokens,
    )


def test_empty_report_yields_no_recommendations() -> None:
    assert Recommender.recommend(_ctx(_report()), now=NOW) == []


def test_unused_mcp_yields_prune_mcp() -> None:
    report = _report(
        BloatItem(
            tool_name="mcp__github_x", source="mcp:github", tokens=TokenCount(1_400), used=False
        ),
    )
    [rec] = Recommender.recommend(_ctx(report), now=NOW)
    assert rec.kind == RecommendationKind.PRUNE_MCP
    assert rec.target == "mcp__github_x"
    assert rec.est_savings_tokens == TokenCount(1_400)
    assert rec.confidence == Confidence(0.8)


def test_unused_system_tool_yields_prune_tool() -> None:
    report = _report(
        BloatItem(tool_name="WebFetch", source="system", tokens=TokenCount(3_000), used=False),
    )
    [rec] = Recommender.recommend(_ctx(report), now=NOW)
    assert rec.kind == RecommendationKind.PRUNE_TOOL
    assert rec.confidence == Confidence(0.95)


def test_used_items_are_ignored() -> None:
    report = _report(
        BloatItem(tool_name="Read", source="system", tokens=TokenCount(2_000), used=True),
    )
    assert Recommender.recommend(_ctx(report), now=NOW) == []


def test_items_below_min_tokens_skipped() -> None:
    report = _report(
        BloatItem(tool_name="tiny", source="system", tokens=TokenCount(50), used=False),
    )
    assert Recommender.recommend(_ctx(report, min_tokens=100), now=NOW) == []


def test_results_sorted_by_tokens_desc() -> None:
    report = _report(
        BloatItem(tool_name="a", source="mcp:a", tokens=TokenCount(500), used=False),
        BloatItem(tool_name="b", source="mcp:b", tokens=TokenCount(3_000), used=False),
        BloatItem(tool_name="c", source="mcp:c", tokens=TokenCount(1_000), used=False),
    )
    recs = Recommender.recommend(_ctx(report), now=NOW)
    assert [r.target for r in recs] == ["b", "c", "a"]


def test_pricing_missing_yields_zero_usd() -> None:
    report = _report(
        BloatItem(tool_name="x", source="mcp:x", tokens=TokenCount(1_000), used=False),
    )
    [rec] = Recommender.recommend(_ctx(report, pricing=None), now=NOW)
    assert rec.est_savings_usd == Money.zero()


def test_pricing_present_yields_nonzero_usd() -> None:
    report = _report(
        BloatItem(tool_name="x", source="mcp:x", tokens=TokenCount(1_000_000), used=False),
    )
    pricing = PricingRateBuilder().for_model("claude-opus-4-7").build()
    [rec] = Recommender.recommend(_ctx(report, pricing=pricing), now=NOW)
    assert rec.est_savings_usd.amount == Decimal("15.0")


def test_confidence_tiers() -> None:
    report = _report(
        BloatItem(tool_name="low", source="mcp:a", tokens=TokenCount(100), used=False),
        BloatItem(tool_name="mid", source="mcp:b", tokens=TokenCount(500), used=False),
        BloatItem(tool_name="hi", source="mcp:c", tokens=TokenCount(2_000), used=False),
    )
    recs = {r.target: r.confidence for r in Recommender.recommend(_ctx(report), now=NOW)}
    assert recs["low"] == Confidence(0.5)
    assert recs["mid"] == Confidence(0.8)
    assert recs["hi"] == Confidence(0.95)


def test_created_at_matches_now() -> None:
    report = _report(
        BloatItem(tool_name="x", source="mcp:x", tokens=TokenCount(500), used=False),
    )
    [rec] = Recommender.recommend(_ctx(report), now=NOW)
    assert rec.created_at == NOW
    assert rec.provenance == "recommend"
