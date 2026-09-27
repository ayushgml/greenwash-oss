"""Where Greenwash Live keeps scenarios, the sandbox checkout, and run records."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LIVE_DIR = REPO_ROOT / "live"
SCENARIOS_DIR = LIVE_DIR / "scenarios"
POLICY_FILE = LIVE_DIR / "failproof" / "greenwash-guard-policies.mjs"
STATIC_DIR = LIVE_DIR / "web"


def sandbox_dir() -> Path:
    return Path(os.environ.get("GREENWASH_LIVE_SANDBOX", REPO_ROOT.parent / "greenwash-live-sandbox"))


def runs_dir() -> Path:
    path = Path(os.environ.get("GREENWASH_LIVE_RUNS", LIVE_DIR / "runs"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def guard_python() -> str:
    """The interpreter that has greenwash + typesafe-sdk installed (this one)."""
    return sys.executable


def failproof_activity_file() -> Path:
    home = Path(os.environ.get("FAILPROOFAI_HOME", Path.home() / ".failproofai"))
    return home / "hook-activity" / "current.jsonl"


def live_config_path() -> Path:
    """Where Greenwash Live tells its Failproof policies about the active run.

    With Failproof's daemon installed, policies are evaluated in the daemon's process, so the
    agent's environment variables never reach them; a small file outside every repo does.
    """
    return Path(os.environ.get("GREENWASH_LIVE_CONFIG", Path.home() / ".greenwash" / "live.json"))


def write_live_config(**active: str | None) -> None:
    import json

    path = live_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"python": guard_python(), **active}, indent=2))
