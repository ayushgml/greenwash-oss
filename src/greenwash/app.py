"""HTTP entry point: landing page, health check, and the GitHub webhook.

Run with: uv run uvicorn greenwash.app:create_app --factory
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from githubkit.webhooks import verify
from typesafe_sdk import AsyncTypeSafeClient

from .github import GitHubKitPort, GitHubPort
from .judge import Judge, TypeSafeJudge
from .models import PullRequest
from .pipeline import process_pull_request
from .settings import Settings
from .webhook import pull_request_from_event

logger = logging.getLogger("greenwash")

LANDING_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Greenwash</title>
<style>
  :root {{ color-scheme: light dark; --bg: #fbfbf8; --ink: #17181a; --muted: #5b5e63; --accent: #1f7a45; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #111312; --ink: #eceeea; --muted: #a2a6a0; --accent: #3fae6d; }} }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font: 17px/1.6 system-ui, sans-serif; }}
  main {{ max-width: 42rem; margin: 0 auto; padding: 4rem 1rem; }}
  h1 {{ font-size: 2.4rem; line-height: 1.15; margin: 0 0 .5rem; }}
  p, li {{ color: var(--muted); }}
  strong {{ color: var(--ink); }}
  a.button {{ display: inline-block; margin-top: 1.5rem; padding: .8rem 1.3rem; border-radius: .6rem;
             background: var(--accent); color: #fff; text-decoration: none; font-weight: 600; }}
</style>
</head>
<body>
<main>
  <h1>🧪 Greenwash</h1>
  <p><strong>Catches AI coding agents that cheat to make CI green.</strong></p>
  <p>Greenwash reads every changed hunk in a pull request and flags the shortcuts that turn a red build green:</p>
  <ul>
    <li>weakened or deleted test assertions</li>
    <li>skipped tests and non-blocking CI steps</li>
    <li>hard-coded answers for test inputs</li>
    <li>silenced errors, suppressed type checks, and placeholder code</li>
  </ul>
  <p>Every finding points at the exact line, with a probability instead of a verdict.</p>
  <a class="button" href="{install_url}">Install on GitHub</a>
</main>
</body>
</html>
"""


def create_app(
    settings: Settings | None = None,
    github_factory: Callable[[int], GitHubPort] | None = None,
    judge: Judge | None = None,
) -> FastAPI:
    resolved = settings or Settings.from_env()
    judges: dict[str, Judge] = {}
    if judge is not None:
        judges["default"] = judge

    def default_github_factory(installation_id: int) -> GitHubPort:
        return GitHubKitPort.for_installation(resolved.github_app_id, resolved.github_private_key, installation_id)

    make_github = github_factory or default_github_factory

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if "default" in judges:
            yield
            return
        async with AsyncTypeSafeClient() as client:
            judges["default"] = TypeSafeJudge(client, model=resolved.typesafe_model)
            yield
        judges.pop("default", None)

    app = FastAPI(title="Greenwash", lifespan=lifespan)
    install_url = f"https://github.com/apps/{resolved.github_app_slug}/installations/new"

    async def run_pipeline(pr: PullRequest) -> None:
        try:
            await process_pull_request(pr, make_github(pr.installation_id), judges["default"])
        except Exception:
            logger.exception("could not process %s/%s#%s", pr.owner, pr.repo, pr.number)

    @app.get("/", response_class=HTMLResponse)
    async def landing() -> str:
        return LANDING_PAGE.format(install_url=install_url)

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/github/webhook")
    async def github_webhook(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
        body = await request.body()
        signature = request.headers.get("x-hub-signature-256", "")
        if not signature or not verify(resolved.github_webhook_secret, body, signature):
            return JSONResponse({"error": "invalid signature"}, status_code=401)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        pr = pull_request_from_event(request.headers.get("x-github-event", ""), payload)
        if pr is None:
            return JSONResponse({"status": "ignored"}, status_code=202)
        background_tasks.add_task(run_pipeline, pr)
        return JSONResponse({"status": "queued"}, status_code=202)

    return app
