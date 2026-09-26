"""One Greenwash Live run: reset → route → guarded agent (with escalation) → verify → record."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..judge import Judge
from . import sandbox as sb
from .activity import read_activity
from .paths import guard_python, runs_dir, sandbox_dir
from .router import LARGE, Route, route
from .scenarios import Mode, Scenario
from .verify import verify

AGENT_TOOLS = "Read,Edit,Write,Bash,Glob,Grep"
ATTEMPT_TIMEOUT_S = 420
DENIES_BEFORE_ESCALATION = 2
MAX_ATTEMPTS = 2  # the routed model, then at most one escalation to opus


class RunLog:
    """Append-only event log for one run; subscribers receive events live."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.path = run_dir / "events.jsonl"
        self.events: list[dict[str, Any]] = []
        self.subscribers: list[asyncio.Queue] = []
        self.done = False

    def emit(self, type_: str, **data: Any) -> dict[str, Any]:
        event = {"seq": len(self.events), "t": time.time(), "type": type_, **data}
        self.events.append(event)
        with self.path.open("a") as fh:
            fh.write(json.dumps(event, default=str) + "\n")
        for queue in list(self.subscribers):
            queue.put_nowait(event)
        return event

    def close(self) -> None:
        self.done = True
        for queue in list(self.subscribers):
            queue.put_nowait(None)


def counts_toward_escalation(record: dict[str, Any]) -> bool:
    """A blocked attempt to change files, by edit tool or shell; a denied harmless read does not count."""
    return record.get("decision") != "allow" and bool(record.get("write_attempt"))


def agent_command(model: str, prompt: str) -> list[str]:
    return [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "stream-json", "--verbose",
        "--permission-mode", "acceptEdits",
        "--tools", AGENT_TOOLS,
        "--allowedTools", "Bash",  # the Failproof guard, not the permission prompt, gates shell use
        "--setting-sources", "project",
        "--strict-mcp-config",
        "--disable-slash-commands",
    ]


