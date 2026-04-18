"""Unit tests for the CcprophetMcpServer handlers.

Tests go through `dispatch()` to exercise the same path an MCP call-tool
request would take, while skipping the async stdio transport. Use-case
dependencies are real in-memory Fakes (per LAYERING §7.3 — Fake ≫ Mock).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("mcp", reason="requires the `mcp` optional extra")

from ccprophet.adapters.clock.system import FrozenClock
from ccprophet.adapters.mcp.server import CcprophetMcpServer
from ccprophet.adapters.persistence.inmemory.repositories import (
    InMemoryRepositorySet,
)
from ccprophet.domain.entities import ToolDef
from ccprophet.domain.values import (
    OutcomeLabelValue,
    SessionId,
    TokenCount,
)
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
from ccprophet.use_cases.assess_quality import AssessQualityUseCase
from ccprophet.use_cases.detect_phases import DetectPhasesUseCase
from ccprophet.use_cases.estimate_budget import EstimateBudgetUseCase
from ccprophet.use_cases.list_recommendations import ListRecommendationsUseCase
from tests.fixtures.builders import (
    OutcomeLabelBuilder,
    PricingRateBuilder,
    RecommendationBuilder,
    SessionBuilder,
    ToolCallBuilder,
)

FROZEN = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _build_server(repos: InMemoryRepositorySet) -> CcprophetMcpServer:
    return CcprophetMcpServer(
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
        list_recommendations=ListRecommendationsUseCase(
            recommendations=repos.recommendations
        ),
        estimate_budget=EstimateBudgetUseCase(
            outcomes=repos.outcomes,
            tool_calls=repos.tool_calls,
            tool_defs=repos.tool_defs,
            pricing=repos.pricing,
        ),
        assess_quality=AssessQualityUseCase(
            sessions=repos.sessions,
            tool_calls=repos.tool_calls,
            outcomes=repos.outcomes,
            clock=FrozenClock(FROZEN),
        ),
    )


def _seed_active_bloat_session(
    repos: InMemoryRepositorySet, sid: str = "s-live"
) -> None:
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


# -- get_current_bloat --------------------------------------------------------


class TestGetCurrentBloat:
    def test_returns_shaped_bloat_for_active_session(self) -> None:
        repos = InMemoryRepositorySet()
        _seed_active_bloat_session(repos)
        payload = _build_server(repos).dispatch("get_current_bloat", {})

        assert "error" not in payload
        assert payload["bloat_tokens"] == 1_400
        assert payload["total_tokens"] == 1_900
        assert payload["bloat_count"] == 1
        assert payload["used_count"] == 1
        assert "system" in payload["used_sources"]
        assert any(b["source"] == "mcp:github" for b in payload["by_source"])

    def test_returns_error_payload_when_no_active_session(self) -> None:
        repos = InMemoryRepositorySet()
        payload = _build_server(repos).dispatch("get_current_bloat", {})
        # unified code: all SessionNotFound paths emit `session_not_found`
        assert payload["code"] == "session_not_found"
        assert "error" in payload


# -- get_phase_breakdown ------------------------------------------------------


class TestGetPhaseBreakdown:
    def test_explicit_sid_unknown_session_returns_error(self) -> None:
        repos = InMemoryRepositorySet()
        payload = _build_server(repos).dispatch(
            "get_phase_breakdown", {"sid": "nope"}
        )
        assert payload["code"] == "session_not_found"

    def test_null_sid_uses_active_session(self) -> None:
        repos = InMemoryRepositorySet()
        _seed_active_bloat_session(repos)
        payload = _build_server(repos).dispatch(
            "get_phase_breakdown", {"sid": None}
        )
        assert "phases" in payload
        assert isinstance(payload["phases"], list)


# -- recommend_action ---------------------------------------------------------


class TestRecommendAction:
    def test_returns_empty_list_when_none_pending(self) -> None:
        repos = InMemoryRepositorySet()
        payload = _build_server(repos).dispatch("recommend_action", {})
        assert payload == {"recommendations": []}

    def test_returns_pending_recommendations(self) -> None:
        repos = InMemoryRepositorySet()
        repos.recommendations.save_all(
            [RecommendationBuilder().in_session("s-1").build()]
        )
        payload = _build_server(repos).dispatch(
            "recommend_action", {"limit": 10}
        )
        assert len(payload["recommendations"]) == 1
        rec = payload["recommendations"][0]
        assert rec["kind"] == "prune_mcp"
        assert rec["session_id"] == "s-1"
        assert rec["status"] == "pending"
        assert rec["est_savings_tokens"] == 1_400


# -- estimate_budget ----------------------------------------------------------


class TestEstimateBudget:
    def test_insufficient_samples_error(self) -> None:
        repos = InMemoryRepositorySet()
        payload = _build_server(repos).dispatch(
            "estimate_budget", {"task_type": "refactor"}
        )
        assert payload["code"] == "insufficient_samples"

    def test_returns_envelope_when_enough_successes(self) -> None:
        repos = InMemoryRepositorySet()
        repos.pricing.add(
            PricingRateBuilder().for_model("claude-opus-4-6").build()
        )
        for i in range(3):
            sid = f"success-{i}"
            repos.sessions.upsert(SessionBuilder().with_id(sid).build())
            repos.outcomes.set_label(
                OutcomeLabelBuilder()
                .for_session(sid)
                .with_label(OutcomeLabelValue.SUCCESS)
                .with_task("refactor")
                .build()
            )
            repos.tool_calls.append(
                ToolCallBuilder().in_session(sid).for_tool("Read").build()
            )
            repos.tool_defs.bulk_add(
                SessionId(sid), [ToolDef("Read", TokenCount(500), "system")]
            )

        payload = _build_server(repos).dispatch(
            "estimate_budget", {"task_type": "refactor"}
        )
        assert "error" not in payload
        assert payload["task_type"] == "refactor"
        assert payload["sample_size"] == 3
        assert "best_config" in payload


# -- quality_report -----------------------------------------------------------


class TestQualityReport:
    def test_returns_reports_list(self) -> None:
        repos = InMemoryRepositorySet()
        payload = _build_server(repos).dispatch(
            "quality_report", {"window_days": 7, "baseline_days": 30}
        )
        assert "reports" in payload
        assert isinstance(payload["reports"], list)


# -- dispatch safety ----------------------------------------------------------


class TestDispatchSafety:
    def test_unknown_tool_returns_error_payload(self) -> None:
        repos = InMemoryRepositorySet()
        payload = _build_server(repos).dispatch("nonexistent", {})
        assert payload["code"] == "unknown_tool"

    def test_dispatch_does_not_persist_recommendations(self) -> None:
        """AP-7 / read-only: MCP must not side-effect the DB."""
        repos = InMemoryRepositorySet()
        _seed_active_bloat_session(repos)
        _build_server(repos).dispatch("get_current_bloat", {})
        _build_server(repos).dispatch(
            "get_phase_breakdown", {"sid": "s-live"}
        )
        # Phases are persisted by DetectPhasesUseCase.execute() by design —
        # that's not a new write from MCP, it's upserting derived state.
        # What MUST NOT happen is writing recommendations or outcomes.
        assert list(repos.recommendations.list_pending()) == []
        assert repos.outcomes.get_label(SessionId("s-live")) is None


# -- tool discovery -----------------------------------------------------------


class TestToolDefinitions:
    def test_declares_five_tools_with_descriptions(self) -> None:
        from ccprophet.adapters.mcp.server import _tool_definitions

        tools = _tool_definitions()
        names = {t.name for t in tools}
        assert names == {
            "get_current_bloat",
            "get_phase_breakdown",
            "recommend_action",
            "estimate_budget",
            "quality_report",
        }
        # Keep the combined description+schema tight (NFR FR-6.3 budget).
        for t in tools:
            assert t.description and len(t.description) < 200
