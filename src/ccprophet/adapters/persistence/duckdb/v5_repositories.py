"""DuckDB repositories introduced in V5 (rollup / session_summary).

Kept in its own module so V1/V2/V3 files stay below the ~300 LOC AP-5 ceiling.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from ccprophet.adapters.persistence.duckdb._tz import from_utc as _from_utc
from ccprophet.adapters.persistence.duckdb._tz import to_utc_naive as _to_utc_naive
from ccprophet.domain.entities import SessionSummary
from ccprophet.domain.values import BloatRatio, SessionId, TokenCount

if TYPE_CHECKING:
    import duckdb


class DuckDBSessionSummaryRepository:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def upsert(self, summary: SessionSummary) -> None:
        self._conn.execute(
            """
            INSERT INTO session_summary
                (session_id, project_slug, model, started_at, ended_at,
                 total_input_tokens, total_output_tokens,
                 total_cache_creation_tokens, total_cache_read_tokens,
                 compacted, tool_call_count, unique_tools_used,
                 loaded_tool_def_tokens, bloat_tokens, bloat_ratio,
                 file_read_count, phase_count, summarized_at,
                 source_rows_deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (session_id) DO UPDATE SET
                project_slug = EXCLUDED.project_slug,
                model = EXCLUDED.model,
                started_at = EXCLUDED.started_at,
                ended_at = EXCLUDED.ended_at,
                total_input_tokens = EXCLUDED.total_input_tokens,
                total_output_tokens = EXCLUDED.total_output_tokens,
                total_cache_creation_tokens = EXCLUDED.total_cache_creation_tokens,
                total_cache_read_tokens = EXCLUDED.total_cache_read_tokens,
                compacted = EXCLUDED.compacted,
                tool_call_count = EXCLUDED.tool_call_count,
                unique_tools_used = EXCLUDED.unique_tools_used,
                loaded_tool_def_tokens = EXCLUDED.loaded_tool_def_tokens,
                bloat_tokens = EXCLUDED.bloat_tokens,
                bloat_ratio = EXCLUDED.bloat_ratio,
                file_read_count = EXCLUDED.file_read_count,
                phase_count = EXCLUDED.phase_count,
                summarized_at = EXCLUDED.summarized_at,
                source_rows_deleted = EXCLUDED.source_rows_deleted
            """,
            [
                summary.session_id.value,
                summary.project_slug,
                summary.model,
                _to_utc_naive(summary.started_at),
                _to_utc_naive(summary.ended_at),
                summary.total_input_tokens.value,
                summary.total_output_tokens.value,
                summary.total_cache_creation_tokens.value,
                summary.total_cache_read_tokens.value,
                summary.compacted,
                summary.tool_call_count,
                summary.unique_tools_used,
                summary.loaded_tool_def_tokens.value,
                summary.bloat_tokens.value,
                summary.bloat_ratio.value,
                summary.file_read_count,
                summary.phase_count,
                _to_utc_naive(summary.summarized_at),
                summary.source_rows_deleted,
            ],
        )

    def get(self, sid: SessionId) -> SessionSummary | None:
        row = self._conn.execute(
            "SELECT * FROM session_summary WHERE session_id = ?", [sid.value]
        ).fetchone()
        if row is None:
            return None
        return _row_to_summary(row)

    def list_in_range(
        self, start: datetime, end: datetime
    ) -> Sequence[SessionSummary]:
        rows = self._conn.execute(
            "SELECT * FROM session_summary WHERE started_at >= ? AND started_at < ? "
            "ORDER BY started_at",
            [_to_utc_naive(start), _to_utc_naive(end)],
        ).fetchall()
        return [_row_to_summary(r) for r in rows]

    def mark_pruned(self, sids: Sequence[SessionId]) -> None:
        """Flip `source_rows_deleted=TRUE` for summaries whose hot rows were pruned."""
        if not sids:
            return
        ids = [s.value for s in sids]
        self._conn.execute(
            "UPDATE session_summary SET source_rows_deleted = TRUE "
            "WHERE session_id = ANY(?)",
            [ids],
        )


def _row_to_summary(row: tuple[object, ...]) -> SessionSummary:
    # Column order matches the CREATE TABLE in V5__session_summary.sql.
    return SessionSummary(
        session_id=SessionId(str(row[0])),
        project_slug=str(row[1]),
        model=str(row[2]),
        started_at=_from_utc(row[3]),  # type: ignore[arg-type]
        ended_at=_from_utc(row[4]),  # type: ignore[arg-type]
        total_input_tokens=TokenCount(int(row[5] or 0)),  # type: ignore[call-overload]
        total_output_tokens=TokenCount(int(row[6] or 0)),  # type: ignore[call-overload]
        total_cache_creation_tokens=TokenCount(int(row[7] or 0)),  # type: ignore[call-overload]
        total_cache_read_tokens=TokenCount(int(row[8] or 0)),  # type: ignore[call-overload]
        compacted=bool(row[9]),
        tool_call_count=int(row[10] or 0),  # type: ignore[call-overload]
        unique_tools_used=int(row[11] or 0),  # type: ignore[call-overload]
        loaded_tool_def_tokens=TokenCount(int(row[12] or 0)),  # type: ignore[call-overload]
        bloat_tokens=TokenCount(int(row[13] or 0)),  # type: ignore[call-overload]
        bloat_ratio=BloatRatio(float(row[14] or 0.0)),  # type: ignore[arg-type]
        file_read_count=int(row[15] or 0),  # type: ignore[call-overload]
        phase_count=int(row[16] or 0),  # type: ignore[call-overload]
        summarized_at=_from_utc(row[17]),  # type: ignore[arg-type]
        source_rows_deleted=bool(row[18]),
    )
