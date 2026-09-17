from greenwash.models import ChangedFile
from greenwash.pipeline import process_pull_request
from greenwash.report import COMMENT_MARKER
from tests.fakes import (
    CLEAN_SOURCE_FILE,
    WEAKENED_KEYWORD,
    WEAKENED_TEST_FILE,
    FakeGitHub,
    KeywordJudge,
    make_pr,
)


async def test_flags_weakened_assertion_and_fails_in_check_mode():
    github = FakeGitHub(files=[WEAKENED_TEST_FILE, CLEAN_SOURCE_FILE], config_text="mode: check\n")
    judge = KeywordJudge({"weakened_assertion": WEAKENED_KEYWORD})
    await process_pull_request(make_pr(), github, judge)
    run = github.check_runs[1]
    assert run["conclusion"] == "failure"
    assert run["title"] == "1 likely problem found"
    assert [(a["path"], a["start_line"]) for a in run["annotations"]] == [("tests/test_cart.py", 4)]
    assert github.read_calls == [(".github/greenwash.yml", "base-sha")]
    assert len(github.comments) == 1
    assert github.comments[0].startswith(COMMENT_MARKER)
    assert "Weakened test assertion" in github.comments[0]
    assert judge.requests == 2


async def test_default_comment_mode_never_fails_the_check():
    github = FakeGitHub(files=[WEAKENED_TEST_FILE])
    await process_pull_request(make_pr(), github, KeywordJudge({"weakened_assertion": WEAKENED_KEYWORD}))
    assert github.check_runs[1]["conclusion"] == "neutral"


async def test_ignore_paths_skip_files():
    github = FakeGitHub(files=[WEAKENED_TEST_FILE], config_text="ignore_paths: ['tests/**']\n")
    judge = KeywordJudge({"weakened_assertion": WEAKENED_KEYWORD})
    await process_pull_request(make_pr(), github, judge)
    assert judge.requests == 0
    assert github.check_runs[1]["conclusion"] == "success"


async def test_invalid_config_falls_back_and_is_reported():
    github = FakeGitHub(files=[CLEAN_SOURCE_FILE], config_text="mode: [broken")
    await process_pull_request(make_pr(), github, KeywordJudge({}))
    assert github.check_runs[1]["conclusion"] == "success"
    assert "Could not use `.github/greenwash.yml`" in github.comments[0]


async def test_deleted_test_file_is_reported_without_annotation():
    github = FakeGitHub(files=[ChangedFile(path="tests/test_old.py", status="removed", patch=None)])
    judge = KeywordJudge({})
    await process_pull_request(make_pr(), github, judge)
    run = github.check_runs[1]
    assert run["conclusion"] == "neutral"
    assert run["annotations"] == []
    assert "Test file deleted" in github.comments[0]
    assert judge.requests == 0


async def test_errors_complete_the_check_as_neutral():
    github = FakeGitHub(files=[], fail_on_list=True)
    await process_pull_request(make_pr(), github, KeywordJudge({}))
    run = github.check_runs[1]
    assert run["conclusion"] == "neutral"
    assert run["title"] == "Greenwash could not finish"
    assert "RuntimeError: GitHub is down" in run["summary"]
    assert github.comments == []
