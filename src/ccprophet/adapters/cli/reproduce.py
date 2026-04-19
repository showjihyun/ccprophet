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
        outcome = use_case.execute(TaskType(task), target_path=target_path, apply=apply)
    except InsufficientSamples as e:
        auto_summary = getattr(e, "auto_label_summary", None)
        _insufficient_samples(
            task,
            needed=e.needed,
            got=e.got,
            auto_summary=auto_summary,
            as_json=as_json,
        )
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
    task: str,
    *,
    needed: int,
    got: int,
    auto_summary: object | None = None,
    as_json: bool,
) -> None:
    auto_success = _auto_success_count(auto_summary)
    if as_json:
        print(
            json_module.dumps(
                {
                    "error": "insufficient_samples",
                    "task": task,
                    "needed": needed,
                    "got": got,
                    "auto_labeled_success": auto_success,
                    "hint": _build_hint(task, auto_success),
                }
            )
        )
        return
    from rich.console import Console

    console = Console(stderr=True)
    console.print(f"[bold red]Not enough success-labelled sessions[/] for task '[cyan]{task}[/]'.")
    console.print(f"  Found [bold]{got}[/], need [bold]{needed}[/].")
    console.print()
    if auto_success > 0:
        # The use case already ran `mark --auto` for us, so skip that step in
        # the hint and go straight to the (still-manual) task-type tagging
        # stage. Once a real task-type heuristic lands, this branch can drop
        # to just "try reproduce again".
        console.print(
            f"[dim]Auto-labeled[/] [bold]{auto_success}[/] success session(s) just now, "
            "but none carry a task-type yet."
        )
        console.print("[dim]Tag them so reproduce can use them:[/]")
        console.print(f"  [cyan]ccprophet mark <SID> --task-type {task}[/]")
        console.print("  [dim](`ccprophet sessions` lists recent IDs)[/]")
    else:
        console.print("[dim]Label more sessions:[/]")
        console.print(f"  [cyan]ccprophet mark <SID> --outcome success --task-type {task}[/]")
        console.print("  [dim](use `ccprophet sessions` to find recent session IDs)[/]")


def _auto_success_count(auto_summary: object | None) -> int:
    if auto_summary is None:
        return 0
    return int(getattr(auto_summary, "labeled_success", 0) or 0)


def _build_hint(task: str, auto_success: int) -> str:
    if auto_success > 0:
        return (
            f"{auto_success} success session(s) were auto-labeled. "
            f"Tag them with `ccprophet mark <SID> --task-type {task}` to include "
            "them in the next reproduce."
        )
    return f"Label more sessions with `ccprophet mark <SID> --outcome success --task-type {task}`"


def _render(o: ReproduceOutcome, *, applied: bool) -> None:
    from rich.console import Console

    console = Console()
    cfg = o.best_config
    console.print(f"[bold]Best config for [cyan]{cfg.task_type.value}[/]  (n={cfg.cluster_size})")
    if cfg.common_tools:
        console.print("  recommended tools: " + ", ".join(cfg.common_tools))
    if cfg.dropped_mcps:
        console.print("  drop MCPs: " + ", ".join(cfg.dropped_mcps))

    console.print()
    console.print(f"Generated [bold]{len(o.recommendations)}[/] recommendation(s).")
    if o.apply_outcome is not None and o.apply_outcome.written:
        assert o.apply_outcome.snapshot is not None
        console.print(
            f"[green]Applied[/] — snapshot [bold]{o.apply_outcome.snapshot.snapshot_id.value}[/]"
        )
    elif not applied:
        console.print("[dim]Dry-run. Re-run with `--apply --target <settings.json>`.[/]")
