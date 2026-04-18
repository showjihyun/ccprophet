from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ccprophet.harness.commands._shared import DB_PATH, connect_readwrite


def register(app: typer.Typer) -> None:
    @app.command()
    def rollup(
        older_than: str = typer.Option(
            "90d", "--older-than", help="Cutoff age (e.g. 90d, 30d, 0d)"
        ),
        apply_changes: bool = typer.Option(
            False,
            "--apply",
            help="Actually summarize and delete (default is dry-run)",
        ),
        archive_parquet: Optional[Path] = typer.Option(
            None,
            "--archive-parquet",
            help="Directory to dump hot-table Parquet archives before --apply",
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Summarize and prune old sessions (data lifecycle, PRD NFR-6)."""
        from ccprophet.adapters.cli.rollup import parse_older_than, run_rollup_command
        from ccprophet.adapters.clock.system import SystemClock
        from ccprophet.adapters.persistence.duckdb.hot_table_pruner import (
            DuckDBHotTablePruner,
        )
        from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBPhaseRepository,
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
            DuckDBToolDefRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v5_repositories import (
            DuckDBSessionSummaryRepository,
        )
        from ccprophet.use_cases.rollup_sessions import RollupSessionsUseCase

        try:
            delta = parse_older_than(older_than)
        except ValueError as e:
            typer.secho(str(e), err=True, fg="red")
            raise typer.Exit(2) from e

        conn = connect_readwrite()
        ensure_schema(conn)
        pruner = DuckDBHotTablePruner(conn)
        uc = RollupSessionsUseCase(
            sessions=DuckDBSessionRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            tool_defs=DuckDBToolDefRepository(conn),
            phases=DuckDBPhaseRepository(conn),
            session_summaries=DuckDBSessionSummaryRepository(conn),
            hot_pruner=pruner,
            clock=SystemClock(),
        )
        code = run_rollup_command(
            uc,
            older_than_days=delta.days,
            apply=apply_changes,
            archive_parquet=archive_parquet,
            as_json=json,
            db_path=DB_PATH,
            preview_pruner=pruner,
            archive_conn=conn,
        )
        raise typer.Exit(code)
