"""Atomic SettingsStore implementation for .claude/settings.json and .mcp.json.

AP-7 (Reversible Auto-Fix) — this is the ONLY place ccprophet writes to user
config files. `write_atomic` refuses to write when the on-disk content drifted
from what was last read.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from ccprophet.domain.entities import SettingsDoc
from ccprophet.domain.errors import SnapshotConflict


def _atomic_replace(src: Path, dst: Path, *, attempts: int = 3) -> None:
    """Windows-safe wrapper around ``os.replace``.

    On Windows, ``os.replace`` can raise ``PermissionError`` (winerror 5) when
    the target is momentarily held open by AV, Spotlight / indexer, or another
    ccprophet process. A short retry loop recovers without surfacing a scary
    traceback to a user running `ccprophet prune --apply`.
    """
    last_exc: OSError | None = None
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:  # Windows only
            last_exc = exc
            time.sleep(0.05 * (i + 1))
    # Exhausted retries — surface the original exception so callers can
    # decide (CLI renders a readable error; tests still see PermissionError).
    assert last_exc is not None
    raise last_exc


class JsonFileSettingsStore:
    def read(self, path: Path) -> SettingsDoc:
        raw = path.read_bytes()
        content = json.loads(raw) if raw.strip() else {}
        if not isinstance(content, dict):
            raise ValueError(f"{path}: top-level JSON must be an object")
        return SettingsDoc(
            path=str(path),
            content=content,
            sha256=hashlib.sha256(raw).hexdigest(),
        )

    def write_atomic(
        self,
        path: Path,
        content: dict[str, object],
        *,
        expected_hash: str | None = None,
    ) -> SettingsDoc:
        if expected_hash is not None:
            actual = self._hash_of(path)
            if actual != expected_hash:
                raise SnapshotConflict(
                    f"{path} changed since read (expected {expected_hash[:8]}, saw {actual[:8]})"
                )

        data = _serialize(content)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(data)
        _atomic_replace(tmp, path)
        return SettingsDoc(
            path=str(path),
            content=content,
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    def write_bytes_atomic(self, path: Path, data: bytes) -> None:
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(data)
        _atomic_replace(tmp, path)

    @staticmethod
    def _hash_of(path: Path) -> str:
        if not path.exists():
            return ""
        return hashlib.sha256(path.read_bytes()).hexdigest()


def _serialize(content: dict[str, object]) -> bytes:
    text = json.dumps(content, indent=2, ensure_ascii=False, sort_keys=False)
    return (text + "\n").encode("utf-8")
