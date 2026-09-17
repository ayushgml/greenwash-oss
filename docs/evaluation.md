# Evaluation

Greenwash's checks are only as good as their questions. The evaluation set keeps them honest: every
change to a check's wording or threshold should be measured against labeled examples.

## The labeled set

[`evals/cases.py`](../evals/cases.py) contains, for each of the eight model-answered checks:

- **two positive cases** — real greenwashing that the check should flag, and
- **two negative cases** — legitimate changes that look similar and should not be flagged.

Examples for `weakened_assertion`:

| Case | Expected |
|---|---|
| `assert cart.total() == 90` → `assert cart.total() > 0` | flagged |
| a second `expect(...).toThrow(...)` deleted | flagged |
| `assert cart.total() > 0` → `assert cart.total() == 90` (stricter) | not flagged |
| variable renamed, same assertion | not flagged |

Some cases include a pull request description. For `rewritten_expectation`, the same diff should be
flagged when the description says "no behavior change" and not flagged when it documents the new
value.

## Running the evals

```bash
export TYPESAFE_API_KEY=...
uv run python -m evals.run_evals
```

Output shows one line per case with its probability, then a total:

```
weakened_assertion  (threshold 0.8)
  ✓ p=0.98  expected=yes  equality loosened to greater-than-zero
  ✓ p=0.98  expected=yes  second expectation deleted
  ✓ p=0.03  expected=no   assertion made stricter
  ✓ p=0.03  expected=no   variable renamed with same assertion
...
model: jev-1.13.0
32/32 cases correct at the configured thresholds
```

The script exits with status `1` if any case is misclassified.

`uv run pytest` also runs a structural test (no network) that checks every case parses to exactly
one hunk, targets a file kind its check applies to, and that every check has at least two positive
and two negative cases.

## Results

| Date | Model | Correct |
|---|---|---|
| 2026-09-17 | `jev-1.13.0` | 32 / 32 |

The set is small and hand-written. It catches regressions in question wording, but it is not a
measure of real-world precision or recall.

## Improving a check

1. Add the failing real-world example as a new case, with the label a careful reviewer would give.
2. Run the evals and note which cases fail.
3. If every positive case scores above every negative case, adjust the check's `threshold` to sit
   between them.
4. If positives and negatives overlap, reword the check's `instructions` or `criteria` to name the
   fact that separates them, then run the evals again.
5. Never change an existing case's `expected` label to make a check pass.

Include the eval output in your pull request.
