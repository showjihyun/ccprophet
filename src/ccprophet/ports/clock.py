from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Source of current time for the domain.

    Contract: implementations MUST return a **timezone-aware UTC** datetime
    (`tzinfo is datetime.timezone.utc`). Mixing naive and aware values inside
    the domain would raise `TypeError` at comparison boundaries (see
    `forecast._filter_window`); the contract removes the ambiguity at the port.

    Enforced by the adapters: `SystemClock` calls `datetime.now(timezone.utc)`
    and `FrozenClock` refuses naive inputs in its constructor.
    """

    def now(self) -> datetime: ...
