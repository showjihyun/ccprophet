"""Regression guard: Web endpoints MUST tolerate a read-only DuckDB connection.

`harness/web_main.py` opens DuckDB with `read_only=True` (NFR-2). Any Use Case
that silently writes back (e.g. `DetectPhasesUseCase.replace_for_session`)
will crash `/api/sessions/{sid}/dag` and `/api/sessions/{sid}/replay` with
`InvalidInputException: Cannot execute statement of type "DELETE" on database
attached in read-only mode`.

This test exercises the full Web app against a DB opened `read_only=True` and
asserts both endpoints return 200.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import duckdb
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema  # noqa: E402
from ccprophet.adapters.persistence.duckdb.repositories import (  # noqa: E402
    DuckDBEventRepository,
    DuckDBPhaseRepository,
    DuckDBSessionRepository,
    DuckDBToolCallRepository,
    DuckDBToolDefRepository,
)
from ccprophet.adapters.persistence.duckdb.v2_repositories import (  # noqa: E402
    DuckDBPricingProvider,
)
from ccprophet.adapters.web.app import WebUseCases, create_app  # noqa: E402
from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase  # noqa: E402
from ccprophet.use_cases.compute_session_cost import ComputeSessionCostUseCase  # noqa: E402
from ccprophet.use_cases.detect_phases import DetectPhasesUseCase  # noqa: E402


def _seed_and_reopen_readonly(db_path):  # type: ignore[no-untyped-def]
    rw = duckdb.connect(str(db_path))
    ensure_schema(rw)
    t0 = datetime(2026, 4, 18, 9, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    rw.execute(
        """INSERT INTO sessions (session_id, project_slug, model, started_at, ended_at,
            total_input_tokens, total_output_tokens, compacted, context_window_size,
            total_cache_creation_tokens, total_cache_read_tokens)
           VALUES ('s-ro', 'proj', 'claude-opus-4-7', ?, NULL, 10000, 2000, FALSE,
                   200000, 0, 0)""",
        [t0],
    )
    for i in range(3):
        rw.execute(
            "INSERT INTO events (event_id, session_id, event_type, ts, payload, raw_hash, ingested_via) VALUES (?,?,?,?,?::JSON,?,?)",
            [
                f"e-{i}",
                "s-ro",
                "AssistantResponse",
                t0 + timedelta(minutes=i * 5),
                '{"message":{"usage":{"input_tokens":1000}}}',
                f"h-{i}",
                "hook",
            ],
        )
    rw.close()
    return duckdb.connect(str(db_path), read_only=True)


def _build_app(conn):  # type: ignore[no-untyped-def]
    sessions = DuckDBSessionRepository(conn)
    tool_defs = DuckDBToolDefRepository(conn)
    tool_calls = DuckDBToolCallRepository(conn)
    events = DuckDBEventRepository(conn)
    phases = DuckDBPhaseRepository(conn)
    pricing = DuckDBPricingProvider(conn)
    uc = WebUseCases(
        analyze_bloat=AnalyzeBloatUseCase(sessions, tool_defs, tool_calls),
        detect_phases=DetectPhasesUseCase(sessions, events, phases),
        compute_session_cost=ComputeSessionCostUseCase(sessions=sessions, pricing=pricing),
        sessions=sessions,
        tool_calls=tool_calls,
        phases=phases,
        pricing=pricing,
        tool_defs=tool_defs,
    )
    return create_app(uc)


def test_dag_endpoint_works_with_readonly_connection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    conn = _seed_and_reopen_readonly(tmp_path / "ro.duckdb")
    try:
        client = TestClient(_build_app(conn))
        resp = client.get("/api/sessions/s-ro/dag")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "session" in body
        # DAG endpoint returns nodes/edges + bloat_summary; the crucial
        # invariant is that the endpoint did not crash on detect_phases.
        assert "nodes" in body or "edges" in body
    finally:
        conn.close()


def test_replay_endpoint_works_with_readonly_connection(tmp_path) -> None:  # type: ignore[no-untyped-def]
    conn = _seed_and_reopen_readonly(tmp_path / "ro.duckdb")
    try:
        client = TestClient(_build_app(conn))
        resp = client.get("/api/sessions/s-ro/replay")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session"]["session_id"] == "s-ro"
    finally:
        conn.close()


def test_detect_phases_persist_false_is_side_effect_free(tmp_path) -> None:  # type: ignore[no-untyped-def]
    conn = _seed_and_reopen_readonly(tmp_path / "ro.duckdb")
    try:
        sessions = DuckDBSessionRepository(conn)
        events = DuckDBEventRepository(conn)
        phases = DuckDBPhaseRepository(conn)
        from ccprophet.domain.values import SessionId

        uc = DetectPhasesUseCase(sessions, events, phases)
        detected = uc.execute(SessionId("s-ro"), persist=False)
        assert len(detected) >= 1
        # DB is read-only; had persist=True been used, this call would have
        # raised InvalidInputException. Reaching this point proves the guard.
    finally:
        conn.close()
