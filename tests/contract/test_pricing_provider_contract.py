from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

import pytest

from ccprophet.domain.errors import UnknownPricingModel
from tests.fixtures.builders import PricingRateBuilder


class PricingProviderContract(ABC):
    @pytest.fixture
    @abstractmethod
    def provider(self):  # type: ignore[no-untyped-def]
        ...

    @abstractmethod
    def upsert(self, provider, rate) -> None:  # type: ignore[no-untyped-def]
        """Adapter-specific seeding."""

    def test_rate_for_matches_model(self, provider) -> None:  # type: ignore[no-untyped-def]
        rate = PricingRateBuilder().for_model("claude-opus-4-7").build()
        self.upsert(provider, rate)
        got = provider.rate_for("claude-opus-4-7")
        assert got.input_per_mtok == rate.input_per_mtok

    def test_unknown_model_raises(self, provider) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(UnknownPricingModel):
            provider.rate_for("does-not-exist")

    def test_at_filter_picks_most_recent_not_after(self, provider) -> None:  # type: ignore[no-untyped-def]
        old = (
            PricingRateBuilder()
            .for_model("model-x")
            .effective_at(datetime(2026, 1, 1, tzinfo=timezone.utc))
            .build()
        )
        new = (
            PricingRateBuilder()
            .for_model("model-x")
            .effective_at(datetime(2026, 3, 1, tzinfo=timezone.utc))
            .build()
        )
        self.upsert(provider, old)
        self.upsert(provider, new)
        got = provider.rate_for(
            "model-x", at=datetime(2026, 2, 1, tzinfo=timezone.utc)
        )
        assert got.effective_at == old.effective_at


class TestInMemoryPricingProvider(PricingProviderContract):
    @pytest.fixture
    def provider(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import (
            InMemoryPricingProvider,
        )
        return InMemoryPricingProvider()

    def upsert(self, provider, rate) -> None:  # type: ignore[no-untyped-def]
        provider.add(rate)
