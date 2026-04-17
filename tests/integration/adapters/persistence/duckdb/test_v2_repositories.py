from __future__ import annotations

import duckdb
import pytest

from ccprophet.adapters.persistence.duckdb.migrations import ensure_schema
from tests.contract.test_outcome_repository_contract import OutcomeRepositoryContract
from tests.contract.test_pricing_provider_contract import PricingProviderContract
from tests.contract.test_recommendation_repository_contract import (
    RecommendationRepositoryContract,
)
from tests.contract.test_snapshot_repository_contract import SnapshotRepositoryContract
from tests.contract.test_forecast_repository_contract import (
    ForecastRepositoryContract,
)
from tests.contract.test_subagent_repository_contract import (
    SubagentRepositoryContract,
)
from tests.contract.test_subset_profile_contract import SubsetProfileStoreContract


@pytest.fixture
def duck_conn(tmp_path):  # type: ignore[no-untyped-def]
    conn = duckdb.connect(str(tmp_path / "v2.duckdb"))
    ensure_schema(conn)
    yield conn
    conn.close()


class TestDuckDBRecommendationRepository(RecommendationRepositoryContract):
    @pytest.fixture
    def repository(self, duck_conn):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBRecommendationRepository,
        )
        return DuckDBRecommendationRepository(duck_conn)


class TestDuckDBSnapshotRepository(SnapshotRepositoryContract):
    @pytest.fixture
    def repository(self, duck_conn):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBSnapshotRepository,
        )
        return DuckDBSnapshotRepository(duck_conn)


class TestDuckDBOutcomeRepository(OutcomeRepositoryContract):
    @pytest.fixture
    def sessions_repo(self, duck_conn):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.duckdb.repositories import (
            DuckDBSessionRepository,
        )
        return DuckDBSessionRepository(duck_conn)

    @pytest.fixture
    def repository(self, duck_conn, sessions_repo):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBOutcomeRepository,
        )
        return DuckDBOutcomeRepository(duck_conn)


class TestDuckDBSubsetProfileStore(SubsetProfileStoreContract):
    @pytest.fixture
    def store(self, duck_conn):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBSubsetProfileStore,
        )
        return DuckDBSubsetProfileStore(duck_conn)


class TestDuckDBSubagentRepository(SubagentRepositoryContract):
    @pytest.fixture
    def repository(self, duck_conn):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.duckdb.v3_repositories import (
            DuckDBSubagentRepository,
        )
        return DuckDBSubagentRepository(duck_conn)


class TestDuckDBForecastRepository(ForecastRepositoryContract):
    @pytest.fixture
    def repository(self, duck_conn):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.duckdb.v3_repositories import (
            DuckDBForecastRepository,
        )
        return DuckDBForecastRepository(duck_conn)


class TestDuckDBPricingProvider(PricingProviderContract):
    @pytest.fixture
    def provider(self, duck_conn):  # type: ignore[no-untyped-def]
        duck_conn.execute("DELETE FROM pricing_rates")
        from ccprophet.adapters.persistence.duckdb.v2_repositories import (
            DuckDBPricingProvider,
        )
        return DuckDBPricingProvider(duck_conn)

    def upsert(self, provider, rate) -> None:  # type: ignore[no-untyped-def]
        provider.upsert(rate)
