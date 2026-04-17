from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class JsonlRecord:
    raw_hash_hex: str
    session_id: str
    event_type: str
    ts: datetime
    uuid: str
    payload: dict[str, object]


class JsonlSource(Protocol):
    def read_file(self, path: Path) -> Iterator[JsonlRecord]: ...
