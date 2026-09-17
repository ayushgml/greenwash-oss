"""Score the labeled cases with the real TypeSafe API.

Usage (TYPESAFE_API_KEY must be exported): uv run python -m evals.run_evals
"""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict

from typesafe_sdk import AsyncTypeSafeClient

from evals.cases import CASES, EvalCase
from greenwash.checks import BUILTIN_CHECKS
from greenwash.diff import parse_patch
from greenwash.judge import TypeSafeJudge, build_questions, build_state
from greenwash.models import PullRequest

CHECKS = {check.id: check for check in BUILTIN_CHECKS}


def pull_request_for(case: EvalCase) -> PullRequest:
    return PullRequest(
        owner="eval",
        repo="eval",
        number=1,
        title=case.name,
        body=case.pr_description,
        head_sha="head",
        base_sha="base",
        installation_id=0,
    )


async def score(judge: TypeSafeJudge, case: EvalCase, semaphore: asyncio.Semaphore) -> tuple[float, str]:
    check = CHECKS[case.check_id]
    hunk = parse_patch(case.path, case.patch)[0]
    async with semaphore:
        result = await judge.judge(build_state(hunk, pull_request_for(case)), build_questions([check]))
    return result.nouls[check.id], result.model


async def main() -> int:
    semaphore = asyncio.Semaphore(4)
    async with AsyncTypeSafeClient() as client:
        judge = TypeSafeJudge(client)
        scored = await asyncio.gather(*(score(judge, case, semaphore) for case in CASES))

    rows_by_check: dict[str, list[tuple[EvalCase, float]]] = defaultdict(list)
    for case, (probability, _model) in zip(CASES, scored, strict=True):
        rows_by_check[case.check_id].append((case, probability))

    wrong = 0
    for check_id, rows in rows_by_check.items():
        threshold = CHECKS[check_id].threshold
        print(f"\n{check_id}  (threshold {threshold})")
        for case, probability in rows:
            correct = (probability >= threshold) == case.expected
            wrong += not correct
            label = "yes" if case.expected else "no"
            print(f"  {'✓' if correct else '✗'} p={probability:.2f}  expected={label:<3}  {case.name}")

    models = sorted({model for _probability, model in scored})
    print(f"\nmodel: {', '.join(models)}")
    print(f"{len(CASES) - wrong}/{len(CASES)} cases correct at the configured thresholds")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
