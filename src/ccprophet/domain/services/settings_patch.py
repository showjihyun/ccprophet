"""Pure planner: settings.json content + Recommendations → new content.

No IO. The SettingsStore adapter performs the actual write using the plan's
`new_content`. Handles two kinds for the MVP:
- `prune_mcp` → adds MCP server names to `disabledMcpjsonServers`
- `prune_tool` → adds tool names to `disabledTools`
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass

from ccprophet.domain.entities import Recommendation, SettingsDoc
from ccprophet.domain.values import RecommendationKind

KEY_DISABLED_MCPS = "disabledMcpjsonServers"
KEY_DISABLED_TOOLS = "disabledTools"


@dataclass(frozen=True, slots=True)
class SettingsPatchPlan:
    original: SettingsDoc
    new_content: dict[str, object]
    applied_rec_ids: tuple[str, ...]
    added_mcps: tuple[str, ...]
    added_tools: tuple[str, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.applied_rec_ids) and self.new_content != self.original.content


class SettingsPatchPlanner:
    @staticmethod
    def plan(doc: SettingsDoc, recommendations: Sequence[Recommendation]) -> SettingsPatchPlan:
        new_content = deepcopy(doc.content)
        applied: list[str] = []
        added_mcps: list[str] = []
        added_tools: list[str] = []

        disabled_mcps = _as_str_list(new_content.get(KEY_DISABLED_MCPS))
        disabled_tools = _as_str_list(new_content.get(KEY_DISABLED_TOOLS))

        for rec in recommendations:
            if rec.kind == RecommendationKind.PRUNE_MCP:
                server = _mcp_server_from_target(rec.target)
                if server is None or server in disabled_mcps:
                    continue
                disabled_mcps.append(server)
                added_mcps.append(server)
                applied.append(rec.rec_id)
            elif rec.kind == RecommendationKind.PRUNE_TOOL:
                tool = rec.target
                if not tool or tool in disabled_tools:
                    continue
                disabled_tools.append(tool)
                added_tools.append(tool)
                applied.append(rec.rec_id)
            # other kinds are out-of-scope for settings.json patching

        if added_mcps:
            new_content[KEY_DISABLED_MCPS] = disabled_mcps
        if added_tools:
            new_content[KEY_DISABLED_TOOLS] = disabled_tools

        return SettingsPatchPlan(
            original=doc,
            new_content=new_content,
            applied_rec_ids=tuple(applied),
            added_mcps=tuple(added_mcps),
            added_tools=tuple(added_tools),
        )


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value if isinstance(x, str)]
    return []


def _mcp_server_from_target(target: str | None) -> str | None:
    """mcp__<server>__<rest> → <server>. Also accepts bare server names.

    Claude Code tool names follow `mcp__<server>__<tool>`. A Recommendation with
    `target="mcp__github_x__create_issue"` maps to server `github_x`.
    """
    if not target:
        return None
    if target.startswith("mcp__"):
        rest = target[len("mcp__") :]
        idx = rest.find("__")
        return rest[:idx] if idx >= 0 else rest
    return target
