from __future__ import annotations

from pathlib import Path

import typer

from ccprophet.harness.commands._shared import (
    DB_PATH,
    DEFAULT_JSONL_ROOT,
    DEFAULT_SETTINGS_PATH,
    connect_readonly,
    connect_readwrite,
)


def register(app: typer.Typer) -> None:
    @app.command(rich_help_panel="Getting started")
    def install(
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Register hooks, create DB, set up ccprophet."""
        import duckdb

        from ccprophet.adapters.cli.install import run_install_command
        from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema
        from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore

        def _bootstrap_db(db_path: Path) -> int:
            conn = duckdb.connect(str(db_path))
            try:
                return ensure_schema(conn)
            finally:
                conn.close()

        code = run_install_command(
            settings=JsonFileSettingsStore(),
            bootstrap_db=_bootstrap_db,
            dry_run=dry_run,
            as_json=json,
        )
        raise typer.Exit(code)

    @app.command(rich_help_panel="Getting started")
    def ingest(
        root: Path = typer.Option(
            DEFAULT_JSONL_ROOT, "--root", help="Claude Code projects directory"
        ),
        file: Path | None = typer.Option(
            None, "--file", help="Ingest a single JSONL file (overrides --root)"
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Backfill historical sessions from Claude Code JSONL transcripts."""
        from ccprophet.adapters.cli.ingest import (
            discover_jsonl_files,
            run_ingest_command,
        )
        from ccprophet.adapters.filewatch.jsonl_reader import JsonlReader
        from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBEventRepository,
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
        )
        from ccprophet.adapters.persistence.duckdb.transaction import transaction
        from ccprophet.adapters.persistence.duckdb.v3_repositories import (
            DuckDBSubagentRepository,
        )
        from ccprophet.use_cases.backfill_from_jsonl import BackfillFromJsonlUseCase

        conn = connect_readwrite(create_if_missing=True)
        ensure_schema(conn)
        uc = BackfillFromJsonlUseCase(
            source=JsonlReader(),
            events=DuckDBEventRepository(conn),
            sessions=DuckDBSessionRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            subagents=DuckDBSubagentRepository(conn),
        )
        paths = [file] if file is not None else discover_jsonl_files(root)
        # Collapse per-row commits into one transaction per ingest run.
        with transaction(conn):
            code = run_ingest_command(uc, paths=paths, as_json=json)
        raise typer.Exit(code)

    @app.command(rich_help_panel="Advanced")
    def doctor(
        migrate: bool = typer.Option(False, "--migrate", help="Apply pending schema migrations"),
        repair: bool = typer.Option(False, "--repair", help="Delete orphan records (destructive)"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """DB health checks — schema version, orphans, data quality, disk usage."""
        from ccprophet.adapters.cli.doctor import MigrationOps, run_doctor_command
        from ccprophet.adapters.persistence.duckdb.migrations import (
            MIGRATIONS_DIR,
            apply_migrations,
            current_version,
        )

        code = run_doctor_command(
            db_path=DB_PATH,
            as_json=json,
            repair=repair,
            migrate=migrate,
            migration_ops=MigrationOps(
                migrations_dir=MIGRATIONS_DIR,
                current_version=current_version,
                apply_migrations=apply_migrations,
            ),
        )
        raise typer.Exit(code)

    query_app = typer.Typer(help="Read-only SQL query against events.duckdb")
    app.add_typer(query_app, name="query", rich_help_panel="Advanced")

    def _require_db(as_json: bool = False) -> None:
        if DB_PATH.exists():
            return
        import json as _json
        import sys as _sys

        msg = (
            f"ccprophet DB not found at {DB_PATH}\nRun `ccprophet install` or trigger a hook first."
        )
        if as_json:
            # Stable shape for pipelines: stderr JSON + exit 2.
            print(
                _json.dumps({"error": msg, "code": "db_missing"}),
                file=_sys.stderr,
            )
        else:
            typer.secho(msg, err=True, fg="red")
        raise typer.Exit(2)

    @query_app.command("run")
    def query_run(
        sql: str = typer.Argument(..., help="SQL to run"),
        limit: int = typer.Option(100, "--limit", "-n", help="Max rows to return"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Run an ad-hoc read-only SQL query against events.duckdb."""
        _require_db(as_json=json)
        from ccprophet.adapters.cli.query import run_query_command

        raise typer.Exit(run_query_command(db_path=DB_PATH, sql=sql, as_json=json, limit=limit))

    @query_app.command("tables")
    def query_tables(
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """List all tables in events.duckdb with row counts."""
        _require_db(as_json=json)
        from ccprophet.adapters.cli.query import run_query_tables_command

        raise typer.Exit(run_query_tables_command(db_path=DB_PATH, as_json=json))

    @query_app.command("schema")
    def query_schema(
        table: str = typer.Argument(..., help="Table name"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Show column types for a table in events.duckdb."""
        _require_db(as_json=json)
        from ccprophet.adapters.cli.query import run_query_schema_command

        raise typer.Exit(run_query_schema_command(db_path=DB_PATH, table=table, as_json=json))

    @app.command("claude-md", rich_help_panel="Advanced")
    def claude_md(
        root: Path = typer.Option(Path.cwd(), "--root", help="Project root to search"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Audit CLAUDE.md files for context rot."""
        from ccprophet.adapters.cli.claude_md import run_claude_md_command

        raise typer.Exit(run_claude_md_command(root=root, as_json=json))

    @app.command(rich_help_panel="Cost")
    def savings(
        window: int = typer.Option(30, "--window", help="Days to look back for applied savings"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Token-savings dashboard — applied, pending, and opportunity knobs."""
        from ccprophet.adapters.cli.savings import run_savings_command
        from ccprophet.adapters.clock.system import SystemClock
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBRecommendationRepository,
        )
        from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
        from ccprophet.use_cases.compute_savings import ComputeSavingsUseCase

        conn = connect_readonly()
        uc = ComputeSavingsUseCase(
            recommendations=DuckDBRecommendationRepository(conn),
            settings=JsonFileSettingsStore(),
            clock=SystemClock(),
            settings_path=DEFAULT_SETTINGS_PATH,
        )
        code = run_savings_command(uc, window_days=window, as_json=json)
        raise typer.Exit(code)
