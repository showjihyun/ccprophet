from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

DB_PATH = Path.home() / ".claude-prophet" / "events.duckdb"
SNAPSHOT_ROOT = Path.home() / ".claude-prophet" / "snapshots"
DEFAULT_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
DEFAULT_JSONL_ROOT = Path.home() / ".claude" / "projects"


def connect_readonly() -> "duckdb.DuckDBPyConnection":
    import duckdb

    if not DB_PATH.exists():
        raise SystemExit(
            f"ccprophet DB not found at {DB_PATH}\n"
            f"Run `ccprophet install` or trigger a hook first."
        )
    return duckdb.connect(str(DB_PATH), read_only=True)


def connect_readwrite() -> "duckdb.DuckDBPyConnection":
    import duckdb

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))
