"""Domain service: audit CLAUDE.md files for context rot.

Pure stdlib — no third-party imports.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Severity rank for comparison
_RANK: dict[str, int] = {"ok": 0, "info": 1, "warn": 2, "critical": 3}

# Thresholds
_TOTAL_WARN = 200
_TOTAL_CRITICAL = 400
_TOTAL_CRITICAL_UPGRADE = 500  # upgrade to critical at this line count
_SECTION_WARN = 100
_SECTION_CRITICAL = 200
_CODE_BLOCK_INFO = 50


@dataclass(frozen=True, slots=True)
class ClaudeMdFinding:
    kind: str      # 'too_long' | 'section_too_long' | 'deep_heading' | 'big_code_block'
    severity: str  # 'info' | 'warn' | 'critical'
    line_range: tuple[int, int]  # (start, end) — 1-indexed inclusive
    detail: str


@dataclass(frozen=True, slots=True)
class ClaudeMdReport:
    path: str
    line_count: int
    byte_size: int
    estimated_tokens: int  # rough: bytes / 4
    findings: tuple[ClaudeMdFinding, ...]

    @property
    def worst_severity(self) -> str:
        """Return highest severity across findings, or 'ok' when there are none."""
        best = "ok"
        for f in self.findings:
            if _RANK[f.severity] > _RANK[best]:
                best = f.severity
        return best


class ClaudeMdAuditor:
    """Stateless auditor — all logic in audit()."""

    @staticmethod
    def audit(path: str, content: str) -> ClaudeMdReport:
        lines = content.splitlines()
        line_count = len(lines)
        byte_size = len(content.encode("utf-8"))
        estimated_tokens = max(1, byte_size // 4) if byte_size > 0 else 0

        findings: list[ClaudeMdFinding] = []

        # --- 1. Total length ---
        if line_count > _TOTAL_WARN:
            if line_count > _TOTAL_CRITICAL_UPGRADE:
                sev = "critical"
            elif line_count > _TOTAL_CRITICAL:
                sev = "critical"
            else:
                sev = "warn"
            findings.append(ClaudeMdFinding(
                kind="too_long",
                severity=sev,
                line_range=(1, line_count),
                detail=(
                    f"{line_count} lines exceeds the recommended 200-line limit. "
                    "Modularize via @docs/<file>.md imports."
                ),
            ))

        # --- 2. Section spans and deep headings ---
        findings.extend(_check_headings(lines))

        # --- 3. Code blocks ---
        findings.extend(_check_code_blocks(lines))

        return ClaudeMdReport(
            path=path,
            line_count=line_count,
            byte_size=byte_size,
            estimated_tokens=estimated_tokens,
            findings=tuple(findings),
        )


# ── private helpers ───────────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s")
_FENCE_RE = re.compile(r"^```")


def _heading_depth(line: str) -> int | None:
    """Return heading depth (1-6) or None if not a heading."""
    m = _HEADING_RE.match(line)
    return len(m.group(1)) if m else None


def _check_headings(lines: list[str]) -> list[ClaudeMdFinding]:
    findings: list[ClaudeMdFinding] = []
    # Collect all headings: (1-indexed line_no, depth)
    headings: list[tuple[int, int]] = []
    for i, line in enumerate(lines, start=1):
        depth = _heading_depth(line)
        if depth is not None:
            headings.append((i, depth))
            # Deep heading check (#### or deeper)
            if depth >= 4:
                findings.append(ClaudeMdFinding(
                    kind="deep_heading",
                    severity="info",
                    line_range=(i, i),
                    detail=(
                        f"Heading depth {depth} at line {i}. "
                        "Deep headings suggest sub-sections that could be extracted to docs/."
                    ),
                ))

    # Section span check for ## and ### headings
    for idx, (start_line, depth) in enumerate(headings):
        if depth not in (2, 3):
            continue
        # Find end: the line before the next heading of same or higher level
        end_line = len(lines)
        for later_line, later_depth in headings[idx + 1:]:
            if later_depth <= depth:
                end_line = later_line - 1
                break
        span = end_line - start_line + 1
        if span > _SECTION_WARN:
            sev = "critical" if span > _SECTION_CRITICAL else "warn"
            findings.append(ClaudeMdFinding(
                kind="section_too_long",
                severity=sev,
                line_range=(start_line, end_line),
                detail=(
                    f"Section at line {start_line} spans {span} lines "
                    f"(threshold: warn>{_SECTION_WARN}, critical>{_SECTION_CRITICAL}). "
                    "Consider splitting into separate docs/ files."
                ),
            ))

    return findings


def _check_code_blocks(lines: list[str]) -> list[ClaudeMdFinding]:
    findings: list[ClaudeMdFinding] = []
    in_block = False
    block_start = 0

    for i, line in enumerate(lines, start=1):
        if _FENCE_RE.match(line.rstrip()):
            if not in_block:
                in_block = True
                block_start = i
            else:
                # closing fence
                block_len = i - block_start - 1  # lines of content inside fences
                if block_len > _CODE_BLOCK_INFO:
                    findings.append(ClaudeMdFinding(
                        kind="big_code_block",
                        severity="info",
                        line_range=(block_start, i),
                        detail=(
                            f"Code block at lines {block_start}–{i} is {block_len} lines. "
                            "Consider linking to the file instead of inlining."
                        ),
                    ))
                in_block = False

    return findings
