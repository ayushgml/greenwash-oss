from collections import Counter

from evals.cases import CASES
from greenwash.checks import BUILTIN_CHECKS
from greenwash.diff import parse_patch


def test_every_case_is_a_single_applicable_hunk():
    checks = {check.id: check for check in BUILTIN_CHECKS}
    for case in CASES:
        hunks = parse_patch(case.path, case.patch)
        assert len(hunks) == 1, case.name
        assert case.check_id in checks, case.name
        assert hunks[0].file_kind in checks[case.check_id].applies_to, case.name


def test_every_builtin_check_has_positive_and_negative_cases():
    positives = Counter(case.check_id for case in CASES if case.expected)
    negatives = Counter(case.check_id for case in CASES if not case.expected)
    for check in BUILTIN_CHECKS:
        assert positives[check.id] >= 2, check.id
        assert negatives[check.id] >= 2, check.id


def test_case_names_are_unique():
    names = [case.name for case in CASES]
    assert len(names) == len(set(names))
