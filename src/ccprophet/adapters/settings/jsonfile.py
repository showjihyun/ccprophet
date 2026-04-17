"""Atomic SettingsStore implementation for .claude/settings.json and .mcp.json.

AP-7 (Reversible Auto-Fix) — this is the ONLY place ccprophet writes to user
config files. `write_atomic` refuses to write when the on-disk content drifted
from what was last read.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from ccprophet.domain.entities import SettingsDoc
from ccprophet.domain.errors import SnapshotConflict


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
                    f"{path} changed since read "
                    f"(expected {expected_hash[:8]}, saw {actual[:8]})"
                )

        data = _serialize(content)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return SettingsDoc(
            path=str(path),
            content=content,
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def write_bytes_atomic(self, path: Path, data: bytes) -> None:
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    @staticmethod
    def _hash_of(path: Path) -> str:
        if not path.exists():
            return ""
        return hashlib.sha256(path.read_bytes()).hexdigest()


def _serialize(content: dict[str, object]) -> bytes:
    text = json.dumps(content, indent=2, ensure_ascii=False, sort_keys=False)
    return (text + "\n").encode("utf-8")
