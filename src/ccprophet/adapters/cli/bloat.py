from __future__ import annotations

import json as json_module
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import Session
    from ccprophet.ports.pricing import PricingProvider
    from ccprophet.ports.repositories import SessionRepository
    from ccprophet.use_cases.analyze_bloat import AnalyzeBloatUseCase

from ccprophet.domain.errors import SessionNotFound, UnknownPricingModel
from ccprophet.domain.values import SessionId


def run_bloat_command(
    use_case: AnalyzeBloatUseCase,
    *,
    session: str | None = None,
    as_json: bool = False,
    with_cost: bool = False,
    sessions_repo: SessionRepository | None = None,
    pricing: PricingProvider | None = None,
) -> int:
    from rich.console import Console
    from rich.table import Table

    console = Console(stderr=True)

    try:
        if session:
            report = use_case.execute(SessionId(session))
            resolved_sid = SessionId(session)
        else:
            report = use_case.execute_current()
            resolved_sid = None
    except SessionNotFound as e:
        console.print(f"[bold red]Error:[/] {e}")
        return 2

    bloat_cost_usd: float | None = None
    total_cost_usd: float | None = None
    if with_cost and sessions_repo is not None and pricing is not None:
        session_obj = _resolve_session(sessions_repo, resolved_sid)
        if session_obj is not None:
            rate = _safe_rate(pricing, session_obj)
            if rate is not None:
                bloat_cost_usd = float(
                    _tokens_to_usd(report.bloat_tokens.value, rate.input_per_mtok)
                )
                total_cost_usd = float(
                    _tokens_to_usd(report.total_tokens.value, rate.input_per_mtok)
                )

    if as_json:
        data = {
            "total_tokens": report.total_tokens.value,
            "bloat_tokens": report.bloat_tokens.value,
            "bloat_ratio": report.bloat_ratio.value,
            "bloat_cost_usd": bloat_cost_usd,
            "total_cost_usd": total_cost_usd,
            "used_count": report.used_count,
            "bloat_count": report.bloat_count,
            "sources": [
                {
                    "source": s.source,
                    "total_tokens": s.total_tokens.value,
                    "bloat_tokens": s.bloat_tokens.value,
                    "bloat_pct": s.bloat_ratio.as_percent(),
                    "tool_count": s.tool_count,
                    "bloat_count": s.bloat_count,
                }
                for s in report.by_source().values()
            ],
            "items": [
                {
                    "tool_name": i.tool_name,
                    "source": i.source,
                    "tokens": i.tokens.value,
                    "used": i.used,
                }
                for i in report.items
            ],
        }
        print(json_module.dumps(data, indent=2))
        return 0

    console.print()
    console.print("[bold]Bloat Report[/]", justify="center")
    console.print()

    table = Table(show_header=True, header_style="dim")
    table.add_column("Source", style="default")
    table.add_column("Bloat Tokens", justify="right", style="bold")
    table.add_column("Total", justify="right")
    table.add_column("Bloat %", justify="right")

    for source_summary in sorted(
        report.by_source().values(),
        key=lambda s: s.bloat_tokens.value,
        reverse=True,
    ):
        pct = source_summary.bloat_ratio.as_percent()
        style = "red" if pct > 50 else "yellow" if pct > 0 else "green"
        table.add_row(
            source_summary.source,
            f"{source_summary.bloat_tokens.value:,}",
            f"{source_summary.total_tokens.value:,}",
            f"[{style}]{pct}%[/{style}]",
        )

    console.print(table)
    console.print()
    bloat_tail = (
        f"Total bloat: [bold]{report.bloat_tokens.value:,}[/] tokens "
        f"({report.bloat_ratio.as_percent()}% of loaded tools)"
    )
    if bloat_cost_usd is not None:
        bloat_tail += f"  [dim]≈[/] [bold green]${bloat_cost_usd:.4f}[/]"
    console.print(bloat_tail)

    if report.bloat_count > 0:
        console.print()
        console.print("[dim]Recommended: disable unused tool sources to free context.[/]")

    return 0


def _resolve_session(sessions_repo: SessionRepository, sid: SessionId | None) -> Session | None:
    if sid is not None:
        return sessions_repo.get(sid)
    return sessions_repo.latest_active()


def _safe_rate(pricing: PricingProvider, session: Session):  # type: ignore[no-untyped-def]
    try:
        return pricing.rate_for(session.model, session.started_at)
    except UnknownPricingModel:
        return None


def _tokens_to_usd(tokens: int, rate_per_mtok: float) -> Decimal:
    if tokens == 0:
        return Decimal(0)
    return Decimal(str(rate_per_mtok)) * Decimal(tokens) / Decimal(1_000_000)
