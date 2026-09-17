"""Turn findings into a check conclusion, line annotations, and Markdown."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from .models import AnalysisResult, Finding, PullRequest

Conclusion = Literal["success", "neutral", "failure"]

COMMENT_MARKER = "<!-- greenwash:report -->"
MAX_ANNOTATIONS = 50
_ICONS = {"critical": "🔴", "warning": "🟡"}


def decide_conclusion(findings: Sequence[Finding], mode: str) -> Conclusion:
    flagged = [finding for finding in findings if finding.tier == "flagged"]
    if mode == "check" and any(finding.severity == "critical" for finding in flagged):
        return "failure"
    return "neutral" if flagged else "success"


def build_annotations(findings: Sequence[Finding]) -> list[dict]:
    """Line annotations for flagged findings, most severe first, capped at GitHub's limit."""
    annotations: list[dict] = []
    for finding in findings:
        if finding.tier != "flagged" or finding.line is None:
            continue
        annotations.append(
            {
                "path": finding.path,
                "start_line": finding.line,
                "end_line": finding.line,
                "annotation_level": "failure" if finding.severity == "critical" else "warning",
                "title": finding.title,
                "message": (
                    f"Greenwash: {finding.title.lower()} (probability {finding.probability:.0%}). "
                    "Please confirm this change is intentional."
                ),
            }
        )
        if len(annotations) == MAX_ANNOTATIONS:
            break
    return annotations


def headline(result: AnalysisResult) -> str:
    flagged = sum(1 for finding in result.findings if finding.tier == "flagged")
    if flagged == 0:
        return "No likely problems found"
    return f"{flagged} likely problem{'' if flagged == 1 else 's'} found"


def _location(pr: PullRequest, finding: Finding) -> str:
    if finding.line is None:
        return f"`{finding.path}`"
    url = f"https://github.com/{pr.owner}/{pr.repo}/blob/{pr.head_sha}/{finding.path}#L{finding.line}"
    return f"[`{finding.path}#L{finding.line}`]({url})"


def _table(pr: PullRequest, findings: Sequence[Finding]) -> str:
    rows = ["| | Check | Where | Probability |", "|---|---|---|---|"]
    rows += [
        f"| {_ICONS[f.severity]} | {f.title} | {_location(pr, f)} | {f.probability:.0%} |"
        for f in findings
    ]
    return "\n".join(rows)


def render_report(pr: PullRequest, result: AnalysisResult, config_error: str | None) -> str:
    flagged = [finding for finding in result.findings if finding.tier == "flagged"]
    possible = [finding for finding in result.findings if finding.tier == "possible"]
    stats = result.stats

    lines = [f"### 🧪 Greenwash: {headline(result)}", ""]
    if config_error:
        lines += [f"> ⚠️ Could not use `.github/greenwash.yml` ({config_error}). Using the default settings.", ""]
    checked = (
        f"Checked {stats.hunks_analyzed} changed hunk{'' if stats.hunks_analyzed == 1 else 's'} "
        f"in {stats.duration_ms / 1000:.1f}s"
    )
    if stats.hunks_skipped:
        checked += f" · {stats.hunks_skipped} more skipped (limit reached)"
    lines += [checked, ""]
    if flagged:
        lines += [_table(pr, flagged), ""]
    else:
        lines += ["✅ No signs of weakened tests, skipped checks, silenced errors, or placeholder code.", ""]
    if possible:
        lines += [
            f"<details><summary>Worth a second look ({len(possible)})</summary>",
            "",
            _table(pr, possible),
            "",
            "</details>",
            "",
        ]
    lines.append(
        "<sub>Greenwash asks narrow yes/no questions about every changed hunk. "
        "Scores are probabilities, not verdicts — a flagged change may be intentional.</sub>"
    )
    return "\n".join(lines)


def render_comment(pr: PullRequest, result: AnalysisResult, config_error: str | None) -> str:
    return f"{COMMENT_MARKER}\n{render_report(pr, result, config_error)}"
