"""Integration tests for `ccprophet bloat` CLI adapter.

Exercises the `run_bloat_command` function with InMemory repos, both `--json`
and rich-table paths, and the `--cost` flag integration with pricing.
"""
from __future__ import annotations

import json

import pytest

from ccprophet.adapters.cli.bloat import run_bloat_command
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.values import SessionId, TokenCount
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
from tests.fixtures.builders import (
    PricingRateBuilder,
    SessionBuilder,
    ToolCallBuilder,
    ToolDefBuilder,
)


def _wire() -> tuple[InMemoryRepositorySet, AnalyzeBloatUseCase]:
    repos = InMemoryRepositorySet()
    uc = AnalyzeBloatUseCase(
        sessions=repos.sessions,
        tool_defs=repos.tool_defs,
        tool_calls=repos.tool_calls,
    )
    return repos, uc


def _seed_session_with_bloat(
    repos: InMemoryRepositorySet, sid: str = "s-1"
) -> None:
    session = SessionBuilder().with_id(sid).build()
    repos.sessions.upsert(session)
    repos.tool_defs.bulk_add(
        SessionId(sid),
        [
            ToolDefBuilder().named("Read").with_tokens(100).build(),
            ToolDefBuilder().named("Write").with_tokens(500).build(),
        ],
    )
    repos.tool_calls.append(
        ToolCallBuilder().in_session(SessionId(sid)).for_tool("Read").build()
    )


def test_bloat_unknown_session_exits_2(capsys) -> None:  # type: ignore[no-untyped-def]
    _, uc = _wire()
    code = run_bloat_command(uc, session="nope", as_json=True)
    assert code == 2


def test_bloat_json_shape(capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc = _wire()
    _seed_session_with_bloat(repos)

    code = run_bloat_command(uc, session="s-1", as_json=True)
    out = capsys.readouterr().out
    payload = json.loads(out)

    assert code == 0
    assert payload["total_tokens"] == 600
    assert payload["bloat_tokens"] == 500  # "Write" loaded but never called
    assert 0.0 <= payload["bloat_ratio"] <= 1.0
    tools = payload["items"]
    assert any(t["tool_name"] == "Write" and not t["used"] for t in tools)
    assert any(t["tool_name"] == "Read" and t["used"] for t in tools)


def test_bloat_rich_path_has_output(capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc = _wire()
    _seed_session_with_bloat(repos)
    code = run_bloat_command(uc, session="s-1", as_json=False)
    assert code == 0


def test_bloat_with_cost_annotates_usd(capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc = _wire()
    _seed_session_with_bloat(repos)
    repos.pricing.add(PricingRateBuilder().for_model("claude-opus-4-7").build())

    code = run_bloat_command(
        uc,
        session="s-1",
        as_json=True,
        with_cost=True,
        sessions_repo=repos.sessions,
        pricing=repos.pricing,
    )
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    # bloat $ is present and non-negative; exact value depends on rate but
    # the field must exist when --cost is set.
    assert "bloat_cost_usd" in out
    assert out["bloat_cost_usd"] is None or out["bloat_cost_usd"] >= 0


def test_bloat_no_active_session_exits_2(capsys) -> None:  # type: ignore[no-untyped-def]
    _, uc = _wire()
    # No session seeded at all — execute_current() should raise SessionNotFound.
    code = run_bloat_command(uc, session=None, as_json=True)
    assert code == 2
