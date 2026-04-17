from __future__ import annotations

from typing import Protocol


class Redactor(Protocol):
    def redact_path(self, path: str) -> str: ...
    def redact_command(self, cmd: str) -> str: ...
