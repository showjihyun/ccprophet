from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


@dataclass(frozen=True, slots=True)
class SessionId:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class EventId:
    value: str


@dataclass(frozen=True, slots=True)
class TokenCount:
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(f"TokenCount cannot be negative: {self.value}")

    def __add__(self, other: TokenCount) -> TokenCount:
        return TokenCount(self.value + other.value)

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class BloatRatio:
    value: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.value <= 1.0):
            raise ValueError(f"BloatRatio must be in [0.0, 1.0]: {self.value}")

    def as_percent(self) -> float:
        return round(self.value * 100, 1)


@dataclass(frozen=True, slots=True)
class RawHash:
    value: str


@dataclass(frozen=True, slots=True)
class FilePathHash:
    value: str


class ToolSource(str, Enum):
    SYSTEM = "system"
    MCP = "mcp"
    CUSTOM_AGENT = "custom_agent"
    SKILL = "skill"
    DEFERRED = "deferred"

    @classmethod
    def from_string(cls, s: str) -> ToolSource:
        if s.startswith("mcp:"):
            return cls.MCP
        try:
            return cls(s)
        except ValueError:
            return cls.SYSTEM


class PhaseType(str, Enum):
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    DEBUGGING = "debugging"
    REVIEW = "review"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SnapshotId:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")
        return Money(self.amount - other.amount, self.currency)

    @classmethod
    def zero(cls, currency: str = "USD") -> Money:
        return cls(Decimal("0"), currency)


@dataclass(frozen=True, slots=True)
class Confidence:
    value: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.value <= 1.0):
            raise ValueError(f"Confidence must be in [0.0, 1.0]: {self.value}")


@dataclass(frozen=True, slots=True)
class TaskType:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("TaskType cannot be empty")


class RecommendationKind(str, Enum):
    PRUNE_MCP = "prune_mcp"
    PRUNE_TOOL = "prune_tool"
    RUN_CLEAR = "run_clear"
    SWITCH_SUBSET = "switch_subset"
    COMPACT_FOCUS = "compact_focus"
    REPRODUCE_CONFIG = "reproduce_config"
    SET_ENV_VAR = "set_env_var"  # advisory env-var setting recommendation


class RecommendationStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class OutcomeLabelValue(str, Enum):
    SUCCESS = "success"
    FAIL = "fail"
    PARTIAL = "partial"
    UNLABELED = "unlabeled"


def int_or_zero(value: object) -> int:
    """Coerce a loosely-typed value to int, returning 0 on None or parse error."""
    try:
        return int(value) if value is not None else 0  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
