from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer  # module-level so typer.Context annotations resolve via get_annotations

if TYPE_CHECKING:
    import duckdb

DB_PATH = Path.home() / ".claude-prophet" / "events.duckdb"
SNAPSHOT_ROOT = Path.home() / ".claude-prophet" / "snapshots"
DEFAULT_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
DEFAULT_JSONL_ROOT = Path.home() / ".claude" / "projects"


def _connect_readonly() -> duckdb.DuckDBPyConnection:
    import duckdb

    if not DB_PATH.exists():
        raise SystemExit(
            f"ccprophet DB not found at {DB_PATH}\n"
            f"Run `ccprophet install` or trigger a hook first."
        )
    return duckdb.connect(str(DB_PATH), read_only=True)


def _connect_readwrite() -> duckdb.DuckDBPyConnection:
    import duckdb

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


def main() -> None:
    import typer

    app = typer.Typer(
        name="ccprophet",
        help="Context Efficiency Profiler for Claude Code",
        no_args_is_help=True,
    )

    @app.command()
    def bloat(
        session: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
        cost: bool = typer.Option(
            False, "--cost", help="Include $ estimate for bloat tokens"
        ),
    ) -> None:
        """Loaded vs Referenced bloat report."""
        from ccprophet.adapters.cli.bloat import run_bloat_command
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
            DuckDBToolDefRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBPricingProvider,
        )
        from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase

        conn = _connect_readonly()
        sessions_repo = DuckDBSessionRepository(conn)
        uc = AnalyzeBloatUseCase(
            sessions=sessions_repo,
            tool_defs=DuckDBToolDefRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
        )
        code = run_bloat_command(
            uc,
            session=session,
            as_json=json,
            with_cost=cost,
            sessions_repo=sessions_repo if cost else None,
            pricing=DuckDBPricingProvider(conn) if cost else None,
        )
        raise typer.Exit(code)

    @app.command()
    def ingest(
        root: Path = typer.Option(
            DEFAULT_JSONL_ROOT, "--root", help="Claude Code projects directory"
        ),
        file: Optional[Path] = typer.Option(
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

        conn = _connect_readwrite()
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

    @app.command()
    def install(
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Preview changes without writing"
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Register hooks, create DB, set up ccprophet."""
        from ccprophet.adapters.cli.install import run_install_command

        code = run_install_command(dry_run=dry_run, as_json=json)
        raise typer.Exit(code)

    @app.command()
    def sessions(
        limit: int = typer.Option(10, "--limit", "-n", help="Max rows"),
        latest: bool = typer.Option(False, "--latest", help="Show only the latest"),
        id_only: bool = typer.Option(False, "--id-only", help="Print just the session id"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """List recent sessions."""
        from ccprophet.adapters.cli.sessions import run_sessions_command
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v3_repositories import (
            DuckDBSubagentRepository,
        )

        conn = _connect_readonly()
        code = run_sessions_command(
            DuckDBSessionRepository(conn),
            limit=limit,
            latest=latest,
            id_only=id_only,
            as_json=json,
            subagents_repo=DuckDBSubagentRepository(conn),
        )
        raise typer.Exit(code)

    @app.command()
    def recommend(
        session: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID"),
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
        from ccprophet.use_cases.recommend_action import RecommendActionUseCase

        conn = _connect_readwrite()
        uc = RecommendActionUseCase(
            sessions=DuckDBSessionRepository(conn),
            tool_defs=DuckDBToolDefRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            recommendations=DuckDBRecommendationRepository(conn),
            pricing=DuckDBPricingProvider(conn),
            clock=SystemClock(),
        )
        code = run_recommend_command(
            uc, session=session, as_json=json, persist=not no_persist
        )
        raise typer.Exit(code)

    snapshot_app = typer.Typer(help="Manage settings snapshots")
    app.add_typer(snapshot_app, name="snapshot")

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

        conn = _connect_readonly()
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

        conn = _connect_readwrite()
        SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
        uc = RestoreSnapshotUseCase(
            settings=JsonFileSettingsStore(),
            snapshot_store=FilesystemSnapshotStore(SNAPSHOT_ROOT),
            snapshots=DuckDBSnapshotRepository(conn),
        )
        code = run_snapshot_restore_command(uc, snapshot_id=snapshot_id, as_json=json)
        raise typer.Exit(code)

    @app.command()
    def mark(
        session_id: str = typer.Argument(..., help="Session ID to label"),
        outcome: str = typer.Option(
            ..., "--outcome", "-o",
            help="success | fail | partial | unlabeled",
        ),
        task: Optional[str] = typer.Option(
            None, "--task", help="Task type (e.g., refactor-auth)"
        ),
        reason: Optional[str] = typer.Option(
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

        conn = _connect_readwrite()
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

    @app.command()
    def statusline(
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """One-line session status for Claude Code statusLine integration."""
        if not DB_PATH.exists():
            if json:
                import json as _j
                print(_j.dumps({"status": "no-db"}))
            else:
                print("(ccprophet: not installed)")
            raise typer.Exit(0)

        import duckdb as _duckdb

        from ccprophet.adapters.cli.statusline import run_statusline_command
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
            DuckDBToolDefRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBPricingProvider,
        )

        conn = _duckdb.connect(str(DB_PATH), read_only=True)
        tool_defs = DuckDBToolDefRepository(conn)
        tool_calls = DuckDBToolCallRepository(conn)
        code = run_statusline_command(
            DuckDBSessionRepository(conn),
            DuckDBPricingProvider(conn),
            tool_defs_for=tool_defs.list_for_session,
            tool_calls_for=tool_calls.list_for_session,
            as_json=json,
        )
        raise typer.Exit(code)

    @app.command()
    def quality(
        model: Optional[str] = typer.Option(
            None, "--model", help="Filter to a single model"
        ),
        window: int = typer.Option(
            7, "--window", help="Recent window (days)"
        ),
        baseline: int = typer.Option(
            30, "--baseline", help="Baseline window (days, prior to recent)"
        ),
        threshold: float = typer.Option(
            2.0, "--threshold", help="Sigma threshold for regression flag"
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
        ascii: bool = typer.Option(
            False, "--ascii", help="ASCII-only sparklines (fallback terminals)"
        ),
        export_parquet: Optional[Path] = typer.Option(
            None, "--export-parquet",
            help="Dump time series to a Parquet file",
        ),
    ) -> None:
        """Quality Watch - detect model performance regressions over time."""
        from ccprophet.adapters.cli.quality import run_quality_command
        from ccprophet.adapters.clock.system import SystemClock
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBOutcomeRepository,
        )
        from ccprophet.use_cases.assess_quality import AssessQualityUseCase

        conn = _connect_readonly()
        uc = AssessQualityUseCase(
            sessions=DuckDBSessionRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            outcomes=DuckDBOutcomeRepository(conn),
            clock=SystemClock(),
        )
        code = run_quality_command(
            uc,
            model=model,
            window_days=window,
            baseline_days=baseline,
            threshold_sigma=threshold,
            as_json=json,
            ascii_only=ascii,
            export_parquet=export_parquet,
        )
        raise typer.Exit(code)

    @app.command()
    def cost(
        month: Optional[str] = typer.Option(
            None, "--month", help="YYYY-MM; defaults to current month"
        ),
        session: Optional[str] = typer.Option(
            None, "--session", "-s", help="Single session id"
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Cost Dashboard - monthly $ summary and per-session cost."""
        from ccprophet.adapters.cli.cost import run_cost_command
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBPricingProvider,
            DuckDBRecommendationRepository,
        )
        from ccprophet.use_cases.compute_monthly_cost import ComputeMonthlyCostUseCase
        from ccprophet.use_cases.compute_session_cost import ComputeSessionCostUseCase

        conn = _connect_readonly()
        sessions_repo = DuckDBSessionRepository(conn)
        pricing = DuckDBPricingProvider(conn)
        recs = DuckDBRecommendationRepository(conn)
        monthly = ComputeMonthlyCostUseCase(
            sessions=sessions_repo, recommendations=recs, pricing=pricing
        )
        session_cost_uc = ComputeSessionCostUseCase(
            sessions=sessions_repo, pricing=pricing
        )
        code = run_cost_command(
            monthly, session_cost_uc, month=month, session=session, as_json=json
        )
        raise typer.Exit(code)

    @app.command()
    def reproduce(
        task: str = typer.Argument(..., help="Task type to reproduce"),
        target: Path = typer.Option(
            DEFAULT_SETTINGS_PATH, "--target", "-t",
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

        conn = _connect_readwrite()
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
    def diff(
        sid_a: str = typer.Argument(..., help="Session A"),
        sid_b: str = typer.Argument(..., help="Session B"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Structural delta between two sessions."""
        from ccprophet.adapters.cli.diff import run_diff_command
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
            DuckDBToolDefRepository,
        )
        from ccprophet.use_cases.diff_sessions import DiffSessionsUseCase

        conn = _connect_readonly()
        uc = DiffSessionsUseCase(
            sessions=DuckDBSessionRepository(conn),
            tool_defs=DuckDBToolDefRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
        )
        code = run_diff_command(uc, sid_a=sid_a, sid_b=sid_b, as_json=json)
        raise typer.Exit(code)

    @app.command()
    def postmortem(
        session_id: str = typer.Argument(..., help="Failed session ID"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Explain why a session failed vs similar successes."""
        from ccprophet.adapters.cli.postmortem import run_postmortem_command
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
            DuckDBToolDefRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBOutcomeRepository,
        )
        from ccprophet.use_cases.analyze_postmortem import AnalyzePostmortemUseCase

        conn = _connect_readonly()
        uc = AnalyzePostmortemUseCase(
            sessions=DuckDBSessionRepository(conn),
            outcomes=DuckDBOutcomeRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            tool_defs=DuckDBToolDefRepository(conn),
        )
        code = run_postmortem_command(uc, session_id=session_id, as_json=json)
        raise typer.Exit(code)

    @app.command()
    def budget(
        task: str = typer.Argument(..., help="Task type (e.g., refactor-auth)"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Budget envelope for a task type (needs >=3 success-labelled sessions)."""
        from ccprophet.adapters.cli.budget import run_budget_command
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBToolCallRepository,
            DuckDBToolDefRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBOutcomeRepository,
            DuckDBPricingProvider,
        )
        from ccprophet.use_cases.estimate_budget import EstimateBudgetUseCase

        conn = _connect_readonly()
        uc = EstimateBudgetUseCase(
            outcomes=DuckDBOutcomeRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            tool_defs=DuckDBToolDefRepository(conn),
            pricing=DuckDBPricingProvider(conn),
        )
        code = run_budget_command(uc, task=task, as_json=json)
        raise typer.Exit(code)

    @app.command()
    def prune(
        target: Path = typer.Option(
            DEFAULT_SETTINGS_PATH, "--target", "-t",
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

        conn = _connect_readwrite()
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
    def subagents(
        session: Optional[str] = typer.Option(
            None, "--session", "-s", help="Parent session ID"
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """List Task-tool-spawned subagents for a parent session."""
        from ccprophet.adapters.cli.subagents import run_subagents_command
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v3_repositories import (
            DuckDBSubagentRepository,
        )
        from ccprophet.use_cases.list_subagents import ListSubagentsUseCase

        conn = _connect_readonly()
        uc = ListSubagentsUseCase(subagents=DuckDBSubagentRepository(conn))
        code = run_subagents_command(
            uc,
            DuckDBSessionRepository(conn),
            session=session,
            as_json=json,
        )
        raise typer.Exit(code)

    @app.command()
    def forecast(
        session: Optional[str] = typer.Option(
            None, "--session", "-s", help="Session ID (default: latest active)"
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Forecast when this session will hit the autocompact threshold."""
        from ccprophet.adapters.cli.forecast import run_forecast_command
        from ccprophet.adapters.clock.system import SystemClock
        from ccprophet.adapters.forecast.linear import LinearForecastModel
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBEventRepository,
            DuckDBSessionRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v3_repositories import (
            DuckDBForecastRepository,
        )
        from ccprophet.use_cases.forecast_compact import ForecastCompactUseCase

        conn = _connect_readwrite()
        uc = ForecastCompactUseCase(
            sessions=DuckDBSessionRepository(conn),
            events=DuckDBEventRepository(conn),
            forecasts=DuckDBForecastRepository(conn),
            model=LinearForecastModel(),
            clock=SystemClock(),
        )
        code = run_forecast_command(uc, session=session, as_json=json)
        raise typer.Exit(code)

    @app.command()
    def rollup(
        older_than: str = typer.Option(
            "90d", "--older-than", help="Cutoff age (e.g. 90d, 30d, 0d)"
        ),
        apply_changes: bool = typer.Option(
            False, "--apply",
            help="Actually summarize and delete (default is dry-run)",
        ),
        archive_parquet: Optional[Path] = typer.Option(
            None, "--archive-parquet",
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

        conn = _connect_readwrite()
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

    # ------------------------------------------------------------------ query
    query_app = typer.Typer(help="Read-only SQL query against events.duckdb")
    app.add_typer(query_app, name="query")

    @query_app.command("run")
    def query_run(
        sql: str = typer.Argument(..., help="SQL to run"),
        limit: int = typer.Option(100, "--limit", "-n", help="Max rows to return"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Run an ad-hoc read-only SQL query against events.duckdb."""
        if not DB_PATH.exists():
            typer.secho(
                f"ccprophet DB not found at {DB_PATH}\n"
                "Run `ccprophet install` or trigger a hook first.",
                err=True,
                fg="red",
            )
            raise typer.Exit(2)
        from ccprophet.adapters.cli.query import run_query_command

        raise typer.Exit(run_query_command(db_path=DB_PATH, sql=sql, as_json=json, limit=limit))

    @query_app.command("tables")
    def query_tables(
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """List all tables in events.duckdb with row counts."""
        if not DB_PATH.exists():
            typer.secho(
                f"ccprophet DB not found at {DB_PATH}\n"
                "Run `ccprophet install` or trigger a hook first.",
                err=True,
                fg="red",
            )
            raise typer.Exit(2)
        from ccprophet.adapters.cli.query import run_query_tables_command

        raise typer.Exit(run_query_tables_command(db_path=DB_PATH, as_json=json))

    @query_app.command("schema")
    def query_schema(
        table: str = typer.Argument(..., help="Table name"),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """Show column types for a table in events.duckdb."""
        if not DB_PATH.exists():
            typer.secho(
                f"ccprophet DB not found at {DB_PATH}\n"
                "Run `ccprophet install` or trigger a hook first.",
                err=True,
                fg="red",
            )
            raise typer.Exit(2)
        from ccprophet.adapters.cli.query import run_query_schema_command

        raise typer.Exit(run_query_schema_command(db_path=DB_PATH, table=table, as_json=json))

    @app.command()
    def doctor(
        migrate: bool = typer.Option(
            False, "--migrate", help="Apply pending schema migrations"
        ),
        repair: bool = typer.Option(
            False, "--repair", help="Delete orphan records (destructive)"
        ),
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ) -> None:
        """DB health checks — schema version, orphans, data quality, disk usage."""
        from ccprophet.adapters.cli.doctor import run_doctor_command

        code = run_doctor_command(
            db_path=DB_PATH,
            as_json=json,
            repair=repair,
            migrate=migrate,
        )
        raise typer.Exit(code)

    @app.command()
    def mcp() -> None:
        """Run the read-only MCP stdio server (for Claude Code registration)."""
        from ccprophet.harness.mcp_main import main as mcp_main

        mcp_main()

    @app.command()
    def serve(
        host: str = typer.Option(
            "127.0.0.1", "--host", help="Bind host (localhost only)"
        ),
        port: int = typer.Option(8765, "--port", help="Bind port"),
        open_: bool = typer.Option(
            False, "--open", help="Open the viewer in the default browser"
        ),
    ) -> None:
        """Run the local Work DAG viewer at http://127.0.0.1:8765."""
        from ccprophet.harness.web_main import serve as _serve

        _serve(host=host, port=port, open_browser=open_)

    @app.command()
    def live(
        json: bool = typer.Option(False, "--json", help="Output as JSON"),
        cost: bool = typer.Option(
            False, "--cost", help="Include session $ estimate"
        ),
    ) -> None:
        """Snapshot of the current active session (phases + bloat)."""
        from ccprophet.adapters.cli.live import run_live_command
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBEventRepository,
            DuckDBPhaseRepository,
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
            DuckDBToolDefRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBPricingProvider,
        )
        from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
        from ccprophet.use_cases.detect_phases import DetectPhasesUseCase

        conn = _connect_readwrite()
        sessions_repo = DuckDBSessionRepository(conn)
        detect = DetectPhasesUseCase(
            sessions=sessions_repo,
            events=DuckDBEventRepository(conn),
            phases=DuckDBPhaseRepository(conn),
        )
        analyze = AnalyzeBloatUseCase(
            sessions=sessions_repo,
            tool_defs=DuckDBToolDefRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
        )
        code = run_live_command(
            detect,
            analyze,
            as_json=json,
            with_cost=cost,
            pricing=DuckDBPricingProvider(conn) if cost else None,
        )
        raise typer.Exit(code)

    app()
