from __future__ import annotations

import json
from dataclasses import replace

from ccprophet.adapters.cli.statusline import run_statusline_command
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.domain.entities import ToolDef
from ccprophet.domain.values import SessionId, TokenCount
from tests.fixtures.builders import (
    PricingRateBuilder,
    SessionBuilder,
    ToolCallBuilder,
)


def test_no_session_prints_placeholder(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    code = run_statusline_command(repos.sessions)
    assert code == 0
    assert "no session" in capsys.readouterr().out


def test_formats_session_line(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    session = replace(
        SessionBuilder().with_id("8bd6e079-abc").build(),
        model="claude-opus-4-7",
        total_input_tokens=TokenCount(2_500_000),
        total_output_tokens=TokenCount(85_000),
    )
    repos.sessions.upsert(session)
    code = run_statusline_command(repos.sessions)
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert "[8bd6e079]" in out
    assert "claude-opus-4-7" in out
    assert "2.5M" in out
    assert "85k" in out


def test_with_pricing_shows_cost(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    session = replace(
        SessionBuilder().with_id("cost").build(),
        model="claude-opus-4-7",
        total_input_tokens=TokenCount(1_000_000),
        total_output_tokens=TokenCount(0),
    )
    repos.sessions.upsert(session)
    repos.pricing.add(PricingRateBuilder().for_model("claude-opus-4-7").build())
    # G3 (FR-10.3): cost is opt-in via `with_cost=True` (i.e. `--cost` flag).
    code = run_statusline_command(repos.sessions, repos.pricing, with_cost=True)
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert "$15.00" in out


def test_without_cost_flag_hides_cost(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    session = replace(
        SessionBuilder().with_id("nocost").build(),
        model="claude-opus-4-7",
        total_input_tokens=TokenCount(1_000_000),
    )
    repos.sessions.upsert(session)
    repos.pricing.add(PricingRateBuilder().for_model("claude-opus-4-7").build())
    code = run_statusline_command(repos.sessions, repos.pricing)  # default with_cost=False
    out = capsys.readouterr().out.strip()
    assert code == 0
    assert "$" not in out


def test_with_bloat_shows_percent(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    session = SessionBuilder().with_id("bloat").build()
    repos.sessions.upsert(session)
    repos.tool_defs.bulk_add(
        SessionId("bloat"),
        [
            ToolDef("Read", TokenCount(500), "system"),
            ToolDef("mcp__unused", TokenCount(1_500), "mcp:unused"),
        ],
    )
    repos.tool_calls.append(
        ToolCallBuilder().in_session(SessionId("bloat")).for_tool("Read").build()
    )
    run_statusline_command(
        repos.sessions,
        tool_defs_for=repos.tool_defs.list_for_session,
        tool_calls_for=repos.tool_calls.list_for_session,
    )
    out = capsys.readouterr().out.strip()
    assert "bloat" in out
    assert "75%" in out


def test_json_output(capsys) -> None:  # type: ignore[no-untyped-def]
    repos = InMemoryRepositorySet()
    session = SessionBuilder().with_id("json-session-id-1234").build()
    repos.sessions.upsert(session)
    code = run_statusline_command(repos.sessions, as_json=True)
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["session_id"] == "json-ses"  # first 8 chars
