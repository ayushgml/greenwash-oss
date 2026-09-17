"""Everything Greenwash needs from GitHub, behind one small interface."""

from __future__ import annotations

from typing import Protocol

from githubkit import AppAuthStrategy, GitHub
from githubkit.exception import RequestFailed

from .models import ChangedFile, PullRequest
from .report import COMMENT_MARKER

CHECK_RUN_NAME = "Greenwash"
MAX_SUMMARY_CHARS = 65_000


class GitHubPort(Protocol):
    async def list_changed_files(self, pr: PullRequest) -> list[ChangedFile]: ...

    async def read_file(self, pr: PullRequest, path: str, ref: str) -> str | None: ...

    async def start_check_run(self, pr: PullRequest) -> int: ...

    async def complete_check_run(
        self,
        pr: PullRequest,
        check_run_id: int,
        *,
        conclusion: str,
        title: str,
        summary: str,
        annotations: list[dict],
    ) -> None: ...

    async def upsert_comment(self, pr: PullRequest, body: str) -> None: ...


class GitHubKitPort:
    """`GitHubPort` backed by githubkit."""

    def __init__(self, github: GitHub) -> None:
        self._gh = github

    @classmethod
    def for_installation(cls, app_id: str, private_key: str, installation_id: int) -> GitHubKitPort:
        app = GitHub(AppAuthStrategy(app_id, private_key))
        return cls(app.with_auth(app.auth.as_installation(installation_id)))

    async def list_changed_files(self, pr: PullRequest) -> list[ChangedFile]:
        files: list[ChangedFile] = []
        async for item in self._gh.rest.paginate(
            self._gh.rest.pulls.async_list_files,
            owner=pr.owner,
            repo=pr.repo,
            pull_number=pr.number,
            per_page=100,
        ):
            patch = item.patch if isinstance(item.patch, str) else None
            files.append(ChangedFile(path=item.filename, status=item.status, patch=patch))
        return files

    async def read_file(self, pr: PullRequest, path: str, ref: str) -> str | None:
        try:
            response = await self._gh.rest.repos.async_get_content(
                pr.owner,
                pr.repo,
                path,
                ref=ref,
                headers={"Accept": "application/vnd.github.raw+json"},
            )
        except RequestFailed as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return response.text

    async def start_check_run(self, pr: PullRequest) -> int:
        response = await self._gh.rest.checks.async_create(
            pr.owner,
            pr.repo,
            data={
                "name": CHECK_RUN_NAME,
                "head_sha": pr.head_sha,
                "status": "in_progress",
                "output": {
                    "title": "Checking for greenwashed tests",
                    "summary": "Greenwash is analyzing the changed hunks in this pull request.",
                },
            },
        )
        return int(response.json()["id"])

    async def complete_check_run(
        self,
        pr: PullRequest,
        check_run_id: int,
        *,
        conclusion: str,
        title: str,
        summary: str,
        annotations: list[dict],
    ) -> None:
        output: dict = {"title": title[:255], "summary": summary[:MAX_SUMMARY_CHARS]}
        if annotations:
            output["annotations"] = annotations
        await self._gh.rest.checks.async_update(
            pr.owner,
            pr.repo,
            check_run_id,
            data={"status": "completed", "conclusion": conclusion, "output": output},
        )

    async def upsert_comment(self, pr: PullRequest, body: str) -> None:
        async for comment in self._gh.rest.paginate(
            self._gh.rest.issues.async_list_comments,
            owner=pr.owner,
            repo=pr.repo,
            issue_number=pr.number,
            per_page=100,
        ):
            if isinstance(comment.body, str) and comment.body.startswith(COMMENT_MARKER):
                await self._gh.rest.issues.async_update_comment(pr.owner, pr.repo, comment.id, data={"body": body})
                return
        await self._gh.rest.issues.async_create_comment(pr.owner, pr.repo, pr.number, data={"body": body})
