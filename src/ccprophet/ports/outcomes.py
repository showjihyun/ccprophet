from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ccprophet.domain.entities import OutcomeLabel, Session
from ccprophet.domain.values import OutcomeLabelValue, SessionId, TaskType


@dataclass(frozen=True, slots=True)
class OutcomeRule:
    name: str
    description: str
    applies_when: str


class OutcomeRepository(Protocol):
    def set_label(self, label: OutcomeLabel) -> None: ...
    def get_label(self, sid: SessionId) -> OutcomeLabel | None: ...
    def list_sessions_by_label(
        self,
        label: OutcomeLabelValue,
        task_type: TaskType | None = None,
    ) -> Sequence[Session]: ...


class OutcomeRulesProvider(Protocol):
    def rules(self) -> Sequence[OutcomeRule]: ...
