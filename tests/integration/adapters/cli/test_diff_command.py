"""Integration tests for `ccprophet diff` CLI adapter."""

from __future__ import annotations

import json

from ccprophet.adapters.cli.diff import run_diff_command
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import SessionId
from ccprophet.use_cases.diff_sessions import DiffSessionsUseCase
from tests.fixtures.builders import SessionBuilder, ToolDefBuilder


def _wire() -> tuple[InMemoryRepositorySet, DiffSessionsUseCase]:
    repos = InMemoryRepositorySet()
    uc = DiffSessionsUseCase(
        sessions=repos.sessions,
        tool_defs=repos.tool_defs,
        tool_calls=repos.tool_calls,
    )
    return repos, uc


def test_diff_unknown_session_exits_2(capsys) -> None:  # type: ignore[no-untyped-def]
    _, uc = _wire()
    code = run_diff_command(uc, sid_a="a", sid_b="b", as_json=True)
    assert code == 2
    assert "error" in json.loads(capsys.readouterr().out)


def test_diff_json_shape(capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc = _wire()
    repos.sessions.upsert(SessionBuilder().with_id("a").build())
    repos.sessions.upsert(SessionBuilder().with_id("b").build())
    repos.tool_defs.bulk_add(
        SessionId("a"),
        [ToolDefBuilder().named("Read").with_tokens(100).build()],
    )

    code = run_diff_command(uc, sid_a="a", sid_b="b", as_json=True)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["session_a"] == "a"
    assert payload["session_b"] == "b"
    for key in (
        "input_tokens_delta",
        "output_tokens_delta",
        "tool_call_count_delta",
        "bloat_ratio_delta",
        "tools_added",
        "tools_removed",
        "mcps_added",
        "mcps_removed",
    ):
        assert key in payload
    # tools_added/removed compare *called* tools, not loaded ones — since
    # neither session has a tool_call, those collections are empty.
    assert payload["tools_added"] == []
    assert payload["tools_removed"] == []


def test_diff_rich_path(capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc = _wire()
    repos.sessions.upsert(SessionBuilder().with_id("a").build())
    repos.sessions.upsert(SessionBuilder().with_id("b").build())

    code = run_diff_command(uc, sid_a="a", sid_b="b", as_json=False)
    assert code == 0
