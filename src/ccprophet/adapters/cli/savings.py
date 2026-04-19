"""Render the token-savings dashboard."""

from __future__ import annotations

import json as json_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.use_cases.compute_savings import ComputeSavingsUseCase, SavingsSummary


def run_savings_command(
    use_case: ComputeSavingsUseCase,
    *,
    window_days: int = 30,
    as_json: bool = False,
) -> int:
    summary = use_case.execute(window_days=window_days)

    if as_json:
        print(json_module.dumps(_summary_dict(summary), indent=2, default=str))
        return 0

    _render(summary)
    return 0


def _summary_dict(s: SavingsSummary) -> dict:  # type: ignore[type-arg]
    return {
        "window_start": s.window_start.isoformat(),
        "window_end": s.window_end.isoformat(),
        "applied": {
            "count": s.applied_count,
            "total_usd": float(s.applied_total.amount),
            "items": [
                {
                    "kind": r.kind.value,
                    "target": r.target,
                    "savings_usd": float(r.est_savings_usd.amount),
                }
                for r in s.applied_items
            ],
        },
        "pending": {
            "count": s.pending_count,
            "total_usd": float(s.pending_total.amount),
            "items": [
                {
                    "kind": r.kind.value,
                    "target": r.target,
                    "savings_usd": float(r.est_savings_usd.amount),
                    "confidence": r.confidence.value,
                }
                for r in s.pending_items
            ],
        },
        "active_env_vars": [
            {"name": e.name, "value": e.value, "source": e.source} for e in s.active_env_vars
        ],
        "opportunities": [
            {"name": o.name, "suggested_value": o.suggested_value, "note": o.note}
            for o in s.opportunity_env_vars
        ],
        "total_potential_usd": float(s.total_potential.amount),
    }


def _render(s: SavingsSummary) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print()
    console.print(
        f"[bold]Token Savings Dashboard[/]  "
        f"[dim]{s.window_start.strftime('%Y-%m-%d')} → "
        f"{s.window_end.strftime('%Y-%m-%d')}[/]"
    )

    # Applied
    console.print()
    console.print(
        f"[bold green]Applied[/]  "
        f"{s.applied_count} recommendation(s)  "
        f"[bold]${float(s.applied_total.amount):.4f}[/] realized"
    )
    if s.applied_items:
        applied_table = Table(show_header=True, header_style="dim")
        applied_table.add_column("Kind")
        applied_table.add_column("Target")
        applied_table.add_column("Saved ($)", justify="right")
        for r in s.applied_items[:10]:
            applied_table.add_row(
                r.kind.value,
                r.target or "-",
                f"${float(r.est_savings_usd.amount):.4f}",
            )
        console.print(applied_table)
    if s.active_env_vars:
        console.print("  [dim]Active env vars:[/]")
        for e in s.active_env_vars:
            console.print(f"    [cyan]{e.name}={e.value}[/]  [dim]({e.source})[/]")

    # Pending
    console.print()
    console.print(
        f"[bold yellow]Pending[/]  "
        f"{s.pending_count} recommendation(s)  "
        f"[bold]${float(s.pending_total.amount):.4f}[/] potential"
    )
    if s.pending_items:
        pending_table = Table(show_header=True, header_style="dim")
        pending_table.add_column("Kind")
        pending_table.add_column("Target")
        pending_table.add_column("Potential $", justify="right")
        pending_table.add_column("Conf.", justify="right")
        for r in s.pending_items[:10]:
            pending_table.add_row(
                r.kind.value,
                r.target or "-",
                f"${float(r.est_savings_usd.amount):.4f}",
                f"{r.confidence.value:.2f}",
            )
        console.print(pending_table)

    # Opportunities
    if s.opportunity_env_vars:
        console.print()
        console.print(
            f"[bold cyan]Opportunities[/]  {len(s.opportunity_env_vars)} knob(s) not yet set"
        )
        for o in s.opportunity_env_vars:
            console.print(f"  [cyan]{o.name}={o.suggested_value}[/]  [dim]{o.note}[/]")
        console.print("  [dim]Add to `.claude/settings.json` env block or your shell profile.[/]")

    # Total
    console.print()
    console.print(
        f"[bold]Total realized + potential:[/] "
        f"[bold green]${float(s.total_potential.amount):.4f}[/]"
    )
