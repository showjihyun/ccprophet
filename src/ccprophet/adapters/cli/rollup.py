"""CLI wiring for `ccprophet rollup` (data-lifecycle §6.2 + PRD NFR-6).

Three modes:
  1. Plain dry-run — print the plan (sessions considered, row counts the
     DELETE would remove) and exit.
  2. `--apply` — execute the rollup + delete step, print counts.
  3. `--apply --archive-parquet PATH` — archive hot-table rows as a directory
     of Parquet files FIRST, then delete.
"""
from __future__ import annotations

import json as json_module
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ccprophet.ports.hot_table_pruner import PruneCounts

if TYPE_CHECKING:
    from ccprophet.adapters.persistence.duckdb.hot_table_pruner import (
        DuckDBHotTablePruner,
    )
    from ccprophet.domain.values import SessionId
    from ccprophet.use_cases.rollup_sessions import RollupOutcome, RollupSessionsUseCase

_OLDER_THAN_RE = re.compile(r"^(\d+)d$")


def parse_older_than(s: str) -> timedelta:
    """Parse `Nd` strings. `0d` means "everything up to now"."""
    m = _OLDER_THAN_RE.match(s.strip())
    if not m:
        raise ValueError(f"--older-than must match `\\d+d` (e.g. 90d), got: {s!r}")
    return timedelta(days=int(m.group(1)))


def run_rollup_command(
    use_case: RollupSessionsUseCase,
    *,
    older_than_days: int,
    apply: bool,
    archive_parquet: Path | None = None,
    as_json: bool = False,
    now: datetime | None = None,
    db_path: Path | None = None,
    preview_pruner: DuckDBHotTablePruner | None = None,
    archive_conn: object | None = None,
) -> int:
    cutoff = (now or datetime.now(tz=timezone.utc)) - timedelta(days=older_than_days)

    # 1) Dry-run plan (always computed; --apply reuses it).
    from ccprophet.use_cases.rollup_sessions import RollupSessionsUseCase as _UC  # noqa: F401

    dry_outcome = use_case.execute(older_than=cutoff, apply=False)

    if dry_outcome.plan.is_empty:
        _render(dry_outcome, as_json=as_json, cutoff=cutoff, archive_path=None)
        # Apply with nothing-to-do is not success (exit 1 per spec).
        return 1 if apply else 0

    # 2) Optional Parquet archive before deletion.
    archive_path: Path | None = None
    if apply and archive_parquet is not None and archive_conn is not None:
        archive_path = _write_parquet_archive(
            conn=archive_conn,
            out_dir=archive_parquet,
            session_ids=list(dry_outcome.plan.session_ids),
        )

    # 3) Apply step.
    if apply:
        applied = use_case.execute(older_than=cutoff, apply=True)
        outcome_with_archive = _attach_archive(applied, archive_path)
        _render(outcome_with_archive, as_json=as_json, cutoff=cutoff,
                archive_path=archive_path)
        return 0

    # Pure dry-run: enrich with a pre-run count of rows that WOULD be deleted.
    preview = (
        preview_pruner.preview_counts(
            [_as_sid(v) for v in dry_outcome.plan.session_ids]
        )
        if preview_pruner is not None
        else None
    )
    _render(
        dry_outcome,
        as_json=as_json,
        cutoff=cutoff,
        archive_path=None,
        preview=preview,
    )
    return 0


def _attach_archive(outcome: RollupOutcome, path: Path | None) -> RollupOutcome:
    from dataclasses import replace

    return replace(outcome, archive_path=path)


def _as_sid(v: str) -> "SessionId":
    from ccprophet.domain.values import SessionId as _SID

    return _SID(v)


