"""Integration tests for `ccprophet ingest` CLI adapter."""
from __future__ import annotations

import json

from ccprophet.adapters.cli.ingest import discover_jsonl_files, run_ingest_command
from ccprophet.adapters.filewatch.jsonl_reader import JsonlReader
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.use_cases.backfill_from_jsonl import BackfillFromJsonlUseCase


def _wire() -> BackfillFromJsonlUseCase:
    repos = InMemoryRepositorySet()
    return BackfillFromJsonlUseCase(
        source=JsonlReader(),
        events=repos.events,
        sessions=repos.sessions,
        tool_calls=repos.tool_calls,
        subagents=repos.subagents,
    )


def test_ingest_empty_root_returns_success(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    uc = _wire()
    code = run_ingest_command(uc, paths=[], as_json=True)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["files_read"] == 0
    assert payload["events_ingested"] == 0
    assert payload["errors"] == []


def test_ingest_single_file_path(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    uc = _wire()
    # Minimal valid JSONL with one UserPromptSubmit event.
    f = tmp_path / "session.jsonl"
    f.write_text(
        '{"type":"user","message":{"role":"user","content":"hi"},'
        '"sessionId":"s-1","timestamp":"2026-04-18T12:00:00Z",'
        '"uuid":"abc123","cwd":"/tmp"}\n',
        encoding="utf-8",
    )

    code = run_ingest_command(uc, paths=[f], as_json=True)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["files_read"] == 1
    assert payload["records_seen"] >= 1


def test_discover_jsonl_files_handles_missing_root(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Absent root: must return empty list, not crash.
    assert discover_jsonl_files(tmp_path / "does_not_exist") == []


def test_discover_jsonl_files_finds_all(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "proj1").mkdir()
    (tmp_path / "proj1" / "a.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "proj2").mkdir()
    (tmp_path / "proj2" / "b.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "not_jsonl.txt").write_text("", encoding="utf-8")

    found = discover_jsonl_files(tmp_path)
    names = sorted(p.name for p in found)
    assert names == ["a.jsonl", "b.jsonl"]


def test_ingest_rich_path(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    uc = _wire()
    code = run_ingest_command(uc, paths=[], as_json=False)
    assert code == 0
