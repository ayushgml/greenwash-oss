# Contributing to Greenwash

Thanks for helping make AI-written pull requests easier to trust. This guide covers how to set up
the project, what kinds of contributions help most, and how changes get reviewed.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report a false positive or a missed problem.** Real examples are the most valuable input the
  project gets. Use the *False positive / missed problem* issue template and include the smallest
  diff hunk that reproduces it (remove anything private).
- **Add evaluation cases.** Every model-answered check needs labeled examples of both real
  greenwashing and legitimate look-alike changes. See [docs/evaluation.md](docs/evaluation.md).
- **Improve or add a check.** See [Changing checks](#changing-checks) below.
- **Fix bugs, improve docs, or add integrations.**

For anything larger than a small fix, please open an issue first so we can agree on the approach.

## Development setup

You need Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ayushgml/greenwash-oss.git
cd greenwash-oss
uv sync
uv run pytest
```

The default test run makes no network calls. Two optional commands call the real TypeSafe API and
need `TYPESAFE_API_KEY` exported:

```bash
uv run pytest -m live               # end-to-end pipeline test
uv run python -m evals.run_evals    # labeled accuracy check for every built-in check
```

To run the server locally against a real GitHub App, follow
[docs/self-hosting.md](docs/self-hosting.md#local-development).

## Project layout

```
src/greenwash/
  app.py        HTTP routes: landing page, /healthz, webhook
  webhook.py    signature helper and event parsing
  settings.py   environment variables
  pipeline.py   runs one pull request end to end
  github.py     GitHub port + githubkit adapter
  judge.py      TypeSafe port + request building
  diff.py       file classification and patch parsing
  config.py     .github/greenwash.yml parsing
  checks.py     every question and threshold
  analyze.py    one request per hunk, tiers, stats
  report.py     conclusion, annotations, Markdown
  models.py     shared data types
tests/          unit tests (no network) + one live end-to-end test
evals/          labeled cases and the live scorer
scripts/        developer utilities
docs/           user and contributor documentation
```

[docs/architecture.md](docs/architecture.md) explains how these fit together.

## Changing checks

All questions and thresholds live in [`src/greenwash/checks.py`](src/greenwash/checks.py). When you
add or change a check:

1. **Ask one narrow question.** A check should decide one fact about one hunk. Phrase it so "yes"
   means "this needs a human look".
2. **Define both answers.** Fill in `criteria` with what counts as yes and what counts as no,
   including the legitimate changes that look similar.
3. **Scope it.** Set `applies_to` to the file kinds where the question makes sense.
4. **Add evaluation cases.** At least two positive and two negative cases in
   [`evals/cases.py`](evals/cases.py). Negative cases should be realistic look-alikes, not obviously
   unrelated code.
5. **Run the evals** with `uv run python -m evals.run_evals` and include the output in your pull
   request.

Never change a case's `expected` label to make a check pass.

## Pull request guidelines

- Keep pull requests focused on one change.
- Add or update tests for behavior changes. `uv run pytest` must pass.
- Keep the default test run free of network calls. Mark tests that call TypeSafe with
  `@pytest.mark.live`.
- Update the docs and [CHANGELOG.md](CHANGELOG.md) (under *Unreleased*) when behavior changes.
- Match the style of the surrounding code: type hints, small functions, and plain data classes.

## Reporting security issues

Please don't open public issues for vulnerabilities. Follow [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE).
