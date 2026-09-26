"""Judge one PreToolUse payload and produce a decision record."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..judge import Judge, build_questions, build_state
from ..models import PullRequest
from .bash import check_bash, looks_like_write
from .policy import POLICY_VERSION, UNJUDGED_ALLOWED, Verdict, checks_for, decide, protected
from .proposal import FILE_TOOLS, ProposalError, build_proposal

JUDGE_DEADLINE_S = 5.0  # below the Failproof policy's 8s spawn timeout, itself below Failproof's 10s
READ_ONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "LS", "TodoWrite"})


@dataclass(frozen=True)
class RunContext:
    sandbox: Path
    task_title: str
    task_description: str


@dataclass
class Record:
    attempt_id: str
    timestamp: float
    session_id: str | None
    tool: str
    path: str | None = None
    file_kind: str | None = None
    command: str | None = None
    sha256: str | None = None
    diff: str | None = None
    checks: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    model: str | None = None
    judge_ms: int | None = None
    decision: str = "error"
    reason: str = ""
    fired: list[str] = field(default_factory=list)
    policy_version: str = POLICY_VERSION
    route: str = "rule"  # "rule" (no model call) or "jev"
    write_attempt: bool = False  # a blocked action that tried to change files (counts toward escalation)
    error: str | None = None

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def _finish(record: Record, verdict: Verdict) -> Record:
    if verdict.decision != "allow" and record.tool in FILE_TOOLS:
        record.write_attempt = True
    record.decision = verdict.decision
    record.reason = verdict.reason
    record.fired = list(verdict.fired)
    return record


async def guard(
    payload: dict[str, Any],
    context: RunContext | None,
    judge_factory: Callable[[], Judge],
    *,
    deadline_s: float = JUDGE_DEADLINE_S,
    clock: Callable[[], float] = time.perf_counter,
) -> Record:
    tool = str(payload.get("toolName") or "")
    tool_input = payload.get("toolInput") if isinstance(payload.get("toolInput"), dict) else None
    record = Record(
        attempt_id=uuid.uuid4().hex[:12],
        timestamp=time.time(),
        session_id=payload.get("sessionId"),
        tool=tool or "<missing>",
    )

    if context is None:
        return _finish(record, Verdict("error", "Greenwash guard has no run context; guarded actions are denied."))
    if not tool or tool_input is None:
        return _finish(record, Verdict("error", "Malformed hook payload: missing tool name or input."))

    if tool in READ_ONLY_TOOLS:
        return _finish(record, Verdict("allow", f"{tool} does not modify files."))

    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        record.command = command
        problem = check_bash(command)
        if problem:
            record.write_attempt = looks_like_write(command)
            return _finish(
                record,
                Verdict(
                    "deny",
                    f"Shell command blocked in the guarded sandbox: {problem}. Use the Edit or Write "
                    "tool for file changes (Greenwash can inspect those) and `python -m pytest` to run tests.",
                ),
            )
        return _finish(record, Verdict("allow", "Read/test command on the allowlist."))

    if tool not in FILE_TOOLS:
        return _finish(record, Verdict("deny", f"{tool} is not permitted in the guarded sandbox."))

    try:
        proposal = build_proposal(context.sandbox, tool, tool_input)
    except (ProposalError, OSError, UnicodeDecodeError) as exc:
        return _finish(record, Verdict("deny", f"Edit blocked: cannot inspect the proposed change ({exc})."))

    record.path, record.file_kind = proposal.path, proposal.file_kind
    record.sha256 = hashlib.sha256(proposal.after.encode()).hexdigest()
    record.diff = "\n".join(h.diff for h in proposal.hunks)

    if protected(proposal.path):
        return _finish(record, Verdict("deny", f"{proposal.path} is guard configuration and cannot be edited."))
    if proposal.unchanged:
        return _finish(record, Verdict("allow", "The edit changes nothing."))
    if proposal.file_kind in UNJUDGED_ALLOWED:
        return _finish(record, Verdict("allow", f"{proposal.path} is not code, tests, or CI."))
    if proposal.file_kind == "snapshot":
        return _finish(record, Verdict("review", "Snapshot/golden updates need human review in the guarded sandbox."))
    if any(h.truncated for h in proposal.hunks):
        return _finish(record, Verdict("review", "The change is too large to judge. Make a smaller, focused edit."))

    checks = checks_for(proposal.file_kind)
    record.checks = [c.id for c in checks]
    record.route = "jev"
    pr = PullRequest("sandbox", "sandbox", 0, context.task_title, context.task_description, "", "", 0)
    questions = build_questions(checks)
    judge = judge_factory()

    started = clock()
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(judge.judge(build_state(h, pr), questions) for h in proposal.hunks)),
            timeout=deadline_s,
        )
    except TimeoutError:
        record.error = f"judge timed out after {deadline_s:.0f}s"
        return _finish(record, Verdict("error", f"Edit blocked: Jev did not answer within {deadline_s:.0f}s. Retry once."))
    except Exception as exc:  # any judge failure must deny, never allow
        record.error = f"{type(exc).__name__}"
        return _finish(record, Verdict("error", f"Edit blocked: Jev judgment failed ({type(exc).__name__})."))
    finally:
        record.judge_ms = round((clock() - started) * 1000)

    scores: dict[str, float] = {}
    for result in results:
        for check_id, value in result.nouls.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                scores[check_id] = max(scores.get(check_id, 0.0), float(value))
    record.scores = scores
    record.model = ",".join(sorted({r.model for r in results})) or None
    return _finish(record, decide(checks, scores, proposal.path))


def load_context(env: dict[str, str]) -> RunContext | None:
    run_dir, sandbox = env.get("GREENWASH_RUN_DIR"), env.get("GREENWASH_SANDBOX")
    if not run_dir or not sandbox:
        return None
    try:
        run = json.loads((Path(run_dir) / "run.json").read_text())
        return RunContext(Path(sandbox), str(run["task_title"]), str(run["task_description"]))
    except (OSError, ValueError, KeyError):
        return None


def append_record(env: dict[str, str], record: Record) -> None:
    run_dir = env.get("GREENWASH_RUN_DIR")
    if not run_dir:
        return
    with (Path(run_dir) / "decisions.jsonl").open("a") as fh:
        fh.write(json.dumps(record.as_json()) + "\n")
