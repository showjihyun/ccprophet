from __future__ import annotations

import json as json_module
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.use_cases.apply_pruning import ApplyPruningUseCase, PruningOutcome
    from ccprophet.use_cases.prune_tools import PrunePreview, PruneToolsUseCase

from ccprophet.domain.errors import SnapshotConflict


def run_prune_command(
    preview_uc: PruneToolsUseCase,
    apply_uc: ApplyPruningUseCase,
    *,
    target_path: Path,
    apply: bool = False,
    assume_yes: bool = False,
    as_json: bool = False,
    confirm: "Confirm" | None = None,
) -> int:
    try:
        preview = preview_uc.execute(target_path=target_path)
    except FileNotFoundError as e:
        _print_err(str(e), as_json=as_json)
        return 2

    if not apply:
        _render_preview(preview, as_json=as_json, would_apply=False)
        return 0

    if not preview.has_changes:
        _render_preview(preview, as_json=as_json, would_apply=True)
        return 0

    if not assume_yes:
        confirm = confirm or _prompt_confirm
        if not confirm(
            f"Apply {len(preview.plan.applied_rec_ids)} change(s) to {target_path}?"
        ):
            _print_info("aborted", as_json=as_json)
            return 1

    try:
        outcome = apply_uc.execute(target_path=target_path)
    except SnapshotConflict as e:
        _print_err(f"Aborted: {e}", as_json=as_json)
        return 3

    _render_outcome(outcome, as_json=as_json)
    return 0


Confirm = "callable[[str], bool]"  # type alias shim for stub


def _prompt_confirm(message: str) -> bool:
    answer = input(f"{message} [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def _render_preview(
    preview: PrunePreview, *, as_json: bool, would_apply: bool
) -> None:
    if as_json:
        print(
            json_module.dumps(
                {
                    "dry_run": not would_apply,
                    "target": str(preview.target_path),
                    "has_changes": preview.has_changes,
                    "added_mcps": list(preview.plan.added_mcps),
                    "added_tools": list(preview.plan.added_tools),
                    "applied_rec_ids": list(preview.plan.applied_rec_ids),
                },
                indent=2,
            )
        )
        return

    from rich.console import Console
    from rich.table import Table

    console = Console()
    if not preview.has_changes:
        console.print("[dim]No pending prune recommendations — nothing to apply.[/]")
        return

    console.print(f"[bold]Target:[/] {preview.target_path}")
    table = Table(show_header=True, header_style="dim")
    table.add_column("Change")
    table.add_column("Name")
    for mcp in preview.plan.added_mcps:
        table.add_row("[cyan]disable MCP[/]", mcp)
    for tool in preview.plan.added_tools:
        table.add_row("[yellow]disable tool[/]", tool)
    console.print(table)
    if not would_apply:
        console.print()
        console.print(
            "[dim]Dry-run. Re-run with `--apply` to write these changes.[/]"
        )


def _render_outcome(outcome: PruningOutcome, *, as_json: bool) -> None:
    if as_json:
        print(
            json_module.dumps(
                {
                    "written": outcome.written,
                    "snapshot_id": (
                        outcome.snapshot.snapshot_id.value if outcome.snapshot else None
                    ),
                    "applied_rec_ids": list(outcome.applied_rec_ids),
                    "reason": outcome.reason,
                },
                indent=2,
            )
        )
        return

    from rich.console import Console

    console = Console()
    if not outcome.written:
        console.print(f"[dim]{outcome.reason}[/]")
        return
    assert outcome.snapshot is not None
    console.print(
        f"[green]Applied[/] {len(outcome.applied_rec_ids)} change(s). "
        f"Snapshot: [bold]{outcome.snapshot.snapshot_id.value}[/]"
    )
    console.print(
        f"[dim]Rollback:[/] ccprophet snapshot restore {outcome.snapshot.snapshot_id.value}"
    )


def _print_err(msg: str, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"error": msg}))
        return
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/] {msg}")


def _print_info(msg: str, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"info": msg}))
        return
    from rich.console import Console

    Console().print(f"[dim]{msg}[/]")
