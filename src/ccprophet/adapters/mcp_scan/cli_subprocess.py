from __future__ import annotations

"""ClaudeCliMcpLister — shells out to `claude mcp list` and parses the output.

Parsing approach
----------------
Each non-blank, non-header line has the shape:

    <name>: <command-or-url> - <status>

The command-or-url can itself contain colons (URLs, Windows paths) so a naive
split(":") would break.  Strategy:

1. ``split(":", 1)``  → ``(raw_name, rest)``   (name never has a colon)
2. ``rsplit(" - ", 1)`` on ``rest`` → ``(raw_cmd, raw_status)``   (status is at
   the very end, preceded by " - "; the command may contain " - " only as a
   highly pathological edge case — if that happens we treat the whole thing as
   "unknown" rather than silently mangling it).

Name normalisation (for the match inside the CLI adapter) lives in the CLI
adapter; this module only returns raw strings.
"""

import subprocess
import sys
from collections.abc import Sequence

from ccprophet.domain.entities import McpServerInfo

# Map from observed status suffixes to canonical values.
_STATUS_MAP: dict[str, str] = {
    "\u2713 Connected": "connected",           # ✓ Connected
    "\u2717 Failed to connect": "failed",      # ✗ Failed to connect
    "! Needs authentication": "needs_auth",
}

_HEADER_PREFIX = "Checking"


def _parse_status(raw: str) -> str:
    stripped = raw.strip()
    return _STATUS_MAP.get(stripped, "unknown")


def _parse_line(line: str) -> McpServerInfo | None:
    """Return an McpServerInfo for a valid server line, or None to skip."""
    stripped = line.strip()
    if not stripped or stripped.startswith(_HEADER_PREFIX):
        return None

    # Names may themselves contain colons (e.g. "plugin:github:github").
    # The separator between name and command is always ": " (colon + space),
    # but the name portion never has a trailing space, so we look for the
    # pattern "non-space character followed by ': '" which unambiguously marks
    # the transition.  Specifically: find the first occurrence of ": " that is
    # followed by non-empty content (i.e. not the very end of the string).
    # This handles "plugin:github:github: https://..." correctly because the
    # split point is the ": " after "github" (the last segment).
    sep = ": "
    idx = stripped.find(sep)
    if idx < 0:
        return None
    raw_name = stripped[:idx].strip()
    rest = stripped[idx + len(sep):].strip()

    if not raw_name:
        return None

    # rsplit on " - " to get (command_or_url, status).
    # If there is no " - " separator the line is malformed — skip it.
    parts = rest.rsplit(" - ", 1)
    if len(parts) != 2:
        # Might be a line with no status (e.g. a section header we missed).
        return None
    raw_cmd, raw_status = parts
    raw_cmd = raw_cmd.strip()
    raw_status = raw_status.strip()

    return McpServerInfo(
        name=raw_name,
        command_or_url=raw_cmd,
        status=_parse_status(raw_status),
    )


class ClaudeCliMcpLister:
    """Adapter: queries the `claude` binary to discover loaded MCP servers.

    Returns an empty sequence and logs a warning to stderr when:
    - the ``claude`` binary is not found on PATH.
    - the command exits with a non-zero code.
    - the invocation raises ``PermissionError``.
    """

    def list_servers(self) -> Sequence[McpServerInfo]:
        # NOTE: subprocess(text=True) decodes via locale.getpreferredencoding()
        # which on Windows (cp949/cp1252) would crash on the Unicode ✓/✗ that
        # `claude mcp list` emits. Capture bytes + decode UTF-8 with replace.
        try:
            result = subprocess.run(
                _claude_cmd(),
                capture_output=True,
                timeout=5,
            )
        except FileNotFoundError:
            _warn("claude binary not found on PATH — mcp-scan unavailable")
            return ()
        except PermissionError as exc:
            _warn(f"permission denied running claude mcp list: {exc}")
            return ()
        except subprocess.TimeoutExpired:
            _warn("claude mcp list timed out after 5 s")
            return ()
        except OSError as exc:
            _warn(f"could not launch claude mcp list: {exc}")
            return ()

        stdout = (result.stdout or b"").decode("utf-8", errors="replace")
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")

        if result.returncode != 0:
            stderr_snippet = stderr.strip()[:200]
            _warn(
                f"claude mcp list exited with code {result.returncode}"
                + (f": {stderr_snippet}" if stderr_snippet else "")
            )
            return ()

        servers: list[McpServerInfo] = []
        for line in stdout.splitlines():
            info = _parse_line(line)
            if info is not None:
                servers.append(info)
        return tuple(servers)


def _claude_cmd() -> list[str]:
    """Resolve the `claude` binary across platforms.

    On Windows, Claude Code is typically installed as `claude.cmd` (batch
    wrapper). `subprocess.run` without `shell=True` does NOT auto-resolve
    `.cmd` extensions on Python < 3.12, so fall back explicitly.
    """
    import shutil
    import sys

    resolved = shutil.which("claude")
    if resolved:
        return [resolved, "mcp", "list"]
    if sys.platform == "win32":
        cmd_resolved = shutil.which("claude.cmd")
        if cmd_resolved:
            return [cmd_resolved, "mcp", "list"]
    return ["claude", "mcp", "list"]


def _warn(msg: str) -> None:
    print(f"[ccprophet mcp-scan] WARNING: {msg}", file=sys.stderr)
