from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

from ccprophet.adapters.cli.recommend import run_recommend_command
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import ToolDef
from ccprophet.domain.values import RecommendationKind, SessionId, TokenCount
from ccprophet.use_cases.recommend_action import RecommendActionUseCase
from tests.fixtures.builders import SessionBuilder, SubagentBuilder, ToolCallBuilder

FROZEN = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _use_case(
    repos: InMemoryRepositorySet, *, with_subagents: bool = False
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


def _seed(repos: InMemoryRepositorySet) -> None:
    sid = "s-rec"
    repos.sessions.upsert(SessionBuilder().with_id(sid).build())
    repos.tool_defs.bulk_add(
        SessionId(sid),
        [
            ToolDef("Read", TokenCount(500), "system"),
            ToolDef("mcp__github_x", TokenCount(1_400), "mcp:github"),
        ],
    )
    repos.tool_calls.append(ToolCallBuilder().in_session(sid).for_tool("Read").build())


def test_no_session_returns_2(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    code = run_recommend_command(_use_case(repos), as_json=True)
    assert code == 2
    assert "error" in json.loads(capsys.readouterr().out)


def test_json_output(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    _seed(repos)
    code = run_recommend_command(_use_case(repos), session="s-rec", as_json=True)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert len(payload) == 1
    assert payload[0]["kind"] == "prune_mcp"
    assert payload[0]["target"] == "mcp__github_x"


def test_persist_controls_db_writes(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    _seed(repos)
    run_recommend_command(_use_case(repos), session="s-rec", as_json=True, persist=False)
    assert list(repos.recommendations.list_pending()) == []


# ─── env-var recommendations appear in JSON output ───────────────────────────


def _seed_env_var_session(repos: InMemoryRepositorySet) -> None:
    """Seed a session that triggers Rule 2 (heavy subagent use)."""
    sid = "s-env-cli"
    session = SessionBuilder().with_id(sid).build()
    repos.sessions.upsert(session)
    # Seed two subagents with 30k tokens each → 60k total > 50k threshold
    sub1 = SubagentBuilder().with_parent(sid).build()
    sub1 = replace(sub1, context_tokens=TokenCount(30_000))
    sub2 = SubagentBuilder().with_parent(sid).build()
    sub2 = replace(sub2, context_tokens=TokenCount(30_000))
    repos.subagents.upsert(sub1)
    repos.subagents.upsert(sub2)


def test_env_var_recommendation_in_json_output(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    _seed_env_var_session(repos)
    code = run_recommend_command(
        _use_case(repos, with_subagents=True),
        session="s-env-cli",
        as_json=True,
        persist=False,
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    kinds = {r["kind"] for r in payload}
    assert RecommendationKind.SET_ENV_VAR.value in kinds
    env_recs = [r for r in payload if r["kind"] == RecommendationKind.SET_ENV_VAR.value]
    targets = {r["target"] for r in env_recs}
    assert "CLAUDE_CODE_SUBAGENT_MODEL=haiku" in targets


def test_env_var_rec_has_required_fields(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    _seed_env_var_session(repos)
    run_recommend_command(
        _use_case(repos, with_subagents=True),
        session="s-env-cli",
        as_json=True,
        persist=False,
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    env_recs = [r for r in payload if r["kind"] == RecommendationKind.SET_ENV_VAR.value]
    assert env_recs, "expected at least one SET_ENV_VAR recommendation"
    r = env_recs[0]
    assert "rec_id" in r
    assert "kind" in r
    assert "target" in r
    assert "est_savings_tokens" in r
    assert "confidence" in r
    assert "rationale" in r
