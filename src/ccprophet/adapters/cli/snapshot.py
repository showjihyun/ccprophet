from __future__ import annotations

import json as json_module
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import Snapshot
    from ccprophet.use_cases.list_snapshots import ListSnapshotsUseCase
    from ccprophet.use_cases.restore_snapshot import RestoreSnapshotUseCase

from ccprophet.domain.errors import SnapshotMissing
from ccprophet.domain.values import SnapshotId


def run_snapshot_restore_command(
    use_case: RestoreSnapshotUseCase,
    *,
    snapshot_id: str,
    as_json: bool = False,
) -> int:
    try:
        outcome = use_case.execute(SnapshotId(snapshot_id))
    except SnapshotMissing as e:
        if as_json:
            print(json_module.dumps({"error": str(e)}))
        else:
            from rich.console import Console

            Console(stderr=True).print(f"[bold red]Error:[/] {e}")
        return 2

    if as_json:
        print(
            json_module.dumps(
                {
                    "snapshot_id": outcome.snapshot_id.value,
                    "restored_paths": list(outcome.restored_paths),
                },
                indent=2,
            )
        )
        return 0

    from rich.console import Console

    console = Console()
    console.print(
        f"[green]Restored[/] snapshot [bold]{outcome.snapshot_id.value}[/] "
        f"({len(outcome.restored_paths)} file(s))"
    )
    for p in outcome.restored_paths:
        console.print(f"  · {p}")
    return 0


def run_snapshot_list_command(
    use_case: ListSnapshotsUseCase,
    *,
    limit: int = 20,
    as_json: bool = False,
) -> int:
    snapshots = list(use_case.execute(limit=limit))

    if as_json:
        print(json_module.dumps([_to_dict(s) for s in snapshots], indent=2, default=str))
        return 0

    _render_table(snapshots)
    return 0 if snapshots else 1


def _to_dict(s: Snapshot) -> dict[str, object]:
    return {
        "snapshot_id": s.snapshot_id.value,
        "captured_at": s.captured_at.isoformat(),
        "reason": s.reason,
        "triggered_by": s.triggered_by,
        "file_count": len(s.files),
        "byte_size": s.byte_size,
        "restored_at": s.restored_at.isoformat() if s.restored_at else None,
    }


def _render_table(rows: Sequence[Snapshot]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    if not rows:
        console.print("[dim]No snapshots recorded yet.[/]")
        return

    table = Table(show_header=True, header_style="dim")
    table.add_column("Snapshot", overflow="fold")
    table.add_column("Captured", style="dim")
    table.add_column("Reason")
    table.add_column("Files", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Restored?", style="dim")

    for s in rows:
        restored = s.restored_at.strftime("%Y-%m-%d %H:%M") if s.restored_at else "-"
        table.add_row(
            s.snapshot_id.value[:12],
            s.captured_at.strftime("%Y-%m-%d %H:%M"),
            s.reason,
            str(len(s.files)),
            f"{s.byte_size:,}",
            restored,
        )

    console.print(table)
