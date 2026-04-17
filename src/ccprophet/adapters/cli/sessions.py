from __future__ import annotations

import json as json_module
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import Session
    from ccprophet.ports.repositories import SessionRepository
    from ccprophet.ports.subagents import SubagentRepository


def run_sessions_command(
    sessions_repo: SessionRepository,
    *,
    limit: int = 10,
    latest: bool = False,
    id_only: bool = False,
    as_json: bool = False,
    subagents_repo: SubagentRepository | None = None,
) -> int:
    rows = list(sessions_repo.list_recent(limit=1 if latest else limit))

    if latest and id_only:
        if not rows:
            return 1
        print(rows[0].session_id.value)
        return 0

    subagent_counts = _count_subagents(rows, subagents_repo)

    if as_json:
        print(
            json_module.dumps(
                [_to_dict(s, subagent_counts.get(s.session_id.value, 0)) for s in rows],
                indent=2,
                default=str,
            )
        )
        return 0

    _render_table(rows, subagent_counts)
    return 0 if rows else 1


def _count_subagents(
    rows: Sequence[Session], subagents_repo: SubagentRepository | None
) -> dict[str, int]:
    if subagents_repo is None:
        return {}
    counts: dict[str, int] = {}
    for s in rows:
        counts[s.session_id.value] = len(
            list(subagents_repo.list_for_parent(s.session_id))
        )
    return counts


def _to_dict(s: Session, subagent_count: int = 0) -> dict[str, object]:
    return {
        "session_id": s.session_id.value,
        "project_slug": s.project_slug,
        "model": s.model,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "total_input_tokens": s.total_input_tokens.value,
        "total_output_tokens": s.total_output_tokens.value,
        "compacted": s.compacted,
        "subagent_count": subagent_count,
    }


def _render_table(
    rows: Sequence[Session], subagent_counts: dict[str, int]
) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    if not rows:
        console.print("[dim]No sessions recorded yet.[/]")
        return

    show_subagents = any(subagent_counts.values())

    table = Table(show_header=True, header_style="dim")
    table.add_column("Session", style="default")
    table.add_column("Project")
    table.add_column("Model")
    table.add_column("Started", style="dim")
    table.add_column("Status")
    table.add_column("Tokens", justify="right")
    if show_subagents:
        table.add_column("Subagents", justify="right")

    for s in rows:
        status = "[yellow]active[/]" if s.ended_at is None else "ended"
        if s.compacted:
            status += " [magenta](compacted)[/]"
        tokens = s.total_input_tokens.value + s.total_output_tokens.value
        row = [
            s.session_id.value[:12],
            s.project_slug,
            s.model,
            s.started_at.strftime("%Y-%m-%d %H:%M") if s.started_at else "-",
            status,
            f"{tokens:,}",
        ]
        if show_subagents:
            count = subagent_counts.get(s.session_id.value, 0)
            row.append(str(count) if count else "[dim]-[/]")
        table.add_row(*row)

    console.print(table)
