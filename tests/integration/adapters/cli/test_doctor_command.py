"""Integration tests for ccprophet doctor command."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from ccprophet.adapters.cli.doctor import MigrationOps, run_doctor_command
from ccprophet.adapters.persistence.duckdb.migrations import (
    MIGRATIONS_DIR,
    apply_migrations,
    current_version,
)


def _migration_ops() -> MigrationOps:
    return MigrationOps(
        migrations_dir=MIGRATIONS_DIR,
        current_version=current_version,
        apply_migrations=apply_migrations,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _fresh_db(path: Path) -> duckdb.DuckDBPyConnection:
    """Create a DB with full schema applied, then close and return path info."""
    conn = duckdb.connect(str(path))
    apply_migrations(conn)
    conn.close()
    return duckdb.connect(str(path))


def _seed_session(conn: duckdb.DuckDBPyConnection, session_id: str = "sess-001") -> None:
    conn.execute(
        """
        INSERT INTO sessions(session_id, project_slug, model, started_at,
                             total_input_tokens, total_output_tokens)
        VALUES (?, 'proj', 'claude-opus-4-6', ?, 100, 50)
        """,
        [session_id, datetime(2026, 4, 1, tzinfo=timezone.utc)],
    )


def _seed_tool_call(
    conn: duckdb.DuckDBPyConnection,
    session_id: str,
    tool_call_id: str = "tc-001",
) -> None:
    conn.execute(
        """
        INSERT INTO tool_calls(tool_call_id, session_id, tool_name, input_hash, ts)
        VALUES (?, ?, 'Read', 'hash1', ?)
        """,
        [tool_call_id, session_id, datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)],
    )


# --------------------------------------------------------------------------- #
# Test: orphan check triggers warn, repair removes them
# --------------------------------------------------------------------------- #

def test_orphan_triggers_warn(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    db = tmp_path / "events.duckdb"
    conn = _fresh_db(db)

    # Insert a tool_call referencing a non-existent session
    conn.execute(
        """
        INSERT INTO tool_calls(tool_call_id, session_id, tool_name, input_hash, ts)
        VALUES ('orphan-tc', 'ghost-session', 'Bash', 'h', '2026-04-01')
        """
    )
    conn.close()

    code = run_doctor_command(
        migration_ops=_migration_ops(),
        db_path=db, as_json=True, repair=False, migrate=False
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 1  # WARN
    assert out["overall"] == "warn"
    orphan_check = next(c for c in out["checks"] if c["name"] == "orphan_records")
    assert orphan_check["status"] == "warn"
    assert "tool_calls:1" in orphan_check["detail"]


def test_repair_removes_orphans(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    db = tmp_path / "events.duckdb"
    conn = _fresh_db(db)

    conn.execute(
        """
        INSERT INTO tool_calls(tool_call_id, session_id, tool_name, input_hash, ts)
        VALUES ('orphan-tc', 'ghost-session', 'Bash', 'h', '2026-04-01')
        """
    )
    conn.close()

    # First run with repair
    code = run_doctor_command(
        migration_ops=_migration_ops(),
        db_path=db, as_json=True, repair=True, migrate=False
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0  # ok after repair
    orphan_check = next(c for c in out["checks"] if c["name"] == "orphan_records")
    assert orphan_check["status"] == "ok"
    assert out["repair"]["status"] == "applied"
    assert out["repair"]["orphans_deleted"]["tool_calls"] == 1

    # Second run should confirm ok
    capsys.readouterr()
    code2 = run_doctor_command(
        migration_ops=_migration_ops(),
        db_path=db, as_json=True, repair=False, migrate=False
    )
    out2 = json.loads(capsys.readouterr().out)
    assert code2 == 0
    orphan_check2 = next(c for c in out2["checks"] if c["name"] == "orphan_records")
    assert orphan_check2["status"] == "ok"


# --------------------------------------------------------------------------- #
# Test: missing DB file → critical
# --------------------------------------------------------------------------- #

def test_missing_db_critical(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    db = tmp_path / "nonexistent.duckdb"

    code = run_doctor_command(
        migration_ops=_migration_ops(),
        db_path=db, as_json=True, repair=False, migrate=False
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 2
    assert out["overall"] == "critical"
    db_check = next(c for c in out["checks"] if c["name"] == "db_file")
    assert db_check["status"] == "critical"
    # Should not have more checks after critical DB failure
    assert len(out["checks"]) == 1


# --------------------------------------------------------------------------- #
# Test: --migrate on empty DB applies all V* migrations
# --------------------------------------------------------------------------- #

def test_migrate_on_empty_db(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    db = tmp_path / "events.duckdb"
    # Create an empty DuckDB (no tables at all)
    conn = duckdb.connect(str(db))
    conn.close()

    code = run_doctor_command(
        migration_ops=_migration_ops(),
        db_path=db, as_json=True, repair=False, migrate=True
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["migration"]["needs_migration"] is False
    assert out["migration"]["applied"] >= 1  # at least V1 was applied

    # Verify schema actually exists now
    conn2 = duckdb.connect(str(db), read_only=True)
    ver = current_version(conn2)
    conn2.close()
    sql_files = sorted(MIGRATIONS_DIR.glob("V*__*.sql"))
    latest = max(
        int(f.name.split("__")[0].removeprefix("V")) for f in sql_files
    )
    assert ver == latest


# --------------------------------------------------------------------------- #
# Test: --json output shape
# --------------------------------------------------------------------------- #

def test_json_output_shape(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    db = tmp_path / "events.duckdb"
    conn = _fresh_db(db)
    _seed_session(conn)
    _seed_tool_call(conn, "sess-001")
    conn.close()

    code = run_doctor_command(
        migration_ops=_migration_ops(),
        db_path=db, as_json=True, repair=False, migrate=False
    )
    out = json.loads(capsys.readouterr().out)

    # Verify top-level keys
    assert "overall" in out
    assert "checks" in out
    assert "db_path" in out
    assert "migration" in out
    assert "repair" in out

    # Verify each check has required fields
    for check in out["checks"]:
        assert "name" in check
        assert "status" in check
        assert "detail" in check
        assert check["status"] in ("ok", "warn", "critical")

    assert out["overall"] in ("ok", "warn", "critical")
    assert out["db_path"] == str(db)
    assert code in (0, 1, 2)


# --------------------------------------------------------------------------- #
# Test: schema already up-to-date reports ok
# --------------------------------------------------------------------------- #

def test_schema_up_to_date(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    db = tmp_path / "events.duckdb"
    conn = _fresh_db(db)
    conn.close()

    code = run_doctor_command(
        migration_ops=_migration_ops(),
        db_path=db, as_json=True, repair=False, migrate=False
    )
    out = json.loads(capsys.readouterr().out)

    schema_check = next(c for c in out["checks"] if c["name"] == "schema_version")
    assert schema_check["status"] == "ok"
    assert out["migration"]["needs_migration"] is False
    # No orphans on empty DB → overall ok
    assert code == 0


# --------------------------------------------------------------------------- #
# Test: repair with no orphans → nothing_to_repair
# --------------------------------------------------------------------------- #

def test_repair_no_orphans(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    db = tmp_path / "events.duckdb"
    conn = _fresh_db(db)
    _seed_session(conn)
    _seed_tool_call(conn, "sess-001")
    conn.close()

    code = run_doctor_command(
        migration_ops=_migration_ops(),
        db_path=db, as_json=True, repair=True, migrate=False
    )
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["repair"]["status"] == "nothing_to_repair"
