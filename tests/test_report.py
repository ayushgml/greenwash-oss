from greenwash.models import AnalysisResult, AnalysisStats, Finding
from greenwash.report import (
    COMMENT_MARKER,
    MAX_ANNOTATIONS,
    build_annotations,
    decide_conclusion,
    headline,
    render_comment,
)
from tests.fakes import make_pr


def finding(
    check_id="weakened_assertion",
    title="Weakened test assertion",
    severity="critical",
    tier="flagged",
    path="tests/test_cart.py",
    line=12,
    probability=0.97,
):
    return Finding(
        check_id=check_id,
        title=title,
        severity=severity,
        tier=tier,
        path=path,
        line=line,
        probability=probability,
    )


def test_decide_conclusion():
    assert decide_conclusion([], "check") == "success"
    assert decide_conclusion([finding(tier="possible")], "check") == "success"
    assert decide_conclusion([finding(severity="warning")], "check") == "neutral"
    assert decide_conclusion([finding()], "check") == "failure"
    assert decide_conclusion([finding()], "comment") == "neutral"


def test_build_annotations_only_flagged_with_lines_and_capped():
    findings = [finding(line=i) for i in range(1, 60)]
    findings += [finding(tier="possible"), finding(line=None, severity="warning")]
    annotations = build_annotations(findings)
    assert len(annotations) == MAX_ANNOTATIONS
    assert annotations[0] == {
        "path": "tests/test_cart.py",
        "start_line": 1,
        "end_line": 1,
        "annotation_level": "failure",
        "title": "Weakened test assertion",
        "message": "Greenwash: weakened test assertion (probability 97%). Please confirm this change is intentional.",
    }
    assert build_annotations([finding(severity="warning")])[0]["annotation_level"] == "warning"
    assert build_annotations([finding(line=None)]) == []


def test_render_comment_with_findings():
    result = AnalysisResult(
        findings=(
            finding(),
            finding(check_id="deleted_test_file", title="Test file deleted", severity="warning", path="tests/test_old.py", line=None, probability=1.0),
            finding(check_id="swallowed_error", title="Error silently swallowed", severity="warning", tier="possible", path="src/cart.py", line=40, probability=0.62),
        ),
        stats=AnalysisStats(hunks_analyzed=5, requests=5, duration_ms=1234),
    )
    body = render_comment(make_pr(), result, None)
    assert body.startswith(COMMENT_MARKER + "\n")
    assert "### 🧪 Greenwash: 2 likely problems found" in body
    assert "Checked 5 changed hunks in 1.2s" in body
    assert (
        "| 🔴 | Weakened test assertion | "
        "[`tests/test_cart.py#L12`](https://github.com/acme/shop/blob/head-sha/tests/test_cart.py#L12) | 97% |"
    ) in body
    assert "| 🟡 | Test file deleted | `tests/test_old.py` | 100% |" in body
    assert "<details><summary>Worth a second look (1)</summary>" in body
    assert "Error silently swallowed" in body


def test_render_comment_clean_run_with_config_error_and_skipped_hunks():
    result = AnalysisResult(findings=(), stats=AnalysisStats(hunks_analyzed=1, hunks_skipped=4, requests=1, duration_ms=200))
    body = render_comment(make_pr(), result, "invalid YAML: bad")
    assert "No likely problems found" in body
    assert "Checked 1 changed hunk in 0.2s · 4 more skipped (limit reached)" in body
    assert "✅ No signs of weakened tests" in body
    assert "Could not use `.github/greenwash.yml` (invalid YAML: bad)" in body
    assert "<details>" not in body


def test_headline_is_singular_for_one_problem():
    assert headline(AnalysisResult(findings=(finding(),))) == "1 likely problem found"
