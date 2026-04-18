from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


DB_PATH = Path(
    os.environ.get("CCPROPHET_DB")
    or (Path.home() / ".claude-prophet" / "events.duckdb")
)
SNAPSHOT_ROOT = Path.home() / ".claude-prophet" / "snapshots"
DEFAULT_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
DEFAULT_JSONL_ROOT = Path.home() / ".claude" / "projects"


def connect_readonly() -> duckdb.DuckDBPyConnection:
    import duckdb

    if not DB_PATH.exists():
        raise SystemExit(
            f"ccprophet DB not found at {DB_PATH}\n"
            f"Run `ccprophet install` or trigger a hook first."
        )
    return duckdb.connect(str(DB_PATH), read_only=True)


def connect_readwrite(*, create_if_missing: bool = False) -> duckdb.DuckDBPyConnection:
    """Open DB for read-write.

    Default: refuses to auto-create. Auto-created DBs have no schema and the
    first query crashes with `CatalogException`; a clear "run ccprophet install"
    hint is strictly better UX.

    `create_if_missing=True` is reserved for `ingest` / hook ingestion paths
    that call `ensure_schema(conn)` right after opening.
    """
    import duckdb

    if not DB_PATH.exists() and not create_if_missing:
        raise SystemExit(
            f"ccprophet DB not found at {DB_PATH}\n"
            f"Run `ccprophet install` or trigger a hook first."
        )
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))