def agent_env(run_dir: Path, sandbox: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_") and k != "CLAUDECODE"}
    venv_bin = str(Path(guard_python()).parent)
    env.update(
        GREENWASH_PYTHON=guard_python(),
        GREENWASH_RUN_DIR=str(run_dir),
        GREENWASH_SANDBOX=str(sandbox),
        PATH=f"{venv_bin}:{env.get('PATH', '')}",
    )
    return env


def _summarize_agent_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a stream-json message into small UI events."""
    out: list[dict[str, Any]] = []
    kind = message.get("type")
    if kind == "system" and message.get("subtype") == "init":
        out.append({"kind": "init", "session_id": message.get("session_id"), "model": message.get("model")})
    elif kind == "assistant":
        for block in message.get("message", {}).get("content", []):
            if block.get("type") == "text" and block.get("text", "").strip():
                out.append({"kind": "text", "text": block["text"]})
            elif block.get("type") == "tool_use":
                out.append({"kind": "tool_use", "id": block.get("id"), "tool": block.get("name"), "input": block.get("input")})
    elif kind == "user":
        for block in message.get("message", {}).get("content", []) if isinstance(message.get("message", {}).get("content"), list) else []:
            if block.get("type") == "tool_result":
                content = block.get("content")
                if isinstance(content, list):
                    content = "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
                out.append({"kind": "tool_result", "id": block.get("tool_use_id"), "is_error": bool(block.get("is_error")),
                            "text": str(content)[:2000]})
    elif kind == "result":
        out.append({"kind": "result", "subtype": message.get("subtype"), "text": message.get("result"),
                    "turns": message.get("num_turns"), "cost_usd": message.get("total_cost_usd"),
                    "duration_ms": message.get("duration_ms"), "denials": message.get("permission_denials")})
    return out


class Runner:
    def __init__(self, scenario: Scenario, mode: Mode, judge_factory: Callable[[], Judge]) -> None:
        self.scenario, self.mode, self.judge_factory = scenario, mode, judge_factory
        self.run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.run_dir = runs_dir() / self.run_id
        self.run_dir.mkdir(parents=True)
        self.sandbox = sandbox_dir()
        self.log = RunLog(self.run_dir)
        self.session_ids: set[str] = set()
        self.decisions_seen = 0
        self.activity_seen: set[tuple] = set()

    # --- helpers -------------------------------------------------------------

    def _write_meta(self, **extra: Any) -> None:
        meta_path = self.run_dir / "run.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        meta.update(extra)
        meta_path.write_text(json.dumps(meta, indent=2, default=str))

    def _new_decisions(self) -> list[dict[str, Any]]:
        path = self.run_dir / "decisions.jsonl"
        if not path.exists():
            return []
        lines = path.read_text().splitlines()
        fresh, self.decisions_seen = lines[self.decisions_seen:], len(lines)
        return [json.loads(line) for line in fresh if line.strip()]

    def _emit_new_activity(self) -> None:
        for entry in read_activity(self.session_ids):
            key = (entry.get("timestamp"), entry.get("toolName"), entry.get("decision"))
            if key not in self.activity_seen:
                self.activity_seen.add(key)
                self.log.emit("failproof_entry", entry=entry)

    def records(self) -> list[dict[str, Any]]:
        path = self.run_dir / "decisions.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []

    # --- phases --------------------------------------------------------------

    def _reset(self, attempt: int) -> str:
        branch = f"run/{self.run_id}" + (f"-a{attempt}" if attempt > 1 else "")
        base_sha = sb.reset(self.sandbox, self.scenario, branch)
        loaded = sb.installed_policy_matches(self.sandbox) and sb.failproof_lists_guard(self.sandbox)
        self.log.emit("sandbox_reset", attempt=attempt, branch=branch, base_sha=base_sha, guard_loaded=loaded)
        if not loaded:
            raise sb.SandboxError("Failproof does not list the greenwash-guard policy in the sandbox; refusing to run unguarded.")
        return base_sha

    async def _attempt(self, attempt: int, model: str) -> dict[str, Any]:
        prompt = self.scenario.prompt(self.mode)
        self.log.emit("attempt_started", attempt=attempt, model=model, command="claude -p … --model " + model)
        proc = await asyncio.create_subprocess_exec(
            *agent_command(model, prompt), cwd=self.sandbox, env=agent_env(self.run_dir, self.sandbox),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True,
            limit=16 * 1024 * 1024,
        )
        denies = 0
        stopped: str | None = None
        result: dict[str, Any] | None = None
        deadline = time.monotonic() + ATTEMPT_TIMEOUT_S

        async def pump_decisions() -> None:
            nonlocal denies, stopped
            tick = 0
            while proc.returncode is None:
                tick += 1
                if tick % 6 == 0:
                    self._emit_new_activity()
                for record in self._new_decisions():
                    self.log.emit("guard_decision", attempt=attempt, record=record)
                    if counts_toward_escalation(record):
                        denies += 1
                        if denies >= DENIES_BEFORE_ESCALATION and stopped is None:
                            stopped = f"{denies} guarded edits blocked"
                            _kill(proc)
                if time.monotonic() > deadline and stopped is None:
                    stopped = f"attempt exceeded {ATTEMPT_TIMEOUT_S}s"
                    _kill(proc)
                await asyncio.sleep(0.25)

        pump = asyncio.create_task(pump_decisions())
        assert proc.stdout is not None
        async for raw in proc.stdout:
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            for item in _summarize_agent_message(message):
                if item["kind"] == "init" and item.get("session_id"):
                    self.session_ids.add(item["session_id"])
                if item["kind"] == "result":
                    result = item
                self.log.emit("agent", attempt=attempt, **item)
        stderr = (await proc.stderr.read()).decode(errors="replace")[-2000:] if proc.stderr else ""
        await proc.wait()
        await asyncio.sleep(0.3)
        pump.cancel()
        for record in self._new_decisions():  # decisions written just before exit
            self.log.emit("guard_decision", attempt=attempt, record=record)
            if counts_toward_escalation(record):
                denies += 1
        outcome = {"attempt": attempt, "model": model, "exit": proc.returncode, "stopped": stopped,
                   "guarded_denies": denies, "result": result, "stderr": stderr if proc.returncode else ""}
        self.log.emit("attempt_finished", **outcome)
        return outcome

    async def run(self) -> dict[str, Any]:
        sc = self.scenario
        self._write_meta(run_id=self.run_id, scenario=sc.id, mode=self.mode, task_title=sc.task_title,
                         task_description=sc.task_description, started=time.time(), live=True)
        self.log.emit("run_started", run_id=self.run_id, scenario=sc.public(), mode=self.mode,
                      prompt=sc.prompt(self.mode))
        status, summary = "error", {}
        try:
            base_sha = self._reset(1)
            chosen: Route = await route(sc.task_title, sc.task_description, self.sandbox, self.judge_factory())
            self.log.emit("route", **chosen.as_json())
            model = chosen.model
            attempts = []
            for attempt in range(1, MAX_ATTEMPTS + 1):
                if attempt > 1:
                    base_sha = self._reset(attempt)
                outcome = await self._attempt(attempt, model)
                attempts.append(outcome)
                escalate = outcome["stopped"] and "blocked" in outcome["stopped"]
                if not escalate:
                    break
                if model == LARGE or attempt == MAX_ATTEMPTS:
                    self.log.emit("escalation", action="needs_human",
                                  reason=f"{outcome['stopped']} on {model}; stopping for human review")
                    status = "needs_human"
                    break
                self.log.emit("escalation", action="rerun", from_model=model, to_model=LARGE,
                              reason=f"{outcome['stopped']} on {model}; re-running once on {LARGE}")
                model = LARGE
            await asyncio.sleep(1.0)  # let Failproof finish writing its last activity rows
            self._emit_new_activity()
            activity = read_activity(self.session_ids)
            self.log.emit("failproof_activity", entries=activity, session_ids=sorted(self.session_ids))
            result = verify(self.sandbox, sc, base_sha, self.records())
            self.log.emit("verification", **result)
            if status != "needs_human":
                status = "repaired" if result["original_tests_pass"] else "not_repaired"
            summary = {
                "status": status,
                "model": model,
                "attempts": len(attempts),
                "denies": sum(1 for r in self.records() if r.get("decision") != "allow"),
                "jev_calls": sum(1 for r in self.records() if r.get("route") == "jev"),
                "original_tests_pass": result["original_tests_pass"],
                "tests_changed": result["tests_changed"],
                "blocked_content_absent": result["blocked_content_absent"],
            }
        except Exception as exc:  # surface every failure in the UI; never report success
            self.log.emit("error", message=f"{type(exc).__name__}: {exc}")
            summary = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        self._write_meta(finished=time.time(), summary=summary)
        self.log.emit("run_finished", **summary)
        self.log.close()
        return summary


def _kill(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
