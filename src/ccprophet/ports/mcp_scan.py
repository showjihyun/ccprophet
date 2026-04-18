from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ccprophet.domain.entities import McpServerInfo


class McpServerLister(Protocol):
    """Driven port: enumerate currently-loaded MCP servers."""

    def list_servers(self) -> Sequence[McpServerInfo]: ...
