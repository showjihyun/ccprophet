from __future__ import annotations

import json as json_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import BudgetEnvelope
    from ccprophet.use_cases.estimate_budget import EstimateBudgetUseCase

from ccprophet.domain.errors import InsufficientSamples
from ccprophet.domain.values import TaskType


def run_budget_command(
    use_case: EstimateBudgetUseCase,
    *,
    task: str,
    as_json: bool = False,
) -> int:
    try:
        envelope = use_case.execute(TaskType(task))
    except InsufficientSamples as e:
        _err(
            f"Insufficient success-labelled sessions for task '{task}': {e}",
            as_json=as_json,
        )
        return 3

    if as_json:
        print(json_module.dumps(_envelope_dict(envelope), indent=2, default=str))
        return 0

    _render(envelope)
    return 0


def _envelope_dict(e: BudgetEnvelope) -> dict[str, object]:
    return {
        "task_type": e.task_type.value,
        "sample_size": e.sample_size,
        "estimated_input_tokens_mean": e.estimated_input_tokens_mean.value,
        "estimated_input_tokens_stddev": e.estimated_input_tokens_stddev,
        "estimated_output_tokens_mean": e.estimated_output_tokens_mean.value,
        "estimated_cost_usd": float(e.estimated_cost.amount),
        "currency": e.estimated_cost.currency,
        "best_config": {
            "cluster_size": e.best_config.cluster_size,
            "common_tools": list(e.best_config.common_tools),
            "dropped_mcps": list(e.best_config.dropped_mcps),
            "autocompact_hit_rate": e.best_config.autocompact_hit_rate,
        },
        "risk_flags": list(e.risk_flags),
    }


def _err(msg: str, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"error": msg}))
        return
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/] {msg}")


def _render(e: BudgetEnvelope) -> None:
    from rich.console import Console

    console = Console()
    console.print()
    console.print(f"[bold]Budget estimate for [cyan]{e.task_type.value}[/]")
    console.print(
        f"  sample_size: {e.sample_size}   "
        f"autocompact_hit_rate: "
        f"{round(e.best_config.autocompact_hit_rate * 100)}%"
    )
    console.print(
        f"  estimated tokens (in/out): "
        f"[bold]{e.estimated_input_tokens_mean.value:,}[/] "
        f"± {e.estimated_input_tokens_stddev:,} / "
        f"{e.estimated_output_tokens_mean.value:,}"
    )
    console.print(
        f"  estimated cost: [green]${float(e.estimated_cost.amount):.4f}[/] "
        f"{e.estimated_cost.currency}"
    )
    if e.best_config.common_tools:
        console.print("  recommended subset: " + ", ".join(e.best_config.common_tools))
    if e.best_config.dropped_mcps:
        console.print("  drop MCPs: [dim]" + ", ".join(e.best_config.dropped_mcps) + "[/]")
    if e.risk_flags:
        console.print()
        for flag in e.risk_flags:
            console.print(f"  [yellow]![/] {flag}")
