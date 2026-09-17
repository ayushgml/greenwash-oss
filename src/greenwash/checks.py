"""Every question Greenwash asks, and every threshold it applies, lives in this file."""

from __future__ import annotations

from collections.abc import Sequence

from .config import RepoConfig
from .diff import classify_file
from .models import ChangedFile, Check, Finding

POSSIBLE_THRESHOLD = 0.5

BUILTIN_CHECKS: tuple[Check, ...] = (
    Check(
        id="weakened_assertion",
        title="Weakened test assertion",
        severity="critical",
        applies_to=frozenset({"test"}),
        instructions=(
            "Does `hunk.diff` delete a test assertion, or replace it with a weaker one "
            "that would pass in more cases than before?"
        ),
        criteria=(
            "A removed ('-') line held an assertion or expectation, and no added ('+') line "
            "checks the same thing at least as strictly (for example an exact equality became "
            "a truthiness or 'greater than zero' check, or an assertion was deleted).",
            "Assertions are unchanged, added, made stricter, or only renamed, moved, or "
            "reformatted with the same strength.",
        ),
        threshold=0.8,
    ),
    Check(
        id="skipped_test",
        title="Test skipped or disabled",
        severity="critical",
        applies_to=frozenset({"test"}),
        instructions=(
            "Does `hunk.diff` add something that stops a test from running or from failing, "
            "such as a skip or xfail marker, an early return, a commented-out test, or "
            "catching the failure inside the test?"
        ),
        criteria=(
            "An added ('+') line disables, skips, or neutralizes a test that was previously active.",
            "No test is skipped, disabled, or neutralized by the added lines; tests may be "
            "added or re-enabled.",
        ),
        threshold=0.8,
    ),
    Check(
        id="rewritten_expectation",
        title="Expected value rewritten",
        severity="warning",
        applies_to=frozenset({"test"}),
        instructions=(
            "Does `hunk.diff` change the expected value in a test to a different value, even "
            "though `pull_request.description` does not say this behavior was intentionally changed?"
        ),
        criteria=(
            "An expected value or reference output in a test was replaced with a different value, "
            "and the pull request description does not explain a deliberate behavior change.",
            "Expected values are unchanged, or the pull request description explicitly says the "
            "behavior was meant to change.",
        ),
        threshold=0.8,
    ),
    Check(
        id="special_cased_test_input",
        title="Hard-coded answer for specific inputs",
        severity="critical",
        applies_to=frozenset({"source"}),
        instructions=(
            "Does `hunk.diff` add production code that returns a hard-coded result for specific "
            "inputs or detects a test environment, instead of implementing the general logic?"
        ),
        criteria=(
            "An added ('+') line special-cases particular literal inputs, fixture values, or a "
            "test/CI environment check to force a specific output.",
            "The added logic handles inputs generally, or its special cases are ordinary input "
            "validation or documented business rules.",
        ),
        threshold=0.8,
    ),
    Check(
        id="placeholder_logic",
        title="Logic replaced with a placeholder",
        severity="critical",
        applies_to=frozenset({"source"}),
        instructions=(
            "Does `hunk.diff` replace working logic with a stub, such as a hard-coded return "
            "value, a TODO, 'pass', or a 'not implemented' placeholder?"
        ),
        criteria=(
            "Removed ('-') lines contained real logic and the added ('+') lines put a placeholder, "
            "constant return, or TODO in its place.",
            "No real logic was replaced by a placeholder; logic may be refactored, moved into "
            "helpers, or newly added.",
        ),
        threshold=0.8,
    ),
    Check(
        id="swallowed_error",
        title="Error silently swallowed",
        severity="warning",
        applies_to=frozenset({"source"}),
        instructions=(
            "Does `hunk.diff` add code that catches or discards an error without handling, "
            "re-raising, returning, or logging it?"
        ),
        criteria=(
            "An added ('+') line introduces an empty catch/except block, a bare 'pass' in an "
            "exception handler, an ignored error return value, or catches everything and "
            "continues silently.",
            "Errors are handled, logged, re-raised, or returned, or no error handling was changed.",
        ),
        threshold=0.8,
    ),
    Check(
        id="suppressed_check",
        title="Type or lint check suppressed",
        severity="warning",
        applies_to=frozenset({"source", "test", "lint_config"}),
        instructions=(
            "Does `hunk.diff` add a directive or configuration change that turns off type "
            "checking, linting, or compiler errors?"
        ),
        criteria=(
            "An added ('+') line adds a suppression such as '@ts-ignore', 'eslint-disable', "
            "'# type: ignore', '# noqa', 'nolint', or '@SuppressWarnings', or relaxes a "
            "strictness setting in a config file.",
            "No new suppression or relaxed strictness setting was added.",
        ),
        threshold=0.8,
    ),
    Check(
        id="weakened_ci",
        title="CI step removed or made non-blocking",
        severity="critical",
        applies_to=frozenset({"ci"}),
        instructions=(
            "Does `hunk.diff` remove, skip, or make non-blocking a CI step that runs tests, "
            "linting, type checking, or builds?"
        ),
        criteria=(
            "The change deletes such a step, or adds 'continue-on-error: true', '|| true', "
            "'allow_failure: true', an always-false condition, or otherwise lets the pipeline "
            "pass when that step fails.",
            "CI steps that verify the code still run and still block on failure; steps may be "
            "added, cached, or expanded.",
        ),
        threshold=0.8,
    ),
)


def active_checks(config: RepoConfig) -> list[Check]:
    """Built-in checks minus disabled ones, plus the repository's custom rules."""
    disabled = set(config.disabled_checks)
    checks = [check for check in BUILTIN_CHECKS if check.id not in disabled]
    for rule in config.rules:
        check_id = f"custom:{rule.id}"
        if check_id in disabled:
            continue
        checks.append(
            Check(
                id=check_id,
                title=rule.title,
                severity=rule.severity,
                applies_to=frozenset(rule.applies_to),
                instructions=rule.question,
                criteria=None,
                threshold=rule.threshold,
            )
        )
    return checks


def code_rule_findings(files: Sequence[ChangedFile], disabled_checks: Sequence[str] = ()) -> list[Finding]:
    """Findings that need no model call: they follow directly from which files changed."""
    disabled = set(disabled_checks)
    kinds = {changed.path: classify_file(changed.path) for changed in files}
    findings: list[Finding] = []

    if "deleted_test_file" not in disabled:
        findings.extend(
            Finding(
                check_id="deleted_test_file",
                title="Test file deleted",
                severity="warning",
                tier="flagged",
                path=changed.path,
                line=None,
                probability=1.0,
            )
            for changed in files
            if changed.status == "removed" and kinds[changed.path] == "test"
        )

    if "snapshot_without_source_change" not in disabled:
        source_changed = any(kind == "source" for kind in kinds.values())
        if not source_changed:
            findings.extend(
                Finding(
                    check_id="snapshot_without_source_change",
                    title="Snapshot updated without any source change",
                    severity="warning",
                    tier="flagged",
                    path=changed.path,
                    line=None,
                    probability=1.0,
                )
                for changed in files
                if changed.status != "removed" and kinds[changed.path] == "snapshot"
            )
    return findings
