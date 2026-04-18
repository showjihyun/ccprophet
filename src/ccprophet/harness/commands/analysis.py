from __future__ import annotations

from pathlib import Path

import typer

from ccprophet.harness.commands._shared import (
    DB_PATH,
    connect_readonly,
    connect_readwrite,
)


def register(app: typer.Typer) -> None:
    @app.command()
    def bloat(
        session: str | None = typer.Option(None, "--session", "-s", help="Session ID"),
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

        conn = connect_readonly()
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

        conn = connect_readwrite()
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
            sessions_repo=sessions_repo,
            as_json=json,
            with_cost=cost,
            pricing=DuckDBPricingProvider(conn) if cost else None,
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

        from ccprophet.adapters.cli.statusline import run_statusline_command
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
            DuckDBToolDefRepository,
        )
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBPricingProvider,
        )

        conn = connect_readonly()
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
        model: str | None = typer.Option(
            None, "--model", help="Filter to a single model"
        ),
        window: int = typer.Option(7, "--window", help="Recent window (days)"),
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
        export_parquet: Path | None = typer.Option(
            None,
            "--export-parquet",
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

        conn = connect_readonly()
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
    def forecast(
        session: str | None = typer.Option(
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

        conn = connect_readwrite()
        uc = ForecastCompactUseCase(
            sessions=DuckDBSessionRepository(conn),
            events=DuckDBEventRepository(conn),
            forecasts=DuckDBForecastRepository(conn),
            model=LinearForecastModel(),
            clock=SystemClock(),
        )
        code = run_forecast_command(uc, session=session, as_json=json)
        raise typer.Exit(code)
