"""Turn a hunk plus its checks into one TypeSafe request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from typesafe_sdk import AsyncTypeSafeClient, Noul, NoulCriteria

from .models import Check, Hunk, PullRequest

DIFF_LEGEND = (
    "Lines starting with '-' were removed, lines starting with '+' were added, "
    "and lines starting with a space are unchanged context."
)


@dataclass(frozen=True)
class JudgeResult:
    nouls: dict[str, float]
    model: str
    input_tokens: int
    output_tokens: int


class Judge(Protocol):
    async def judge(self, state: dict[str, Any], questions: dict[str, Noul]) -> JudgeResult: ...


def build_state(hunk: Hunk, pr: PullRequest) -> dict[str, Any]:
    """The context every question about this hunk sees."""
    return {
        "pull_request": {"title": pr.title, "description": pr.body},
        "hunk": {
            "file_path": hunk.path,
            "file_kind": hunk.file_kind,
            "header": hunk.header,
            "diff_legend": DIFF_LEGEND,
            "diff": hunk.diff,
            "truncated": hunk.truncated,
        },
    }


def build_questions(checks: list[Check]) -> dict[str, Noul]:
    """One Noul per check, keyed by check id (ids are never sent to the model)."""
    questions: dict[str, Noul] = {}
    for check in checks:
        if check.criteria is None:
            questions[check.id] = Noul(instructions=check.instructions)
        else:
            true, false = check.criteria
            questions[check.id] = Noul(
                instructions=check.instructions,
                criteria=NoulCriteria(true=true, false=false),
            )
    return questions


class TypeSafeJudge:
    """Sends all of one hunk's questions to TypeSafe in a single request."""

    def __init__(self, client: AsyncTypeSafeClient, model: str | None = None) -> None:
        self._client = client
        self._model = model

    async def judge(self, state: dict[str, Any], questions: dict[str, Noul]) -> JudgeResult:
        response = await self._client.system_one(state=state, questions=questions, model=self._model)
        return JudgeResult(
            nouls={question_id: answer.noul for question_id, answer in response.nouls.items()},
            model=response.model,
            input_tokens=response.usage.input_tokens or 0,
            output_tokens=response.usage.output_tokens or 0,
        )
