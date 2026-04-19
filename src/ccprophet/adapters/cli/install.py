"""Installer — creates DB, registers Claude Code hooks, seeds pricing.

The settings.json patch goes through JsonFileSettingsStore.write_atomic so the
same AP-7 guarantees (tmp+rename, SHA256 hash guard) apply here as they do to
`ccprophet prune --apply`.

Cross-platform: uses pathlib.Path throughout. On POSIX (macOS/Linux) the DB
file is chmod'd to 0o600 to honor NFR-2; Windows permissions are inherited
from the parent directory (no-op).
"""

from __future__ import annotations

import contextlib
import json as json_module
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ccprophet.ports.settings import SettingsStore

# A harness-provided callable that creates `<prophet_dir>/events.duckdb` and
# runs migrations. Returns the number of migrations actually applied (so the
# installer can report "Schema up to date" vs "Applied N migrations"). CLI
# stays ignorant of DuckDB and the persistence adapter.
DbBootstrap = Callable[[Path], int]

HOOK_COMMAND = "ccprophet-hook"
STATUSLINE_COMMAND = "ccprophet statusline"
HOOK_CONFIG = {
    "PostToolUse": [{"type": "command", "command": HOOK_COMMAND, "timeout": 10}],
    "Stop": [{"type": "command", "command": HOOK_COMMAND, "timeout": 10}],
    "UserPromptSubmit": [{"type": "command", "command": HOOK_COMMAND, "timeout": 5}],
    "SubagentStop": [{"type": "command", "command": HOOK_COMMAND, "timeout": 10}],
}
STATUSLINE_CONFIG = {
    "type": "command",
    "command": STATUSLINE_COMMAND,
}


def run_install_command(
    *,
    settings: SettingsStore,
    bootstrap_db: DbBootstrap,
    dry_run: bool = False,
    as_json: bool = False,
    prophet_dir: Path | None = None,
    settings_path: Path | None = None,
) -> int:
    prophet_dir = prophet_dir or Path.home() / ".claude-prophet"
    settings_path = settings_path or Path.home() / ".claude" / "settings.json"

    migrations_applied = 0
    if not dry_run:
        prophet_dir.mkdir(parents=True, exist_ok=True)
        db_path = prophet_dir / "events.duckdb"
        result = bootstrap_db(db_path)
        # Older harness wiring returned None; treat that as "unknown" (0).
        migrations_applied = int(result) if isinstance(result, int) else 0
        _lock_down_permissions(db_path)

    plan = _plan_hook_patch(settings_path)
    if not dry_run and plan["needs_write"]:
        _apply_hook_patch(settings, settings_path, plan["new_content"])

    report = {
        "db_path": str(prophet_dir / "events.duckdb"),
        "settings_path": str(settings_path),
        "hooks_added": plan["added"],
        "hooks_already_present": plan["already"],
        "statusline_added": plan["statusline_added"],
        "statusline_already_present": plan["statusline_already_present"],
        "migrations_applied": migrations_applied,
        "dry_run": dry_run,
        "applied": (not dry_run) and plan["needs_write"],
    }
    if as_json:
        print(json_module.dumps(report, indent=2))
    else:
        _render(report)
    return 0


def _plan_hook_patch(settings_path: Path) -> dict:  # type: ignore[type-arg]
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists():
        raw = settings_path.read_text(encoding="utf-8")
        settings = json_module.loads(raw) if raw.strip() else {}
    else:
        settings = {}
    if not isinstance(settings, dict):
        settings = {}

    hooks = settings.setdefault("hooks", {})
    added: list[str] = []
    already: list[str] = []

    for event_type, entries in HOOK_CONFIG.items():
        existing = hooks.get(event_type, [])
        has_ours = any(
            isinstance(h, dict) and _command_value(h).startswith(HOOK_COMMAND) for h in existing
        )
        if has_ours:
            already.append(event_type)
            continue
        existing.extend(entries)
        hooks[event_type] = existing
        added.append(event_type)

    statusline_added, statusline_already = _apply_statusline(settings)

    return {
        "new_content": settings,
        "added": added,
        "already": already,
        "statusline_added": statusline_added,
        "statusline_already_present": statusline_already,
        "needs_write": bool(added) or statusline_added,
    }


def _apply_statusline(settings: dict) -> tuple[bool, bool]:  # type: ignore[type-arg]
    existing = settings.get("statusLine")
    if isinstance(existing, dict) and _command_value(existing).startswith(
        STATUSLINE_COMMAND.split()[0]
    ):
        return False, True
    settings["statusLine"] = dict(STATUSLINE_CONFIG)
    return True, False


def _command_value(entry: dict) -> str:  # type: ignore[type-arg]
    cmd = entry.get("command")
    return cmd if isinstance(cmd, str) else ""


def _apply_hook_patch(  # type: ignore[type-arg]
    store: SettingsStore, settings_path: Path, new_content: dict
) -> None:
    expected_hash: str | None = None
    if settings_path.exists():
        expected_hash = store.read(settings_path).sha256
    store.write_atomic(settings_path, new_content, expected_hash=expected_hash)


def _lock_down_permissions(path: Path) -> None:
    """POSIX: chmod 0o600 so only the user can read the DB. Windows: no-op
    (file ACLs are inherited from the user profile directory)."""
    if sys.platform == "win32":
        return
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def _render(report: dict) -> None:  # type: ignore[type-arg]
    from rich.console import Console

    console = Console()
    if report["dry_run"]:
        console.print("[bold cyan]Dry-run[/]. Re-run without --dry-run to apply.")
    elif report["applied"]:
        console.print("[bold green]Installed[/] ccprophet")
    else:
        console.print("[dim]Nothing to install — hooks already present.[/]")

    console.print(f"  DB: {report['db_path']}")
    console.print(f"  Settings: {report['settings_path']}")
    if report["hooks_added"]:
        console.print("  [green]+ hooks[/]: " + ", ".join(report["hooks_added"]))
    if report["hooks_already_present"]:
        console.print("  [dim]already registered[/]: " + ", ".join(report["hooks_already_present"]))
    if report.get("statusline_added"):
        console.print("  [green]+ statusLine[/]: " + STATUSLINE_COMMAND)
    elif report.get("statusline_already_present"):
        console.print("  [dim]statusLine already registered[/]")
    migrated = report.get("migrations_applied", 0)
    if migrated:
        console.print(f"  [green]+ schema[/]: applied {migrated} migration(s)")
    elif not report["dry_run"]:
        console.print("  [dim]schema up to date[/]")

    if not report["dry_run"]:
        console.print()
        console.print("[bold]Next:[/]")
        console.print("  1. Restart Claude Code so the new hooks load.")
        console.print("  2. Backfill past sessions:     [cyan]ccprophet ingest[/]")
        console.print("  3. See your first report:      [cyan]ccprophet bloat[/]")
