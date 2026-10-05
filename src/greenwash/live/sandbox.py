"""Reset the sandbox checkout to a scenario's buggy state, with the guard installed."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .paths import POLICY_FILE
from .scenarios import Scenario

GUARD_POLICY_NAME = "greenwash-guard-policies.mjs"
KEEP = {".git", ".venv"}  # survive resets: history, and the sandbox's own test interpreter


class SandboxError(RuntimeError):
    pass


def _run(args: list[str], cwd: Path, timeout: float = 120) -> str:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise SandboxError(f"{' '.join(args[:4])} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def git(sandbox: Path, *args: str) -> str:
    return _run(["git", *args], sandbox)


def reset(sandbox: Path, scenario: Scenario, branch: str) -> str:
    """Replace the working tree with the scenario, install the guard, commit. Returns the base SHA."""
    sandbox.mkdir(parents=True, exist_ok=True)
    if not (sandbox / ".git").exists():
        git(sandbox, "init", "-q", "-b", "main")
    ensure_venv(sandbox)
    for child in sandbox.iterdir():
        if child.name in KEEP:
            continue
        shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
    shutil.copytree(scenario.repo, sandbox, dirs_exist_ok=True)

    policies = sandbox / ".failproofai" / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    shutil.copy2(POLICY_FILE, policies / GUARD_POLICY_NAME)
    # The official installer writes the project-scope Claude Code hooks (.claude/settings.json).
    _run(["failproofai", "policies", "--install", "block-sudo", "--cli", "claude", "--scope", "project"], sandbox)
    if not (sandbox / ".claude" / "settings.json").exists():
        raise SandboxError("failproofai did not write .claude/settings.json")

    git(sandbox, "checkout", "-q", "-B", branch)
    git(sandbox, "add", "-A")
    git(sandbox, "-c", "user.name=Greenwash Live", "-c", "user.email=greenwash-live@localhost",
        "commit", "-q", "--allow-empty", "-m", f"Scenario base: {scenario.title}")
    return git(sandbox, "rev-parse", "HEAD").strip()


def ensure_venv(sandbox: Path) -> None:
    """A sandbox-local interpreter with pytest, so the agent's shell does not depend on the host PATH."""
    python = sandbox / ".venv" / "bin" / "python"
    if python.exists():
        return
    _run(["uv", "venv", "-q", "--python", "3.13", str(sandbox / ".venv")], sandbox)
    _run(["uv", "pip", "install", "-q", "--python", str(python), "pytest"], sandbox, timeout=300)


def installed_policy_matches(sandbox: Path) -> bool:
    installed = sandbox / ".failproofai" / "policies" / GUARD_POLICY_NAME
    return installed.exists() and installed.read_bytes() == POLICY_FILE.read_bytes()


def failproof_lists_guard(sandbox: Path) -> bool:
    """Ask Failproof itself whether the convention policy loads in this project."""
    try:
        out = _run(["failproofai", "policies"], sandbox, timeout=60)
    except (SandboxError, subprocess.TimeoutExpired):
        return False
    return "greenwash-guard" in out and GUARD_POLICY_NAME in out
