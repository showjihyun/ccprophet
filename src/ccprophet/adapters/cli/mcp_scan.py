from __future__ import annotations

"""CLI adapter for `ccprophet mcp-scan`.

Algorithm
---------
1. Call lister.list_servers().  Empty → print unavailable message, exit 0.
2. Collect called_servers from the last `recent_limit` sessions' tool_calls.
   Tool names follow the pattern ``mcp__<server>__<tool>`` or ``mcp__<server>``.
   We extract the server slug from position [1] after splitting on ``__``.
3. Bucket each McpServerInfo:
   - connected + used        → connected_used
   - connected + unused      → connected_unused   (bloat candidates)
   - failed                  → failed
   - needs_auth              → needs_auth
4. Rich table output (grouped) or JSON.

Name normalisation
------------------
``claude mcp list`` may use names like ``plugin:github:github`` or
``claude.ai Gmail``.  We normalise both sides to a set of candidate slugs:
  - lowercase
  - strip non-alphanumeric characters
  - also take the last segment after ``:`` as an alternate slug

A server is considered "used" if ANY of its candidate slugs appears in the
set of server slugs extracted from tool_call.tool_name strings.

When the match is ambiguous (e.g. multiple candidate slugs all map to
different called servers) we keep the positive "used" result rather than
false-pruning a server that was actually called.  If no slug matches, the
server is conservatively marked unused (better to suggest prune than miss
bloat).
"""

import json as json_module
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import McpServerInfo, Session
    from ccprophet.ports.mcp_scan import McpServerLister
    from ccprophet.ports.repositories import SessionRepository, ToolCallRepository


_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _name_slugs(name: str) -> set[str]:
    """Return candidate slugs for a server name."""
    lower = name.lower()
    slugs: set[str] = set()
    # Whole-name slug: strip non-alphanumeric.
    whole = _NON_ALNUM.sub("", lower)
    if whole:
        slugs.add(whole)
    # Last colon-segment slug.
    if ":" in lower:
        last = lower.rsplit(":", 1)[-1]
        seg = _NON_ALNUM.sub("", last)
        if seg:
            slugs.add(seg)
    # Also try first colon-segment if three parts (plugin:family:name).
    parts = lower.split(":")
    if len(parts) >= 3:
        seg = _NON_ALNUM.sub("", parts[-1])
        if seg:
            slugs.add(seg)
    return slugs or {lower}


def _extract_mcp_server_slug(tool_name: str) -> str | None:
    """Return the server slug from an ``mcp__<server>__<tool>`` tool name.

    Returns None if the tool name does not follow the MCP prefix convention.
    """
    if not tool_name.startswith("mcp__"):
        return None
    parts = tool_name.split("__")
    if len(parts) < 2:
        return None
    # parts[0] = "mcp", parts[1] = server slug
    return parts[1].lower() if parts[1] else None


def _collect_called_slugs(
    sessions: Sequence[Session],
    tool_calls_repo: ToolCallRepository,
) -> set[str]:
    called: set[str] = set()

    for session in sessions:
        for tc in tool_calls_repo.list_for_session(session.session_id):
            slug = _extract_mcp_server_slug(tc.tool_name)
            if slug:
                called.add(slug)
    return called


def _is_used(server: McpServerInfo, called_slugs: set[str]) -> bool:
    """Return True if any candidate slug of server matches called_slugs."""
    return bool(_name_slugs(server.name) & called_slugs)


def run_mcp_scan_command(
    lister: McpServerLister,
    tool_calls_repo: ToolCallRepository,
    sessions_repo: SessionRepository,
    *,
    recent_limit: int = 20,
    as_json: bool = False,
) -> int:
    servers = lister.list_servers()

    if not servers:
        if as_json:
            print(json_module.dumps({"loaded": []}))
        else:
            print(
                "Claude Code `claude mcp list` unavailable or no MCPs loaded."
            )
        return 0

    recent_sessions = sessions_repo.list_recent(recent_limit)
    called_slugs = _collect_called_slugs(list(recent_sessions), tool_calls_repo)

    connected_used: list[McpServerInfo] = []
    connected_unused: list[McpServerInfo] = []
    failed: list[McpServerInfo] = []
    needs_auth: list[McpServerInfo] = []

    for srv in servers:
        if srv.status == "connected":
            if _is_used(srv, called_slugs):
                connected_used.append(srv)
            else:
                connected_unused.append(srv)
        elif srv.status == "failed":
            failed.append(srv)
        elif srv.status == "needs_auth":
            needs_auth.append(srv)
        else:
            # unknown status — treat as unused connected (conservative)
            connected_unused.append(srv)

    if as_json:
        print(
            json_module.dumps(
                {
                    "connected_used": [_srv_dict(s) for s in connected_used],
                    "connected_unused": [_srv_dict(s) for s in connected_unused],
                    "failed": [_srv_dict(s) for s in failed],
                    "needs_auth": [_srv_dict(s) for s in needs_auth],
                },
                indent=2,
            )
        )
    else:
        _render_rich(
            connected_used=connected_used,
            connected_unused=connected_unused,
            failed=failed,
            needs_auth=needs_auth,
            recent_limit=recent_limit,
        )

    has_action = bool(connected_unused or failed or needs_auth)
    return 1 if has_action else 0


def _srv_dict(srv: McpServerInfo) -> dict[str, str]:
    return {
        "name": srv.name,
        "command_or_url": srv.command_or_url,
        "status": srv.status,
    }


def _render_rich(
    *,
    connected_used: list[McpServerInfo],
    connected_unused: list[McpServerInfo],
    failed: list[McpServerInfo],
    needs_auth: list[McpServerInfo],
    recent_limit: int,
) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()

    def _section(
        title: str,
        servers: list[McpServerInfo],
        style: str = "default",
    ) -> None:
        if not servers:
            return
        console.print(f"\n[bold]{title} ({len(servers)})[/]")
        t = Table(show_header=True, header_style="dim", box=None)
        t.add_column("Name")
        t.add_column("Command / URL", overflow="fold")
        for srv in servers:
            t.add_row(f"[{style}]{srv.name}[/{style}]", srv.command_or_url)
        console.print(t)

    _section("\u2713 Used connected servers", connected_used, style="green")
    _section(
        "\u26a0 Unused connected servers",
        connected_unused,
        style="yellow",
    )
    if connected_unused:
        console.print(
            "[dim]  \u2192 consider `ccprophet prune` or disable via"
            " `.claude/settings.json`[/]"
        )
    _section("\u2717 Failed servers", failed, style="red")
    _section("! Needs auth", needs_auth, style="magenta")

    total = len(connected_used) + len(connected_unused) + len(failed) + len(needs_auth)
    unused_or_bad = len(connected_unused) + len(failed) + len(needs_auth)
    console.print()
    if unused_or_bad:
        console.print(
            f"[bold]{total}[/] servers loaded, "
            f"[bold yellow]{unused_or_bad}[/] never called in last "
            f"[bold]{recent_limit}[/] sessions — "
            "disable to save bootstrap tokens."
        )
    else:
        console.print(
            f"[bold green]{total}[/] servers loaded, all connected servers active."
        )
