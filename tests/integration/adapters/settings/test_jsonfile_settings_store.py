from __future__ import annotations

import json

import pytest

from ccprophet.adapters.settings.jsonfile import JsonFileSettingsStore
from ccprophet.domain.errors import SnapshotConflict


def _write(path, content: dict) -> None:  # type: ignore[no-untyped-def]
    path.write_text(
        json.dumps(content, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_read_returns_parsed_content_and_hash(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "settings.json"
    _write(p, {"hello": "world"})
    store = JsonFileSettingsStore()
    doc = store.read(p)
    assert doc.content == {"hello": "world"}
    assert len(doc.sha256) == 64


def test_write_atomic_persists_and_returns_new_hash(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "settings.json"
    _write(p, {"a": 1})
    store = JsonFileSettingsStore()
    original = store.read(p)

    new_doc = store.write_atomic(
        p, {"a": 2, "b": [1, 2]}, expected_hash=original.sha256
    )
    reloaded = store.read(p)
    assert reloaded.content == {"a": 2, "b": [1, 2]}
    assert reloaded.sha256 == new_doc.sha256
    assert new_doc.sha256 != original.sha256


def test_write_atomic_rejects_concurrent_edit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "settings.json"
    _write(p, {"a": 1})
    store = JsonFileSettingsStore()
    stale = store.read(p)

    _write(p, {"a": 999})

    with pytest.raises(SnapshotConflict):
        store.write_atomic(p, {"a": 2}, expected_hash=stale.sha256)

    untouched = store.read(p)
    assert untouched.content == {"a": 999}


def test_write_atomic_without_expected_hash_overwrites(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "settings.json"
    _write(p, {"old": True})
    store = JsonFileSettingsStore()
    store.write_atomic(p, {"new": True})
    assert store.read(p).content == {"new": True}


def test_write_leaves_no_tmp_file_after_success(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "settings.json"
    _write(p, {"k": 1})
    store = JsonFileSettingsStore()
    store.write_atomic(p, {"k": 2})
    leftovers = [f for f in tmp_path.iterdir() if f.name.endswith(".tmp")]
    assert leftovers == []
