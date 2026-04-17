from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ccprophet.domain.entities import SettingsDoc


class SettingsStore(Protocol):
    """Atomic reader/writer for JSON config files (.claude/settings.json etc.).

    Implementations MUST:
    - hash source bytes as SHA256 (hex) and populate `SettingsDoc.sha256` on `read`
    - perform `write_atomic` via tmp + os.replace (POSIX+Windows)
    - if `expected_hash` is provided, re-read and compare hash immediately before
      writing; on mismatch raise `SnapshotConflict`.
    """

    def read(self, path: Path) -> SettingsDoc: ...

    def write_atomic(
        self,
        path: Path,
        content: dict[str, object],
        *,
        expected_hash: str | None = None,
    ) -> SettingsDoc: ...

    def write_bytes_atomic(self, path: Path, data: bytes) -> None:
        """Used by RestoreSnapshotUseCase to put original bytes back verbatim.

        No hash guard — restore is an explicit overwrite.
        """
        ...
