from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.adapters.web.app import WebUseCases, create_app
from ccprophet.domain.entities import PricingRate
from ccprophet.domain.values import SessionId
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
from ccprophet.use_cases.compute_session_cost import ComputeSessionCostUseCase
from ccprophet.use_cases.detect_phases import DetectPhasesUseCase
from tests.fixtures.builders import (
    EventBuilder,
    SessionBuilder,
    ToolCallBuilder,
    ToolDefBuilder,
)

SID = "web-session-1"


@pytest.fixture
def seeded_repos() -> InMemoryRepositorySet:
    repos = InMemoryRepositorySet()
    session = SessionBuilder().with_id(SID).build()
    repos.sessions.upsert(session)

    # Loaded tool defs: one system tool (used) + one MCP tool (unused → bloat).
    repos.tool_defs.bulk_add(
        SessionId(SID),
        [
            ToolDefBuilder().named("Read").with_tokens(200).from_source("system").build(),
            ToolDefBuilder()
            .named("mcp__github_list")
            .with_tokens(1400)
            .from_source("mcp:github")
            .build(),
        ],
    )

    # Two tool_calls in chronological order so they map to the detected phase.
    for _i, ts in enumerate(
        [
            datetime(2026, 4, 16, 9, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 16, 9, 2, 0, tzinfo=timezone.utc),
        ]
    ):
        repos.tool_calls.append(ToolCallBuilder().in_session(SID).for_tool("Read").at(ts).build())

    # UserPromptSubmit + two PostToolUse events so PhaseDetector emits >=1 phase.
    repos.events.append(
        EventBuilder()
        .for_session(SID)
        .of_type("UserPromptSubmit")
        .at(datetime(2026, 4, 16, 9, 0, 30, tzinfo=timezone.utc))
        .with_hash("h-prompt-1")
        .build()
    )
    repos.events.append(
        EventBuilder()
        .for_session(SID)
        .tool_use("Read", "/tmp/a.py")
        .at(datetime(2026, 4, 16, 9, 1, 0, tzinfo=timezone.utc))
        .with_hash("h-post-1")
        .build()
    )
    repos.events.append(
        EventBuilder()
        .for_session(SID)
        .tool_use("Read", "/tmp/b.py")
        .at(datetime(2026, 4, 16, 9, 2, 0, tzinfo=timezone.utc))
        .with_hash("h-post-2")
        .build()
    )

    # Pricing so the cost endpoint reports a number.
    repos.pricing.add(
        PricingRate(
            rate_id="rate-seed",
            model="claude-opus-4-6",
            input_per_mtok=15.0,
            output_per_mtok=75.0,
            effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            source="test",
            currency="USD",
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
    app = create_app(uc)
    return TestClient(app)


def test_healthz_returns_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_index_serves_html(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<html" in r.text.lower()
    # Confirm the bundled D3 reference is local.
    assert "./vendor/d3.v7.min.js" in r.text


def test_vendor_asset_served_locally(client: TestClient) -> None:
    r = client.get("/vendor/d3.v7.min.js")
    assert r.status_code == 200
    # D3 file starts with a banner comment — check the prefix to avoid binary diff noise.
    assert r.content[:20].startswith(b"// https://d3js.org")


def test_vendor_asset_missing_returns_404(client: TestClient) -> None:
    r = client.get("/vendor/does-not-exist.js")
    assert r.status_code == 404


def test_list_sessions_returns_list_shape(client: TestClient) -> None:
    r = client.get("/api/sessions")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert any(s["session_id"] == SID for s in rows)
    first = rows[0]
    for key in ("session_id", "model", "started_at", "is_active"):
        assert key in first


def test_session_detail_unknown_returns_404(client: TestClient) -> None:
    r = client.get("/api/sessions/does-not-exist")
    assert r.status_code == 404


def test_session_detail_includes_bloat_and_cost(client: TestClient) -> None:
    r = client.get(f"/api/sessions/{SID}")
    assert r.status_code == 200
    body = r.json()
    assert body["session"]["session_id"] == SID
    assert body["bloat"]["bloat_tokens"] == 1400  # unused mcp tool
    assert body["cost"] is not None
    assert body["cost"]["currency"] == "USD"


def test_session_dag_returns_nodes_and_edges(client: TestClient) -> None:
    r = client.get(f"/api/sessions/{SID}/dag")
    assert r.status_code == 200
    body = r.json()
    assert "nodes" in body and "edges" in body
    node_ids = {n["id"] for n in body["nodes"]}
    assert f"session:{SID}" in node_ids
    # Tool calls from the seeded session should be present.
    tool_nodes = [n for n in body["nodes"] if n["kind"] == "tool_call"]
    assert len(tool_nodes) == 2
    # Phase nodes should exist (PhaseDetector emitted at least one phase).
    phase_nodes = [n for n in body["nodes"] if n["kind"] == "phase"]
    assert phase_nodes, "expected at least one phase node from detected phases"
    # Every edge should reference real node ids.
    for e in body["edges"]:
        assert e["source"] in node_ids
        assert e["target"] in node_ids


def test_session_bloat_endpoint_returns_summary_keys(client: TestClient) -> None:
    r = client.get(f"/api/sessions/{SID}/bloat")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "total_tokens",
        "bloat_tokens",
        "bloat_ratio",
        "bloat_percent",
        "used_count",
        "bloat_count",
        "by_source",
    ):
        assert key in body
    assert body["bloat_tokens"] == 1400


def test_session_detail_handles_missing_pricing(client: TestClient) -> None:
    # Swap the session model to one with no pricing rate on record; cost becomes None.
    # We do this by issuing the request against a second session with unknown model.
    repos = InMemoryRepositorySet()
    other_sid = "web-session-nopricing"
    repos.sessions.upsert(SessionBuilder().with_id(other_sid).build())
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
    c = TestClient(create_app(uc))
    r = c.get(f"/api/sessions/{other_sid}")
    assert r.status_code == 200
    assert r.json()["cost"] is None


def test_web_main_refuses_non_localhost() -> None:
    from ccprophet.harness.web_main import serve

    with pytest.raises(SystemExit) as exc:
        serve(host="0.0.0.0", port=65535)
    assert exc.value.code == 2
