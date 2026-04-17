from __future__ import annotations

import json as json_module
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import CostBreakdown, MonthlyCostSummary
    from ccprophet.use_cases.compute_monthly_cost import ComputeMonthlyCostUseCase
    from ccprophet.use_cases.compute_session_cost import ComputeSessionCostUseCase

from ccprophet.domain.errors import SessionNotFound, UnknownPricingModel
from ccprophet.domain.values import SessionId


def run_cost_command(
    monthly_uc: ComputeMonthlyCostUseCase,
    session_uc: ComputeSessionCostUseCase,
    *,
    month: str | None = None,
    session: str | None = None,
    as_json: bool = False,
) -> int:
    if session:
        return _run_session(session_uc, session, as_json=as_json)

    start, end = _resolve_month_range(month)
    summary = monthly_uc.execute(month_start=start, month_end=end)
    if as_json:
        print(json_module.dumps(_summary_dict(summary), indent=2, default=str))
    else:
        _render_summary(summary)
    return 0


def _run_session(
    session_uc: ComputeSessionCostUseCase, session_id: str, *, as_json: bool
) -> int:
    try:
        cost = session_uc.execute(SessionId(session_id))
    except SessionNotFound as e:
        _print_err(str(e), as_json=as_json)
        return 2
    except UnknownPricingModel as e:
        _print_err(str(e), as_json=as_json)
        return 3

    if as_json:
        print(json_module.dumps(_breakdown_dict(cost), indent=2, default=str))
    else:
        _render_breakdown(cost)
    return 0


def _resolve_month_range(month: str | None) -> tuple[datetime, datetime]:
    if month is None:
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        try:
            start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise SystemExit(f"--month expects YYYY-MM, got {month!r}") from exc
    end = (start + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0)
    return start, end


def _summary_dict(s: MonthlyCostSummary) -> dict[str, object]:
    return {
        "month_start": s.month_start.isoformat(),
        "month_end": s.month_end.isoformat(),
        "session_count": s.session_count,
        "total_cost": _money_dict(s.total_cost),
        "avg_session_cost": _money_dict(s.avg_session_cost),
        "realized_savings": _money_dict(s.realized_savings),
        "by_model": [
            {
                "model": m.model,
                "session_count": m.session_count,
                "total_input_tokens": m.total_input_tokens.value,
                "total_output_tokens": m.total_output_tokens.value,
                "total_cost": _money_dict(m.total_cost),
            }
            for m in s.by_model
        ],
    }


def _breakdown_dict(b: CostBreakdown) -> dict[str, object]:
    return {
        "session_id": b.session_id.value,
        "model": b.model,
        "input_cost": _money_dict(b.input_cost),
        "output_cost": _money_dict(b.output_cost),
        "cache_cost": _money_dict(b.cache_cost),
        "total_cost": _money_dict(b.total_cost),
        "rate_id": b.rate_id,
    }


def _money_dict(m) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {"amount": float(m.amount), "currency": m.currency}


def _print_err(msg: str, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"error": msg}))
        return
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/] {msg}")


def _render_summary(s: MonthlyCostSummary) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print()
    console.print(
        f"[bold]Month:[/] {s.month_start.strftime('%Y-%m')}   "
        f"[bold]Sessions:[/] {s.session_count}   "
        f"[bold]Total:[/] [green]${float(s.total_cost.amount):.2f}[/] "
        f"{s.total_cost.currency}"
    )
    console.print(
        f"Avg/session: ${float(s.avg_session_cost.amount):.4f}   "
        f"Realized savings: [bold cyan]${float(s.realized_savings.amount):.2f}[/]"
    )

    if not s.by_model:
        return

    table = Table(show_header=True, header_style="dim")
    table.add_column("Model")
    table.add_column("Sessions", justify="right")
    table.add_column("Input tok", justify="right")
    table.add_column("Output tok", justify="right")
    table.add_column("Cost ($)", justify="right")

    for m in s.by_model:
        table.add_row(
            m.model,
            str(m.session_count),
            f"{m.total_input_tokens.value:,}",
            f"{m.total_output_tokens.value:,}",
            f"${float(m.total_cost.amount):.4f}",
        )
    console.print(table)


def _render_breakdown(b: CostBreakdown) -> None:
    from rich.console import Console

    console = Console()
    console.print(f"[bold]Session:[/] {b.session_id.value}  [dim]({b.model})[/]")
    console.print(
        f"  input:  ${float(b.input_cost.amount):.4f}   "
        f"output: ${float(b.output_cost.amount):.4f}   "
        f"cache: ${float(b.cache_cost.amount):.4f}"
    )
    console.print(
        f"  [bold green]total: ${float(b.total_cost.amount):.4f}[/] "
        f"{b.total_cost.currency}"
    )
