# Configuration

Greenwash works with no configuration. To tune it for a repository, add
`.github/greenwash.yml`. A complete example is in
[`greenwash.example.yml`](../greenwash.example.yml).

> **Greenwash reads this file from the pull request's base commit.** Changes to the config take
> effect for pull requests opened after the change is merged. A pull request cannot change the
> checks that apply to itself.

## Reference

```yaml
mode: comment
ignore_paths: []
disabled_checks: []
rules: []
```

### `mode`

| Value | Behavior |
|---|---|
| `comment` (default) | Report findings. The check concludes `neutral` when something is flagged and `success` otherwise. Never blocks a merge. |
| `check` | Same report, but the check concludes `failure` when a **critical** finding is flagged. Combine with branch protection to block merges. |

### `ignore_paths`

Glob patterns for files Greenwash should skip entirely. `**` matches any number of folders.

```yaml
ignore_paths:
  - "docs/**"
  - "**/*.md"
  - "vendor/**"
```

### `disabled_checks`

IDs of checks to turn off. Works for built-in checks, code rules, and custom rules (prefixed with
`custom:`).

```yaml
disabled_checks:
  - swallowed_error
  - snapshot_without_source_change
  - custom:billing
```

Built-in IDs:

| ID | Title | Applies to | Severity |
|---|---|---|---|
| `weakened_assertion` | Weakened test assertion | test | critical |
| `skipped_test` | Test skipped or disabled | test | critical |
| `rewritten_expectation` | Expected value rewritten | test | warning |
| `special_cased_test_input` | Hard-coded answer for specific inputs | source | critical |
| `placeholder_logic` | Logic replaced with a placeholder | source | critical |
| `swallowed_error` | Error silently swallowed | source | warning |
| `suppressed_check` | Type or lint check suppressed | source, test, lint_config | warning |
| `weakened_ci` | CI step removed or made non-blocking | ci | critical |
| `deleted_test_file` | Test file deleted | code rule | warning |
| `snapshot_without_source_change` | Snapshot updated without any source change | code rule | warning |

### `rules` — custom rules

Add your own checks in plain English. Each rule becomes one more yes/no question asked about every
matching hunk.

```yaml
rules:
  - id: billing                 # lowercase letters, digits, "-" or "_"
    title: Billing logic changed
    question: "Does `hunk.diff` change how customers are charged, refunded, or invoiced?"
    applies_to: [source]        # default: [source]
    severity: warning           # critical or warning; default: warning
    threshold: 0.8              # 0.0–1.0; default: 0.8
```

| Field | Required | Default | Notes |
|---|---|---|---|
| `id` | yes | — | Up to 64 characters. Appears as `custom:<id>`. |
| `title` | yes | — | Shown in the report. Up to 120 characters. |
| `question` | yes | — | Up to 1,000 characters. |
| `applies_to` | no | `[source]` | Any of `test`, `snapshot`, `ci`, `lint_config`, `source`, `other`. |
| `severity` | no | `warning` | In `check` mode, critical findings fail the check. |
| `threshold` | no | `0.8` | Probability at which a finding is flagged. |

#### Writing good questions

- **"Yes" must mean "needs a human look".** Findings are raised when the answer is likely yes.
- **Ask one thing.** "Does this change billing and skip validation?" hides two judgments. Write two
  rules instead.
- **Point at the diff.** Refer to `` `hunk.diff` `` in the question. The model also sees
  `` `hunk.file_path` ``, `` `hunk.file_kind` ``, and `` `pull_request.description` ``.
- **Name the look-alikes.** If legitimate changes resemble the problem, say so: "…not counting
  renames or added logging."

## File kinds

Greenwash decides a file's kind from its path:

| Kind | Examples |
|---|---|
| `snapshot` | `__snapshots__/`, `*.snap`, `*.golden`, `golden/` |
| `ci` | `.github/workflows/`, `.gitlab-ci.yml`, `.circleci/`, `Jenkinsfile`, `azure-pipelines.yml` |
| `lint_config` | `tsconfig*.json`, `pyproject.toml`, `setup.cfg`, `.eslintrc*`, `eslint.config.*`, `ruff.toml`, `.golangci.yml` |
| `test` | `test/`, `tests/`, `__tests__/`, `spec/`, `test_*.py`, `*_test.go`, `*.test.ts`, `*Test.java` |
| `source` | common source extensions (`.py`, `.ts`, `.go`, `.rs`, `.java`, …) |
| `other` | everything else — never sent to the model |

Kinds are checked in the order above, so `tests/__snapshots__/a.snap` is a snapshot.

## Invalid configuration

If the file isn't valid YAML, contains unknown keys, or has invalid values, Greenwash uses the
defaults and adds a warning to the report explaining what was wrong.
