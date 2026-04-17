from __future__ import annotations

from datetime import datetime, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(tz=timezone.utc)


class FrozenClock:
    def __init__(self, frozen_at: datetime | None = None) -> None:
        self._now = frozen_at or datetime(2026, 4, 16, 9, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)
