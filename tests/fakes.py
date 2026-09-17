"""Test doubles shared across the test suite."""

from __future__ import annotations

from greenwash.models import PullRequest


def make_pr(**overrides) -> PullRequest:
    values = {
        "owner": "acme",
        "repo": "shop",
        "number": 7,
        "title": "Fix cart total",
        "body": "Fixes rounding in cart totals.",
        "head_sha": "head-sha",
        "base_sha": "base-sha",
        "installation_id": 4242,
    }
    values.update(overrides)
    return PullRequest(**values)


from greenwash.judge import JudgeResult  # noqa: E402
from greenwash.models import ChangedFile  # noqa: E402

WEAKENED_TEST_FILE = ChangedFile(
    path="tests/test_cart.py",
    status="modified",
    patch="@@ -3,2 +3,2 @@ def test_total():\n     cart = Cart([2, 4])\n-    assert cart.total() == 6\n+    assert cart.total()",
)
CLEAN_SOURCE_FILE = ChangedFile(
    path="src/cart.py",
    status="modified",
    patch="@@ -1,2 +1,2 @@\n def total(items):\n-    return sum(items)\n+    return sum(item for item in items)",
)
WEAKENED_KEYWORD = "+    assert cart.total()"


class FakeGitHub:
    """In-memory GitHubPort that records what the pipeline published."""

    def __init__(self, files, config_text=None, fail_on_list=False):
        self.files = files
        self.config_text = config_text
        self.fail_on_list = fail_on_list
        self.read_calls = []
        self.check_runs = {}
        self.comments = []

    async def list_changed_files(self, pr):
        if self.fail_on_list:
            raise RuntimeError("GitHub is down")
        return self.files

    async def read_file(self, pr, path, ref):
        self.read_calls.append((path, ref))
        return self.config_text

    async def start_check_run(self, pr):
        check_run_id = len(self.check_runs) + 1
        self.check_runs[check_run_id] = {"status": "in_progress"}
        return check_run_id

    async def complete_check_run(self, pr, check_run_id, *, conclusion, title, summary, annotations):
        self.check_runs[check_run_id] = {
            "status": "completed",
            "conclusion": conclusion,
            "title": title,
            "summary": summary,
            "annotations": annotations,
        }

    async def upsert_comment(self, pr, body):
        self.comments.append(body)


class KeywordJudge:
    """Answers 0.95 for a check when its keyword appears in the hunk diff, otherwise 0.05."""

    def __init__(self, keywords):
        self.keywords = keywords
        self.requests = 0

    async def judge(self, state, questions):
        self.requests += 1
        diff = state["hunk"]["diff"]
        nouls = {
            question_id: 0.95 if question_id in self.keywords and self.keywords[question_id] in diff else 0.05
            for question_id in questions
        }
        return JudgeResult(nouls=nouls, model="fake-jev", input_tokens=50, output_tokens=2)


from pathlib import Path  # noqa: E402

from greenwash.settings import Settings  # noqa: E402
from greenwash.webhook import sign_payload  # noqa: E402

SECRET = "webhook-secret"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pull_request_opened.json"
SETTINGS = Settings(
    github_app_id="123",
    github_private_key="unused",
    github_webhook_secret=SECRET,
    github_app_slug="greenwash-test",
    typesafe_model=None,
)


def post_webhook(client, body, *, event="pull_request", secret=SECRET):
    return client.post(
        "/api/github/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "x-github-event": event,
            "x-hub-signature-256": sign_payload(secret, body),
        },
    )
