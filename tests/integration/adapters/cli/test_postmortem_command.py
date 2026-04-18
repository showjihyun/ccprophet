"""Integration tests for `ccprophet postmortem` CLI adapter.

Covers happy path, SessionNotFound, JSON shape, rationale surface (FR-11.3),
and `--md` Markdown export (FR-11.5).
"""
from __future__ import annotations

import json

from ccprophet.adapters.cli.postmortem import run_postmortem_command
from ccprophet.adapters.persistence.inmemory.repositories import InMemoryRepositorySet
from ccprophet.use_cases.analyze_postmortem import AnalyzePostmortemUseCase
from tests.fixtures.builders import SessionBuilder


def _wire() -> tuple[InMemoryRepositorySet, AnalyzePostmortemUseCase]:
    repos = InMemoryRepositorySet()
    uc = AnalyzePostmortemUseCase(
        sessions=repos.sessions,
        outcomes=repos.outcomes,
        tool_calls=repos.tool_calls,
        tool_defs=repos.tool_defs,
    )
    return repos, uc


def test_unknown_session_exits_2(capsys) -> None:  # type: ignore[no-untyped-def]
    _, uc = _wire()
    code = run_postmortem_command(uc, session_id="nope", as_json=True)
    assert code == 2
    assert "error" in json.loads(capsys.readouterr().out)


def test_json_shape_includes_rationale(capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc = _wire()
    # Seed a failed session with no label so the analyzer produces a
    # degenerate (no-baseline) report — rationale must still be present.
    session = SessionBuilder().with_id("s-fail").build()
    repos.sessions.upsert(session)

    code = run_postmortem_command(uc, session_id="s-fail", as_json=True)
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["failed_session_id"] == "s-fail"
    assert "rationale" in payload  # FR-11.3 / AP-8
    # rationale is always populated by _rationale() — even for 0-sample case.
    assert isinstance(payload["rationale"], str)
    assert payload["rationale"]  # non-empty


def test_md_export_writes_file(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc = _wire()
    repos.sessions.upsert(SessionBuilder().with_id("s-md").build())
    md_path = tmp_path / "report.md"

    code = run_postmortem_command(
        uc, session_id="s-md", as_json=False, output_markdown=md_path
    )
    assert code == 0
    assert md_path.exists()
    body = md_path.read_text(encoding="utf-8")
    assert body.startswith("# Postmortem")
    assert "## Findings" in body
    assert "## Suggestions" in body


def test_md_export_with_json_also_writes(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    repos, uc = _wire()
    repos.sessions.upsert(SessionBuilder().with_id("s-both").build())
    md_path = tmp_path / "both.md"

    code = run_postmortem_command(
        uc, session_id="s-both", as_json=True, output_markdown=md_path
    )
    assert code == 0
    # JSON still goes to stdout.
    assert json.loads(capsys.readouterr().out)["failed_session_id"] == "s-both"
    # And the MD file exists too.
    assert md_path.exists()
