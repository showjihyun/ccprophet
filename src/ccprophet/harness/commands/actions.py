from __future__ import annotations

from pathlib import Path

import typer

from ccprophet.harness.commands._shared import (
    DEFAULT_SETTINGS_PATH,
    SNAPSHOT_ROOT,
    connect_readwrite,
)


def register(app: typer.Typer) -> None:
    @app.command()
    def recommend(
        session: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
        no_persist: bool = typer.Option(
            False, "--no-persist", help="Skip saving recommendations to DB"
        ),
    ) -> None:
        """Action-first recommendations (prune candidates, etc.)."""
        from ccprophet.adapters.cli.recommend import run_recommend_command
        from ccprophet.adapters.clock.system import SystemClock
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
            DuckDBToolDefRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBPricingProvider,
            DuckDBRecommendationRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v3_repositories import (
            DuckDBSubagentRepository,
        )
        from ccprophet.use_cases.recommend_action import RecommendActionUseCase

        conn = connect_readwrite()
        uc = RecommendActionUseCase(
            sessions=DuckDBSessionRepository(conn),
            tool_defs=DuckDBToolDefRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            recommendations=DuckDBRecommendationRepository(conn),
            pricing=DuckDBPricingProvider(conn),
            clock=SystemClock(),
            subagents=DuckDBSubagentRepository(conn),
        )
        code = run_recommend_command(
            uc, session=session, as_json=json, persist=not no_persist
        )
        raise typer.Exit(code)

    @app.command()
    def prune(
        target: Path = typer.Option(
            DEFAULT_SETTINGS_PATH,
            "--target",
            "-t",
            help="settings.json path to patch",
        ),
        apply_changes: bool = typer.Option(
            False, "--apply", help="Actually write changes (default is dry-run)"
        ),
        assume_yes: bool = typer.Option(
            False, "--yes", "-y", help="Skip interactive confirmation"
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Preview or apply Auto Tool Pruning."""
        from ccprophet.adapters.cli.prune import run_prune_command
        from ccprophet.adapters.clock.system import SystemClock
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBRecommendationRepository,
            DuckDBSnapshotRepository,
        )
        from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
        from ccprophet.adapters.snapshot.filesystem import FilesystemSnapshotStore
        from ccprophet.use_cases.apply_pruning import ApplyPruningUseCase
        from ccprophet.use_cases.prune_tools import PruneToolsUseCase

        conn = connect_readwrite()
        SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
        settings = JsonFileSettingsStore()
        rec_repo = DuckDBRecommendationRepository(conn)
        snap_repo = DuckDBSnapshotRepository(conn)
        snap_store = FilesystemSnapshotStore(SNAPSHOT_ROOT)

        preview_uc = PruneToolsUseCase(recommendations=rec_repo, settings=settings)
        apply_uc = ApplyPruningUseCase(
            prune=preview_uc,
            settings=settings,
            snapshot_store=snap_store,
            snapshots=snap_repo,
            recommendations=rec_repo,
            clock=SystemClock(),
        )
        code = run_prune_command(
            preview_uc,
            apply_uc,
            target_path=target,
            apply=apply_changes,
            assume_yes=assume_yes,
            as_json=json,
        )
        raise typer.Exit(code)

    @app.command()
    def reproduce(
        task: str = typer.Argument(..., help="Task type to reproduce"),
        target: Path = typer.Option(
            DEFAULT_SETTINGS_PATH,
            "--target",
            "-t",
            help="settings.json path for --apply",
        ),
        apply_changes: bool = typer.Option(
            False, "--apply", help="Also run Auto-Fix using best config"
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Reproduce the best config from successful sessions for a task type."""
        from ccprophet.adapters.cli.reproduce import run_reproduce_command
        from ccprophet.adapters.clock.system import SystemClock
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBToolCallRepository,
            DuckDBToolDefRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBOutcomeRepository,
            DuckDBRecommendationRepository,
            DuckDBSnapshotRepository,
        )
        from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
        from ccprophet.adapters.snapshot.filesystem import FilesystemSnapshotStore
        from ccprophet.use_cases.apply_pruning import ApplyPruningUseCase
        from ccprophet.use_cases.prune_tools import PruneToolsUseCase
        from ccprophet.use_cases.reproduce_session import ReproduceSessionUseCase

        conn = connect_readwrite()
        SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
        settings = JsonFileSettingsStore()
        rec_repo = DuckDBRecommendationRepository(conn)
        snap_repo = DuckDBSnapshotRepository(conn)
        snap_store = FilesystemSnapshotStore(SNAPSHOT_ROOT)
        preview = PruneToolsUseCase(recommendations=rec_repo, settings=settings)
        apply_uc = ApplyPruningUseCase(
            prune=preview,
            settings=settings,
            snapshot_store=snap_store,
            snapshots=snap_repo,
            recommendations=rec_repo,
            clock=SystemClock(),
        )
        uc = ReproduceSessionUseCase(
            outcomes=DuckDBOutcomeRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            tool_defs=DuckDBToolDefRepository(conn),
            recommendations=rec_repo,
            apply=apply_uc,
            clock=SystemClock(),
        )
        code = run_reproduce_command(
            uc,
            task=task,
            target_path=target,
            apply=apply_changes,
            as_json=json,
        )
        raise typer.Exit(code)

    @app.command()
    def mark(
        session_id: str = typer.Argument(..., help="Session ID to label"),
        outcome: str = typer.Option(
            ...,
            "--outcome",
            "-o",
            help="success | fail | partial | unlabeled",
        ),
        task: str | None = typer.Option(
            None,
            "--task-type",
            "--task",  # v0.5 alias kept for backwards compat
            help="Task type (e.g., refactor-auth) for pattern reproduction",
        ),
        reason: str | None = typer.Option(
            None, "--reason", help="Short note (optional)"
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Label a session for the Outcome Engine."""
        from ccprophet.adapters.cli.mark import run_mark_command
        from ccprophet.adapters.clock.system import SystemClock
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBOutcomeRepository,
        )
        from ccprophet.use_cases.mark_outcome import MarkOutcomeUseCase

        conn = connect_readwrite()
        uc = MarkOutcomeUseCase(
            sessions=DuckDBSessionRepository(conn),
            outcomes=DuckDBOutcomeRepository(conn),
            clock=SystemClock(),
        )
        code = run_mark_command(
            uc,
            session_id=session_id,
            outcome=outcome,
            task_type=task,
            reason=reason,
            as_json=json,
        )
        raise typer.Exit(code)
