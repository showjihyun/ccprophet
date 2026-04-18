from __future__ import annotations

from typing import Optional

import typer

from ccprophet.harness.commands._shared import connect_readonly


def register(app: typer.Typer) -> None:
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

        conn = connect_readonly()
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

        conn = connect_readonly()
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

        conn = connect_readonly()
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

        conn = connect_readonly()
        uc = EstimateBudgetUseCase(
            outcomes=DuckDBOutcomeRepository(conn),
            tool_calls=DuckDBToolCallRepository(conn),
            tool_defs=DuckDBToolDefRepository(conn),
            pricing=DuckDBPricingProvider(conn),
        )
        code = run_budget_command(uc, task=task, as_json=json)
        raise typer.Exit(code)
