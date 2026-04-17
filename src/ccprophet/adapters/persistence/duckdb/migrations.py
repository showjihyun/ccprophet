from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

MIGRATIONS_DIR = Path(__file__).resolve().parents[5] / "migrations"


def current_version(conn: duckdb.DuckDBPyConnection) -> int:
    try:
        result = conn.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()
        return result[0] if result and result[0] is not None else 0
    except Exception:
        return 0


def apply_migrations(
    conn: duckdb.DuckDBPyConnection,
    *,
    up_to: int | None = None,
    migrations_dir: Path | None = None,
) -> int:
    mdir = migrations_dir or MIGRATIONS_DIR
    version = current_version(conn)

    sql_files = sorted(mdir.glob("V*__*.sql"))
    applied = 0

    for sql_file in sql_files:
        file_version = int(sql_file.name.split("__")[0].removeprefix("V"))
        if file_version <= version:
            continue
        if up_to is not None and file_version > up_to:
            break

        sql = sql_file.read_text(encoding="utf-8")
        conn.execute(sql)
        applied += 1

    return applied


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    apply_migrations(conn)
