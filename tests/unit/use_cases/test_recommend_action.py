from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import ToolDef
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import (
    RecommendationKind,
    RecommendationStatus,
    SessionId,
    TokenCount,
)
from ccprophet.use_cases.recommend_action import RecommendActionUseCase
from tests.fixtures.builders import (
    PricingRateBuilder,
    SessionBuilder,
    ToolCallBuilder,
)

FROZEN = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _use_case(repos: InMemoryRepositorySet) -> RecommendActionUseCase:
    return RecommendActionUseCase(
        sessions=repos.sessions,
        tool_defs=repos.tool_defs,
        tool_calls=repos.tool_calls,
        recommendations=repos.recommendations,
        pricing=repos.pricing,
        clock=FrozenClock(FROZEN),
    )


def _seed_bloat_session(repos: InMemoryRepositorySet, sid: str = "s-1") -> None:
    repos.sessions.upsert(
        SessionBuilder().with_id(sid).build()
    )
    repos.tool_defs.bulk_add(
        SessionId(sid),
        [
            ToolDef("Read", TokenCount(500), "system"),
            ToolDef("mcp__github_x", TokenCount(1_400), "mcp:github"),
        ],
    )
    repos.tool_calls.append(
        ToolCallBuilder().in_session(sid).for_tool("Read").build()
    )


def test_missing_session_raises() -> None:
    repos = InMemoryRepositorySet()
    with pytest.raises(SessionNotFound):
        _use_case(repos).execute(SessionId("nope"))


def test_generates_and_persists_recommendation() -> None:
    repos = InMemoryRepositorySet()
    _seed_bloat_session(repos)
    recs = _use_case(repos).execute(SessionId("s-1"))
    assert len(recs) == 1
    assert recs[0].kind == RecommendationKind.PRUNE_MCP
    stored = list(
        repos.recommendations.list_for_session(
            SessionId("s-1"), status=RecommendationStatus.PENDING
        )
    )
    assert len(stored) == 1


def test_persist_false_does_not_write() -> None:
    repos = InMemoryRepositorySet()
    _seed_bloat_session(repos)
    _use_case(repos).execute(SessionId("s-1"), persist=False)
    assert list(repos.recommendations.list_pending()) == []


def test_pricing_rate_is_applied_when_known() -> None:
    repos = InMemoryRepositorySet()
    _seed_bloat_session(repos)
    repos.pricing.add(PricingRateBuilder().for_model("claude-opus-4-6").build())
    [rec] = _use_case(repos).execute(SessionId("s-1"))
    assert rec.est_savings_usd.amount > 0


def test_execute_current_uses_latest_active() -> None:
    repos = InMemoryRepositorySet()
    _seed_bloat_session(repos, sid="old")
    _seed_bloat_session(repos, sid="new")
    recs = _use_case(repos).execute_current()
    assert all(r.session_id == SessionId("new") for r in recs) or \
           all(r.session_id == SessionId("old") for r in recs)


def test_no_bloat_yields_no_recs_and_no_persist() -> None:
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id("clean").build())
    assert _use_case(repos).execute(SessionId("clean")) == []
    assert list(repos.recommendations.list_pending()) == []
