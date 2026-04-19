from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


def _resolve_migrations_dir() -> Path:
    """Locate the `migrations/` directory under both layouts.

    - Installed wheel: `ccprophet/_migrations/` (force-included by hatch, see
      pyproject.toml `[tool.hatch.build.targets.wheel.force-include]`).
    - Editable / source install: repo-root `migrations/`.

    Picking the first that actually exists keeps `ccprophet doctor --migrate`
    working in both modes without an env var.
    """
    # Packaged location (inside the installed wheel, co-located with the
    # ccprophet package). `__file__` is .../ccprophet/adapters/persistence/duckdb/migrations.py
    # so `parents[3]` is .../ccprophet/.
    packaged = Path(__file__).resolve().parents[3] / "_migrations"
    if packaged.is_dir():
        return packaged
    # Repo-root (development checkout: src/ccprophet/... → parents[5] == repo)
    return Path(__file__).resolve().parents[5] / "migrations"


MIGRATIONS_DIR = _resolve_migrations_dir()


def current_version(conn: duckdb.DuckDBPyConnection) -> int:
    import duckdb as _duckdb

    try:
        result = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return result[0] if result and result[0] is not None else 0
    except _duckdb.CatalogException:
        # Fresh DB — `schema_migrations` table doesn't exist yet. Callers
        # interpret 0 as "nothing applied", which is correct.
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


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> int:
    """Apply any pending migrations. Returns the count actually applied."""
    return apply_migrations(conn)
