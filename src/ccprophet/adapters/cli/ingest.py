from __future__ import annotations

import json as json_module
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.use_cases.backfill_from_jsonl import (
        BackfillFromJsonlUseCase,
        BackfillSummary,
    )


def run_ingest_command(
    use_case: BackfillFromJsonlUseCase,
    *,
    paths: Iterable[Path],
    as_json: bool = False,
) -> int:
    path_list = list(paths)

    if as_json or not path_list:
        summary = use_case.execute(path_list)
        if as_json:
            print(json_module.dumps(_summary_dict(summary), indent=2))
        else:
            _render(summary)
        return 0 if not summary.errors else 1

    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        TextColumn,
        TimeRemainingColumn,
    )

    with Progress(
        TextColumn("[bold]Ingesting[/]"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        transient=True,
    ) as progress:
        task_id = progress.add_task("ingest", total=len(path_list))

        def _tick(iterable: list[Path]) -> Iterator[Path]:
            for path in iterable:
                yield path
                progress.advance(task_id)

        summary = use_case.execute(_tick(path_list))

    _render(summary)
    return 0 if not summary.errors else 1


def _summary_dict(s: BackfillSummary) -> dict[str, object]:
    return {
        "files_read": s.files_read,
        "records_seen": s.records_seen,
        "events_ingested": s.events_ingested,
        "tool_calls_ingested": s.tool_calls_ingested,
        "sessions_touched": sorted(s.sessions_touched),
        "errors": s.errors,
    }


def _render(s: BackfillSummary) -> None:
    from rich.console import Console

    console = Console()
    console.print(
        f"[bold]Backfill complete[/]  "
        f"files: {s.files_read}  records: {s.records_seen}  "
        f"events: [green]{s.events_ingested}[/]  "
        f"tool_calls: [green]{s.tool_calls_ingested}[/]  "
        f"sessions: {len(s.sessions_touched)}"
    )
    if s.errors:
        console.print()
        console.print("[bold red]Errors[/]")
        for err in s.errors:
            console.print(f"  · {err}")


def discover_jsonl_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.glob("**/*.jsonl"))
