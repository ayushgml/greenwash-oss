import json

from fastapi.testclient import TestClient

from greenwash.app import create_app
from tests.fakes import (
    FIXTURE_PATH,
    SETTINGS,
    WEAKENED_KEYWORD,
    WEAKENED_TEST_FILE,
    FakeGitHub,
    KeywordJudge,
    post_webhook,
)


def make_client(github, judge):
    created = []

    def github_factory(installation_id):
        created.append(installation_id)
        return github

    app = create_app(settings=SETTINGS, github_factory=github_factory, judge=judge)
    return TestClient(app), created


def test_landing_page_and_healthz():
    client, _ = make_client(FakeGitHub(files=[]), KeywordJudge({}))
    response = client.get("/")
    assert response.status_code == 200
    assert "https://github.com/apps/greenwash-test/installations/new" in response.text
    assert client.get("/healthz").json() == {"ok": True}


def test_rejects_bad_or_missing_signature():
    client, created = make_client(FakeGitHub(files=[]), KeywordJudge({}))
    assert post_webhook(client, FIXTURE_PATH.read_bytes(), secret="wrong").status_code == 401
    unsigned = client.post("/api/github/webhook", content=b"{}", headers={"x-github-event": "pull_request"})
    assert unsigned.status_code == 401
    assert created == []


def test_ignores_unhandled_events():
    client, created = make_client(FakeGitHub(files=[]), KeywordJudge({}))
    payload = json.loads(FIXTURE_PATH.read_text())
    payload["action"] = "closed"
    response = post_webhook(client, json.dumps(payload).encode())
    assert (response.status_code, response.json()) == (202, {"status": "ignored"})
    ping = post_webhook(client, b'{"zen": "Keep it logically awesome."}', event="ping")
    assert ping.json() == {"status": "ignored"}
    assert created == []


def test_rejects_invalid_json():
    client, _ = make_client(FakeGitHub(files=[]), KeywordJudge({}))
    assert post_webhook(client, b"not json").status_code == 400


def test_queues_pull_request_and_runs_pipeline():
    github = FakeGitHub(files=[WEAKENED_TEST_FILE])
    client, created = make_client(github, KeywordJudge({"weakened_assertion": WEAKENED_KEYWORD}))
    response = post_webhook(client, FIXTURE_PATH.read_bytes())
    assert (response.status_code, response.json()) == (202, {"status": "queued"})
    assert created == [4242]
    assert github.check_runs[1]["conclusion"] == "neutral"
    assert "Weakened test assertion" in github.comments[0]
