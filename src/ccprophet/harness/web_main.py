"""Composition root for ``ccprophet serve`` (PRD F4).

Wires DuckDB repositories behind read-only use cases and hands the resulting
FastAPI app to uvicorn. Bound to 127.0.0.1 by default and refuses any other
host (NFR-2, ARCHITECT §9). No business logic lives here.
"""
from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

DB_PATH = Path.home() / ".claude-prophet" / "events.duckdb"

_WEB_MISSING_HINT = (
    "ccprophet serve requires the optional `web` extra.\n"
    "Install with:  uv sync --extra web\n"
)

_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _connect_readonly():  # type: ignore[no-untyped-def]
    import duckdb

    if not DB_PATH.exists():
        raise SystemExit(
            f"ccprophet DB not found at {DB_PATH}\n"
            f"Run `ccprophet install` or trigger a hook first."
        )
    return duckdb.connect(str(DB_PATH), read_only=True)


def _build_app():  # type: ignore[no-untyped-def]
    """Assemble production adapters + use cases and return a FastAPI app."""
    from ccprophet.adapters.persistence.duckdb.repositories import (
        DuckDBEventRepository,
        DuckDBPhaseRepository,
        DuckDBSessionRepository,
        DuckDBToolCallRepository,
        DuckDBToolDefRepository,
    )
    from ccprophet.adapters.persistence.duckdb.v2_repositories import (
        DuckDBPricingProvider,
    )
    from ccprophet.adapters.web.app import WebUseCases, create_app
    from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
    from ccprophet.use_cases.compute_session_cost import ComputeSessionCostUseCase
    from ccprophet.use_cases.detect_phases import DetectPhasesUseCase

    conn = _connect_readonly()
    sessions = DuckDBSessionRepository(conn)
    tool_defs = DuckDBToolDefRepository(conn)
    tool_calls = DuckDBToolCallRepository(conn)
    events = DuckDBEventRepository(conn)
    phases = DuckDBPhaseRepository(conn)
    pricing = DuckDBPricingProvider(conn)

    uc = WebUseCases(
        analyze_bloat=AnalyzeBloatUseCase(
            sessions=sessions, tool_defs=tool_defs, tool_calls=tool_calls
        ),
        detect_phases=DetectPhasesUseCase(
            sessions=sessions, events=events, phases=phases
        ),
        compute_session_cost=ComputeSessionCostUseCase(
            sessions=sessions, pricing=pricing
        ),
        sessions=sessions,
        tool_calls=tool_calls,
        phases=phases,
        pricing=pricing,
        tool_defs=tool_defs,
    )
    return create_app(uc)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
) -> None:
    """Boot the local Work DAG viewer.

    Raises ``SystemExit`` if the caller asks for a non-localhost bind or the
    optional ``web`` extra isn't installed.
    """
    if host not in _ALLOWED_HOSTS:
        sys.stderr.write(
            f"ccprophet serve refuses host={host!r}; "
            f"localhost only (NFR-2). Allowed: {sorted(_ALLOWED_HOSTS)}\n"
        )
        raise SystemExit(2)

    try:
        import uvicorn  # noqa: F401
        import fastapi  # noqa: F401
    except ImportError:
        sys.stderr.write(_WEB_MISSING_HINT)
        raise SystemExit(1) from None

    import uvicorn

    app = _build_app()

    if open_browser:
        url = f"http://{host}:{port}/"
        threading.Timer(0.5, lambda: webbrowser.open_new_tab(url)).start()

    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    serve()
