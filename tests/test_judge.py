from types import SimpleNamespace

from typesafe_sdk import Noul

from greenwash.checks import BUILTIN_CHECKS
from greenwash.diff import parse_patch
from greenwash.judge import DIFF_LEGEND, TypeSafeJudge, build_questions, build_state
from greenwash.models import Check
from tests.fakes import make_pr


def test_build_state_contains_pr_and_hunk():
    hunk = parse_patch("tests/test_cart.py", "@@ -1,1 +1,1 @@\n-    assert total() == 6\n+    assert total()")[0]
    state = build_state(hunk, make_pr())
    assert state["pull_request"] == {"title": "Fix cart total", "description": "Fixes rounding in cart totals."}
    assert state["hunk"] == {
        "file_path": "tests/test_cart.py",
        "file_kind": "test",
        "header": "@@ -1,1 +1,1 @@",
        "diff_legend": DIFF_LEGEND,
        "diff": "-    assert total() == 6\n+    assert total()",
        "truncated": False,
    }


def test_build_questions_uses_check_ids_and_optional_criteria():
    builtin = BUILTIN_CHECKS[0]
    custom = Check(
        id="custom:billing",
        title="Billing",
        severity="warning",
        applies_to=frozenset({"source"}),
        instructions="Does `hunk.diff` change billing?",
        criteria=None,
        threshold=0.8,
    )
    questions = build_questions([builtin, custom])
    assert list(questions) == [builtin.id, "custom:billing"]
    assert questions[builtin.id].instructions == builtin.instructions
    assert questions[builtin.id].criteria == {"true": builtin.criteria[0], "false": builtin.criteria[1]}
    assert questions["custom:billing"].criteria is None


class FakeTypeSafeClient:
    def __init__(self):
        self.calls = []

    async def system_one(self, *, state, questions, model):
        self.calls.append({"state": state, "questions": questions, "model": model})
        return SimpleNamespace(
            nouls={question_id: SimpleNamespace(noul=0.91) for question_id in questions},
            model="jev-1.13.0",
            usage=SimpleNamespace(input_tokens=400, output_tokens=None),
        )


async def test_typesafe_judge_maps_the_response():
    client = FakeTypeSafeClient()
    judge = TypeSafeJudge(client, model="jev-latest")
    result = await judge.judge({"k": "v"}, {"q1": Noul(instructions="Is it?")})
    assert result.nouls == {"q1": 0.91}
    assert result.model == "jev-1.13.0"
    assert (result.input_tokens, result.output_tokens) == (400, 0)
    assert client.calls[0]["model"] == "jev-latest"
    assert client.calls[0]["state"] == {"k": "v"}
