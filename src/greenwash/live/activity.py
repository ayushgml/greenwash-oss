"""Read Failproof AI's own local hook-activity log: evidence the block came from the hook."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import failproof_activity_file

GUARD_POLICY = ".failproofai-project/greenwash-guard"
KEEP = ("timestamp", "eventType", "toolName", "policyName", "decision", "reason", "durationMs", "sessionId", "integration")


def read_activity(session_ids: set[str], path: Path | None = None) -> list[dict[str, Any]]:
    """PreToolUse entries for these Claude sessions where the Greenwash guard was evaluated."""
    directory = (path or failproof_activity_file()).parent
    if not session_ids or not directory.exists():
        return []
    entries = []
    # Failproof pages the log: older entries move from current.jsonl into page-*.jsonl files.
    files = sorted(directory.glob("page-*.jsonl")) + [directory / "current.jsonl"]
    for file in files:
        if not file.exists():
            continue
        for line in file.read_text(errors="replace").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("sessionId") not in session_ids or entry.get("eventType") != "PreToolUse":
                continue
            if GUARD_POLICY not in (entry.get("matchedPolicies") or []):
                continue
            entries.append({key: entry.get(key) for key in KEEP})
    return sorted(entries, key=lambda e: e.get("timestamp") or 0)
