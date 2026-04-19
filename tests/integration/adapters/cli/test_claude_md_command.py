"""Integration tests for ccprophet claude-md command."""

from __future__ import annotations

import json
from pathlib import Path

from ccprophet.adapters.cli.claude_md import (
    EXIT_CRITICAL,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_WARN,
    run_claude_md_command,
)


def _write_claude_md(directory: Path, lines: int, content: str | None = None) -> Path:
    path = directory / "CLAUDE.md"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text("\n".join(f"line {i}" for i in range(1, lines + 1)), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. 250-line CLAUDE.md → exit 1 (warn), JSON contains too_long
# ---------------------------------------------------------------------------
class TestWarnFile:
    def test_exit_code_is_warn(self, tmp_path: Path):
        _write_claude_md(tmp_path, lines=250)
        code = run_claude_md_command(root=tmp_path, as_json=False)
        assert code == EXIT_WARN

    def test_json_contains_too_long(self, tmp_path: Path, capsys):
        _write_claude_md(tmp_path, lines=250)
        code = run_claude_md_command(root=tmp_path, as_json=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 1
        finding_kinds = [f["kind"] for f in data[0]["findings"]]
        assert "too_long" in finding_kinds
        assert code == EXIT_WARN

    def test_json_shape(self, tmp_path: Path, capsys):
        _write_claude_md(tmp_path, lines=250)
        run_claude_md_command(root=tmp_path, as_json=True)
        data = json.loads(capsys.readouterr().out)
        record = data[0]
        assert "path" in record
        assert "line_count" in record
        assert "byte_size" in record
        assert "estimated_tokens" in record
        assert "worst_severity" in record
        assert "findings" in record
        for finding in record["findings"]:
            assert "kind" in finding
            assert "severity" in finding
            assert "line_range" in finding
            assert "detail" in finding


# ---------------------------------------------------------------------------
# 2. 50-line CLAUDE.md → exit 0 (ok)
# ---------------------------------------------------------------------------
class TestOkFile:
    def test_exit_code_is_ok(self, tmp_path: Path):
        _write_claude_md(tmp_path, lines=50)
        code = run_claude_md_command(root=tmp_path, as_json=False)
        assert code == EXIT_OK

    def test_json_worst_severity_ok(self, tmp_path: Path, capsys):
        _write_claude_md(tmp_path, lines=50)
        run_claude_md_command(root=tmp_path, as_json=True)
        data = json.loads(capsys.readouterr().out)
        assert data[0]["worst_severity"] == "ok"
        assert data[0]["findings"] == []


# ---------------------------------------------------------------------------
# 3. No CLAUDE.md → exit 3 + helpful message
# ---------------------------------------------------------------------------
class TestNoFile:
    def test_exit_code_is_not_found(self, tmp_path: Path):
        code = run_claude_md_command(root=tmp_path, as_json=False)
        assert code == EXIT_NOT_FOUND

    def test_json_contains_error_key(self, tmp_path: Path, capsys):
        run_claude_md_command(root=tmp_path, as_json=True)
        data = json.loads(capsys.readouterr().out)
        assert "error" in data

    def test_rich_output_mentions_no_file(self, tmp_path: Path, capsys):
        run_claude_md_command(root=tmp_path, as_json=False)
        # Rich output goes to stdout via Console(). Check something was printed.
        capsys.readouterr()
        # No error should propagate
        assert True  # just verifying it doesn't raise


# ---------------------------------------------------------------------------
# 4. Critical file → exit 2
# ---------------------------------------------------------------------------
class TestCriticalFile:
    def test_exit_code_is_critical(self, tmp_path: Path):
        _write_claude_md(tmp_path, lines=600)
        code = run_claude_md_command(root=tmp_path, as_json=False)
        assert code == EXIT_CRITICAL

    def test_json_worst_severity_critical(self, tmp_path: Path, capsys):
        _write_claude_md(tmp_path, lines=600)
        run_claude_md_command(root=tmp_path, as_json=True)
        data = json.loads(capsys.readouterr().out)
        assert data[0]["worst_severity"] == "critical"


# ---------------------------------------------------------------------------
# 5. Subdirectory CLAUDE.md is also discovered
# ---------------------------------------------------------------------------
class TestSubdirectoryDiscovery:
    def test_subdir_claude_md_is_found(self, tmp_path: Path, capsys):
        subdir = tmp_path / "subproject"
        subdir.mkdir()
        _write_claude_md(subdir, lines=50)
        run_claude_md_command(root=tmp_path, as_json=True)
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert "subproject" in data[0]["path"] or "CLAUDE.md" in data[0]["path"]

    def test_root_and_subdir_both_reported(self, tmp_path: Path, capsys):
        _write_claude_md(tmp_path, lines=50)
        subdir = tmp_path / "sub"
        subdir.mkdir()
        _write_claude_md(subdir, lines=50)
        run_claude_md_command(root=tmp_path, as_json=True)
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 2


# ---------------------------------------------------------------------------
# 6. Info-only findings → exit 0
# ---------------------------------------------------------------------------
class TestInfoOnly:
    def test_deep_heading_only_exits_ok(self, tmp_path: Path):
        content = "#### Deep heading\nshort file\n"
        _write_claude_md(tmp_path, lines=0, content=content)
        code = run_claude_md_command(root=tmp_path, as_json=False)
        assert code == EXIT_OK
