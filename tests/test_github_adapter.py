import json

import httpx
import pytest
import respx
from githubkit import GitHub
from githubkit.exception import RequestFailed

from greenwash.github import CHECK_RUN_NAME, GitHubKitPort
from greenwash.models import ChangedFile
from greenwash.report import COMMENT_MARKER
from tests.fakes import make_pr

API = "https://api.github.com"


def diff_entry(filename, status="modified", patch=None):
    entry = {
        "sha": "0" * 40,
        "filename": filename,
        "status": status,
        "additions": 1,
        "deletions": 1,
        "changes": 2,
        "blob_url": "https://github.com/acme/shop/blob/x",
        "raw_url": "https://github.com/acme/shop/raw/x",
        "contents_url": f"{API}/repos/acme/shop/contents/x",
    }
    if patch is not None:
        entry["patch"] = patch
    return entry


def issue_comment(comment_id, body):
    return {
        "id": comment_id,
        "node_id": f"IC_{comment_id}",
        "url": f"{API}/repos/acme/shop/issues/comments/{comment_id}",
        "html_url": f"https://github.com/acme/shop/pull/7#issuecomment-{comment_id}",
        "body": body,
        "user": None,
        "created_at": "2026-09-17T00:00:00Z",
        "updated_at": "2026-09-17T00:00:00Z",
        "issue_url": f"{API}/repos/acme/shop/issues/7",
        "author_association": "NONE",
    }


@pytest.fixture
def port():
    return GitHubKitPort(GitHub("test-token"))


async def test_list_changed_files_maps_missing_patch_to_none(port):
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        mock.get("/repos/acme/shop/pulls/7/files").mock(
            return_value=httpx.Response(
                200,
                json=[
                    diff_entry("tests/test_cart.py", patch="@@ -1 +1 @@\n-a\n+b"),
                    diff_entry("logo.png", status="added"),
                ],
            )
        )
        files = await port.list_changed_files(make_pr())
    assert files == [
        ChangedFile(path="tests/test_cart.py", status="modified", patch="@@ -1 +1 @@\n-a\n+b"),
        ChangedFile(path="logo.png", status="added", patch=None),
    ]


async def test_read_file_returns_text_or_none(port):
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        found = mock.get("/repos/acme/shop/contents/.github/greenwash.yml").mock(
            return_value=httpx.Response(200, text="mode: check\n")
        )
        mock.get("/repos/acme/shop/contents/missing.yml").mock(
            return_value=httpx.Response(404, json={"message": "Not Found"})
        )
        assert await port.read_file(make_pr(), ".github/greenwash.yml", "base-sha") == "mode: check\n"
        assert found.calls.last.request.url.params["ref"] == "base-sha"
        assert found.calls.last.request.headers["accept"] == "application/vnd.github.raw+json"
        assert await port.read_file(make_pr(), "missing.yml", "base-sha") is None


async def test_read_file_reraises_other_errors(port):
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        mock.get("/repos/acme/shop/contents/.github/greenwash.yml").mock(
            return_value=httpx.Response(403, json={"message": "Resource not accessible by integration"})
        )
        with pytest.raises(RequestFailed):
            await port.read_file(make_pr(), ".github/greenwash.yml", "base-sha")


async def test_start_and_complete_check_run(port):
    annotation = {
        "path": "tests/test_cart.py",
        "start_line": 4,
        "end_line": 4,
        "annotation_level": "failure",
        "title": "Weakened test assertion",
        "message": "m",
    }
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        create = mock.post("/repos/acme/shop/check-runs").mock(return_value=httpx.Response(201, json={"id": 99}))
        update = mock.patch("/repos/acme/shop/check-runs/99").mock(return_value=httpx.Response(200, json={"id": 99}))
        check_run_id = await port.start_check_run(make_pr())
        await port.complete_check_run(
            make_pr(),
            check_run_id,
            conclusion="failure",
            title="1 likely problem found",
            summary="s" * 70_000,
            annotations=[annotation],
        )
    assert check_run_id == 99
    created = json.loads(create.calls.last.request.content)
    assert (created["name"], created["head_sha"], created["status"]) == (CHECK_RUN_NAME, "head-sha", "in_progress")
    updated = json.loads(update.calls.last.request.content)
    assert (updated["status"], updated["conclusion"]) == ("completed", "failure")
    assert updated["output"]["title"] == "1 likely problem found"
    assert len(updated["output"]["summary"]) == 65_000
    assert updated["output"]["annotations"] == [annotation]


async def test_complete_check_run_omits_empty_annotations(port):
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        update = mock.patch("/repos/acme/shop/check-runs/5").mock(return_value=httpx.Response(200, json={"id": 5}))
        await port.complete_check_run(make_pr(), 5, conclusion="success", title="t", summary="s", annotations=[])
    assert "annotations" not in json.loads(update.calls.last.request.content)["output"]


async def test_upsert_comment_updates_existing_report(port):
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        mock.get("/repos/acme/shop/issues/7/comments").mock(
            return_value=httpx.Response(200, json=[issue_comment(1, "LGTM"), issue_comment(2, f"{COMMENT_MARKER}\nold")])
        )
        update = mock.patch("/repos/acme/shop/issues/comments/2").mock(
            return_value=httpx.Response(200, json=issue_comment(2, "new"))
        )
        create = mock.post("/repos/acme/shop/issues/7/comments")
        await port.upsert_comment(make_pr(), f"{COMMENT_MARKER}\nnew")
    assert json.loads(update.calls.last.request.content) == {"body": f"{COMMENT_MARKER}\nnew"}
    assert not create.called


async def test_upsert_comment_creates_when_no_report_exists(port):
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        mock.get("/repos/acme/shop/issues/7/comments").mock(
            return_value=httpx.Response(200, json=[issue_comment(1, "LGTM")])
        )
        create = mock.post("/repos/acme/shop/issues/7/comments").mock(
            return_value=httpx.Response(201, json=issue_comment(3, "body"))
        )
        await port.upsert_comment(make_pr(), "body")
    assert json.loads(create.calls.last.request.content) == {"body": "body"}


def test_for_installation_builds_without_network():
    assert isinstance(GitHubKitPort.for_installation("123", "not-a-real-key", 4242), GitHubKitPort)
