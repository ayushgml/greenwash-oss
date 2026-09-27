import json

import httpx
import pytest
from typesafe_sdk import Noul, NoulCriteria

from greenwash.guard.jev_source import HttpJevJudge, failproof_jev, resolve_judge

QUESTIONS = {"weakened_assertion": Noul(instructions="Weakened?", criteria=NoulCriteria(true="yes", false="no"))}


async def test_http_judge_sends_policykit_shape_and_reads_nouls():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], json.loads(request.content)
        return httpx.Response(200, json={"answers": {"weakened_assertion": {"type": "noul", "noul": 0.97}}, "model": "jev-1.13.0"})

    judge = HttpJevJudge("https://jev.example/v1/jev/systemone", "k", transport=httpx.MockTransport(handler))
    result = await judge.judge({"hunk": {"diff": "-a\n+b"}}, QUESTIONS)
    assert result.nouls == {"weakened_assertion": 0.97} and result.model == "jev-1.13.0"
    assert seen["url"].endswith("/systemone") and seen["auth"] == "Bearer k"
    assert seen["body"]["questions"]["weakened_assertion"] == {"type": "noul", "instructions": "Weakened?", "criteria": {"true": "yes", "false": "no"}}


async def test_http_error_raises_so_the_guard_denies():
    judge = HttpJevJudge("https://jev.example/systemone", "k", transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(httpx.HTTPStatusError):
        await judge.judge({}, QUESTIONS)


def test_failproof_config_is_found_and_incomplete_config_is_rejected(tmp_path):
    (tmp_path / "jev.json").write_text(json.dumps({"provider": "failproofai", "baseUrl": "https://x/enforcement/v1/jev/"}))
    (tmp_path / "credentials.json").write_text(json.dumps({"jev": {"key": "secret"}}))
    judge = failproof_jev(tmp_path)
    assert judge.url == "https://x/enforcement/v1/jev/systemone"
    (tmp_path / "credentials.json").write_text(json.dumps({"jev": {}}))
    assert failproof_jev(tmp_path) is None
    (tmp_path / "jev.json").write_text(json.dumps({"provider": "typesafe", "baseUrl": "https://y"}))
    assert failproof_jev(tmp_path) is None


def test_typesafe_key_wins_and_nothing_configured_gives_none(tmp_path, monkeypatch):
    monkeypatch.setenv("FAILPROOFAI_HOME", str(tmp_path))
    assert resolve_judge({"TYPESAFE_API_KEY": "k"}, lambda: "typesafe") == "typesafe"
    assert resolve_judge({}, lambda: "typesafe") is None
