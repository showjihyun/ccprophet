from __future__ import annotations

from abc import ABC, abstractmethod

import pytest

from ccprophet.domain.values import OutcomeLabelValue, SessionId, TaskType
from tests.fixtures.builders import OutcomeLabelBuilder, SessionBuilder


class OutcomeRepositoryContract(ABC):
    """Contract that assumes the repo is backed by a SessionRepository
    accessible via the `sessions_repo` fixture."""

    @pytest.fixture
    @abstractmethod
    def sessions_repo(self):  # type: ignore[no-untyped-def]
        ...

    @pytest.fixture
    @abstractmethod
    def repository(self, sessions_repo):  # type: ignore[no-untyped-def]
        ...

    def test_set_and_get_label(self, repository) -> None:  # type: ignore[no-untyped-def]
        label = OutcomeLabelBuilder().for_session("s1").build()
        repository.set_label(label)
        got = repository.get_label(SessionId("s1"))
        assert got is not None
        assert got.label == OutcomeLabelValue.SUCCESS

    def test_get_unknown_returns_none(self, repository) -> None:  # type: ignore[no-untyped-def]
        assert repository.get_label(SessionId("nope")) is None

    def test_list_sessions_by_label_and_task(
        self, repository, sessions_repo
    ) -> None:  # type: ignore[no-untyped-def]
        for sid in ("s1", "s2", "s3"):
            sessions_repo.upsert(SessionBuilder().with_id(sid).build())
        repository.set_label(
            OutcomeLabelBuilder().for_session("s1").with_task("refactor").build()
        )
        repository.set_label(
            OutcomeLabelBuilder().for_session("s2").with_task("refactor").build()
        )
        repository.set_label(
            OutcomeLabelBuilder()
            .for_session("s3")
            .with_task("refactor")
            .with_label(OutcomeLabelValue.FAIL)
            .build()
        )

        successes = list(
            repository.list_sessions_by_label(
                OutcomeLabelValue.SUCCESS, TaskType("refactor")
            )
        )
        assert {s.session_id.value for s in successes} == {"s1", "s2"}


class TestInMemoryOutcomeRepository(OutcomeRepositoryContract):
    @pytest.fixture
    def sessions_repo(self):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import (
            InMemorySessionRepository,
        )
        return InMemorySessionRepository()

    @pytest.fixture
    def repository(self, sessions_repo):  # type: ignore[no-untyped-def]
        from ccprophet.adapters.persistence.inmemory.repositories import (
            InMemoryOutcomeRepository,
        )
        return InMemoryOutcomeRepository(sessions_repo)
