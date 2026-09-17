import json

from githubkit.webhooks import verify

from greenwash.webhook import HANDLED_ACTIONS, pull_request_from_event, sign_payload
from tests.fakes import FIXTURE_PATH, make_pr


def load():
    return json.loads(FIXTURE_PATH.read_text())


def test_sign_payload_matches_githubkit_verify():
    body = FIXTURE_PATH.read_bytes()
    assert verify("s3cret", body, sign_payload("s3cret", body))
    assert not verify("other-secret", body, sign_payload("s3cret", body))


def test_parses_opened_pull_request():
    assert pull_request_from_event("pull_request", load()) == make_pr()


def test_missing_body_becomes_empty_string():
    payload = load()
    payload["pull_request"]["body"] = None
    assert pull_request_from_event("pull_request", payload).body == ""


def test_handles_every_supported_action():
    for action in HANDLED_ACTIONS:
        payload = load()
        payload["action"] = action
        assert pull_request_from_event("pull_request", payload) is not None, action


def test_ignores_other_events_actions_and_closed_pull_requests():
    assert pull_request_from_event("issues", load()) is None
    for action in ("closed", "labeled", "edited"):
        payload = load()
        payload["action"] = action
        assert pull_request_from_event("pull_request", payload) is None, action
    closed = load()
    closed["pull_request"]["state"] = "closed"
    assert pull_request_from_event("pull_request", closed) is None
