"""Unit tests verifying that RecommendActionUseCase correctly populates the
three new env-var signal fields and delegates them to the Recommender.

Uses InMemory fakes throughout (no IO).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import ToolCall, ToolDef
from ccprophet.domain.values import (
    RecommendationKind,
    SessionId,
    TokenCount,
)
from ccprophet.use_cases.recommend_action import RecommendActionUseCase
from tests.fixtures.builders import (
    PricingRateBuilder,
    SessionBuilder,
    SubagentBuilder,
    ToolCallBuilder,
)

FROZEN = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)

_OPUS_MODEL = "claude-opus-4-6"
_SONNET_MODEL = "claude-sonnet-4-5"


def _use_case(
    repos: InMemoryRepositorySet,
    *,
    with_subagents: bool = True,
) -> RecommendActionUseCase:
    return RecommendActionUseCase(
        sessions=repos.sessions,
        tool_defs=repos.tool_defs,
        tool_calls=repos.tool_calls,
        recommendations=repos.recommendations,
        pricing=repos.pricing,
        clock=FrozenClock(FROZEN),
        subagents=repos.subagents if with_subagents else None,
    )


def _seed_session(
    repos: InMemoryRepositorySet,
    sid: str = "s-env",
    model: str = _OPUS_MODEL,
    total_output_tokens: int = 0,
) -> None:
    session = SessionBuilder().with_id(sid).build()
    # inject output tokens via dataclass replace
    session = replace(
        session,
        model=model,
        total_output_tokens=TokenCount(total_output_tokens),
    )
    repos.sessions.upsert(session)


# ─── Rule 1: thinking_tokens proxy ───────────────────────────────────────────

def test_opus_model_with_high_output_triggers_thinking_rule() -> None:
    repos = InMemoryRepositorySet()
    _seed_session(repos, model=_OPUS_MODEL, total_output_tokens=60_000)
    recs = _use_case(repos).execute(SessionId("s-env"), persist=False)
    kinds = {r.kind for r in recs}
    assert RecommendationKind.SET_ENV_VAR in kinds
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]
    targets = {r.target for r in env_recs}
    assert "MAX_THINKING_TOKENS=10000" in targets


def test_non_opus_model_does_not_trigger_thinking_rule() -> None:
    repos = InMemoryRepositorySet()
    _seed_session(repos, model=_SONNET_MODEL, total_output_tokens=200_000)
    recs = _use_case(repos).execute(SessionId("s-env"), persist=False)
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]
    targets = {r.target for r in env_recs}
    assert "MAX_THINKING_TOKENS=10000" not in targets


def test_opus_model_low_output_does_not_trigger_thinking_rule() -> None:
    repos = InMemoryRepositorySet()
    # 19_999 < 20_000 threshold
    _seed_session(repos, model=_OPUS_MODEL, total_output_tokens=19_999)
    recs = _use_case(repos).execute(SessionId("s-env"), persist=False)
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]
    targets = {r.target for r in env_recs}
    assert "MAX_THINKING_TOKENS=10000" not in targets


# ─── Rule 2: subagent_context_tokens ─────────────────────────────────────────

def test_large_subagents_trigger_haiku_rule() -> None:
    repos = InMemoryRepositorySet()
    _seed_session(repos)
    # seed two subagents totalling 60_000 tokens (> 50_000 threshold)
    sub1 = SubagentBuilder().with_parent("s-env").build()
    sub1 = replace(sub1, context_tokens=TokenCount(30_000))
    sub2 = SubagentBuilder().with_parent("s-env").build()
    sub2 = replace(sub2, context_tokens=TokenCount(30_000))
    repos.subagents.upsert(sub1)
    repos.subagents.upsert(sub2)
    recs = _use_case(repos).execute(SessionId("s-env"), persist=False)
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]
    targets = {r.target for r in env_recs}
    assert "CLAUDE_CODE_SUBAGENT_MODEL=haiku" in targets


def test_small_subagents_do_not_trigger_haiku_rule() -> None:
    repos = InMemoryRepositorySet()
    _seed_session(repos)
    sub = SubagentBuilder().with_parent("s-env").build()
    sub = replace(sub, context_tokens=TokenCount(10_000))
    repos.subagents.upsert(sub)
    recs = _use_case(repos).execute(SessionId("s-env"), persist=False)
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]
    targets = {r.target for r in env_recs}
    assert "CLAUDE_CODE_SUBAGENT_MODEL=haiku" not in targets


def test_no_subagent_repo_injected_does_not_crash() -> None:
    """Rule 2 silently produces 0 context tokens when SubagentRepository is absent."""
    repos = InMemoryRepositorySet()
    _seed_session(repos)
    # Should not raise even though repos.subagents exists but is not injected
    recs = _use_case(repos, with_subagents=False).execute(
        SessionId("s-env"), persist=False
    )
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]
    targets = {r.target for r in env_recs}
    assert "CLAUDE_CODE_SUBAGENT_MODEL=haiku" not in targets


# ─── Rule 3: mcp_max_output_seen ─────────────────────────────────────────────

def _add_mcp_tool_call(
    repos: InMemoryRepositorySet,
    sid: str,
    output_tokens: int,
) -> None:
    tc = ToolCallBuilder().in_session(sid).for_tool("mcp__search").build()
    tc = replace(tc, output_tokens=TokenCount(output_tokens))
    repos.tool_calls.append(tc)


def test_large_mcp_output_triggers_cap_rule() -> None:
    repos = InMemoryRepositorySet()
    _seed_session(repos)
    _add_mcp_tool_call(repos, "s-env", output_tokens=25_000)
    recs = _use_case(repos).execute(SessionId("s-env"), persist=False)
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]
    targets = {r.target for r in env_recs}
    assert "MAX_MCP_OUTPUT_TOKENS=15000" in targets


def test_small_mcp_output_does_not_trigger_cap_rule() -> None:
    repos = InMemoryRepositorySet()
    _seed_session(repos)
    _add_mcp_tool_call(repos, "s-env", output_tokens=19_999)
    recs = _use_case(repos).execute(SessionId("s-env"), persist=False)
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]
    targets = {r.target for r in env_recs}
    assert "MAX_MCP_OUTPUT_TOKENS=15000" not in targets


def test_non_mcp_tool_call_does_not_trigger_cap_rule() -> None:
    repos = InMemoryRepositorySet()
    _seed_session(repos)
    # system tool with massive output — should NOT trigger Rule 3
    tc = ToolCallBuilder().in_session("s-env").for_tool("Bash").build()
    tc = replace(tc, output_tokens=TokenCount(50_000))
    repos.tool_calls.append(tc)
    recs = _use_case(repos).execute(SessionId("s-env"), persist=False)
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]
    targets = {r.target for r in env_recs}
    assert "MAX_MCP_OUTPUT_TOKENS=15000" not in targets


# ─── All three rules fire together ───────────────────────────────────────────

def test_all_three_env_var_rules_fire_together() -> None:
    repos = InMemoryRepositorySet()
    # Rule 1: Opus + big output
    _seed_session(repos, model=_OPUS_MODEL, total_output_tokens=60_000)
    # Rule 2: big subagent context
    sub = SubagentBuilder().with_parent("s-env").build()
    sub = replace(sub, context_tokens=TokenCount(60_000))
    repos.subagents.upsert(sub)
    # Rule 3: big MCP output
    _add_mcp_tool_call(repos, "s-env", output_tokens=25_000)

    recs = _use_case(repos).execute(SessionId("s-env"), persist=False)
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]
    targets = {r.target for r in env_recs}
    assert targets == {
        "MAX_THINKING_TOKENS=10000",
        "CLAUDE_CODE_SUBAGENT_MODEL=haiku",
        "MAX_MCP_OUTPUT_TOKENS=15000",
    }
