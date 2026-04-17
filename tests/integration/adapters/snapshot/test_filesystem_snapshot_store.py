from __future__ import annotations

import pytest

from ccprophet.adapters.snapshot.filesystem import FilesystemSnapshotStore
from ccprophet.domain.errors import SnapshotMissing
from ccprophet.domain.values import SnapshotId
from ccprophet.ports.snapshots import SnapshotMeta


def test_capture_then_restore_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = FilesystemSnapshotStore(tmp_path)
    files = {
        "/fake/home/.claude/settings.json": b'{"a": 1}\n',
        "/fake/home/.mcp.json": b'{"mcpServers": {}}\n',
    }
    snap = store.capture(files, SnapshotMeta(reason="test", triggered_by="t"))
    restored = store.restore(snap.snapshot_id)
    assert restored == dict(files)
    assert snap.byte_size == sum(len(b) for b in files.values())


def test_restore_unknown_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = FilesystemSnapshotStore(tmp_path)
    with pytest.raises(SnapshotMissing):
        store.restore(SnapshotId("does-not-exist"))


def test_manifest_file_is_written(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = FilesystemSnapshotStore(tmp_path)
    snap = store.capture(
        {"/x.json": b"{}"},
        SnapshotMeta(reason="r"),
    )
    manifest = tmp_path / snap.snapshot_id.value / "manifest.json"
    assert manifest.exists()
    assert "sha256" in manifest.read_text(encoding="utf-8")


def test_empty_files_mapping_produces_empty_snapshot(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = FilesystemSnapshotStore(tmp_path)
    snap = store.capture({}, SnapshotMeta(reason="empty"))
    assert snap.files == ()
    assert store.restore(snap.snapshot_id) == {}
