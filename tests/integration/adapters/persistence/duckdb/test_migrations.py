from __future__ import annotations

import duckdb
import pytest

from ccprophet.adapters.persistence.duckdb.migrations import (
    apply_migrations,
    current_version,
    ensure_schema,
)


@pytest.fixture
def conn(tmp_path):  # type: ignore[no-untyped-def]
    c = duckdb.connect(str(tmp_path / "test.duckdb"))
    yield c
    c.close()


def test_ensure_schema_on_empty_db_applies_all(conn) -> None:  # type: ignore[no-untyped-def]
    ensure_schema(conn)
    assert current_version(conn) >= 2
    tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
    assert {
        "sessions",
        "events",
        "recommendations",
        "snapshots",
        "outcome_labels",
        "subset_profiles",
        "pricing_rates",
    } <= tables


def test_apply_migrations_is_idempotent(conn) -> None:  # type: ignore[no-untyped-def]
    apply_migrations(conn)
    v1 = current_version(conn)
    apply_migrations(conn)
    v2 = current_version(conn)
    assert v1 == v2


def test_v2_seeds_default_pricing(conn) -> None:  # type: ignore[no-untyped-def]
    ensure_schema(conn)
    count = conn.execute("SELECT COUNT(*) FROM pricing_rates").fetchone()
    assert count is not None and count[0] >= 3


def test_ensure_schema_upgrades_v1_db_to_v2(conn) -> None:  # type: ignore[no-untyped-def]
    apply_migrations(conn, up_to=1)
    assert current_version(conn) == 1
    ensure_schema(conn)
    assert current_version(conn) >= 2
