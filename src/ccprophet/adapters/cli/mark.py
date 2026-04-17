from __future__ import annotations

import json as json_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.use_cases.mark_outcome import MarkOutcomeUseCase

from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import OutcomeLabelValue, SessionId, TaskType


def run_mark_command(
    use_case: MarkOutcomeUseCase,
    *,
    session_id: str,
    outcome: str,
    task_type: str | None = None,
    reason: str | None = None,
    as_json: bool = False,
) -> int:
    try:
        label_value = OutcomeLabelValue(outcome.lower())
    except ValueError:
        _err(
            f"--outcome must be one of: "
            f"{', '.join(v.value for v in OutcomeLabelValue)}",
            as_json=as_json,
        )
        return 2

    try:
        label = use_case.execute(
            SessionId(session_id),
            label_value,
            task_type=TaskType(task_type) if task_type else None,
            reason=reason,
        )
    except SessionNotFound as e:
        _err(str(e), as_json=as_json)
        return 2

    if as_json:
        print(
            json_module.dumps(
                {
                    "session_id": label.session_id.value,
                    "label": label.label.value,
                    "task_type": label.task_type.value if label.task_type else None,
                    "source": label.source,
                    "reason": label.reason,
                    "labeled_at": label.labeled_at.isoformat(),
                },
                indent=2,
            )
        )
        return 0

    from rich.console import Console

    Console().print(
        f"[green]Labeled[/] {label.session_id.value} as "
        f"[bold]{label.label.value}[/]"
        + (f" (task: {label.task_type.value})" if label.task_type else "")
    )
    return 0


def _err(msg: str, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"error": msg}))
        return
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/] {msg}")
