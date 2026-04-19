"""CLI adapter: ccprophet claude-md — audit CLAUDE.md files for context rot."""

from __future__ import annotations

import json as json_module
from pathlib import Path

from ccprophet.domain.services.claude_md_audit import ClaudeMdAuditor, ClaudeMdReport

_GUIDANCE = "Modularize with @docs/<file>.md imports — see https://code.claude.com/docs/en/memory"

_SEV_COLOR = {
    "ok": "green",
    "info": "cyan",
    "warn": "yellow",
    "critical": "red",
}

EXIT_OK = 0
EXIT_WARN = 1
EXIT_CRITICAL = 2
EXIT_NOT_FOUND = 3


def _find_claude_md_files(root: Path) -> list[Path]:
    """Locate CLAUDE.md files: root-level, immediate subdirs, and user-global."""
    found: list[Path] = []

    # Project root
    candidate = root / "CLAUDE.md"
    if candidate.is_file():
        found.append(candidate)

    # Immediate subdirectories
    try:
        for sub in root.iterdir():
            if sub.is_dir():
                sub_candidate = sub / "CLAUDE.md"
                if sub_candidate.is_file():
                    found.append(sub_candidate)
    except PermissionError:
        pass

    # User-global
    global_candidate = Path.home() / ".claude" / "CLAUDE.md"
    if global_candidate.is_file() and global_candidate not in found:
        found.append(global_candidate)

    return found


def _read_report(path: Path, root: Path) -> ClaudeMdReport:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        content = ""
    display = _relative_or_absolute(path, root)
    return ClaudeMdAuditor.audit(display, content)


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def run_claude_md_command(
    *,
    root: Path,
    as_json: bool,
) -> int:
    files = _find_claude_md_files(root)

    if not files:
        if as_json:
            print(json_module.dumps({"error": "No CLAUDE.md files found", "files": []}))
        else:
            from rich.console import Console

            Console().print("[yellow]No CLAUDE.md files found in:[/] " + str(root))
        return EXIT_NOT_FOUND

    reports = [_read_report(f, root) for f in files]

    if as_json:
        return _render_json(reports)
    return _render_rich(reports)


def _render_json(reports: list[ClaudeMdReport]) -> int:
    out = []
    for r in reports:
        out.append(
            {
                "path": r.path,
                "line_count": r.line_count,
                "byte_size": r.byte_size,
                "estimated_tokens": r.estimated_tokens,
                "worst_severity": r.worst_severity,
                "findings": [
                    {
                        "kind": f.kind,
                        "severity": f.severity,
                        "line_range": list(f.line_range),
                        "detail": f.detail,
                    }
                    for f in r.findings
                ],
            }
        )
    print(json_module.dumps(out, indent=2))
    return _exit_code(reports)


def _render_rich(reports: list[ClaudeMdReport]) -> int:
    from rich.console import Console
    from rich.table import Table

    console = Console()

    # Summary table
    table = Table(title="CLAUDE.md Audit", show_header=True, header_style="bold")
    table.add_column("Path", style="dim")
    table.add_column("Lines", justify="right")
    table.add_column("~Tokens", justify="right")
    table.add_column("Severity")

    for r in reports:
        color = _SEV_COLOR.get(r.worst_severity, "white")
        table.add_row(
            r.path,
            str(r.line_count),
            str(r.estimated_tokens),
            f"[{color}]{r.worst_severity}[/{color}]",
        )
    console.print(table)

    # Per-file findings
    for r in reports:
        if not r.findings:
            continue
        console.print(f"\n[bold]{r.path}[/] findings:")
        for f in sorted(r.findings, key=lambda x: x.line_range[0]):
            color = _SEV_COLOR.get(f.severity, "white")
            console.print(
                f"  [{color}]{f.severity:8s}[/{color}]  "
                f"[dim]lines {f.line_range[0]}–{f.line_range[1]}[/dim]  {f.detail}"
            )

    console.print(f"\n[dim]{_GUIDANCE}[/dim]")
    return _exit_code(reports)


def _exit_code(reports: list[ClaudeMdReport]) -> int:
    worst = "ok"
    for r in reports:
        s = r.worst_severity
        if s == "critical":
            return EXIT_CRITICAL
        if s == "warn":
            worst = "warn"
    return EXIT_WARN if worst == "warn" else EXIT_OK
