"""Greenwash Live web app: start guarded runs, stream them live, replay recorded ones."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..checks import BUILTIN_CHECKS, POSSIBLE_THRESHOLD
from ..judge import Judge
from .activity import read_activity
from .paths import STATIC_DIR, runs_dir
from .runner import Runner
from .scenarios import MODE_LABELS, MODES, load_scenarios

REPLAY_MAX_GAP_S = 1.2


class RunRequest(BaseModel):
    scenario: str
    mode: str = "natural"
    open_pr: bool = False


def _version(args: list[str]) -> str | None:
    if not shutil.which(args[0]):
        return None
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def create_app(judge_factory: Callable[[], Judge]) -> FastAPI:
    app = FastAPI(title="Greenwash Live", docs_url=None, redoc_url=None)
    state: dict[str, Any] = {"runner": None, "task": None}

    def busy() -> bool:
        return state["task"] is not None and not state["task"].done()

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        failproof, claude = await asyncio.gather(
            asyncio.to_thread(_version, ["failproofai", "--version"]),
            asyncio.to_thread(_version, ["claude", "--version"]),
        )
        return {
            "failproof": failproof,
            "claude": claude,
            "typesafe_key": bool(os.environ.get("TYPESAFE_API_KEY", "").strip()),
            "busy": busy(),
            "active_run": state["runner"].run_id if busy() else None,
        }

    @app.get("/api/scenarios")
    async def scenarios() -> dict[str, Any]:
        return {"scenarios": [s.public() for s in load_scenarios().values()],
                "modes": [{"id": m, "label": MODE_LABELS[m]} for m in MODES],
                "checks": [{"id": c.id, "title": c.title, "threshold": c.threshold} for c in BUILTIN_CHECKS],
                "possible_threshold": POSSIBLE_THRESHOLD}

    @app.post("/api/runs", status_code=202)
    async def start_run(request: RunRequest) -> dict[str, str]:
        catalog = load_scenarios()
        if request.scenario not in catalog:
            raise HTTPException(404, f"unknown scenario {request.scenario}")
        if request.mode not in MODES:
            raise HTTPException(422, f"mode must be one of {', '.join(MODES)}")
        if busy():
            raise HTTPException(409, "A run is already in progress. Wait for it to finish.")
        runner = Runner(catalog[request.scenario], request.mode, judge_factory,  # type: ignore[arg-type]
                        open_pr=request.open_pr)
        state["runner"], state["task"] = runner, asyncio.create_task(runner.run())
        return {"run_id": runner.run_id}

    @app.get("/api/runs")
    async def list_runs() -> dict[str, Any]:
        runs = []
        for meta_path in sorted(runs_dir().glob("*/run.json"), reverse=True)[:50]:
            try:
                meta = json.loads(meta_path.read_text())
            except ValueError:
                continue
            runs.append({key: meta.get(key) for key in ("run_id", "scenario", "mode", "task_title", "started", "finished", "summary")})
        return {"runs": runs}

    @app.get("/api/runs/{run_id}/activity")
    async def activity(run_id: str) -> dict[str, Any]:
        """Failproof's own hook-log rows for the agent sessions recorded in this run."""
        if "/" in run_id or ".." in run_id:
            raise HTTPException(400, "bad run id")
        path = runs_dir() / run_id / "events.jsonl"
        if not path.exists():
            raise HTTPException(404, "unknown run")
        sessions = {e.get("session_id") for e in map(json.loads, path.read_text().splitlines())
                    if e.get("type") == "agent" and e.get("kind") == "init" and e.get("session_id")}
        return {"entries": await asyncio.to_thread(read_activity, sessions)}

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, paced: bool = True) -> StreamingResponse:
        if "/" in run_id or ".." in run_id:
            raise HTTPException(400, "bad run id")
        runner: Runner | None = state["runner"]
        live = runner is not None and runner.run_id == run_id and not runner.log.done

        async def stream_live():
            assert runner is not None
            queue: asyncio.Queue = asyncio.Queue()
            backlog = list(runner.log.events)
            runner.log.subscribers.append(queue)
            try:
                yield _sse({"type": "stream", "replay": False})
                for event in backlog:
                    yield _sse(event)
                seen = len(backlog)
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if event is None:
                        break
                    if event["seq"] >= seen:
                        yield _sse(event)
            finally:
                runner.log.subscribers.remove(queue)
            yield _sse({"type": "stream_end"})

        async def stream_replay():
            path = runs_dir() / run_id / "events.jsonl"
            if not path.exists():
                yield _sse({"type": "error", "message": f"No recorded events for run {run_id}."})
                return
            yield _sse({"type": "stream", "replay": True})
            previous = None
            for line in path.read_text().splitlines():
                event = json.loads(line)
                if paced and previous is not None:
                    await asyncio.sleep(min(max(event["t"] - previous, 0), REPLAY_MAX_GAP_S))
                previous = event["t"]
                yield _sse(event)
            yield _sse({"type": "stream_end"})

        return StreamingResponse(stream_live() if live else stream_replay(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.middleware("http")
    async def no_cache_static(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
