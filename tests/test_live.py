import os

import pytest
from fastapi.testclient import TestClient

from greenwash.app import create_app
from tests.fakes import CLEAN_SOURCE_FILE, FIXTURE_PATH, SETTINGS, WEAKENED_TEST_FILE, FakeGitHub, post_webhook

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("TYPESAFE_API_KEY"), reason="needs TYPESAFE_API_KEY"),
]


def test_real_typesafe_flags_a_weakened_assertion_end_to_end():
    github = FakeGitHub(files=[WEAKENED_TEST_FILE, CLEAN_SOURCE_FILE], config_text="mode: check\n")
    app = create_app(settings=SETTINGS, github_factory=lambda installation_id: github)
    with TestClient(app) as client:
        response = post_webhook(client, FIXTURE_PATH.read_bytes())
    assert (response.status_code, response.json()) == (202, {"status": "queued"})
    run = github.check_runs[1]
    assert run["status"] == "completed"
    assert run["conclusion"] == "failure", run["summary"]
    assert ("tests/test_cart.py", 4) in [(a["path"], a["start_line"]) for a in run["annotations"]]
    assert "Weakened test assertion" in github.comments[0]
    assert all(a["path"] != "src/cart.py" for a in run["annotations"])
