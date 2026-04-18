"""CLI driving adapter for `ccprophet forecast`."""
from __future__ import annotations

import json as json_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import Forecast
    from ccprophet.ports.pricing import PricingProvider
    from ccprophet.ports.repositories import SessionRepository
    from ccprophet.use_cases.forecast_compact import ForecastCompactUseCase

from ccprophet.domain.errors import SessionNotFound, UnknownPricingModel
from ccprophet.domain.services.cost import CostCalculator
from ccprophet.domain.values import SessionId


def run_forecast_command(
    use_case: ForecastCompactUseCase,
    *,
    session: str | None = None,
    as_json: bool = False,
    with_cost: bool = False,
    sessions_repo: SessionRepository | None = None,
    pricing: PricingProvider | None = None,
) -> int:
    try:
        forecast = (
            use_case.execute(SessionId(session))
            if session
            else use_case.execute_current()
        )
    except SessionNotFound as e:
        _print_error(str(e), as_json=as_json)
        return 2

    payload = _forecast_to_dict(forecast)

    # FR-10.3: annotate forecast with session-to-date $ so users see the cost
    # trajectory alongside the compact ETA.
    if with_cost and sessions_repo is not None and pricing is not None:
        session_obj = sessions_repo.get(forecast.session_id)
        if session_obj is not None:
            try:
                rate = pricing.rate_for(session_obj.model, session_obj.started_at)
                breakdown = CostCalculator.session_cost(session_obj, rate)
                payload["cost_to_date_usd"] = float(breakdown.total_cost.amount)
                payload["pricing_rate_id"] = breakdown.rate_id
            except UnknownPricingModel:
                payload["cost_to_date_usd"] = None
                payload["pricing_rate_id"] = None

    if as_json:
        print(json_module.dumps(payload, indent=2))
        return 0

    _render(forecast, cost_to_date=payload.get("cost_to_date_usd"))
    return 0


def _print_error(msg: str, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"error": msg}))
        return
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/] {msg}")


def _forecast_to_dict(forecast: Forecast) -> dict[str, object]:
    return {
        "forecast_id": forecast.forecast_id,
        "session_id": forecast.session_id.value,
        "predicted_at": forecast.predicted_at.isoformat(),
        "predicted_compact_at": (
            forecast.predicted_compact_at.isoformat()
            if forecast.predicted_compact_at is not None
            else None
        ),
        "confidence": round(forecast.confidence, 3),
        "model_used": forecast.model_used,
        "burn_rate_tokens_per_sec": round(forecast.input_token_rate, 3),
        "context_usage_at_pred": round(forecast.context_usage_at_pred, 3),
    }


def _render(forecast: Forecast, *, cost_to_date: float | None = None) -> None:
    from rich.console import Console

    console = Console()
    console.print()
    console.print("[bold]Autocompact Forecast[/]")
    console.print(
        f"Session: [dim]{forecast.session_id.value}[/]   "
        f"Model: [dim]{forecast.model_used}[/]"
    )
    console.print(
        f"Context usage: "
        f"[bold]{round(forecast.context_usage_at_pred * 100, 1)}%[/]   "
        f"Burn rate: [bold]{forecast.input_token_rate:,.2f}[/] tokens/sec"
    )
    if cost_to_date is not None:
        console.print(f"Cost to date: [bold]${cost_to_date:.4f}[/]")
    console.print()

    if forecast.predicted_compact_at is None:
        console.print(
            "[green]No autocompact projected in the usage window.[/]"
        )
        console.print(
            f"[dim]Confidence: {round(forecast.confidence, 2)}[/]"
        )
        return

    delta = forecast.predicted_compact_at - forecast.predicted_at
    iso = forecast.predicted_compact_at.isoformat()
    human = _humanize_delta(delta.total_seconds())
    color = _confidence_color(forecast.confidence)
    console.print(
        f"[bold yellow]Projected autocompact:[/] {iso}"
    )
    console.print(
        f"  in [bold]{human}[/]   "
        f"confidence [{color}]{round(forecast.confidence, 2)}[/{color}]   "
        f"rate [bold]{forecast.input_token_rate:,.2f}[/] tokens/sec"
    )


def _humanize_delta(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days = hours // 24
    hours = hours % 24
    return f"{days}d {hours}h"


def _confidence_color(confidence: float) -> str:
    if confidence >= 0.7:
        return "green"
    if confidence >= 0.4:
        return "yellow"
    return "red"
