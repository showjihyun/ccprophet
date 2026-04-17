"""ccprophet doctor — DB health checks and optional repair.

Operational adapter-layer command. Talks to DuckDB directly; no use-case layer.
"""
from __future__ import annotations

import json as json_module
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

OK, WARN, CRITICAL = "ok", "warn", "critical"
_RANK = {OK: 0, WARN: 1, CRITICAL: 2}
SNAPSHOTS_WARN_MB = 50


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass
class DoctorReport:
    overall: str
    db_path: str
    checks: list[CheckResult] = field(default_factory=list)
    migration: dict = field(default_factory=dict)  # type: ignore[type-arg]
    repair: dict = field(default_factory=dict)  # type: ignore[type-arg]

    def worst(self, status: str) -> None:
        if _RANK[status] > _RANK[self.overall]:
            self.overall = status


# ── helpers ──────────────────────────────────────────────────────────────── #

def _table_exists(conn: duckdb.DuckDBPyConnection, table: str) -> bool:
    try:
        conn.execute(f"SELECT 1 FROM {table} LIMIT 0").fetchall()
        return True
    except Exception:
        return False


def _count(conn: duckdb.DuckDBPyConnection, sql: str) -> int:
    try:
        row = conn.execute(sql).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def _check_db_file(db_path: Path) -> CheckResult:
    if not db_path.exists():
        return CheckResult("db_file", CRITICAL, f"File not found: {db_path}")
    try:
        import duckdb
        conn = duckdb.connect(str(db_path), read_only=True)
        conn.execute("SELECT 1").fetchone()
        conn.close()
        mb = db_path.stat().st_size / (1024 * 1024)
        return CheckResult("db_file", OK, f"Valid DuckDB ({mb:.1f} MB)")
    except Exception as exc:
        return CheckResult("db_file", CRITICAL, f"Cannot open DB: {exc}")


def _check_schema_version(
    conn: duckdb.DuckDBPyConnection, migrations_dir: Path
) -> tuple[CheckResult, dict]:  # type: ignore[type-arg]
    from ccprophet.adapters.persistence.duckdb.migrations import current_version
    current = current_version(conn)
    latest = max(
        (
            int(f.name.split("__")[0].removeprefix("V"))
            for f in migrations_dir.glob("V*__*.sql")
            if f.name.split("__")[0].removeprefix("V").isdigit()
        ),
        default=0,
    )
    needs = current < latest
    info = {"current": current, "latest_available": latest, "needs_migration": needs}
    if needs:
        result = CheckResult(
            "schema_version", WARN,
            f"Schema at V{current}, latest V{latest} — run --migrate",
        )
    else:
        result = CheckResult("schema_version", OK, f"Schema up to date (V{current})")
    return result, info


