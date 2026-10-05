"""Open a pull request in the sandbox GitHub repo and read back the Greenwash App's review.

The PR's base branch holds the scenario's buggy commit; the head holds the agent's final patch.
Only the sandbox repository configured here is ever written to.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

SANDBOX_REPO = os.environ.get("GREENWASH_LIVE_REPO", "ayushgml/greenwash-live-sandbox")
REVIEW_TIMEOUT_S = 150
CHECK_NAME = "Greenwash"
COMMENT_MARKER = "<!-- greenwash:report -->"


class PullRequestError(RuntimeError):
    pass


def _run(args: list[str], cwd: Path | None = None, timeout: float = 120) -> str:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise PullRequestError(f"{' '.join(args[:3])} failed: {(proc.stderr or proc.stdout).strip()[:400]}")
    return proc.stdout


def open_pull_request(sandbox: Path, run_id: str, base_sha: str, title: str, body: str) -> dict[str, Any]:
    base_branch, head_branch = f"base/{run_id}", f"fix/{run_id}"
    git = ["git", "-c", "user.name=Greenwash Live", "-c", "user.email=greenwash-live@localhost"]
    _run(["git", "add", "-A", "--", ".", ":!.claude", ":!.failproofai"], sandbox)
    _run([*git, "commit", "-q", "--allow-empty", "-m", title], sandbox)
    _run(["git", "push", "-q", "origin", f"{base_sha}:refs/heads/{base_branch}"], sandbox)
    _run(["git", "push", "-q", "origin", f"HEAD:refs/heads/{head_branch}"], sandbox)
    url = _run(["gh", "pr", "create", "--repo", SANDBOX_REPO, "--base", base_branch, "--head", head_branch,
                "--title", title, "--body", body], sandbox).strip().splitlines()[-1]
    return {"url": url, "number": int(url.rstrip("/").rsplit("/", 1)[-1]), "repo": SANDBOX_REPO,
            "head_sha": _run(["git", "rev-parse", "HEAD"], sandbox).strip()}


def _gh_json(path: str) -> Any:
    return json.loads(_run(["gh", "api", path]))


async def wait_for_review(pr: dict[str, Any]) -> dict[str, Any]:
    """Poll the real GitHub check run and sticky comment posted by the Greenwash App."""
    deadline = asyncio.get_running_loop().time() + REVIEW_TIMEOUT_S
    check: dict[str, Any] | None = None
    while asyncio.get_running_loop().time() < deadline:
        runs = await asyncio.to_thread(_gh_json, f"repos/{pr['repo']}/commits/{pr['head_sha']}/check-runs")
        check = next((r for r in runs.get("check_runs", []) if r.get("name") == CHECK_NAME), None)
        if check and check.get("status") == "completed":
            break
        await asyncio.sleep(5)
    comments = await asyncio.to_thread(_gh_json, f"repos/{pr['repo']}/issues/{pr['number']}/comments")
    report = next((c for c in comments if COMMENT_MARKER in (c.get("body") or "")), None)
    if check is None:
        return {"state": "missing", "detail": f"No {CHECK_NAME} check appeared within {REVIEW_TIMEOUT_S}s. Is the app installed on {pr['repo']}?"}
    return {
        "state": check.get("status"),
        "conclusion": check.get("conclusion"),
        "title": (check.get("output") or {}).get("title"),
        "summary": ((check.get("output") or {}).get("summary") or "")[:1500],
        "check_url": check.get("html_url"),
        "comment_url": report.get("html_url") if report else None,
        "app": (check.get("app") or {}).get("slug"),
    }
