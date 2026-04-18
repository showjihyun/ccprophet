from __future__ import annotations

from collections.abc import Sequence

from ccprophet.domain.entities import BloatItem, BloatReport, ToolCall, ToolDef
from ccprophet.domain.values import BloatRatio, TokenCount


class BloatCalculator:
    @staticmethod
    def calculate(
        loaded: Sequence[ToolDef],
        called: Sequence[ToolCall],
    ) -> BloatReport:
        called_names = {tc.tool_name for tc in called}

        items: list[BloatItem] = []
        for td in loaded:
            items.append(
                BloatItem(
                    tool_name=td.tool_name,
                    source=td.source,
                    tokens=td.tokens,
                    used=td.tool_name in called_names,
                )
            )

        total = sum(i.tokens.value for i in items)
        bloat = sum(i.tokens.value for i in items if not i.used)
        ratio = bloat / total if total > 0 else 0.0
        used_sources = frozenset(i.source for i in items if i.used)

        return BloatReport(
            items=tuple(sorted(items, key=lambda i: i.tokens.value, reverse=True)),
            total_tokens=TokenCount(total),
            bloat_tokens=TokenCount(bloat),
            bloat_ratio=BloatRatio(ratio),
            used_sources=used_sources,
        )
