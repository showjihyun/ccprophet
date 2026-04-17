from __future__ import annotations

import pytest

from tests.contract.test_phase_repository_contract import PhaseRepositoryContract


class TestDuckDBPhaseRepository(PhaseRepositoryContract):
    @pytest.fixture
    def repository(self, tmp_path):  # type: ignore[no-untyped-def]
        import duckdb

        from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema
        from ccprophet.adapters.persistence.duckdb.repositories import DuckDBPhaseRepository

        conn = duckdb.connect(str(tmp_path / "ccprophet.duckdb"))
        ensure_schema(conn)
        return DuckDBPhaseRepository(conn)
