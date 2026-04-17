"""Filesystem-backed SnapshotStore.

Directory layout per snapshot:

    <root>/<snapshot-id>/
        manifest.json   # [{"path": "/original/abs/path", "sha256": "...", "size": N, "blob": "0.bin"}, ...]
        0.bin           # raw bytes for file 0
        1.bin           # ...

Separated from the DuckDB `snapshots` metadata on purpose (AP-7, DATAMODELING Q7):
restores and manual inspection stay simple, DB tracks just the manifest entry.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from ccprophet.domain.entities import Snapshot, SnapshotFileEntry
from ccprophet.domain.errors import SnapshotMissing
from ccprophet.domain.values import SnapshotId
from ccprophet.ports.snapshots import SnapshotMeta


class FilesystemSnapshotStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def capture(
        self, files: Mapping[str, bytes], meta: SnapshotMeta
    ) -> Snapshot:
        sid = SnapshotId(str(uuid.uuid4()))
        snap_dir = self._root / sid.value
        snap_dir.mkdir(parents=True, exist_ok=True)

        manifest: list[dict[str, object]] = []
        entries: list[SnapshotFileEntry] = []

        for index, (original_path, data) in enumerate(files.items()):
            blob_name = f"{index}.bin"
            (snap_dir / blob_name).write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            manifest.append(
                {
                    "path": original_path,
                    "sha256": digest,
                    "size": len(data),
                    "blob": blob_name,
                }
            )
            entries.append(
                SnapshotFileEntry(
                    path=original_path, sha256=digest, byte_size=len(data)
                )
            )

        (snap_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        return Snapshot(
            snapshot_id=sid,
            captured_at=datetime.now(timezone.utc),
            reason=meta.reason,
            triggered_by=meta.triggered_by,
            files=tuple(entries),
            byte_size=sum(e.byte_size for e in entries),
        )

    def restore(self, sid: SnapshotId) -> Mapping[str, bytes]:
        snap_dir = self._root / sid.value
        manifest_path = snap_dir / "manifest.json"
        if not manifest_path.exists():
            raise SnapshotMissing(f"Snapshot not found: {sid.value}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result: dict[str, bytes] = {}
        for entry in manifest:
            blob = snap_dir / str(entry["blob"])
            result[str(entry["path"])] = blob.read_bytes()
        return result
