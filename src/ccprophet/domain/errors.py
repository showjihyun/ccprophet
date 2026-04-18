from __future__ import annotations

from ccprophet.domain.values import SessionId


class DomainError(Exception):
    pass


class SessionNotFound(DomainError):
    def __init__(self, session_id: SessionId) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class InvalidPhaseBoundary(DomainError):
    pass


class InsufficientSamples(DomainError):
    def __init__(self, needed: int, got: int, context: str = "") -> None:
        self.needed = needed
        self.got = got
        super().__init__(
            f"Insufficient samples: needed {needed}, got {got} ({context})".rstrip(" ()")
        )


class UnknownPricingModel(DomainError):
    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(f"No pricing rate for model: {model}")


class SnapshotConflict(DomainError):
    pass


class SnapshotMissing(DomainError):
    pass


class ProfileNotFound(DomainError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Subset profile not found: {name}")
