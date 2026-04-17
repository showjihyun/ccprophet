"""Hook entrypoint — must stay minimal for <50ms cold start.

Only stdlib + duckdb allowed at top level. No typer/rich.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    try:
        _run()
    except Exception:
        pass
    sys.exit(0)


def _run() -> None:
    from ccprophet.adapters.hook.receiver import read_hook_payload

    result = read_hook_payload()
    if result is None:
        return

    event_type, payload = result

    import duckdb

    from ccprophet.adapters.clock.system import SystemClock
    from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema
    from ccprophet.adapters.persistence.duckdb.repositories import (
        DuckDBEventRepository,
        DuckDBSessionRepository,
        DuckDBToolCallRepository,
    )
    from ccprophet.use_cases.ingest_event import IngestEventUseCase

    db_path = os.environ.get(
        "CCPROPHET_DB",
        str(Path.home() / ".claude-prophet" / "events.duckdb"),
    )
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(db_path)
    try:
        ensure_schema(conn)
        uc = IngestEventUseCase(
            events=DuckDBEventRepository(conn),
            sessions=DuckDBSessionRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            clock=SystemClock(),
        )
        uc.execute(event_type, payload)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
