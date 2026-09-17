from greenwash.checks import BUILTIN_CHECKS, active_checks, code_rule_findings
from greenwash.config import parse_config
from greenwash.models import ChangedFile


def test_builtin_checks_are_well_formed():
    ids = [check.id for check in BUILTIN_CHECKS]
    assert len(ids) == len(set(ids)) == 8
    for check in BUILTIN_CHECKS:
        assert check.applies_to, check.id
        assert 0.5 <= check.threshold <= 1.0, check.id
        assert "`hunk.diff`" in check.instructions, check.id
        assert check.criteria is not None and all(check.criteria), check.id


def test_active_checks_respect_disabled_and_custom_rules():
    config, error = parse_config(
        """
disabled_checks: [swallowed_error, custom:old-rule]
rules:
  - id: billing
    title: Billing changed
    question: "Does `hunk.diff` change billing?"
  - id: old-rule
    title: Old
    question: "Old question about `hunk.diff`?"
"""
    )
    assert error is None
    checks = {check.id: check for check in active_checks(config)}
    assert "swallowed_error" not in checks
    assert "weakened_assertion" in checks
    assert "custom:old-rule" not in checks
    billing = checks["custom:billing"]
    assert billing.criteria is None
    assert billing.applies_to == frozenset({"source"})
    assert billing.threshold == 0.8
    assert billing.instructions == "Does `hunk.diff` change billing?"


def test_deleted_test_file_is_flagged():
    findings = code_rule_findings(
        [
            ChangedFile(path="tests/test_cart.py", status="removed", patch=None),
            ChangedFile(path="src/cart.py", status="modified", patch="@@ -1 +1 @@\n-a\n+b"),
        ]
    )
    assert [(f.check_id, f.path, f.line, f.tier, f.severity) for f in findings] == [
        ("deleted_test_file", "tests/test_cart.py", None, "flagged", "warning")
    ]


def test_snapshot_without_source_change_is_flagged():
    findings = code_rule_findings(
        [
            ChangedFile(path="src/__snapshots__/Button.test.tsx.snap", status="modified", patch="x"),
            ChangedFile(path="README.md", status="modified", patch="x"),
        ]
    )
    assert [(f.check_id, f.path) for f in findings] == [
        ("snapshot_without_source_change", "src/__snapshots__/Button.test.tsx.snap")
    ]


def test_snapshot_with_source_change_is_fine():
    assert (
        code_rule_findings(
            [
                ChangedFile(path="src/__snapshots__/Button.test.tsx.snap", status="modified", patch="x"),
                ChangedFile(path="src/Button.tsx", status="modified", patch="x"),
            ]
        )
        == []
    )


def test_code_rules_can_be_disabled():
    files = [
        ChangedFile(path="tests/test_cart.py", status="removed", patch=None),
        ChangedFile(path="src/__snapshots__/a.snap", status="modified", patch="x"),
    ]
    assert code_rule_findings(files, ["deleted_test_file", "snapshot_without_source_change"]) == []
