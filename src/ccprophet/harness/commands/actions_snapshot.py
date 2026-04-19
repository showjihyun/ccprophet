from __future__ import annotations

import typer

from ccprophet.harness.commands._shared import (
    SNAPSHOT_ROOT,
    connect_readonly,
    connect_readwrite,
)


def register(app: typer.Typer) -> None:
    snapshot_app = typer.Typer(help="Manage settings snapshots")
    app.add_typer(snapshot_app, name="snapshot", rich_help_panel="Auto-fix")

    @snapshot_app.command("list")
    def snapshot_list(
        limit: int = typer.Option(20, "--limit", "-n", help="Max rows"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """List recent auto-fix snapshots."""
        from ccprophet.adapters.cli.snapshot import run_snapshot_list_command
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBSnapshotRepository,
        )
        from ccprophet.use_cases.list_snapshots import ListSnapshotsUseCase

        conn = connect_readonly()
        uc = ListSnapshotsUseCase(snapshots=DuckDBSnapshotRepository(conn))
        code = run_snapshot_list_command(uc, limit=limit, as_json=json)
        raise typer.Exit(code)

    @snapshot_app.command("restore")
    def snapshot_restore(
        snapshot_id: str = typer.Argument(..., help="Snapshot ID to restore"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Restore files captured in a snapshot."""
        from ccprophet.adapters.cli.snapshot import run_snapshot_restore_command
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBSnapshotRepository,
        )
        from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
        from ccprophet.adapters.snapshot.filesystem import FilesystemSnapshotStore
        from ccprophet.use_cases.restore_snapshot import RestoreSnapshotUseCase

        conn = connect_readwrite()
        SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
        uc = RestoreSnapshotUseCase(
            settings=JsonFileSettingsStore(),
            snapshot_store=FilesystemSnapshotStore(SNAPSHOT_ROOT),
            snapshots=DuckDBSnapshotRepository(conn),
        )
        code = run_snapshot_restore_command(uc, snapshot_id=snapshot_id, as_json=json)
        raise typer.Exit(code)
