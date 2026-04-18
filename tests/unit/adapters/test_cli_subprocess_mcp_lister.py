from __future__ import annotations

"""Unit tests for ClaudeCliMcpLister — subprocess.run is always monkeypatched."""

import subprocess
import types

import pytest

from ccprophet.adapters.mcp_scan.cli_subprocess import ClaudeCliMcpLister


def _make_result(stdout: str, returncode: int = 0, stderr: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


_SAMPLE_OUTPUT = """\
Checking MCP server health\u2026

claude.ai Google Calendar: https://gcal.mcp.claude.com/mcp - ! Needs authentication
plugin:playwright:playwright: npx @playwright/mcp@latest - \u2713 Connected
pencil: C:\\path\\to\\pencil.exe --app desktop - \u2713 Connected
plugin:github:github: https://api.githubcopilot.com/mcp/ - \u2717 Failed to connect
"""


class TestClaudeCliMcpLister:
    def test_parses_mixed_statuses(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run", lambda *a, **kw: _make_result(_SAMPLE_OUTPUT)
        )
        servers = ClaudeCliMcpLister().list_servers()
        assert len(servers) == 4

        by_name = {s.name: s for s in servers}
        assert by_name["claude.ai Google Calendar"].status == "needs_auth"
        assert by_name["plugin:playwright:playwright"].status == "connected"
        assert by_name["pencil"].status == "connected"
        assert by_name["plugin:github:github"].status == "failed"

    def test_parses_command_with_colon_in_url(self, monkeypatch):
        stdout = "myserver: https://example.com:8080/path - \u2713 Connected\n"
        monkeypatch.setattr(
            subprocess, "run", lambda *a, **kw: _make_result(stdout)
        )
        servers = ClaudeCliMcpLister().list_servers()
        assert len(servers) == 1
        assert servers[0].command_or_url == "https://example.com:8080/path"
        assert servers[0].status == "connected"

    def test_empty_stdout_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run", lambda *a, **kw: _make_result("")
        )
        servers = ClaudeCliMcpLister().list_servers()
        assert list(servers) == []

    def test_non_zero_exit_returns_empty_no_crash(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: _make_result("", returncode=1, stderr="err"),
        )
        servers = ClaudeCliMcpLister().list_servers()
        assert list(servers) == []

    def test_file_not_found_returns_empty(self, monkeypatch):
        def _raise(*a, **kw):
            raise FileNotFoundError("claude: not found")

        monkeypatch.setattr(subprocess, "run", _raise)
        servers = ClaudeCliMcpLister().list_servers()
        assert list(servers) == []

    def test_permission_error_returns_empty(self, monkeypatch):
        def _raise(*a, **kw):
            raise PermissionError("permission denied")

        monkeypatch.setattr(subprocess, "run", _raise)
        servers = ClaudeCliMcpLister().list_servers()
        assert list(servers) == []

    def test_timeout_returns_empty(self, monkeypatch):
        def _raise(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="claude", timeout=5)

        monkeypatch.setattr(subprocess, "run", _raise)
        servers = ClaudeCliMcpLister().list_servers()
        assert list(servers) == []

    def test_only_header_line_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: _make_result("Checking MCP server health\u2026\n"),
        )
        servers = ClaudeCliMcpLister().list_servers()
        assert list(servers) == []

    def test_unknown_status_maps_to_unknown(self, monkeypatch):
        stdout = "myserver: cmd arg - ? Weird status\n"
        monkeypatch.setattr(
            subprocess, "run", lambda *a, **kw: _make_result(stdout)
        )
        servers = ClaudeCliMcpLister().list_servers()
        assert len(servers) == 1
        assert servers[0].status == "unknown"
