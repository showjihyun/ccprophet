from __future__ import annotations

import typer

from ccprophet.harness.commands._shared import connect_readonly


def register(app: typer.Typer) -> None:
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

        conn = connect_readonly()
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
    def subagents(
        session: str | None = typer.Option(
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

        conn = connect_readonly()
        uc = ListSubagentsUseCase(subagents=DuckDBSubagentRepository(conn))
        code = run_subagents_command(
            uc,
            DuckDBSessionRepository(conn),
            session=session,
            as_json=json,
        )
        raise typer.Exit(code)

    @app.command("mcp-scan")
    def mcp_scan(
        recent: int = typer.Option(20, "--recent", "-n", help="Sessions to check"),
        json: bool = typer.Option(False, "--json"),
    ) -> None:
        """Scan active MCP servers and flag the ones never called recently."""
        from ccprophet.adapters.cli.mcp_scan import run_mcp_scan_command
        from ccprophet.adapters.mcp_scan.cli_subprocess import ClaudeCliMcpLister
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
            DuckDBToolCallRepository,
        )

        conn = connect_readonly()
        code = run_mcp_scan_command(
            ClaudeCliMcpLister(),
            DuckDBToolCallRepository(conn),
            DuckDBSessionRepository(conn),
            recent_limit=recent,
            as_json=json,
        )
        raise typer.Exit(code)
