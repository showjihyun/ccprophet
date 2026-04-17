from __future__ import annotations

import json
from datetime import datetime, timezone

from ccprophet.adapters.cli.recommend import run_recommend_command
from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import ToolDef
from ccprophet.domain.values import SessionId, TokenCount
from ccprophet.use_cases.recommend_action import RecommendActionUseCase
from tests.fixtures.builders import SessionBuilder, ToolCallBuilder

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
    repos.tool_calls.append(
        ToolCallBuilder().in_session(sid).for_tool("Read").build()
    )


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
    run_recommend_command(
        _use_case(repos), session="s-rec", as_json=True, persist=False
    )
    assert list(repos.recommendations.list_pending()) == []
