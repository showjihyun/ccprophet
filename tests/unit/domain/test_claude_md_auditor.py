"""Unit tests for ClaudeMdAuditor domain service."""
from __future__ import annotations

import pytest

from ccprophet.domain.services.claude_md_audit import ClaudeMdAuditor, ClaudeMdFinding


def _make_lines(n: int, prefix: str = "line ") -> str:
    return "\n".join(f"{prefix}{i}" for i in range(1, n + 1))


def _make_section(heading: str, body_lines: int) -> str:
    """Return a markdown string: heading + body_lines of text."""
    body = "\n".join(f"body line {i}" for i in range(1, body_lines + 1))
    return f"{heading}\n{body}"


# ---------------------------------------------------------------------------
# 1. Short file — no findings, ok
# ---------------------------------------------------------------------------
class TestShortFile:
    def test_100_lines_no_findings(self):
        content = _make_lines(100)
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        assert report.findings == ()
        assert report.worst_severity == "ok"

    def test_empty_file_no_findings(self):
        report = ClaudeMdAuditor.audit("CLAUDE.md", "")
        assert report.findings == ()
        assert report.worst_severity == "ok"
        assert report.line_count == 0

    def test_exactly_200_lines_no_findings(self):
        content = _make_lines(200)
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        assert not any(f.kind == "too_long" for f in report.findings)


# ---------------------------------------------------------------------------
# 2. 250-line file → too_long warn
# ---------------------------------------------------------------------------
class TestTooLongWarn:
    def test_250_lines_is_warn(self):
        content = _make_lines(250)
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        assert report.line_count == 250
        too_long = [f for f in report.findings if f.kind == "too_long"]
        assert len(too_long) == 1
        assert too_long[0].severity == "warn"
        assert too_long[0].line_range == (1, 250)

    def test_worst_severity_is_warn(self):
        content = _make_lines(250)
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        assert report.worst_severity == "warn"


# ---------------------------------------------------------------------------
# 3. 600-line file → too_long critical
# ---------------------------------------------------------------------------
class TestTooLongCritical:
    def test_600_lines_is_critical(self):
        content = _make_lines(600)
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        too_long = [f for f in report.findings if f.kind == "too_long"]
        assert len(too_long) == 1
        assert too_long[0].severity == "critical"

    def test_worst_severity_is_critical(self):
        content = _make_lines(600)
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        assert report.worst_severity == "critical"


# ---------------------------------------------------------------------------
# 4. Single ## section spanning 150 lines → section_too_long warn
# ---------------------------------------------------------------------------
class TestSectionTooLongWarn:
    def test_150_line_section_is_warn(self):
        # Heading at line 1, 149 body lines → span = 150
        content = _make_section("## Big Section", 149)
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        section_findings = [f for f in report.findings if f.kind == "section_too_long"]
        assert len(section_findings) == 1
        assert section_findings[0].severity == "warn"

    def test_section_range_starts_at_heading_line(self):
        preamble = _make_lines(5)
        section = _make_section("## Big Section", 149)
        content = preamble + "\n" + section
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        section_findings = [f for f in report.findings if f.kind == "section_too_long"]
        assert len(section_findings) == 1
        # Heading is at line 6 (5 preamble + 1 heading)
        assert section_findings[0].line_range[0] == 6


# ---------------------------------------------------------------------------
# 5. #### deep heading → deep_heading info
# ---------------------------------------------------------------------------
class TestDeepHeading:
    def test_h4_triggers_deep_heading_info(self):
        content = "# Top\n## Mid\n### Sub\n#### Deep\nsome content\n"
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        deep = [f for f in report.findings if f.kind == "deep_heading"]
        assert len(deep) == 1
        assert deep[0].severity == "info"

    def test_h5_also_triggers_deep_heading(self):
        content = "##### Very Deep\ncontent\n"
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        deep = [f for f in report.findings if f.kind == "deep_heading"]
        assert len(deep) == 1

    def test_h3_does_not_trigger_deep_heading(self):
        content = "### Normal Depth\ncontent\n"
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        deep = [f for f in report.findings if f.kind == "deep_heading"]
        assert deep == []


# ---------------------------------------------------------------------------
# 6. 80-line code block → big_code_block info
# ---------------------------------------------------------------------------
class TestBigCodeBlock:
    def test_80_line_code_block_is_info(self):
        fence_open = "```python\n"
        fence_close = "\n```\n"
        block_body = "\n".join(f"code line {i}" for i in range(1, 81))
        content = fence_open + block_body + fence_close
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        big_blocks = [f for f in report.findings if f.kind == "big_code_block"]
        assert len(big_blocks) == 1
        assert big_blocks[0].severity == "info"
        assert "Consider linking" in big_blocks[0].detail

    def test_50_line_code_block_no_finding(self):
        fence_open = "```\n"
        fence_close = "\n```\n"
        block_body = "\n".join(f"code line {i}" for i in range(1, 51))
        content = fence_open + block_body + fence_close
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        big_blocks = [f for f in report.findings if f.kind == "big_code_block"]
        assert big_blocks == []


# ---------------------------------------------------------------------------
# 7. Multiple findings on the same file — all emitted
# ---------------------------------------------------------------------------
class TestMultipleFindings:
    def test_deep_heading_and_big_code_block_both_emitted(self):
        deep_heading = "#### Very Deep\n"
        fence_open = "```python\n"
        block_body = "\n".join(f"code {i}" for i in range(1, 82))
        fence_close = "\n```\n"
        content = deep_heading + fence_open + block_body + fence_close
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        kinds = {f.kind for f in report.findings}
        assert "deep_heading" in kinds
        assert "big_code_block" in kinds

    def test_too_long_and_section_findings_coexist(self):
        # 250-line file with a big section in the middle
        lines = ["filler line"] * 10
        lines.append("## Big Section")
        lines += ["section line"] * 149
        lines += ["filler after"] * 91  # total = 10 + 1 + 149 + 91 = 251
        content = "\n".join(lines)
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        kinds = {f.kind for f in report.findings}
        assert "too_long" in kinds
        assert "section_too_long" in kinds


# ---------------------------------------------------------------------------
# 8. worst_severity returns highest rank
# ---------------------------------------------------------------------------
class TestWorstSeverity:
    def test_only_info_returns_info(self):
        content = "#### Deep\ncontent\n"
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        assert report.worst_severity == "info"

    def test_warn_beats_info(self):
        # 250-line file with a deep heading
        content = "#### Deep\n" + _make_lines(249)
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        assert report.worst_severity == "warn"

    def test_critical_beats_warn(self):
        content = _make_lines(600)
        report = ClaudeMdAuditor.audit("CLAUDE.md", content)
        assert report.worst_severity == "critical"

    def test_no_findings_returns_ok(self):
        report = ClaudeMdAuditor.audit("CLAUDE.md", "# Hello\nshort file\n")
        assert report.worst_severity == "ok"


# ---------------------------------------------------------------------------
# 9. Metadata fields
# ---------------------------------------------------------------------------
class TestMetadata:
    def test_line_count_accurate(self):
        content = "a\nb\nc"
        report = ClaudeMdAuditor.audit("x.md", content)
        assert report.line_count == 3

    def test_byte_size_and_token_estimate(self):
        content = "hello"
        report = ClaudeMdAuditor.audit("x.md", content)
        assert report.byte_size == len(content.encode("utf-8"))
        assert report.estimated_tokens == max(1, report.byte_size // 4)

    def test_path_stored_as_given(self):
        report = ClaudeMdAuditor.audit("custom/path/CLAUDE.md", "hi")
        assert report.path == "custom/path/CLAUDE.md"
