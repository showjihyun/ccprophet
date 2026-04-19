from __future__ import annotations

import json as json_module
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import Phase, Session
    from ccprophet.ports.pricing import PricingProvider
    from ccprophet.ports.repositories import SessionRepository
    from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase
    from ccprophet.use_cases.detect_phases import DetectPhasesUseCase

from ccprophet.domain.errors import SessionNotFound, UnknownPricingModel
from ccprophet.domain.services.cost import CostCalculator


def run_live_command(
    detect: DetectPhasesUseCase,
    analyze: AnalyzeBloatUseCase,
    *,
    sessions_repo: SessionRepository | None = None,
    as_json: bool = False,
    with_cost: bool = False,
    pricing: PricingProvider | None = None,
) -> int:
    try:
        phases = detect.execute_current()
    except SessionNotFound as e:
        _print_no_session(e, as_json=as_json)
        return 2

    repo = sessions_repo if sessions_repo is not None else detect.sessions
    session = repo.latest_active()
    if session is None:
        msg = "No active session found after phase detection"
        if as_json:
            print(json_module.dumps({"error": msg}))
        else:
            from rich.console import Console

            Console(stderr=True).print(f"[bold red]Error:[/] {msg}")
        return 2

    try:
        report = analyze.execute(session.session_id)
        bloat_ratio = report.bloat_ratio.value
        bloat_tokens = report.bloat_tokens.value
    except SessionNotFound:
        bloat_ratio = 0.0
        bloat_tokens = 0

    session_cost_usd: float | None = None
    if with_cost and pricing is not None:
        try:
            rate = pricing.rate_for(session.model, session.started_at)
            breakdown = CostCalculator.session_cost(session, rate)
            session_cost_usd = float(breakdown.total_cost.amount)
        except UnknownPricingModel:
            session_cost_usd = None

    if as_json:
        print(
            json_module.dumps(
                {
                    "session": _session_dict(session),
                    "phases": [_phase_dict(p) for p in phases],
                    "bloat_ratio": bloat_ratio,
                    "bloat_tokens": bloat_tokens,
                    "session_cost_usd": session_cost_usd,
                },
                indent=2,
                default=str,
            )
        )
        return 0

    _render(session, phases, bloat_ratio, bloat_tokens, session_cost_usd)
    return 0


def _print_no_session(err: SessionNotFound, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"error": str(err)}))
        return
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/] {err}")


def _session_dict(s: Session) -> dict[str, object]:
    return {
        "session_id": s.session_id.value,
        "model": s.model,
        "started_at": s.started_at.isoformat(),
        "total_input_tokens": s.total_input_tokens.value,
        "total_output_tokens": s.total_output_tokens.value,
    }


def _phase_dict(p: Phase) -> dict[str, object]:
    return {
        "phase_type": p.phase_type.value,
        "start_ts": p.start_ts.isoformat(),
        "end_ts": p.end_ts.isoformat() if p.end_ts else None,
        "tool_call_count": p.tool_call_count,
        "confidence": p.detection_confidence,
    }


def _render(
    session: Session,
    phases: Sequence[Phase],
    bloat_ratio: float,
    bloat_tokens: int,
    session_cost_usd: float | None = None,
) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print()
    console.print(f"[bold]Live session:[/] {session.session_id.value}")
    console.print(
        f"Model: {session.model}   "
        f"Started: {session.started_at.strftime('%H:%M:%S')}   "
        f"Tokens in/out: {session.total_input_tokens.value:,}/"
        f"{session.total_output_tokens.value:,}"
    )
    bloat_line = f"Bloat: [bold]{bloat_tokens:,}[/] tokens ({round(bloat_ratio * 100, 1)}%)"
    if session_cost_usd is not None:
        bloat_line += f"   [dim]·[/] Cost: [bold green]${session_cost_usd:.4f}[/]"
    console.print(bloat_line)
    console.print()

    if not phases:
        console.print("[dim]No phases detected yet.[/]")
        return

    table = Table(show_header=True, header_style="dim")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Phase")
    table.add_column("Tools", justify="right")
    table.add_column("Confidence", justify="right")
    table.add_column("Start", style="dim")

    for i, p in enumerate(phases, start=1):
        color = _phase_color(p.phase_type.value)
        table.add_row(
            str(i),
            f"[{color}]{p.phase_type.value}[/{color}]",
            str(p.tool_call_count),
            f"{p.detection_confidence:.2f}",
            p.start_ts.strftime("%H:%M:%S"),
        )
    console.print(table)


def _phase_color(name: str) -> str:
    return {
        "planning": "cyan",
        "implementation": "green",
        "debugging": "red",
        "review": "blue",
        "unknown": "dim",
    }.get(name, "default")
