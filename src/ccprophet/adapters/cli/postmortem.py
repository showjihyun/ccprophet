from __future__ import annotations

import json as json_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import PostmortemReport
    from ccprophet.use_cases.analyze_postmortem import AnalyzePostmortemUseCase

from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import SessionId


def run_postmortem_command(
    use_case: AnalyzePostmortemUseCase,
    *,
    session_id: str,
    as_json: bool = False,
) -> int:
    try:
        report = use_case.execute(SessionId(session_id))
    except SessionNotFound as e:
        _err(str(e), as_json=as_json)
        return 2

    if as_json:
        print(json_module.dumps(_report_dict(report), indent=2, default=str))
        return 0

    _render(report)
    return 0


def _report_dict(r: PostmortemReport) -> dict[str, object]:
    return {
        "failed_session_id": r.failed_session_id.value,
        "task_type": r.task_type.value if r.task_type else None,
        "sample_size": r.sample_size,
        "findings": [
            {"kind": f.kind, "detail": f.detail} for f in r.findings
        ],
        "suggestions": list(r.suggestions),
    }


def _err(msg: str, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"error": msg}))
        return
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/] {msg}")


def _render(r: PostmortemReport) -> None:
    from rich.console import Console

    console = Console()
    task_label = r.task_type.value if r.task_type else "(unlabeled)"
    console.print(
        f"[bold]Postmortem[/] for {r.failed_session_id.value}  "
        f"[dim](task: {task_label}, successes compared: {r.sample_size})[/]"
    )
    if not r.findings:
        console.print("[dim]No structural deltas detected.[/]")
        return
    console.print()
    for f in r.findings:
        console.print(f"  [yellow]·[/] [bold]{f.kind}[/]: {f.detail}")
    if r.suggestions:
        console.print()
        console.print("[bold]Suggestions[/]")
        for s in r.suggestions:
            console.print(f"  - {s}")
