from __future__ import annotations

import json as json_module
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import Recommendation
    from ccprophet.use_cases.recommend_action import RecommendActionUseCase

from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import SessionId


def run_recommend_command(
    use_case: RecommendActionUseCase,
    *,
    session: str | None = None,
    as_json: bool = False,
    persist: bool = True,
) -> int:
    try:
        recs = (
            use_case.execute(SessionId(session), persist=persist)
            if session
            else use_case.execute_current(persist=persist)
        )
    except SessionNotFound as e:
        _render_error(str(e), as_json=as_json)
        return 2

    if as_json:
        print(json_module.dumps([_to_dict(r) for r in recs], indent=2, default=str))
        return 0

    _render_table(recs)
    return 0


def _to_dict(r: Recommendation) -> dict[str, object]:
    return {
        "rec_id": r.rec_id,
        "kind": r.kind.value,
        "target": r.target,
        "est_savings_tokens": r.est_savings_tokens.value,
        "est_savings_usd": float(r.est_savings_usd.amount),
        "currency": r.est_savings_usd.currency,
        "confidence": r.confidence.value,
        "rationale": r.rationale,
        "status": r.status.value,
    }


def _render_error(msg: str, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"error": msg}))
        return
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/] {msg}")


def _render_table(recs: Sequence[Recommendation]) -> None:
    from rich.console import Console
    from rich.table import Table

    from ccprophet.domain.values import RecommendationKind

    console = Console()
    if not recs:
        console.print("[dim]No recommendations — nothing to prune right now.[/]")
        return

    pruning_recs = [r for r in recs if r.kind != RecommendationKind.SET_ENV_VAR]
    env_recs = [r for r in recs if r.kind == RecommendationKind.SET_ENV_VAR]

    if pruning_recs:
        table = Table(show_header=True, header_style="dim", title="Pruning Recommendations")
        table.add_column("Kind", style="bold")
        table.add_column("Target")
        table.add_column("Save", justify="right")
        table.add_column("$ (est)", justify="right")
        table.add_column("Conf.", justify="right")
        table.add_column("Why", overflow="fold")

        for r in pruning_recs:
            conf_pct = round(r.confidence.value * 100)
            conf_color = "green" if conf_pct >= 80 else "yellow" if conf_pct >= 50 else "red"
            table.add_row(
                r.kind.value,
                r.target or "-",
                f"{r.est_savings_tokens.value:,}",
                f"${float(r.est_savings_usd.amount):.4f}" if r.est_savings_usd.amount > 0 else "-",
                f"[{conf_color}]{conf_pct}%[/{conf_color}]",
                r.rationale,
            )

        console.print(table)
        console.print()
        console.print("[dim]Run `ccprophet prune --apply` to act on these.[/]")

    if env_recs:
        env_table = Table(show_header=True, header_style="dim", title="Env-Var Recommendations")
        env_table.add_column("Kind", style="bold cyan")
        env_table.add_column("[env] Variable Assignment")
        env_table.add_column("Save (tokens)", justify="right")
        env_table.add_column("$ (est)", justify="right")
        env_table.add_column("Conf.", justify="right")
        env_table.add_column("Why", overflow="fold")

        for r in env_recs:
            conf_pct = round(r.confidence.value * 100)
            conf_color = "green" if conf_pct >= 80 else "yellow" if conf_pct >= 50 else "red"
            env_table.add_row(
                "[env]",
                r.target or "-",
                f"{r.est_savings_tokens.value:,}",
                f"${float(r.est_savings_usd.amount):.4f}" if r.est_savings_usd.amount > 0 else "-",
                f"[{conf_color}]{conf_pct}%[/{conf_color}]",
                r.rationale,
            )

        console.print(env_table)
        console.print()
        console.print(
            "[dim]Apply env vars by exporting them in your shell (e.g., ~/.zshrc) "
            "or .claude/settings.json `env` block.[/]"
        )
