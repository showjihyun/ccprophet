"""Integration tests for the Replay endpoint (PRD F9 Phase 1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.adapters.web.app import WebUseCases, create_app
from ccprophet.domain.entities import Phase, PricingRate
from ccprophet.domain.values import PhaseType, SessionId, TokenCount
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
from ccprophet.use_cases.compute_session_cost import ComputeSessionCostUseCase
from ccprophet.use_cases.detect_phases import DetectPhasesUseCase
from tests.fixtures.builders import (
    EventBuilder,
    SessionBuilder,
    ToolCallBuilder,
    ToolDefBuilder,
)

SID = "replay-session-1"
T0 = datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def seeded_repos() -> InMemoryRepositorySet:
    repos = InMemoryRepositorySet()
    repos.sessions.upsert(SessionBuilder().with_id(SID).build())

    # Tool defs — one used, one bloat.
    repos.tool_defs.bulk_add(
        SessionId(SID),
        [
            ToolDefBuilder().named("Read").with_tokens(200).from_source("system").build(),
            ToolDefBuilder().named("mcp__unused").with_tokens(800).from_source("mcp:jira").build(),
        ],
    )

    # 3 persisted phases spanning the 10-minute session.
    repos.phases.replace_for_session(
        SessionId(SID),
        [
            Phase(
                phase_id="ph-plan",
                session_id=SessionId(SID),
                phase_type=PhaseType.PLANNING,
                start_ts=T0,
                end_ts=T0 + timedelta(minutes=3),
                input_tokens=TokenCount(100),
                output_tokens=TokenCount(200),
            ),
            Phase(
                phase_id="ph-impl",
                session_id=SessionId(SID),
                phase_type=PhaseType.IMPLEMENTATION,
                start_ts=T0 + timedelta(minutes=3),
                end_ts=T0 + timedelta(minutes=7),
                input_tokens=TokenCount(200),
                output_tokens=TokenCount(300),
            ),
            Phase(
                phase_id="ph-rev",
                session_id=SessionId(SID),
                phase_type=PhaseType.REVIEW,
                start_ts=T0 + timedelta(minutes=7),
                end_ts=T0 + timedelta(minutes=10),
                input_tokens=TokenCount(100),
                output_tokens=TokenCount(100),
            ),
        ],
    )

    # 5 tool_calls spread over 10 minutes.
    offsets_min = [1, 2, 4, 6, 9]
    for off in offsets_min:
        repos.tool_calls.append(
            ToolCallBuilder()
            .in_session(SID)
            .for_tool("Read")
            .at(T0 + timedelta(minutes=off))
            .build()
        )

    # A sparse event stream so DetectPhasesUseCase has something to replace
    # (it will overwrite the persisted phases above; that's intentional —
    # the endpoint then falls back to ``phases.list_for_session`` when the
    # detector returns nothing useful).
    repos.events.append(
        EventBuilder()
        .for_session(SID)
        .of_type("UserPromptSubmit")
        .at(T0)
        .with_hash("h-replay-0")
        .build()
    )
    for i, off in enumerate(offsets_min):
        repos.events.append(
            EventBuilder()
            .for_session(SID)
            .tool_use("Read", f"/tmp/f{i}.py")
            .at(T0 + timedelta(minutes=off))
            .with_hash(f"h-replay-{i + 1}")
            .build()
        )

    repos.pricing.add(
        PricingRate(
            rate_id="rate-replay",
            model="claude-opus-4-6",
            input_per_mtok=15.0,
            output_per_mtok=75.0,
            effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source="test",
        )
    )
    return repos


@pytest.fixture
def client(seeded_repos: InMemoryRepositorySet) -> TestClient:
    uc = WebUseCases(
        analyze_bloat=AnalyzeBloatUseCase(
            sessions=seeded_repos.sessions,
            tool_defs=seeded_repos.tool_defs,
            tool_calls=seeded_repos.tool_calls,
        ),
        detect_phases=DetectPhasesUseCase(
            sessions=seeded_repos.sessions,
            events=seeded_repos.events,
            phases=seeded_repos.phases,
        ),
        compute_session_cost=ComputeSessionCostUseCase(
            sessions=seeded_repos.sessions, pricing=seeded_repos.pricing
        ),
        sessions=seeded_repos.sessions,
        tool_calls=seeded_repos.tool_calls,
        phases=seeded_repos.phases,
        pricing=seeded_repos.pricing,
        tool_defs=seeded_repos.tool_defs,
    )
    return TestClient(create_app(uc))


def test_replay_returns_200_and_expected_top_level_shape(client: TestClient) -> None:
    r = client.get(f"/api/sessions/{SID}/replay")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "session",
        "timeline",
        "node_snapshots",
        "total_duration_sec",
        "total_tokens",
        "final_bloat_ratio",
    ):
        assert key in body
    assert body["session"]["session_id"] == SID
    assert isinstance(body["timeline"], list)
    assert isinstance(body["node_snapshots"], list)


def test_replay_timeline_sorted_ascending(client: TestClient) -> None:
    body = client.get(f"/api/sessions/{SID}/replay").json()
    stamps = [step["ts"] for step in body["timeline"]]
    assert stamps == sorted(stamps)


def test_replay_cumulative_tokens_monotonic(client: TestClient) -> None:
    body = client.get(f"/api/sessions/{SID}/replay").json()
    cumulative = [step["cumulative_tokens"] for step in body["timeline"]]
    assert cumulative == sorted(cumulative)


def test_replay_total_duration_matches_first_last_event(client: TestClient) -> None:
    body = client.get(f"/api/sessions/{SID}/replay").json()
    assert len(body["timeline"]) >= 2
    first = datetime.fromisoformat(body["timeline"][0]["ts"])
    last = datetime.fromisoformat(body["timeline"][-1]["ts"])
    assert body["total_duration_sec"] == pytest.approx((last - first).total_seconds())


def test_replay_node_snapshots_grow_and_match_timeline_length(client: TestClient) -> None:
    body = client.get(f"/api/sessions/{SID}/replay").json()
    assert len(body["node_snapshots"]) == len(body["timeline"])
    seen: set[str] = set()
    for snap in body["node_snapshots"]:
        ids = set(snap["visible_node_ids"])
        assert seen.issubset(ids), "snapshot shrank between steps"
        seen = ids
    # Every tool call ends up visible in the last snapshot.
    final = set(body["node_snapshots"][-1]["visible_node_ids"])
    tool_visible = sum(1 for nid in final if nid.startswith("tool:"))
    assert tool_visible == 5
    assert f"session:{SID}" in final


def test_replay_contains_expected_timeline_event_kinds(client: TestClient) -> None:
    body = client.get(f"/api/sessions/{SID}/replay").json()
    kinds = {step["kind"] for step in body["timeline"]}
    assert {"phase_start", "tool_call"}.issubset(kinds)


def test_replay_unknown_session_returns_404(client: TestClient) -> None:
    r = client.get("/api/sessions/does-not-exist/replay")
    assert r.status_code == 404


def test_existing_dag_endpoint_still_works(client: TestClient) -> None:
    """Ensure we didn't break the DAG route while adding replay."""
    r = client.get(f"/api/sessions/{SID}/dag")
    assert r.status_code == 200
    assert "nodes" in r.json()
