from __future__ import annotations

from dataclasses import replace

import pytest

from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import ToolDef
from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import SessionId, TokenCount
from ccprophet.use_cases.diff_sessions import DiffSessionsUseCase
from tests.fixtures.builders import SessionBuilder, ToolCallBuilder


def _uc(repos: InMemoryRepositorySet) -> DiffSessionsUseCase:
    return DiffSessionsUseCase(
        sessions=repos.sessions,
        tool_defs=repos.tool_defs,
        tool_calls=repos.tool_calls,
    )


def _seed_two(repos: InMemoryRepositorySet) -> None:
    a = replace(
        SessionBuilder().with_id("a").build(),
        total_input_tokens=TokenCount(100_000),
        total_output_tokens=TokenCount(10_000),
    )
    b = replace(
        SessionBuilder().with_id("b").build(),
        total_input_tokens=TokenCount(60_000),
        total_output_tokens=TokenCount(8_000),
        compacted=False,
    )
    repos.sessions.upsert(a)
    repos.sessions.upsert(b)
    repos.tool_defs.bulk_add(
        SessionId("a"),
        [ToolDef("mcp__github_x", TokenCount(500), "mcp:github")],
    )
    repos.tool_defs.bulk_add(
        SessionId("b"),
        [
            ToolDef("mcp__github_x", TokenCount(500), "mcp:github"),
            ToolDef("mcp__linear_y", TokenCount(400), "mcp:linear"),
        ],
    )
    repos.tool_calls.append(
        ToolCallBuilder().in_session(SessionId("a")).for_tool("mcp__github_x").build()
    )
    repos.tool_calls.append(
        ToolCallBuilder().in_session(SessionId("b")).for_tool("mcp__github_x").build()
    )
    repos.tool_calls.append(
        ToolCallBuilder().in_session(SessionId("b")).for_tool("mcp__linear_y").build()
    )


def test_missing_session_raises() -> None:
    repos = InMemoryRepositorySet()
    with pytest.raises(SessionNotFound):
        _uc(repos).execute(SessionId("a"), SessionId("b"))


def test_diff_captures_token_and_mcp_deltas() -> None:
    repos = InMemoryRepositorySet()
    _seed_two(repos)
    diff = _uc(repos).execute(SessionId("a"), SessionId("b"))
    assert diff.input_tokens_delta == -40_000
    assert diff.output_tokens_delta == -2_000
    assert diff.tool_call_count_delta == 1
    assert "linear" in diff.mcps_added
    assert diff.tools_added == ("mcp__linear_y",)
