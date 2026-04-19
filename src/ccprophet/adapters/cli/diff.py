from __future__ import annotations

import json as json_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.domain.entities import SessionDiff
    from ccprophet.use_cases.diff_sessions import DiffSessionsUseCase

from ccprophet.domain.errors import SessionNotFound
from ccprophet.domain.values import SessionId


def run_diff_command(
    use_case: DiffSessionsUseCase,
    *,
    sid_a: str,
    sid_b: str,
    as_json: bool = False,
) -> int:
    try:
        diff = use_case.execute(SessionId(sid_a), SessionId(sid_b))
    except SessionNotFound as e:
        _err(str(e), as_json=as_json)
        return 2

    if as_json:
        print(json_module.dumps(_to_dict(diff), indent=2, default=str))
        return 0

    _render(diff)
    return 0


def _to_dict(d: SessionDiff) -> dict[str, object]:
    return {
        "session_a": d.session_a_id.value,
        "session_b": d.session_b_id.value,
        "input_tokens_delta": d.input_tokens_delta,
        "output_tokens_delta": d.output_tokens_delta,
        "tool_call_count_delta": d.tool_call_count_delta,
        "bloat_ratio_delta": d.bloat_ratio_delta,
        "compacted_delta": d.compacted_delta,
        "tools_added": list(d.tools_added),
        "tools_removed": list(d.tools_removed),
        "mcps_added": list(d.mcps_added),
        "mcps_removed": list(d.mcps_removed),
    }


def _err(msg: str, *, as_json: bool) -> None:
    if as_json:
        print(json_module.dumps({"error": msg}))
        return
    from rich.console import Console

    Console(stderr=True).print(f"[bold red]Error:[/] {msg}")


def _render(d: SessionDiff) -> None:
    from rich.console import Console

    console = Console()
    console.print(f"[bold]{d.session_a_id.value}[/] → [bold]{d.session_b_id.value}[/]")
    console.print(f"  input tokens Δ: {d.input_tokens_delta:+,}")
    console.print(f"  output tokens Δ: {d.output_tokens_delta:+,}")
    console.print(f"  tool calls Δ: {d.tool_call_count_delta:+d}")
    console.print(f"  bloat ratio Δ: {d.bloat_ratio_delta * 100:+.1f}%")
    if d.compacted_delta != 0:
        console.print(f"  compacted Δ: {d.compacted_delta:+d}")
    if d.tools_added:
        console.print("  [green]+ tools[/]: " + ", ".join(d.tools_added))
    if d.tools_removed:
        console.print("  [red]- tools[/]: " + ", ".join(d.tools_removed))
    if d.mcps_added:
        console.print("  [green]+ MCPs[/]: " + ", ".join(d.mcps_added))
    if d.mcps_removed:
        console.print("  [red]- MCPs[/]: " + ", ".join(d.mcps_removed))
