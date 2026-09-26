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
