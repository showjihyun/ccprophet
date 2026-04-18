from __future__ import annotations

# Safety model: We connect read_only=True at the DuckDB engine level, which
# refuses all DDL/DML at the connection level. This is sufficient — no regex
# filtering needed and regex filters are easy to bypass anyway.
import json as json_module
from pathlib import Path
from typing import Any


def run_query_command(
    *,
    db_path: Path,
    sql: str,
    as_json: bool,
    limit: int = 100,
) -> int:
    """Execute an arbitrary read-only SQL and render result as table or JSON."""
    if not db_path.exists():
        _print_no_db(db_path)
        return 2

    import duckdb

    try:
        conn = duckdb.connect(str(db_path), read_only=True)
    except duckdb.IOException as exc:
        _print_error(f"Cannot open database: {exc}", as_json)
        return 2

    try:
        # Wrap user SQL in an outer LIMIT so we never pull unbounded rows.
        # If the user already has a LIMIT, the outer cap still applies.
        wrapped = f"SELECT * FROM ({sql}) _q LIMIT {limit + 1}"
        rel = conn.execute(wrapped)
        columns = [d[0] for d in rel.description or []]
        all_rows = rel.fetchall()
    except (duckdb.Error, duckdb.IOException) as exc:
        _print_error(str(exc), as_json)
        return 2
    finally:
        conn.close()

    truncated = len(all_rows) > limit
    rows = all_rows[:limit]

    if as_json:
        payload: dict[str, Any] = {
            "columns": columns,
            "rows": [list(row) for row in rows],
            "row_count": len(rows),
            "truncated": truncated,
        }
        print(json_module.dumps(payload, indent=2, default=str))
        return 0

    _render_query_table(columns, rows, truncated=truncated, limit=limit)
    return 0


def run_query_tables_command(*, db_path: Path, as_json: bool) -> int:
    """List all tables in the DB with row counts."""
    if not db_path.exists():
        _print_no_db(db_path)
        return 2

    import duckdb

    try:
        conn = duckdb.connect(str(db_path), read_only=True)
    except duckdb.IOException as exc:
        _print_error(f"Cannot open database: {exc}", as_json)
        return 2

    try:
        names_rel = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        )
        table_names: list[str] = [row[0] for row in names_rel.fetchall()]

        counts: list[tuple[str, int]] = []
        for name in table_names:
            count_rel = conn.execute(f'SELECT COUNT(*) FROM "{name}"')
            row_count = int((count_rel.fetchone() or (0,))[0])
            counts.append((name, row_count))
    except (duckdb.Error, duckdb.IOException) as exc:
        _print_error(str(exc), as_json)
        return 2
    finally:
        conn.close()

    if as_json:
        payload = [{"table_name": name, "row_count": cnt} for name, cnt in counts]
        print(json_module.dumps(payload, indent=2))
        return 0

    _render_tables_table(counts)
    return 0


def run_query_schema_command(*, db_path: Path, table: str, as_json: bool) -> int:
    """Show column types for a given table."""
    if not db_path.exists():
        _print_no_db(db_path)
        return 2

    import duckdb

    try:
        conn = duckdb.connect(str(db_path), read_only=True)
    except duckdb.IOException as exc:
        _print_error(f"Cannot open database: {exc}", as_json)
        return 2

    try:
        # Validate table exists first to give a clear error message.
        exists_rel = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='main' AND table_name=?",
            [table],
        )
        if (exists_rel.fetchone() or (0,))[0] == 0:
            _print_error(f"Table '{table}' not found in the database.", as_json)
            conn.close()
            return 2

        desc_rel = conn.execute(f'DESCRIBE "{table}"')
        columns = [d[0] for d in desc_rel.description or []]
        rows = desc_rel.fetchall()
    except (duckdb.Error, duckdb.IOException) as exc:
        _print_error(str(exc), as_json)
        return 2
    finally:
        conn.close()

    if as_json:
        payload = [dict(zip(columns, row)) for row in rows]
        print(json_module.dumps(payload, indent=2, default=str))
        return 0

    _render_schema_table(columns, rows, table_name=table)
    return 0


# ---------------------------------------------------------------------------
# Private rendering helpers
# ---------------------------------------------------------------------------


def _print_no_db(db_path: Path) -> None:
    from rich.console import Console

    Console().print(
        f"[red]ccprophet DB not found at {db_path}[/]\n"
        "Run [bold]ccprophet install[/] or trigger a hook first."
    )


def _print_error(message: str, as_json: bool) -> None:
    if as_json:
        import sys

        print(json_module.dumps({"error": message}), file=sys.stderr)
    else:
        from rich.console import Console

        Console(stderr=True).print(f"[red]Error:[/] {message}")


def _render_query_table(
    columns: list[str],
    rows: list[tuple[Any, ...]],
    *,
    truncated: bool,
    limit: int,
) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    if not columns:
        console.print("[dim]Query returned no columns.[/]")
        return

    table = Table(show_header=True, header_style="bold dim")
    for col in columns:
        table.add_column(str(col))

    for row in rows:
        table.add_row(*[str(v) if v is not None else "[dim]NULL[/]" for v in row])

    console.print(table)

    if truncated:
        console.print(f"[dim]Showing {limit} rows (truncated). Use --limit to increase.[/]")
    else:
        console.print(f"[dim]{len(rows)} row(s)[/]")


def _render_tables_table(counts: list[tuple[str, int]]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    if not counts:
        console.print("[dim]No tables found.[/]")
        return

    table = Table(show_header=True, header_style="bold dim")
    table.add_column("Table")
    table.add_column("Rows", justify="right")

    for name, cnt in counts:
        table.add_row(name, f"{cnt:,}")

    console.print(table)


def _render_schema_table(
    columns: list[str], rows: list[tuple[Any, ...]], *, table_name: str
) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(
        show_header=True,
        header_style="bold dim",
        title=f"Schema: {table_name}",
    )
    for col in columns:
        table.add_column(str(col))

    for row in rows:
        table.add_row(*[str(v) if v is not None else "" for v in row])

    console.print(table)
