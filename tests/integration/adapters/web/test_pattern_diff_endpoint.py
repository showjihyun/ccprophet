"""Integration tests for the pattern-diff endpoint (PRD F9 / FR-9.3)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.adapters.web.app import WebUseCases, create_app
from ccprophet.domain.values import SessionId, TokenCount
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
from ccprophet.use_cases.compute_session_cost import ComputeSessionCostUseCase
from ccprophet.use_cases.detect_phases import DetectPhasesUseCase
from tests.fixtures.builders import (
    SessionBuilder,
    ToolCallBuilder,
    ToolDefBuilder,
)

SID_A = "pattern-diff-a"
SID_B = "pattern-diff-b"
T0 = datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc)


def _seed(repos: InMemoryRepositorySet) -> None:
    base_a = SessionBuilder().with_id(SID_A).build()
    base_b = SessionBuilder().with_id(SID_B).build()
    # Session A: small input, uses Read only.
    repos.sessions.upsert(replace(base_a, total_input_tokens=TokenCount(500)))
    # Session B: much larger input (+300%), uses Bash/Grep instead → triggers
    # both token_delta (critical) and tool_mix_shift (warn).
    repos.sessions.upsert(replace(base_b, total_input_tokens=TokenCount(2000)))

    repos.tool_defs.bulk_add(
        SessionId(SID_A),
        [
            ToolDefBuilder().named("Read").with_tokens(100).from_source("system").build(),
            ToolDefBuilder()
            .named("mcp__gh")
            .with_tokens(1000)
            .from_source("mcp:github")
            .build(),
        ],
    )
    repos.tool_defs.bulk_add(
        SessionId(SID_B),
        [
            ToolDefBuilder().named("Bash").with_tokens(100).from_source("system").build(),
            ToolDefBuilder().named("Grep").with_tokens(100).from_source("system").build(),
        ],
    )
    for i, name in enumerate(["Read"]):
        repos.tool_calls.append(
            ToolCallBuilder()
            .in_session(SID_A)
            .for_tool(name)
            .at(T0 + timedelta(seconds=i))
            .build()
        )
    for i, name in enumerate(["Bash", "Grep"]):
        repos.tool_calls.append(
            ToolCallBuilder()
            .in_session(SID_B)
            .for_tool(name)
            .at(T0 + timedelta(seconds=i))
            .build()
        )


@pytest.fixture
def client() -> TestClient:
    repos = InMemoryRepositorySet()
    _seed(repos)
    uc = WebUseCases(
        analyze_bloat=AnalyzeBloatUseCase(
            sessions=repos.sessions,
            tool_defs=repos.tool_defs,
            tool_calls=repos.tool_calls,
        ),
        detect_phases=DetectPhasesUseCase(
            sessions=repos.sessions,
            events=repos.events,
            phases=repos.phases,
        ),
        compute_session_cost=ComputeSessionCostUseCase(
            sessions=repos.sessions, pricing=repos.pricing
        ),
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        phases=repos.phases,
        pricing=repos.pricing,
        tool_defs=repos.tool_defs,
    )
    return TestClient(create_app(uc))


def test_pattern_diff_returns_200_and_expected_shape(client: TestClient) -> None:
    r = client.get(f"/api/sessions/{SID_A}/pattern-diff", params={"against": SID_B})
    assert r.status_code == 200
    body = r.json()
    assert body["session_a"] == SID_A
    assert body["session_b"] == SID_B
    assert isinstance(body["findings"], list)
    assert body["headline"]
    kinds = {f["kind"] for f in body["findings"]}
    # Our seed guarantees at least these two rules fire.
    assert "token_delta" in kinds
    assert "tool_mix_shift" in kinds
    for f in body["findings"]:
        assert f["severity"] in {"info", "warn", "critical"}
        assert f["detail"]


def test_pattern_diff_unknown_left_session_returns_404(client: TestClient) -> None:
    r = client.get(
        "/api/sessions/does-not-exist/pattern-diff",
        params={"against": SID_B},
    )
    assert r.status_code == 404


def test_pattern_diff_unknown_right_session_returns_404(client: TestClient) -> None:
    r = client.get(
        f"/api/sessions/{SID_A}/pattern-diff",
        params={"against": "does-not-exist"},
    )
    assert r.status_code == 404


def test_pattern_diff_missing_against_query_returns_422(client: TestClient) -> None:
    r = client.get(f"/api/sessions/{SID_A}/pattern-diff")
    assert r.status_code == 422
