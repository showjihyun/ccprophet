"""FastAPI application for the ccprophet Work DAG viewer (PRD F4).

All endpoints are read-only. Bound to 127.0.0.1 by the harness; no CORS is
configured on purpose (NFR-2). Business logic lives in use cases — this
adapter only shapes domain objects into JSON (see ``shapers``) and serves
the bundled HTML assets from ``web/`` at the repo root.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from ccprophet.adapters.web.pattern_diff_shaper import build_pattern_diff
from ccprophet.adapters.web.replay_shaper import build_replay
from ccprophet.adapters.web.shapers import (
    bloat_to_dict,
    build_dag,
    cost_to_dict,
    session_to_dict,
)
from ccprophet.domain.entities import CostBreakdown, Session
from ccprophet.domain.errors import SessionNotFound, UnknownPricingModel
from ccprophet.domain.services.pattern_diff import PatternDiffAnalyzer
from ccprophet.domain.values import SessionId

if TYPE_CHECKING:
    from ccprophet.ports.pricing import PricingProvider
    from ccprophet.ports.repositories import (
        PhaseRepository,
        SessionRepository,
        ToolCallRepository,
        ToolDefRepository,
    )
    from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
    from ccprophet.use_cases.compute_session_cost import ComputeSessionCostUseCase
    from ccprophet.use_cases.detect_phases import DetectPhasesUseCase


# Default repo-root ``web/`` directory for static assets.
_WEB_DIR = Path(__file__).resolve().parents[3].parent / "web"


@dataclass
class WebUseCases:
    """Bundle of collaborators injected by the harness.

    A plain dataclass (not a Protocol) keeps the wiring in
    ``harness/web_main.py`` explicit and makes test doubles trivial.
    """

    analyze_bloat: AnalyzeBloatUseCase
    detect_phases: DetectPhasesUseCase
    compute_session_cost: ComputeSessionCostUseCase
    sessions: SessionRepository
    tool_calls: ToolCallRepository
    phases: PhaseRepository
    pricing: PricingProvider
    tool_defs: ToolDefRepository


def _safe_cost(
    session: Session, uc: ComputeSessionCostUseCase
) -> CostBreakdown | None:
    """Return None when pricing is missing — keeps the UI usable without rates."""
    try:
        return uc.execute(session.session_id)
    except (UnknownPricingModel, SessionNotFound):
        return None


def _require_session(uc: WebUseCases, sid: str) -> Session:
    session = uc.sessions.get(SessionId(sid))
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


def create_app(uc: WebUseCases, *, web_dir: Path | None = None) -> FastAPI:
    """Build the FastAPI app. Pure function of its inputs (LP-6 friendly)."""
    assets_dir = web_dir or _WEB_DIR
    app = FastAPI(title="ccprophet", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> Response:
        index_path = assets_dir / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="index.html not found")
        return FileResponse(index_path, media_type="text/html")

    @app.get("/vendor/{name}")
    def vendor(name: str) -> Response:
        # Flatten to basename to reject traversal (../) attempts.
        safe = Path(name).name
        candidate = assets_dir / "vendor" / safe
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="vendor asset not found")
        return FileResponse(candidate)

    @app.get("/replay.js")
    def replay_js() -> Response:
        candidate = assets_dir / "replay.js"
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="replay.js not found")
        return FileResponse(candidate, media_type="application/javascript")

    @app.get("/pattern_diff.js")
    def pattern_diff_js() -> Response:
        candidate = assets_dir / "pattern_diff.js"
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="pattern_diff.js not found")
        return FileResponse(candidate, media_type="application/javascript")

    @app.get("/api/sessions")
    def api_sessions(limit: int = 50) -> JSONResponse:
        limit = max(1, min(limit, 500))
        rows = list(uc.sessions.list_recent(limit=limit))
        return JSONResponse([session_to_dict(s) for s in rows])

    @app.get("/api/sessions/{sid}")
    def api_session(sid: str) -> JSONResponse:
        session = _require_session(uc, sid)
        try:
            bloat = uc.analyze_bloat.execute(session.session_id)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="session not found") from None
        cost = _safe_cost(session, uc.compute_session_cost)
        return JSONResponse(
            {
                "session": session_to_dict(session),
                "bloat": bloat_to_dict(bloat),
                "cost": cost_to_dict(cost),
            }
        )

    @app.get("/api/sessions/{sid}/bloat")
    def api_bloat(sid: str) -> JSONResponse:
        session = _require_session(uc, sid)
        try:
            report = uc.analyze_bloat.execute(session.session_id)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="session not found") from None
        return JSONResponse(bloat_to_dict(report))

    @app.get("/api/sessions/{sid}/dag")
    def api_dag(sid: str) -> Response:
        session = _require_session(uc, sid)
        try:
            phases = uc.detect_phases.execute(session.session_id)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="session not found") from None
        if not phases:
            phases = list(uc.phases.list_for_session(session.session_id))
        try:
            bloat = uc.analyze_bloat.execute(session.session_id)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="session not found") from None
        tool_calls = sorted(
            uc.tool_calls.list_for_session(session.session_id),
            key=lambda t: t.ts,
        )
        payload = build_dag(session, bloat, phases, tool_calls)
        return Response(
            content=json.dumps(payload, default=str),
            media_type="application/json",
        )

    @app.get("/api/sessions/{sid}/replay")
    def api_replay(sid: str) -> Response:
        session = _require_session(uc, sid)
        try:
            phases = uc.detect_phases.execute(session.session_id)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="session not found") from None
        if not phases:
            phases = list(uc.phases.list_for_session(session.session_id))
        try:
            bloat = uc.analyze_bloat.execute(session.session_id)
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="session not found") from None
        tool_calls = sorted(
            uc.tool_calls.list_for_session(session.session_id),
            key=lambda t: t.ts,
        )
        payload = build_replay(session, phases, tool_calls, bloat)
        return Response(
            content=json.dumps(payload, default=str),
            media_type="application/json",
        )

    @app.get("/api/sessions/{sid_a}/pattern-diff")
    def api_pattern_diff(sid_a: str, against: str) -> Response:
        a = _require_session(uc, sid_a)
        b = _require_session(uc, against)
        calls_a = list(uc.tool_calls.list_for_session(a.session_id))
        calls_b = list(uc.tool_calls.list_for_session(b.session_id))
        defs_a = list(uc.tool_defs.list_for_session(a.session_id))
        defs_b = list(uc.tool_defs.list_for_session(b.session_id))
        phases_a = list(uc.phases.list_for_session(a.session_id))
        phases_b = list(uc.phases.list_for_session(b.session_id))
        report = PatternDiffAnalyzer.analyze(
            a=a,
            b=b,
            calls_a=calls_a,
            calls_b=calls_b,
            defs_a=defs_a,
            defs_b=defs_b,
            phases_a=phases_a,
            phases_b=phases_b,
        )
        return Response(
            content=json.dumps(build_pattern_diff(report), default=str),
            media_type="application/json",
        )

    return app
