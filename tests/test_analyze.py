import asyncio

from greenwash.analyze import analyze, findings_for
from greenwash.diff import parse_patch
from greenwash.judge import JudgeResult
from greenwash.models import Check
from tests.fakes import make_pr


def make_check(check_id, applies_to=("test",), severity="critical", threshold=0.8):
    return Check(
        id=check_id,
        title=check_id.replace("_", " ").title(),
        severity=severity,
        applies_to=frozenset(applies_to),
        instructions=f"Does `hunk.diff` show {check_id}?",
        criteria=None,
        threshold=threshold,
    )


def hunk(path, patch="@@ -1,1 +1,1 @@\n-a\n+b"):
    return parse_patch(path, patch)[0]


class ScriptedJudge:
    """Returns preset probabilities per file path and records concurrency."""

    def __init__(self, nouls_by_path):
        self.nouls_by_path = nouls_by_path
        self.calls = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def judge(self, state, questions):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0.01)
        self.in_flight -= 1
        path = state["hunk"]["file_path"]
        self.calls.append((path, sorted(questions)))
        preset = self.nouls_by_path.get(path, {})
        return JudgeResult(
            nouls={question_id: preset.get(question_id, 0.0) for question_id in questions},
            model="jev-1.13.0",
            input_tokens=100,
            output_tokens=5,
        )


def test_findings_for_applies_tiers():
    checks = [make_check("x"), make_check("y"), make_check("z")]
    findings = findings_for(hunk("tests/test_a.py"), checks, {"x": 0.95, "y": 0.6, "z": 0.2})
    assert [(f.check_id, f.tier, f.line, f.probability) for f in findings] == [
        ("x", "flagged", 1, 0.95),
        ("y", "possible", 1, 0.6),
    ]


async def test_analyze_only_asks_applicable_checks_and_aggregates():
    checks = [
        make_check("weakened", applies_to=("test",)),
        make_check("stub", applies_to=("source",), severity="warning"),
    ]
    judge = ScriptedJudge({"tests/test_a.py": {"weakened": 0.97}, "src/a.py": {"stub": 0.55}})
    result = await analyze([hunk("tests/test_a.py"), hunk("src/a.py"), hunk("README.md")], make_pr(), checks, judge)
    assert sorted(judge.calls) == [("src/a.py", ["stub"]), ("tests/test_a.py", ["weakened"])]
    assert [(f.check_id, f.tier) for f in result.findings] == [("weakened", "flagged"), ("stub", "possible")]
    assert result.stats.hunks_analyzed == 2
    assert result.stats.hunks_skipped == 0
    assert result.stats.requests == 2
    assert result.stats.input_tokens == 200
    assert result.stats.output_tokens == 10
    assert result.stats.models == ("jev-1.13.0",)


async def test_analyze_limits_concurrency_and_hunk_count():
    judge = ScriptedJudge({})
    hunks = [hunk(f"tests/test_{i}.py") for i in range(10)]
    result = await analyze(hunks, make_pr(), [make_check("weakened")], judge, concurrency=3, max_hunks=7)
    assert judge.max_in_flight <= 3
    assert len(judge.calls) == 7
    assert result.stats.hunks_analyzed == 7
    assert result.stats.hunks_skipped == 3
    assert result.findings == ()


async def test_analyze_with_no_hunks_makes_no_requests():
    judge = ScriptedJudge({})
    result = await analyze([], make_pr(), [make_check("weakened")], judge)
    assert judge.calls == []
    assert result.stats.requests == 0
    assert result.findings == ()