def _check_orphans(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    if not _table_exists(conn, "sessions"):
        return {t: 0 for t in ("tool_calls", "events", "phases", "forecasts", "tool_defs_loaded")}
    counts: dict[str, int] = {}
    for tbl in ("tool_calls", "events", "phases", "forecasts", "tool_defs_loaded"):
        if not _table_exists(conn, tbl):
            counts[tbl] = 0
        else:
            counts[tbl] = _count(
                conn,
                f"SELECT COUNT(*) FROM {tbl} t "
                f"LEFT JOIN sessions s ON s.session_id = t.session_id "
                f"WHERE s.session_id IS NULL",
            )
    return counts


def _repair_orphans(conn: duckdb.DuckDBPyConnection, orphan_counts: dict[str, int]) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for tbl, count in orphan_counts.items():
        if count == 0:
            deleted[tbl] = 0
            continue
        try:
            conn.execute(
                f"DELETE FROM {tbl} WHERE session_id NOT IN (SELECT session_id FROM sessions)"
            )
            deleted[tbl] = count
        except Exception:
            deleted[tbl] = -1
    return deleted


def _snapshot_dir_mb(snapshot_dir: Path) -> float:
    if not snapshot_dir.exists():
        return 0.0
    total = 0
    for root, _dirs, files in os.walk(snapshot_dir):
        for fname in files:
            try:
                total += os.path.getsize(os.path.join(root, fname))
            except OSError:
                pass
    return total / (1024 * 1024)


# ── main ─────────────────────────────────────────────────────────────────── #

def run_doctor_command(
    *,
    db_path: Path,
    as_json: bool,
    repair: bool,
    migrate: bool,
    migrations_dir: Path | None = None,
    snapshot_dir: Path | None = None,
) -> int:
    from ccprophet.adapters.persistence.duckdb.migrations import MIGRATIONS_DIR
    mdir = migrations_dir or MIGRATIONS_DIR
    sdir = snapshot_dir or (db_path.parent / "snapshots")

    report = DoctorReport(overall=OK, db_path=str(db_path))

    db_check = _check_db_file(db_path)
    report.checks.append(db_check)
    report.worst(db_check.status)
    if db_check.status == CRITICAL:
        return _finish(report, as_json=as_json)

    import duckdb
    ro_conn = duckdb.connect(str(db_path), read_only=True)
    try:
        # 2: schema version
        schema_check, minfo = _check_schema_version(ro_conn, mdir)
        report.checks.append(schema_check)
        report.worst(schema_check.status)
        report.migration = minfo

        if migrate and minfo["needs_migration"]:
            ro_conn.close()
            rw = duckdb.connect(str(db_path))
            try:
                from ccprophet.adapters.persistence.duckdb.migrations import (
                    apply_migrations, current_version,
                )
                applied = apply_migrations(rw, migrations_dir=mdir)
                new_ver = current_version(rw)
            finally:
                rw.close()
            report.migration.update(applied=applied, new_version=new_ver, needs_migration=False)
            ro_conn = duckdb.connect(str(db_path), read_only=True)
            for c in report.checks:
                if c.name == "schema_version":
                    c.status, c.detail = OK, f"Migrated to V{new_ver} ({applied} applied)"

        # 3: orphan records
        orphan_counts = _check_orphans(ro_conn)
        total_orphans = sum(orphan_counts.values())
        orp_status = WARN if total_orphans > 0 else OK
        orp_detail = (
            ", ".join(f"{t}:{n}" for t, n in orphan_counts.items() if n > 0)
            if total_orphans > 0 else "None"
        )
        report.checks.append(CheckResult("orphan_records", orp_status, orp_detail))
        report.worst(orp_status)

        repair_info: dict = {}  # type: ignore[type-arg]
        if repair and total_orphans > 0:
            ro_conn.close()
            rw = duckdb.connect(str(db_path))
            try:
                repair_info["orphans_deleted"] = _repair_orphans(rw, orphan_counts)
                repair_info["status"] = "applied"
            finally:
                rw.close()
            ro_conn = duckdb.connect(str(db_path), read_only=True)
            for c in report.checks:
                if c.name == "orphan_records":
                    n = sum(v for v in repair_info["orphans_deleted"].values() if v >= 0)
                    c.status, c.detail = OK, f"Repaired — {n} orphan row(s) deleted"
        elif repair:
            repair_info = {"orphans_deleted": {}, "status": "nothing_to_repair"}
        report.repair = repair_info

        # 4: negative tokens
        neg_checks = {
            "tool_calls_neg_tokens": ("tool_calls", "input_tokens < 0 OR output_tokens < 0"),
            "sessions_neg_tokens": ("sessions", "total_input_tokens < 0 OR total_output_tokens < 0"),
        }
        neg_totals = {
            k: (_count(ro_conn, f"SELECT COUNT(*) FROM {t} WHERE {cond}") if _table_exists(ro_conn, t) else 0)
            for k, (t, cond) in neg_checks.items()
        }
        neg_sum = sum(neg_totals.values())
        neg_detail = ", ".join(f"{k}:{v}" for k, v in neg_totals.items() if v > 0) or "None"
        neg_status = WARN if neg_sum > 0 else OK
        report.checks.append(CheckResult("negative_tokens", neg_status, neg_detail))
        report.worst(neg_status)

        # 5: time inversions
        inv_checks = {
            "sessions_time_inversion": ("sessions", "ended_at < started_at"),
            "phases_time_inversion": ("phases", "end_ts < start_ts"),
        }
        inv_totals = {
            k: (_count(ro_conn, f"SELECT COUNT(*) FROM {t} WHERE {cond}") if _table_exists(ro_conn, t) else 0)
            for k, (t, cond) in inv_checks.items()
        }
        inv_sum = sum(inv_totals.values())
        inv_detail = ", ".join(f"{k}:{v}" for k, v in inv_totals.items() if v > 0) or "None"
        inv_status = WARN if inv_sum > 0 else OK
        report.checks.append(CheckResult("time_inversions", inv_status, inv_detail))
        report.worst(inv_status)

        # 6: duplicate event hash
        dup = (
            _count(ro_conn, "SELECT COUNT(*) - COUNT(DISTINCT raw_hash) FROM events")
            if _table_exists(ro_conn, "events") else 0
        )
        dup_status = WARN if dup > 0 else OK
        report.checks.append(CheckResult(
            "duplicate_event_hash", dup_status,
            f"{dup} duplicate(s)" if dup > 0 else "None",
        ))
        report.worst(dup_status)

        # 7: disk usage
        db_mb = db_path.stat().st_size / (1024 * 1024)
        wal_path = db_path.parent / (db_path.name + ".wal")
        wal_mb = wal_path.stat().st_size / (1024 * 1024) if wal_path.exists() else 0.0
        disk_detail = f"DB {db_mb:.1f} MB" + (f", WAL {wal_mb:.1f} MB" if wal_mb > 0 else "")
        report.checks.append(CheckResult("disk_usage", OK, disk_detail))

        # 8: snapshot directory size
        snap_mb = _snapshot_dir_mb(sdir)
        snap_status = WARN if snap_mb > SNAPSHOTS_WARN_MB else OK
        snap_detail = f"{snap_mb:.1f} MB"
        if snap_status == WARN:
            snap_detail += f" (exceeds {SNAPSHOTS_WARN_MB} MB threshold)"
        report.checks.append(CheckResult("snapshot_dir_usage", snap_status, snap_detail))
        report.worst(snap_status)

    finally:
        try:
            ro_conn.close()
        except Exception:
            pass

    # Re-compute overall (repairs may have cleared some WARNs)
    report.overall = OK
    for c in report.checks:
        report.worst(c.status)

    return _finish(report, as_json=as_json)


def _finish(report: DoctorReport, *, as_json: bool) -> int:
    if as_json:
        print(json_module.dumps({
            "overall": report.overall,
            "db_path": report.db_path,
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in report.checks],
            "migration": report.migration,
            "repair": report.repair,
        }, indent=2))
    else:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        style = {OK: "bold green", WARN: "bold yellow", CRITICAL: "bold red"}[report.overall]
        console.print(f"[{style}]Overall: {report.overall.upper()}[/]  —  {report.db_path}")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Check", style="dim")
        table.add_column("Status")
        table.add_column("Detail")
        ss = {OK: "green", WARN: "yellow", CRITICAL: "red"}
        for c in report.checks:
            table.add_row(c.name, f"[{ss[c.status]}]{c.status}[/]", c.detail)
        console.print(table)
        if report.migration:
            console.print(f"[dim]Migration:[/] {report.migration}")
        if report.repair:
            console.print(f"[dim]Repair:[/] {report.repair}")
    return {OK: 0, WARN: 1, CRITICAL: 2}[report.overall]
