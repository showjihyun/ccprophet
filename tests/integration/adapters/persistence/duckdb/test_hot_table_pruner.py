from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ccprophet.domain.values import SessionId
from tests.fixtures.builders import (
    EventBuilder,
    PhaseBuilder,
    SessionBuilder,
    ToolCallBuilder,
    ToolDefBuilder,
)


@pytest.fixture
def db(tmp_path):  # type: ignore[no-untyped-def]
    import duckdb

    from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema

    conn = duckdb.connect(str(tmp_path / "ccprophet.duckdb"))
    ensure_schema(conn)
    return conn


def _seed(conn, sid: str) -> None:  # type: ignore[no-untyped-def]
    from ccprophet.adapters.persistence.duckdb.repositories import (
        DuckDBEventRepository,
        DuckDBPhaseRepository,
        DuckDBSessionRepository,
        DuckDBToolCallRepository,
        DuckDBToolDefRepository,
    )

    DuckDBSessionRepository(conn).upsert(SessionBuilder().with_id(sid).build())
    DuckDBToolDefRepository(conn).bulk_add(
        SessionId(sid),
        [ToolDefBuilder().named("Read").with_tokens(100).build()],
    )
    DuckDBToolCallRepository(conn).append(
        ToolCallBuilder().in_session(sid).for_tool("Read").build()
    )
    DuckDBEventRepository(conn).append(EventBuilder().for_session(sid).build())
    DuckDBPhaseRepository(conn).replace_for_session(
        SessionId(sid),
        [PhaseBuilder().in_session(sid).build()],
    )
    # Seed a file_reads row directly (no repo for this table yet).
    conn.execute(
        "INSERT INTO file_reads "
        "(file_read_id, session_id, file_path_hash, tokens, ts) "
        "VALUES (?, ?, ?, ?, ?)",
        [f"fr-{sid}", sid, "hash", 50, datetime(2026, 1, 1, tzinfo=timezone.utc)],
    )


class TestDuckDBHotTablePruner:
    def test_delete_for_sessions_reports_counts(self, db) -> None:  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.duckdb.hot_table_pruner import (
            DuckDBHotTablePruner,
        )

        _seed(db, "target")
        _seed(db, "keep")

        counts = DuckDBHotTablePruner(db).delete_for_sessions([SessionId("target")])

        assert counts.events == 1
        assert counts.tool_calls == 1
        assert counts.tool_defs_loaded == 1
        assert counts.file_reads == 1
        assert counts.phases == 1

        # "keep" session rows survive.
        keep_tc = db.execute(
            "SELECT COUNT(*) FROM tool_calls WHERE session_id = ?",
            ["keep"],
        ).fetchone()
        assert keep_tc[0] == 1

        # "target" rows are actually gone.
        target_tc = db.execute(
            "SELECT COUNT(*) FROM tool_calls WHERE session_id = ?",
            ["target"],
        ).fetchone()
        assert target_tc[0] == 0

    def test_delete_for_empty_sessions_is_noop(self, db) -> None:  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.duckdb.hot_table_pruner import (
            DuckDBHotTablePruner,
        )

        _seed(db, "survivor")
        counts = DuckDBHotTablePruner(db).delete_for_sessions([])

        assert counts.total == 0
        alive = db.execute(
            "SELECT COUNT(*) FROM events WHERE session_id = ?", ["survivor"]
        ).fetchone()
        assert alive[0] == 1

    def test_preview_counts_does_not_delete(self, db) -> None:  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.duckdb.hot_table_pruner import (
            DuckDBHotTablePruner,
        )

        _seed(db, "target")
        pruner = DuckDBHotTablePruner(db)

        preview = pruner.preview_counts([SessionId("target")])
        assert preview.total == 5

        still_there = db.execute(
            "SELECT COUNT(*) FROM events WHERE session_id = ?", ["target"]
        ).fetchone()
        assert still_there[0] == 1
