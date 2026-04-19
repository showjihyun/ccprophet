"""Shared timezone helpers for DuckDB repository modules.

All datetimes stored in DuckDB are UTC-naive (no tzinfo).  These two helpers
handle the round-trip between Python's tz-aware datetimes and the DB format.
"""

from __future__ import annotations

from datetime import datetime, timezone


def to_utc_naive(dt: datetime | None) -> datetime | None:
    """Strip tzinfo after converting to UTC.  None-safe."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def from_utc(dt: datetime | None) -> datetime | None:
    """Re-attach UTC tzinfo to a naive datetime read from DuckDB.  None-safe."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)
