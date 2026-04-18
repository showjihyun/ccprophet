#!/usr/bin/env python
"""Seed a rich, realistic DuckDB for the ccprophet demo screencast.

Every run produces an identical file (same UUIDs via `uuid.uuid5` with a
fixed namespace) so the screencast can be re-shot without visible drift.

Usage:
    python scripts/seed_demo_db.py [--db ~/.claude-prophet/demo.duckdb]

The resulting DB contains:
  - 2 sessions: one "bloated" (opus-4-7, 11 loaded tools, 3 actually used,
    ~89% bloat, cache hits) and one "success" (sonnet-4-6, labeled success,
    cache-heavy).
  - 6 AssistantResponse events forming a believable cumulative-input curve
    for the forecaster.
  - 8 tool_calls including a realistic Read re-read loop.
  - One success outcome label for `refactor-auth`.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# UUIDs derived from a fixed namespace so the demo is byte-identical on reruns.
_NS = uuid.UUID("ccfafe99-aaaa-4aaa-8aaa-0000cc010000")


def _uuid(key: str) -> str:
    return str(uuid.uuid5(_NS, key))


def seed(db_path: Path) -> None:
    try:
        import duckdb
    except ImportError:  # pragma: no cover
        sys.exit("duckdb not installed — run `uv sync` first.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    # Apply real V1..V5 migrations — demo DB must match what `ccprophet
    # doctor --migrate` would produce for a fresh user.
    from ccprophet.adapters.persistence.duckdb.migrations import (
        MIGRATIONS_DIR,
        apply_migrations,
    )

    conn = duckdb.connect(str(db_path))
    try:
        applied = apply_migrations(conn, migrations_dir=MIGRATIONS_DIR)
        print(f"applied {applied} migrations from {MIGRATIONS_DIR}")
        _seed_sessions(conn)
        _seed_tool_defs(conn)
        _seed_tool_calls(conn)
        _seed_events(conn)
        _seed_outcome(conn)
    finally:
        conn.close()

    print(f"demo DB ready:  {db_path}")
    print("next step:")
    print(f"  export CCPROPHET_DB={db_path}")
    print("  ccprophet bloat --session sess-bloat --cost --json")


# --------------------------------------------------------------------- #
# Individual seed sections (kept separate for readability / narration)  #
# --------------------------------------------------------------------- #

# Anchor time is "now - 55 min" at seed time so the forecast demo shows a
# high-confidence ETA and the events fall inside every default time window.
# Using the wall clock means the forecast curve is always "fresh", which is
# exactly what a viewer expects from a live recording.
_T0 = datetime.now().replace(microsecond=0) - timedelta(minutes=55)


def _seed_sessions(conn) -> None:  # type: ignore[no-untyped-def]
    conn.execute(
        """INSERT INTO sessions (session_id, project_slug, model, started_at, ended_at,
                total_input_tokens, total_output_tokens, compacted, context_window_size,
                total_cache_creation_tokens, total_cache_read_tokens)
           VALUES ('sess-bloat', 'ccprophet-demo', 'claude-opus-4-7', ?, NULL,
                   120000, 40000, FALSE, 200000, 8000, 35000)""",
        [_T0],
    )
    conn.execute(
        """INSERT INTO sessions (session_id, project_slug, model, started_at, ended_at,
                total_input_tokens, total_output_tokens, compacted, context_window_size,
                total_cache_creation_tokens, total_cache_read_tokens)
           VALUES ('sess-succ', 'ccprophet-demo', 'claude-sonnet-4-6', ?, ?,
                   80000, 20000, FALSE, 200000, 20000, 50000)""",
        [_T0 - timedelta(days=2), _T0 - timedelta(days=2) + timedelta(hours=2)],
    )


def _seed_tool_defs(conn) -> None:  # type: ignore[no-untyped-def]
    # 11 tools loaded; only 3 will be called below (Read/Edit/Bash). That yields
    # ~89% bloat — the dramatic number the demo shows on screen.
    defs = [
        ("Read", "builtin", 500),
        ("Edit", "builtin", 500),
        ("Bash", "builtin", 500),
        ("Write", "builtin", 500),
        ("Glob", "builtin", 300),
        ("Grep", "builtin", 300),
        ("mcp__github__create_pr", "mcp:github", 2000),
        ("mcp__github__list_issues", "mcp:github", 1500),
        ("mcp__pencil__draw", "mcp:pencil", 3000),
        ("mcp__pencil__export", "mcp:pencil", 2800),
        ("mcp__gmail__send", "mcp:gmail", 1800),
    ]
    for name, src, tok in defs:
        conn.execute(
            "INSERT INTO tool_defs_loaded (session_id, tool_name, tokens, source, loaded_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ["sess-bloat", name, tok, src, _T0],
        )


def _seed_tool_calls(conn) -> None:  # type: ignore[no-untyped-def]
    # Realistic fail pattern: 4 read re-reads of the same file + one Edit +
    # one Bash. Postmortem will flag the Read loop; bloat will flag the
    # 3 unused MCPs.
    calls = [
        ("Read", 1, "hash-readme"),
        ("Read", 2, "hash-readme"),  # same file re-read
        ("Edit", 3, "hash-edit"),
        ("Bash", 4, "hash-bash"),
        ("Read", 10, "hash-readme"),
        ("Read", 11, "hash-readme"),
        ("Read", 12, "hash-readme"),
        ("Read", 13, "hash-readme"),
    ]
    for idx, (name, off, h) in enumerate(calls):
        conn.execute(
            """INSERT INTO tool_calls (tool_call_id, session_id, parent_id, tool_name,
                   input_hash, input_tokens, output_tokens, latency_ms, success, ts)
               VALUES (?, 'sess-bloat', NULL, ?, ?, 1000, 200, 50, TRUE, ?)""",
            [_uuid(f"tc-{idx}"), name, h, _T0 + timedelta(minutes=off)],
        )


def _seed_events(conn) -> None:  # type: ignore[no-untyped-def]
    # 6 AssistantResponse events on a steady 3k-token-per-10min burn.
    # The forecaster will project autocompact ~30min out; demo shows ETA.
    for i in range(6):
        payload = (
            '{"message":{"usage":{"input_tokens":' + str(5000 + i * 3000)
            + ',"output_tokens":500,"cache_creation_input_tokens":1000,'
            '"cache_read_input_tokens":2000}}}'
        )
        conn.execute(
            """INSERT INTO events (event_id, session_id, event_type, ts, payload,
                   raw_hash, ingested_via)
               VALUES (?, 'sess-bloat', 'AssistantResponse', ?, ?::JSON, ?, 'hook')""",
            [_uuid(f"evt-{i}"), _T0 + timedelta(minutes=i * 10), payload, _uuid(f"raw-{i}")],
        )


def _seed_outcome(conn) -> None:  # type: ignore[no-untyped-def]
    conn.execute(
        """INSERT INTO outcome_labels (session_id, label, task_type, source, labeled_at)
           VALUES ('sess-succ', 'success', 'refactor-auth', 'manual', ?)""",
        [_T0 - timedelta(days=1)],
    )


def _default_db_path() -> Path:
    override = os.environ.get("CCPROPHET_DB")
    if override:
        return Path(override)
    return Path.home() / ".claude-prophet" / "demo.duckdb"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the ccprophet demo DB.")
    parser.add_argument(
        "--db",
        type=Path,
        default=_default_db_path(),
        help="Target DuckDB path (default: ~/.claude-prophet/demo.duckdb or $CCPROPHET_DB).",
    )
    args = parser.parse_args()
    seed(args.db)


if __name__ == "__main__":
    main()
