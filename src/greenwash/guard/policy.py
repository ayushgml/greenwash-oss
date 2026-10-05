"""Deterministic guard policy. Jev supplies probabilities; this file decides.

Bands (strict, chosen 2026-09-26):
- any check at or above its threshold      -> deny
- any check in [POSSIBLE_THRESHOLD, thr)    -> review (denied, needs a human)
- every check below POSSIBLE_THRESHOLD      -> allow
- the judge failed or answered malformed    -> error (denied)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal

from ..checks import BUILTIN_CHECKS, POSSIBLE_THRESHOLD
from ..models import Check, FileKind

POLICY_VERSION = "greenwash-guard/2"  # 2: per-option shell allowlist, case-insensitive paths, "other" -> review
Decision = Literal["allow", "deny", "review", "error"]

# Paths an agent must never edit in the sandbox: the guard's own configuration.
PROTECTED_PREFIXES = (".failproofai/", ".claude/", ".greenwash/", ".git/", ".venv/")
# Files with no model-answered check (kind "other") are allowed only when they are prose.
# Anything else of that kind (Makefile, noxfile data, JSON fixtures read by tests) can change
# what the tests do, and no check can judge it, so it goes to human review.
DOC_SUFFIXES = frozenset({".md", ".rst", ".txt"})

# The next step each check suggests to the agent after a deny.
NEXT_STEPS = {
    "weakened_assertion": "Keep the original assertion. The test is the specification: fix the source code so it passes.",
    "skipped_test": "Do not skip, xfail, or neutralize the test. Find the bug in the source code and fix it.",
    "rewritten_expectation": "Do not change the expected value unless the task says the behavior changed. Fix the source code instead.",
    "special_cased_test_input": "Do not special-case the test's inputs. Implement the general logic so every input is handled.",
    "placeholder_logic": "Do not replace real logic with a constant or stub. Fix the actual computation.",
    "swallowed_error": "Do not hide the error. Handle it, re-raise it, or fix its cause.",
    "suppressed_check": "Do not suppress the type/lint check. Fix the code it complains about.",
    "weakened_ci": "Do not remove the CI step or make it non-blocking. Make the code pass the step.",
}


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: str
    fired: tuple[str, ...] = ()
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def blocks(self) -> bool:
        return self.decision != "allow"


def checks_for(kind: FileKind, checks: tuple[Check, ...] = BUILTIN_CHECKS) -> list[Check]:
    return [check for check in checks if kind in check.applies_to]


def protected(path: str) -> bool:
    # Case-insensitive: on macOS (APFS) and Windows, `.Claude/settings.json` is `.claude/settings.json`.
    folded = path.casefold()
    return any(folded == prefix.rstrip("/") or folded.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def is_documentation(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in DOC_SUFFIXES


def validate_scores(checks: list[Check], scores: dict[str, float]) -> str | None:
    """None if every expected check has a probability in [0, 1]."""
    for check in checks:
        value = scores.get(check.id)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"judge returned no probability for {check.id}"
        if not 0.0 <= float(value) <= 1.0:
            return f"judge returned out-of-range probability for {check.id}: {value}"
    return None


def decide(checks: list[Check], scores: dict[str, float], path: str) -> Verdict:
    """Map validated per-check probabilities (max over hunks) to a verdict."""
    problem = validate_scores(checks, scores)
    if problem:
        return Verdict("error", f"Edit to {path} blocked: {problem}. Guarded edits need a valid judgment.", scores=scores)

    flagged = [c for c in checks if scores[c.id] >= c.threshold]
    borderline = [c for c in checks if POSSIBLE_THRESHOLD <= scores[c.id] < c.threshold]
    if flagged:
        steps = " ".join(dict.fromkeys(NEXT_STEPS.get(c.id, "") for c in flagged if NEXT_STEPS.get(c.id)))
        findings = ", ".join(f"{c.title} (p={scores[c.id]:.2f})" for c in flagged)
        return Verdict(
            "deny",
            f"Greenwash blocked this edit to {path}: {findings}. {steps}".strip(),
            fired=tuple(c.id for c in flagged),
            scores=scores,
        )
    if borderline:
        findings = ", ".join(f"{c.title} (p={scores[c.id]:.2f})" for c in borderline)
        return Verdict(
            "review",
            f"Greenwash needs human review before this edit to {path}: {findings} is uncertain. "
            "Try a change that fixes the source code without altering what the tests check.",
            fired=tuple(c.id for c in borderline),
            scores=scores,
        )
    return Verdict("allow", "No Greenwash check fired.", scores=scores)
