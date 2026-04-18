"""Composition root for `ccprophet mcp`.

Wires DuckDB repositories behind read-only use cases and runs the MCP stdio
server. Keeps zero business logic — any branching lives inside use cases.
"""
from __future__ import annotations

import sys

from ccprophet.harness.commands._shared import connect_readonly as _connect_readonly

_MCP_MISSING_HINT = (
    "ccprophet mcp requires the optional `mcp` extra.\n"
    "Install with:  uv sync --extra mcp\n"
)


def _build_server():  # type: ignore[no-untyped-def]
    """Construct the `CcprophetMcpServer` with production adapters.

    Imported lazily so missing-extra diagnostics in ``main()`` stay clean.
    """
    from ccprophet.adapters.clock.system import SystemClock
    from ccprophet.adapters.mcp.server import CcprophetMcpServer
    from ccprophet.adapters.persistence.duckdb.repositories import (
        DuckDBEventRepository,
        DuckDBPhaseRepository,
        DuckDBSessionRepository,
        DuckDBToolCallRepository,
        DuckDBToolDefRepository,
    )
    from ccprophet.adapters.persistence.duckdb.v2_repositories import (
        DuckDBOutcomeRepository,
        DuckDBPricingProvider,
        DuckDBRecommendationRepository,
    )
    from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
    from ccprophet.use_cases.assess_quality import AssessQualityUseCase
    from ccprophet.use_cases.detect_phases import DetectPhasesUseCase
    from ccprophet.use_cases.estimate_budget import EstimateBudgetUseCase
    from ccprophet.use_cases.list_recommendations import ListRecommendationsUseCase

    conn = _connect_readonly()
    sessions = DuckDBSessionRepository(conn)
    tool_defs = DuckDBToolDefRepository(conn)
    tool_calls = DuckDBToolCallRepository(conn)
    events = DuckDBEventRepository(conn)
    phases = DuckDBPhaseRepository(conn)
    outcomes = DuckDBOutcomeRepository(conn)
    recommendations = DuckDBRecommendationRepository(conn)
    pricing = DuckDBPricingProvider(conn)

    return CcprophetMcpServer(
        analyze_bloat=AnalyzeBloatUseCase(
            sessions=sessions, tool_defs=tool_defs, tool_calls=tool_calls
        ),
        detect_phases=DetectPhasesUseCase(
            sessions=sessions, events=events, phases=phases
        ),
        list_recommendations=ListRecommendationsUseCase(
            recommendations=recommendations
        ),
        estimate_budget=EstimateBudgetUseCase(
            outcomes=outcomes,
            tool_calls=tool_calls,
            tool_defs=tool_defs,
            pricing=pricing,
        ),
        assess_quality=AssessQualityUseCase(
            sessions=sessions,
            tool_calls=tool_calls,
            outcomes=outcomes,
            clock=SystemClock(),
        ),
    )


def main() -> None:
    try:
        import mcp  # noqa: F401
    except ImportError:
        sys.stderr.write(_MCP_MISSING_HINT)
        raise SystemExit(1) from None

    import anyio

    server = _build_server()
    anyio.run(server.run_stdio)
