from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from ccprophet.adapters.cli.query import (
    run_query_command,
    run_query_schema_command,
    run_query_tables_command,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Tiny DuckDB with a single table pre-seeded."""
    path = tmp_path / "events.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute(
        "CREATE TABLE sessions (session_id VARCHAR, model VARCHAR, tokens INTEGER)"
    )
    conn.execute(
        "INSERT INTO sessions VALUES ('s-abc', 'claude-opus-4-7', 12000)"
    )
    conn.close()
    return path


@pytest.fixture()
def db_path_many_rows(tmp_path: Path) -> Path:
    """DuckDB with 200 rows for truncation testing."""
    path = tmp_path / "events.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute("CREATE TABLE items (id INTEGER, value VARCHAR)")
    conn.executemany(
        "INSERT INTO items VALUES (?, ?)",
        [(i, f"val-{i}") for i in range(200)],
    )
    conn.close()
    return path


# ---------------------------------------------------------------------------
# run_query_command
# ---------------------------------------------------------------------------


def test_basic_select_json(capsys: pytest.CaptureFixture[str], db_path: Path) -> None:
    code = run_query_command(
        db_path=db_path,
        sql="SELECT session_id, model, tokens FROM sessions",
        as_json=True,
    )
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["columns"] == ["session_id", "model", "tokens"]
    assert payload["rows"] == [["s-abc", "claude-opus-4-7", 12000]]
    assert payload["row_count"] == 1
    assert payload["truncated"] is False


def test_basic_select_rich_table(
    capsys: pytest.CaptureFixture[str], db_path: Path
) -> None:
    code = run_query_command(
        db_path=db_path,
        sql="SELECT session_id FROM sessions",
        as_json=False,
    )
    assert code == 0
    # Rich prints to its own console; at minimum the process must succeed.
    # The capsys output may be empty when Rich uses a non-capturing Console,
    # so we only assert the return code here.


def test_truncation_json(
    capsys: pytest.CaptureFixture[str], db_path_many_rows: Path
) -> None:
    code = run_query_command(
        db_path=db_path_many_rows,
        sql="SELECT * FROM items",
        as_json=True,
        limit=10,
    )
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert payload["truncated"] is True
    assert payload["row_count"] == 10
    assert len(payload["rows"]) == 10


def test_no_truncation_when_within_limit(
    capsys: pytest.CaptureFixture[str], db_path: Path
) -> None:
    code = run_query_command(
        db_path=db_path,
        sql="SELECT * FROM sessions",
        as_json=True,
        limit=100,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["truncated"] is False


def test_ddl_rejected_returns_2(
    capsys: pytest.CaptureFixture[str], db_path: Path
) -> None:
    """DuckDB read_only=True refuses DDL at the engine level."""
    code = run_query_command(
        db_path=db_path,
        sql="CREATE TABLE foo (x INT)",
        as_json=True,
    )
    assert code == 2
    # Error message goes to stderr; just confirm exit code.


def test_malformed_sql_returns_2(
    capsys: pytest.CaptureFixture[str], db_path: Path
) -> None:
    code = run_query_command(
        db_path=db_path,
        sql="SELECT FROM WHERE ???",
        as_json=True,
    )
    assert code == 2


def test_missing_db_returns_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    missing = tmp_path / "no_such.duckdb"
    code = run_query_command(db_path=missing, sql="SELECT 1", as_json=False)
    assert code == 2


# ---------------------------------------------------------------------------
# run_query_tables_command
# ---------------------------------------------------------------------------


def test_tables_command_json(
    capsys: pytest.CaptureFixture[str], db_path: Path
) -> None:
    code = run_query_tables_command(db_path=db_path, as_json=True)
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    table_names = [entry["table_name"] for entry in payload]
    assert "sessions" in table_names
    # Row count should match what we inserted.
    for entry in payload:
        if entry["table_name"] == "sessions":
            assert entry["row_count"] == 1


def test_tables_command_rich(
    capsys: pytest.CaptureFixture[str], db_path: Path
) -> None:
    code = run_query_tables_command(db_path=db_path, as_json=False)
    assert code == 0


def test_tables_missing_db_returns_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    missing = tmp_path / "no_such.duckdb"
    code = run_query_tables_command(db_path=missing, as_json=False)
    assert code == 2


# ---------------------------------------------------------------------------
# run_query_schema_command
# ---------------------------------------------------------------------------


def test_schema_command_json(
    capsys: pytest.CaptureFixture[str], db_path: Path
) -> None:
    code = run_query_schema_command(db_path=db_path, table="sessions", as_json=True)
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    # DESCRIBE returns at least column_name and column_type.
    col_names = [row.get("column_name") for row in payload]
    assert "session_id" in col_names
    assert "model" in col_names
    assert "tokens" in col_names


def test_schema_command_rich(
    capsys: pytest.CaptureFixture[str], db_path: Path
) -> None:
    code = run_query_schema_command(db_path=db_path, table="sessions", as_json=False)
    assert code == 0


def test_schema_unknown_table_returns_2(
    capsys: pytest.CaptureFixture[str], db_path: Path
) -> None:
    code = run_query_schema_command(
        db_path=db_path, table="nonexistent_table_xyz", as_json=True
    )
    assert code == 2


def test_schema_missing_db_returns_2(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    missing = tmp_path / "no_such.duckdb"
    code = run_query_schema_command(db_path=missing, table="sessions", as_json=False)
    assert code == 2
