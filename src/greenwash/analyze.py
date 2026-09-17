"""Ask TypeSafe about every hunk (one request each) and turn answers into findings."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence

from .checks import POSSIBLE_THRESHOLD
from .judge import Judge, JudgeResult, build_questions, build_state
from .models import AnalysisResult, AnalysisStats, Check, Finding, Hunk, PullRequest, Tier, sort_findings

MAX_HUNKS = 300
DEFAULT_CONCURRENCY = 4


def applicable_checks(hunk: Hunk, checks: Sequence[Check]) -> list[Check]:
    return [check for check in checks if hunk.file_kind in check.applies_to]


def findings_for(hunk: Hunk, checks: Sequence[Check], nouls: dict[str, float]) -> list[Finding]:
    findings: list[Finding] = []
    for check in checks:
        probability = nouls.get(check.id)
        if probability is None or probability < POSSIBLE_THRESHOLD:
            continue
        tier: Tier = "flagged" if probability >= check.threshold else "possible"
        findings.append(
            Finding(
                check_id=check.id,
                title=check.title,
                severity=check.severity,
                tier=tier,
                path=hunk.path,
                line=hunk.anchor_line,
                probability=probability,
            )
        )
    return findings


async def analyze(
    hunks: Sequence[Hunk],
    pr: PullRequest,
    checks: Sequence[Check],
    judge: Judge,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    max_hunks: int = MAX_HUNKS,
    clock: Callable[[], float] = time.perf_counter,
) -> AnalysisResult:
    started = clock()
    work = [(hunk, applicable_checks(hunk, checks)) for hunk in hunks]
    work = [(hunk, hunk_checks) for hunk, hunk_checks in work if hunk_checks]
    selected, skipped = work[:max_hunks], work[max_hunks:]
    semaphore = asyncio.Semaphore(concurrency)

    async def run(hunk: Hunk, hunk_checks: list[Check]) -> tuple[Hunk, list[Check], JudgeResult]:
        async with semaphore:
            result = await judge.judge(build_state(hunk, pr), build_questions(hunk_checks))
        return hunk, hunk_checks, result

    outcomes = await asyncio.gather(*(run(hunk, hunk_checks) for hunk, hunk_checks in selected))

    findings: list[Finding] = []
    for hunk, hunk_checks, result in outcomes:
        findings.extend(findings_for(hunk, hunk_checks, result.nouls))

    stats = AnalysisStats(
        hunks_analyzed=len(selected),
        hunks_skipped=len(skipped),
        requests=len(outcomes),
        input_tokens=sum(result.input_tokens for _, _, result in outcomes),
        output_tokens=sum(result.output_tokens for _, _, result in outcomes),
        duration_ms=round((clock() - started) * 1000),
        models=tuple(sorted({result.model for _, _, result in outcomes})),
    )
    return AnalysisResult(findings=sort_findings(findings), stats=stats)
