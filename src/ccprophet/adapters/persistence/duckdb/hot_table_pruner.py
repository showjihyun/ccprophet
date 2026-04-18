"""DuckDB adapter for `HotTablePruner`.

Issues one `DELETE ... WHERE session_id = ANY(?)` per hot table so the use
case stays SQL-free. Returns a `PruneCounts` whose per-table field equals
the rowcount each DELETE reported (DuckDB exposes this via the result set).
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ccprophet.domain.values import SessionId
from ccprophet.ports.hot_table_pruner import PruneCounts

if TYPE_CHECKING:
    import duckdb


# (column, table) tuples. Keep this list aligned with
# DATAMODELING.md §6.1 hot-table retention targets.
_HOT_TABLES: tuple[tuple[str, str], ...] = (
    ("events", "session_id"),
    ("tool_calls", "session_id"),
    ("tool_defs_loaded", "session_id"),
    ("file_reads", "session_id"),
    ("phases", "session_id"),
)


class DuckDBHotTablePruner:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    def delete_for_sessions(self, sids: Sequence[SessionId]) -> PruneCounts:
        if not sids:
            return PruneCounts()
        ids = [sid.value for sid in sids]

        counts: dict[str, int] = {}
        for table, col in _HOT_TABLES:
            counts[table] = self._delete(table, col, ids)

        return PruneCounts(
            events=counts.get("events", 0),
            tool_calls=counts.get("tool_calls", 0),
            tool_defs_loaded=counts.get("tool_defs_loaded", 0),
            file_reads=counts.get("file_reads", 0),
            phases=counts.get("phases", 0),
        )

    def _delete(self, table: str, col: str, ids: list[str]) -> int:
        # Single round-trip: DELETE ... RETURNING 1 emits one row per deleted
        # row; counting in Python avoids the prior SELECT COUNT(*) pre-query.
        try:
            rows = self._conn.execute(
                f"DELETE FROM {table} WHERE {col} = ANY(?) RETURNING 1", [ids]
            ).fetchall()
        except Exception:
            # Table may not exist yet on a fresh DB (CatalogException or
            # similar).  Treat as zero deleted rows.
            return 0
        return len(rows)

    def preview_counts(self, sids: Sequence[SessionId]) -> PruneCounts:
        """Non-destructive companion used by the CLI dry-run output."""
        if not sids:
            return PruneCounts()
        ids = [sid.value for sid in sids]
        counts: dict[str, int] = {}
        for table, col in _HOT_TABLES:
            row = self._conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {col} = ANY(?)", [ids]
            ).fetchone()
            counts[table] = int(row[0]) if row else 0
        return PruneCounts(
            events=counts.get("events", 0),
            tool_calls=counts.get("tool_calls", 0),
            tool_defs_loaded=counts.get("tool_defs_loaded", 0),
            file_reads=counts.get("file_reads", 0),
            phases=counts.get("phases", 0),
        )