def _write_parquet_archive(
    *, conn: object, out_dir: Path, session_ids: list[str]
) -> Path:
    """Export each hot table's rows for these session_ids to a Parquet dir.

    One file per hot table under `out_dir/` — a directory rather than a single
    file because the hot tables have differing schemas. Uses the existing
    read-write connection via a CTE (DuckDB forbids opening a second
    connection with a different mode while the first is still alive).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = ("events", "tool_calls", "tool_defs_loaded", "file_reads", "phases")

    # Stage session ids in a temp table so the COPY/SELECT stays parameterless
    # (DuckDB's COPY does not take prepared-statement parameters).
    conn.execute(  # type: ignore[attr-defined]
        "CREATE OR REPLACE TEMP TABLE _rollup_targets (session_id VARCHAR)"
    )
    conn.executemany(  # type: ignore[attr-defined]
        "INSERT INTO _rollup_targets VALUES (?)",
        [(sid,) for sid in session_ids],
    )
    try:
        for table in tables:
            exists = conn.execute(  # type: ignore[attr-defined]
                "SELECT 1 FROM duckdb_tables() WHERE table_name=?",
                [table],
            ).fetchone()
            if not exists:
                continue
            target = out_dir / f"{table}.parquet"
            conn.execute(  # type: ignore[attr-defined]
                f"COPY (SELECT * FROM {table} "
                f"WHERE session_id IN (SELECT session_id FROM _rollup_targets)) "
                f"TO '{target.as_posix()}' (FORMAT PARQUET)"
            )
    finally:
        conn.execute("DROP TABLE IF EXISTS _rollup_targets")  # type: ignore[attr-defined]
    return out_dir


def _render(
    outcome: RollupOutcome,
    *,
    as_json: bool,
    cutoff: datetime,
    archive_path: Path | None,
    preview: PruneCounts | None = None,
) -> None:
    if as_json:
        print(json_module.dumps(
            _to_dict(outcome, cutoff=cutoff, archive_path=archive_path, preview=preview),
            indent=2, default=str,
        ))
        return

    from rich.console import Console

    console = Console()
    ids = outcome.plan.session_ids
    console.print(
        f"[bold]Rollup plan[/] — cutoff [dim]< {cutoff.isoformat()}[/] — "
        f"[cyan]{len(ids)}[/] session(s) would be summarized."
    )
    if outcome.applied:
        c = outcome.rows_deleted
        console.print(
            f"[green]Applied[/]: deleted "
            f"{c.events} events, {c.tool_calls} tool_calls, "
            f"{c.tool_defs_loaded} tool_defs_loaded, {c.file_reads} file_reads, "
            f"{c.phases} phases ({c.total} total)."
        )
        if archive_path is not None:
            console.print(f"Archive: [dim]{archive_path}[/]")
    elif preview is not None:
        console.print(
            f"[dim]Would delete (dry-run): "
            f"{preview.events} events, {preview.tool_calls} tool_calls, "
            f"{preview.tool_defs_loaded} tool_defs_loaded, "
            f"{preview.file_reads} file_reads, {preview.phases} phases.[/]"
        )
    if not outcome.applied and ids:
        console.print("[dim]Re-run with --apply to actually delete these rows.[/]")


def _to_dict(
    outcome: RollupOutcome,
    *,
    cutoff: datetime,
    archive_path: Path | None,
    preview: PruneCounts | None,
) -> dict[str, object]:
    counts = outcome.rows_deleted
    payload: dict[str, object] = {
        "cutoff": cutoff.isoformat(),
        "applied": outcome.applied,
        "session_count": len(outcome.plan.session_ids),
        "session_ids": list(outcome.plan.session_ids),
        "rows_deleted": {
            "events": counts.events,
            "tool_calls": counts.tool_calls,
            "tool_defs_loaded": counts.tool_defs_loaded,
            "file_reads": counts.file_reads,
            "phases": counts.phases,
            "total": counts.total,
        },
        "archive_path": str(archive_path) if archive_path else None,
    }
    if preview is not None:
        payload["preview_rows_to_delete"] = {
            "events": preview.events,
            "tool_calls": preview.tool_calls,
            "tool_defs_loaded": preview.tool_defs_loaded,
            "file_reads": preview.file_reads,
            "phases": preview.phases,
            "total": preview.total,
        }
    return payload
