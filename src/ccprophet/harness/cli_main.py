from __future__ import annotations

from typing import TYPE_CHECKING

import typer  # module-level so typer.Context annotations resolve via get_annotations

if TYPE_CHECKING:
    pass

# Re-export shared constants for backward compatibility.
from ccprophet.harness.commands._shared import (  # noqa: F401
    DB_PATH,
    DEFAULT_JSONL_ROOT,
    DEFAULT_SETTINGS_PATH,
    SNAPSHOT_ROOT,
)


def main() -> None:
    app = typer.Typer(
        name="ccprophet",
        help="Context Efficiency Profiler for Claude Code",
        no_args_is_help=True,
    )

    from ccprophet.harness.commands import (
        actions,
        actions_rollup,
        actions_snapshot,
        analysis,
        analysis_extra,
        info,
        ops,
        services,
    )

    analysis.register(app)
    analysis_extra.register(app)
    actions.register(app)
    actions_snapshot.register(app)
    actions_rollup.register(app)
    ops.register(app)
    info.register(app)
    services.register(app)

    app()
