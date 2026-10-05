"""Run a Jev Buildathon agent task under the Greenwash guard and stream it like any Live run.

The organisers' own CLI (`node bin/buildathon.mjs run <agent> <task>`) launches the agent, so the
pinned model, hooks and scoring upload stay exactly theirs. Greenwash Live adds the run directory
that the agent's Greenwash policy writes its decision records into, and shows the result.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .activity import read_activity
from .paths import runs_dir, write_live_config
from .runner import RunLog, _summarize_agent_message, sandbox_lock

AGENT_POLICY = "greenwash-itsm-guard"
RUN_TIMEOUT_S = 600


def buildathon_repo() -> Path | None:
    path = os.environ.get("GREENWASH_BUILDATHON_REPO")
    return Path(path) if path and (Path(path) / "bin" / "buildathon.mjs").exists() else None


def list_tasks(repo: Path, agent: str = "itsm") -> list[dict[str, Any]]:
    data = json.loads((repo / "agents" / f"{agent}-agent" / "tasks.json").read_text())
    tasks = data if isinstance(data, list) else data.get("tasks", [])
    return [{"id": f"{agent}:{t['id']}", "agent": agent, "task": t["id"], "prompt": t["prompt"]} for t in tasks]


class BuildathonRunner:
    def __init__(self, repo: Path, agent: str, task: str, prompt: str) -> None:
        self.repo, self.agent, self.task, self.prompt = repo, agent, task, prompt
        self.run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.run_dir = runs_dir() / self.run_id
        self.run_dir.mkdir(parents=True)
        self.log = RunLog(self.run_dir)
        self.seen = 0

    def _meta(self, **extra: Any) -> None:
        path = self.run_dir / "run.json"
        meta = json.loads(path.read_text()) if path.exists() else {}
        path.write_text(json.dumps({**meta, **extra}, indent=2, default=str))

    def _new_records(self) -> list[dict[str, Any]]:
        path = self.run_dir / "decisions.jsonl"
        if not path.exists():
            return []
        lines = path.read_text().splitlines()
        fresh, self.seen = lines[self.seen:], len(lines)
        return [json.loads(line) for line in fresh if line.strip()]

    async def run(self) -> dict[str, Any]:
        with sandbox_lock(runs_dir()):
            return await self._run()

    async def _run(self) -> dict[str, Any]:
        self._meta(run_id=self.run_id, scenario=f"{self.agent}:{self.task}", mode="buildathon",
                   task_title=f"[{self.task}] {self.prompt}", task_description=self.prompt, started=time.time(), live=True)
        self.log.emit("run_started", run_id=self.run_id, mode="buildathon", prompt=f"[{self.task}] {self.prompt}", scenario={
            "id": f"{self.agent}:{self.task}", "title": f"{self.agent.upper()} {self.task}",
            "task_title": f"{self.agent.upper()} {self.task}: {self.prompt}", "task_description": self.prompt})
        self.log.emit("attempt_started", attempt=1, model="claude-haiku-4-5 (pinned by organisers)",
                      command=f"node bin/buildathon.mjs run {self.agent} {self.task}")
        env = {**os.environ, "GREENWASH_RUN_DIR": str(self.run_dir)}
        # Run the organisers' agent in Claude Code's default ~/.claude: that is where their setup
        # trusted the agent folders and where Failproof's uploader derives the scored agent id
        # (claude-itsm-agent). A custom CLAUDE_CONFIG_DIR would upload as projects-claude-itsm-agent.
        env.pop("CLAUDE_CONFIG_DIR", None)
        write_live_config(run_dir=str(self.run_dir), agent_dir=str(self.repo / "agents" / f"{self.agent}-agent"))
        proc = await asyncio.create_subprocess_exec(
            "node", "bin/buildathon.mjs", "run", self.agent, self.task, cwd=self.repo, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
        chunks: list[bytes] = []

        async def read() -> None:
            assert proc.stdout is not None
            async for line in proc.stdout:
                chunks.append(line)

        reader = asyncio.create_task(read())
        deadline = time.monotonic() + RUN_TIMEOUT_S
        while proc.returncode is None and time.monotonic() < deadline:
            for record in self._new_records():  # the agent's Greenwash policy writes these live
                self.log.emit("guard_decision", attempt=1, record=record)
            await asyncio.sleep(0.3)
            if reader.done():
                await proc.wait()
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        await reader
        write_live_config(run_dir=None, agent_dir=None)
        for record in self._new_records():
            self.log.emit("guard_decision", attempt=1, record=record)

        output = re.sub(r"\x1b\[[0-9;]*m", "", b"".join(chunks).decode(errors="replace"))
        transcript = re.search(r"transcript (\S+\.jsonl)", output)
        session_ids: set[str] = set()
        if transcript and Path(transcript.group(1)).exists():
            for line in Path(transcript.group(1)).read_text().splitlines():
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                for item in _summarize_agent_message(message):
                    if item["kind"] == "init" and item.get("session_id"):
                        session_ids.add(item["session_id"])
                    self.log.emit("agent", attempt=1, **item)
        self.log.emit("attempt_finished", attempt=1, model="claude-haiku-4-5", exit=proc.returncode, stopped=None,
                      guarded_denies=0, result=None, stderr="" if proc.returncode == 0 else output[-1500:])
        await asyncio.sleep(1.0)
        self.log.emit("failproof_activity", entries=read_activity(session_ids, policy=AGENT_POLICY),
                      session_ids=sorted(session_ids))
        executed = [l.strip()[2:] for l in output.splitlines() if l.strip().startswith(("• ", "✗ "))]
        blocked = [l.strip()[2:] for l in output.splitlines() if l.strip().startswith("⊘ ")]
        final = re.search(r"\nAgent: (.*)", output)
        summary = {"status": "completed" if proc.returncode == 0 else "error", "executed": len(executed),
                   "blocked": len(blocked), "exit": proc.returncode}
        self.log.emit("buildathon_result", executed=executed, blocked=blocked,
                      final=final.group(1).strip() if final else "", transcript=transcript.group(1) if transcript else None)
        self._meta(finished=time.time(), summary=summary)
        self.log.emit("run_finished", **summary)
        self.log.close()
        return summary
