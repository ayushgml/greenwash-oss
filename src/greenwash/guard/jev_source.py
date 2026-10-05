"""Where the guard gets Jev from.

1. `TYPESAFE_API_KEY` in the environment: the TypeSafe SDK, as the PR scanner uses.
2. Otherwise, this machine's Failproof Jev connection (`~/.failproofai/jev.json` with provider
   `failproofai`, key in `credentials.json`). This is the same endpoint the Jev Buildathon
   policykit's `askJev` uses, and it is what a Failproof daemon-evaluated policy can reach,
   because the daemon does not inherit the agent's environment.

No source → None, and the guard denies.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import msgspec
from typesafe_sdk import Noul

from ..judge import Judge, JudgeResult

DEFAULT_MODEL = "jev-1.13.0"


def failproof_home() -> Path:
    return Path(os.environ.get("FAILPROOFAI_HOME") or Path.home() / ".failproofai")


class HttpJevJudge:
    """Posts `{model, state, questions}` to `<base>/systemone`, like policykit's askJev."""

    def __init__(self, url: str, key: str, model: str = DEFAULT_MODEL, timeout: float = 5.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url, self._key, self.model, self.timeout, self._transport = url, key, model, timeout, transport

    async def judge(self, state: dict[str, Any], questions: dict[str, Noul]) -> JudgeResult:
        body = {
            "model": self.model,
            "state": state,
            "questions": {qid: {"type": "noul", **msgspec.to_builtins(q)} for qid, q in questions.items()},
        }
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            response = await client.post(self.url, json=body, headers={"authorization": f"Bearer {self._key}"})
        response.raise_for_status()
        data = response.json()
        nouls = {qid: answer.get("noul") for qid, answer in (data.get("answers") or {}).items() if isinstance(answer, dict)}
        usage = data.get("usage") or {}
        return JudgeResult(nouls=nouls, model=str(data.get("model") or self.model),
                           input_tokens=int(usage.get("input_tokens") or 0), output_tokens=int(usage.get("output_tokens") or 0))


def failproof_jev(home: Path | None = None, timeout: float = 5.0) -> HttpJevJudge | None:
    home = home or failproof_home()
    try:
        cfg = json.loads((home / "jev.json").read_text())
        if cfg.get("provider") != "failproofai" or not cfg.get("baseUrl"):
            return None
        key = json.loads((home / "credentials.json").read_text())["jev"]["key"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not key:
        return None
    return HttpJevJudge(cfg["baseUrl"].rstrip("/") + "/systemone", key, cfg.get("model") or DEFAULT_MODEL, timeout)


def resolve_judge(env: dict[str, str], typesafe_factory, timeout: float = 5.0) -> Judge | None:
    if env.get("TYPESAFE_API_KEY", "").strip():
        return typesafe_factory()
    return failproof_jev(timeout=timeout)
