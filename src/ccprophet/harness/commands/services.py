from __future__ import annotations

import typer


def register(app: typer.Typer) -> None:
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
    def mcp() -> None:
        """Run the read-only MCP stdio server (for Claude Code registration)."""
        from ccprophet.harness.mcp_main import main as mcp_main

        mcp_main()
