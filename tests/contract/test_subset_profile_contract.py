from __future__ import annotations

from abc import ABC, abstractmethod

import pytest

from tests.fixtures.builders import SubsetProfileBuilder


class SubsetProfileStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def store(self):  # type: ignore[no-untyped-def]
        ...

    def test_save_load_roundtrip(self, store) -> None:  # type: ignore[no-untyped-def]
        prof = SubsetProfileBuilder().named("refactor").build()
        store.save(prof)
        got = store.load("refactor")
        assert got is not None
        assert got.content == prof.content

    def test_load_unknown_returns_none(self, store) -> None:  # type: ignore[no-untyped-def]
        assert store.load("missing") is None

    def test_list_all_sorted(self, store) -> None:  # type: ignore[no-untyped-def]
        store.save(SubsetProfileBuilder().named("b").build())
        store.save(SubsetProfileBuilder().named("a").build())
        names = [p.name for p in store.list_all()]
        assert names == sorted(names)

    def test_delete(self, store) -> None:  # type: ignore[no-untyped-def]
        store.save(SubsetProfileBuilder().named("tmp").build())
        store.delete("tmp")
        assert store.load("tmp") is None


class TestInMemorySubsetProfileStore(SubsetProfileStoreContract):
    @pytest.fixture
    def store(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import (
            InMemorySubsetProfileStore,
        )

        return InMemorySubsetProfileStore()
