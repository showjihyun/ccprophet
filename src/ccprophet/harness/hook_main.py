"""Hook entrypoint — must stay minimal for <50ms cold start.

Only stdlib + duckdb allowed at top level. No typer/rich.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def main() -> None:
    # AP-3 Silent Fail: hook MUST exit 0 regardless of what goes wrong inside,
    # or the whole Claude Code session stalls. But "silent" makes diagnosis
    # impossible — so we append the traceback to a dedicated error log before
    # exiting. The log itself is best-effort; if writing it fails, we still
    # exit 0. This closes the observability gap called out by the pre-release
    # audit without violating AP-3.
    try:
        _run()
    except Exception:
        _log_hook_error()
    sys.exit(0)


def _log_hook_error() -> None:
    """Best-effort append of the current traceback to the hook error log."""
    try:
        log_dir = Path(
            os.environ.get("CCPROPHET_LOG_DIR")
            or (Path.home() / ".claude-prophet" / "logs")
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "hook_errors.log").open("a", encoding="utf-8") as f:
            f.write("---\n")
            traceback.print_exc(file=f)
    except Exception:
        # If even the log write fails, respect AP-3 — never propagate.
        pass


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
