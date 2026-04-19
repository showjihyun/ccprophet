from __future__ import annotations

import json as json_module
from collections.abc import Sequence
from typing import TYPE_CHECKING

from ccprophet.domain.values import SessionId

if TYPE_CHECKING:
    from ccprophet.domain.entities import Subagent
    from ccprophet.ports.repositories import SessionRepository
    from ccprophet.use_cases.list_subagents import ListSubagentsUseCase


def run_subagents_command(
    use_case: ListSubagentsUseCase,
    sessions_repo: SessionRepository,
    *,
    session: str | None = None,
    as_json: bool = False,
) -> int:
    parent_sid = _resolve_parent(sessions_repo, session)
    if parent_sid is None:
        if as_json:
            print(json_module.dumps({"subagents": [], "parent_session_id": None}))
        else:
            from rich.console import Console

            Console().print("[dim]No session found.[/]")
        return 1

    rows = list(use_case.execute_for_parent(parent_sid))

    if as_json:
        print(
            json_module.dumps(
                {
                    "parent_session_id": parent_sid.value,
                    "subagents": [_to_dict(s) for s in rows],
                },
                indent=2,
                default=str,
            )
        )
        return 0

    _render_table(parent_sid.value, rows)
    return 0


def _resolve_parent(sessions_repo: SessionRepository, session: str | None) -> SessionId | None:
    if session:
        return SessionId(session)
    latest = sessions_repo.latest_active()
    if latest is not None:
        return latest.session_id
    recents = list(sessions_repo.list_recent(limit=1))
    if recents:
        return recents[0].session_id
    return None


def _to_dict(s: Subagent) -> dict[str, object]:
    return {
        "subagent_id": s.subagent_id.value,
        "parent_session_id": s.parent_session_id.value,
        "agent_type": s.agent_type,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "context_tokens": s.context_tokens.value,
        "tool_call_count": s.tool_call_count,
    }


def _render_table(parent_id: str, rows: Sequence[Subagent]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    if not rows:
        console.print(f"[dim]No subagents recorded for parent session[/] [bold]{parent_id[:12]}[/]")
        return

    table = Table(
        title=f"Subagents for {parent_id[:12]}",
        show_header=True,
        header_style="dim",
    )
    table.add_column("Subagent", overflow="fold")
    table.add_column("Agent", style="dim")
    table.add_column("Started", style="dim")
    table.add_column("Ended", style="dim")
    table.add_column("Tool Calls", justify="right")

    for s in rows:
        started = s.started_at.strftime("%H:%M:%S") if s.started_at else "-"
        ended = s.ended_at.strftime("%H:%M:%S") if s.ended_at else "[yellow]-[/]"
        table.add_row(
            s.subagent_id.value[:12],
            s.agent_type or "-",
            started,
            ended,
            str(s.tool_call_count),
        )

    console.print(table)
