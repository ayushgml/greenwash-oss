"""Jev routes a repair task to Sonnet or Opus. Jev judges difficulty; this code picks the model.

Routing only chooses who does the work. Every edit is still judged by the guard.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from typesafe_sdk import Noul, NoulCriteria

from ..judge import Judge

ROUTER_VERSION = "greenwash-router/1"
SMALL, LARGE = "sonnet", "opus"
HARD_AT = 0.7   # any difficulty signal at or above -> opus
EASY_BELOW = 0.3  # every signal below -> sonnet; anything between is uncertain -> opus
ROUTE_DEADLINE_S = 8.0

QUESTIONS: dict[str, Noul] = {
    "multi_file": Noul(
        instructions="Will fixing `task` most likely require changing more than one source file in `repository.files`?",
        criteria=NoulCriteria(
            true="The failing behavior spans several modules, or the fix clearly needs coordinated edits in multiple files.",
            false="The bug is local to one function or file.",
        ),
    ),
    "ambiguous_spec": Noul(
        instructions="Is the expected behavior in `task` ambiguous or underspecified, so the agent must guess what is correct?",
        criteria=NoulCriteria(
            true="The task and failing test leave the correct behavior open to interpretation.",
            false="The task and failing test state the correct behavior precisely.",
        ),
    ),
    "algorithmic": Noul(
        instructions="Does fixing `task` require designing non-trivial new logic, rather than a small correction to existing code?",
        criteria=NoulCriteria(
            true="A correct fix needs a new algorithm, data structure, or substantial rewrite.",
            false="A correct fix is a small, local change such as a comparison, formula, or missing case.",
        ),
    ),
}


@dataclass(frozen=True)
class Route:
    model: str
    reason: str
    band: str  # easy | hard | uncertain | error
    scores: dict[str, float] = field(default_factory=dict)
    jev_model: str | None = None
    error: str | None = None
    version: str = ROUTER_VERSION

    def as_json(self) -> dict[str, Any]:
        return {**self.__dict__}


def decide_route(scores: dict[str, float]) -> Route:
    missing = [key for key in QUESTIONS if not isinstance(scores.get(key), (int, float))]
    if missing:
        return Route(LARGE, f"router answer incomplete ({', '.join(missing)}); escalating to {LARGE}", "error", scores)
    hard = [k for k, v in scores.items() if k in QUESTIONS and v >= HARD_AT]
    if hard:
        return Route(LARGE, f"hard: {', '.join(hard)}", "hard", scores)
    if all(scores[k] < EASY_BELOW for k in QUESTIONS):
        return Route(SMALL, "routine: every difficulty signal is low", "easy", scores)
    return Route(LARGE, f"uncertain difficulty; escalating to {LARGE}", "uncertain", scores)


def repo_summary(repo: Path, limit_chars: int = 6000) -> dict[str, Any]:
    files: dict[str, str] = {}
    budget = limit_chars
    for path in sorted(repo.rglob("*")):
        rel = path.relative_to(repo).as_posix()
        if not path.is_file() or rel.startswith((".git/", ".claude/", ".failproofai/")) or "__pycache__" in rel:
            continue
        text = path.read_text(errors="replace")
        files[rel] = text[: max(budget, 0)]
        budget -= len(text)
    return {"files": files}


async def route(task_title: str, task_description: str, repo: Path, judge: Judge) -> Route:
    state = {"task": {"title": task_title, "description": task_description}, "repository": repo_summary(repo)}
    try:
        result = await asyncio.wait_for(judge.judge(state, QUESTIONS), timeout=ROUTE_DEADLINE_S)
    except Exception as exc:  # routing failure escalates, it never blocks the run
        return Route(LARGE, f"router unavailable ({type(exc).__name__}); escalating to {LARGE}", "error", error=type(exc).__name__)
    decided = decide_route(result.nouls)
    return Route(decided.model, decided.reason, decided.band, dict(result.nouls), result.model)
