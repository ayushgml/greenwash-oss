"""Plain data types shared by every Greenwash module."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

FileKind = Literal["test", "snapshot", "ci", "lint_config", "source", "other"]
Severity = Literal["critical", "warning"]
Tier = Literal["flagged", "possible"]


@dataclass(frozen=True)
class PullRequest:
    owner: str
    repo: str
    number: int
    title: str
    body: str
    head_sha: str
    base_sha: str
    installation_id: int


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str  # added | removed | modified | renamed | copied | changed | unchanged
    patch: str | None


@dataclass(frozen=True)
class Hunk:
    path: str
    file_kind: FileKind
    header: str
    diff: str
    new_start: int
    added_lines: tuple[int, ...]
    truncated: bool

    @property
    def anchor_line(self) -> int:
        """The new-file line an annotation should point at."""
        if self.added_lines:
            return self.added_lines[0]
        return max(self.new_start, 1)


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    severity: Severity
    applies_to: frozenset[FileKind]
    instructions: str
    criteria: tuple[str, str] | None  # (what "yes" means, what "no" means)
    threshold: float


@dataclass(frozen=True)
class Finding:
    check_id: str
    title: str
    severity: Severity
    tier: Tier
    path: str
    line: int | None
    probability: float


@dataclass(frozen=True)
class AnalysisStats:
    hunks_analyzed: int = 0
    hunks_skipped: int = 0
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    models: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnalysisResult:
    findings: tuple[Finding, ...]
    stats: AnalysisStats = field(default_factory=AnalysisStats)

    def with_findings(self, extra: list[Finding] | tuple[Finding, ...]) -> AnalysisResult:
        return replace(self, findings=sort_findings([*self.findings, *extra]))


_TIER_RANK = {"flagged": 0, "possible": 1}
_SEVERITY_RANK = {"critical": 0, "warning": 1}


def sort_findings(findings: list[Finding] | tuple[Finding, ...]) -> tuple[Finding, ...]:
    """Flagged before possible, critical before warning, most likely first."""
    return tuple(
        sorted(
            findings,
            key=lambda f: (
                _TIER_RANK[f.tier],
                _SEVERITY_RANK[f.severity],
                -f.probability,
                f.path,
                f.line or 0,
                f.check_id,
            ),
        )
    )
