from __future__ import annotations

from ccprophet.domain.entities import SettingsDoc
from ccprophet.domain.services.settings_patch import (
    KEY_DISABLED_MCPS,
    KEY_DISABLED_TOOLS,
    SettingsPatchPlanner,
)
from ccprophet.domain.values import RecommendationKind
from tests.fixtures.builders import RecommendationBuilder


def _doc(content: dict | None = None) -> SettingsDoc:
    return SettingsDoc(
        path="/fake/settings.json",
        content=dict(content or {}),
        sha256="0" * 64,
    )


def test_empty_recommendations_no_changes() -> None:
    plan = SettingsPatchPlanner.plan(_doc({"a": 1}), [])
    assert plan.new_content == {"a": 1}
    assert plan.has_changes is False
    assert plan.applied_rec_ids == ()


def test_prune_mcp_adds_server_to_disabled_list() -> None:
    rec = (
        RecommendationBuilder()
        .kind(RecommendationKind.PRUNE_MCP)
        .target("mcp__github_x__create_issue")
        .build()
    )
    plan = SettingsPatchPlanner.plan(_doc(), [rec])
    assert plan.added_mcps == ("github_x",)
    assert plan.new_content[KEY_DISABLED_MCPS] == ["github_x"]
    assert plan.has_changes is True
    assert plan.applied_rec_ids == (rec.rec_id,)


def test_prune_tool_adds_name_to_disabled_tools() -> None:
    rec = RecommendationBuilder().kind(RecommendationKind.PRUNE_TOOL).target("WebFetch").build()
    plan = SettingsPatchPlanner.plan(_doc(), [rec])
    assert plan.added_tools == ("WebFetch",)
    assert plan.new_content[KEY_DISABLED_TOOLS] == ["WebFetch"]


def test_already_disabled_is_idempotent() -> None:
    rec = RecommendationBuilder().kind(RecommendationKind.PRUNE_MCP).target("mcp__already").build()
    plan = SettingsPatchPlanner.plan(_doc({KEY_DISABLED_MCPS: ["already"]}), [rec])
    assert plan.added_mcps == ()
    assert plan.has_changes is False


def test_preserves_unrelated_keys() -> None:
    rec = RecommendationBuilder().kind(RecommendationKind.PRUNE_TOOL).target("Noisy").build()
    plan = SettingsPatchPlanner.plan(
        _doc({"mcpServers": {"a": {"command": "x"}}, "theme": "dark"}),
        [rec],
    )
    assert plan.new_content["mcpServers"] == {"a": {"command": "x"}}
    assert plan.new_content["theme"] == "dark"
    assert plan.new_content[KEY_DISABLED_TOOLS] == ["Noisy"]


def test_mixed_kinds_batched() -> None:
    recs = [
        RecommendationBuilder().kind(RecommendationKind.PRUNE_MCP).target("mcp__a__x").build(),
        RecommendationBuilder().kind(RecommendationKind.PRUNE_TOOL).target("Bash").build(),
    ]
    plan = SettingsPatchPlanner.plan(_doc(), recs)
    assert plan.added_mcps == ("a",)
    assert plan.added_tools == ("Bash",)
    assert len(plan.applied_rec_ids) == 2


def test_ignores_other_recommendation_kinds() -> None:
    rec = (
        RecommendationBuilder()
        .kind(RecommendationKind.RUN_CLEAR)
        .target(None)  # type: ignore[arg-type]
        .build()
    )
    plan = SettingsPatchPlanner.plan(_doc(), [rec])
    assert plan.has_changes is False
    assert plan.applied_rec_ids == ()


def test_original_doc_is_not_mutated() -> None:
    doc = _doc({KEY_DISABLED_TOOLS: ["existing"]})
    rec = RecommendationBuilder().kind(RecommendationKind.PRUNE_TOOL).target("new").build()
    plan = SettingsPatchPlanner.plan(doc, [rec])
    assert doc.content[KEY_DISABLED_TOOLS] == ["existing"]
    assert plan.new_content[KEY_DISABLED_TOOLS] == ["existing", "new"]
