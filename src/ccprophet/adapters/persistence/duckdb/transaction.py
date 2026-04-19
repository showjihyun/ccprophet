"""Explicit BEGIN/COMMIT scope for DuckDB batch writes.

DuckDB commits on every `execute()` by default. When the backfill path
inserts thousands of rows one-by-one (one `Event` + one `ToolCall` per
JSONL record), the per-insert commit overhead dominates. Wrapping the
loop in an explicit transaction collapses those N commits into 1.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


@contextmanager
def transaction(conn: duckdb.DuckDBPyConnection) -> Iterator[None]:
    conn.execute("BEGIN TRANSACTION")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
