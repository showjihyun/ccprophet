from __future__ import annotations

import json as json_module
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.use_cases.reproduce_session import (
        ReproduceOutcome,
        ReproduceSessionUseCase,
    )

from ccprophet.domain.errors import InsufficientSamples, SnapshotConflict
from ccprophet.domain.values import TaskType


def run_reproduce_command(
    use_case: ReproduceSessionUseCase,
    *,
    task: str,
    target_path: Path,
    apply: bool = False,
    as_json: bool = False,
) -> int:
    try:
        outcome = use_case.execute(
            TaskType(task), target_path=target_path, apply=apply
        )
    except InsufficientSamples as e:
        _insufficient_samples(task, needed=e.needed, got=e.got, as_json=as_json)
        return 3
    except SnapshotConflict as e:
        _err(f"Aborted: {e}", as_json=as_json)
        return 4

    if as_json:
        print(json_module.dumps(_outcome_dict(outcome), indent=2, default=str))
        return 0

    _render(outcome, applied=apply)
    return 0


def _outcome_dict(o: ReproduceOutcome) -> dict[str, object]:
    return {
        "task_type": o.best_config.task_type.value,
        "cluster_size": o.best_config.cluster_size,
        "common_tools": list(o.best_config.common_tools),
        "dropped_mcps": list(o.best_config.dropped_mcps),
        "recommendations_count": len(o.recommendations),
        "applied": o.apply_outcome is not None and o.apply_outcome.written,
        "snapshot_id": (
            o.apply_outcome.snapshot.snapshot_id.value
            if o.apply_outcome and o.apply_outcome.snapshot
            else None
        ),
    }


def _err(msg: str, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"error": msg}))
        return
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/] {msg}")


def _insufficient_samples(
    task: str, *, needed: int, got: int, as_json: bool
) -> None:
    if as_json:
        print(
            json_module.dumps(
                {
                    "error": "insufficient_samples",
                    "task": task,
                    "needed": needed,
                    "got": got,
                    "hint": (
                        f"Label more sessions with `ccprophet mark <SID> "
                        f"--outcome success --task-type {task}`"
                    ),
                }
            )
        )
        return
    from rich.console import Console

    console = Console(stderr=True)
    console.print(
        f"[bold red]Not enough success-labelled sessions[/] for task "
        f"'[cyan]{task}[/]'."
    )
    console.print(f"  Found [bold]{got}[/], need [bold]{needed}[/].")
    console.print()
    console.print("[dim]Label more sessions:[/]")
    console.print(
        f"  [cyan]ccprophet mark <SID> --outcome success --task-type {task}[/]"
    )
    console.print(
        "  [dim](use `ccprophet sessions` to find recent session IDs)[/]"
    )


def _render(o: ReproduceOutcome, *, applied: bool) -> None:
    from rich.console import Console

    console = Console()
    cfg = o.best_config
    console.print(
        f"[bold]Best config for [cyan]{cfg.task_type.value}[/]  "
        f"(n={cfg.cluster_size})"
    )
    if cfg.common_tools:
        console.print(
            "  recommended tools: " + ", ".join(cfg.common_tools)
        )
    if cfg.dropped_mcps:
        console.print(
            "  drop MCPs: " + ", ".join(cfg.dropped_mcps)
        )

    console.print()
    console.print(
        f"Generated [bold]{len(o.recommendations)}[/] recommendation(s)."
    )
    if o.apply_outcome is not None and o.apply_outcome.written:
        assert o.apply_outcome.snapshot is not None
        console.print(
            f"[green]Applied[/] — snapshot "
            f"[bold]{o.apply_outcome.snapshot.snapshot_id.value}[/]"
        )
    elif not applied:
        console.print(
            "[dim]Dry-run. Re-run with `--apply --target <settings.json>`.[/]"
        )
