"""JSON shaper for :class:`PatternDiffReport` (PRD F9 / FR-9.3).

Kept tiny on purpose — the domain service carries all of the logic; this
module just renders the structured findings as a serialisable dict for the
Web adapter.
"""

from __future__ import annotations

from typing import Any

from ccprophet.domain.services.pattern_diff import PatternDiffReport


def build_pattern_diff(report: PatternDiffReport) -> dict[str, Any]:
    return {
        "session_a": report.session_a_id.value,
        "session_b": report.session_b_id.value,
        "headline": report.headline,
        "findings": [
            {"kind": f.kind, "severity": f.severity, "detail": f.detail} for f in report.findings
        ],
    }
