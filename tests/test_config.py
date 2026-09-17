from greenwash.config import RepoConfig, is_ignored, parse_config


def test_missing_config_uses_defaults():
    config, error = parse_config(None)
    assert config == RepoConfig()
    assert config.mode == "comment"
    assert error is None


def test_empty_file_uses_defaults():
    assert parse_config("   \n") == (RepoConfig(), None)


def test_full_config_parses():
    config, error = parse_config(
        """
mode: check
ignore_paths: ["docs/**", "**/*.md"]
disabled_checks: [swallowed_error]
rules:
  - id: billing-needs-tests
    title: Billing logic changed
    question: "Does `hunk.diff` change how customers are billed or charged?"
    applies_to: [source]
    severity: critical
    threshold: 0.7
"""
    )
    assert error is None
    assert config.mode == "check"
    assert config.ignore_paths == ["docs/**", "**/*.md"]
    assert config.disabled_checks == ["swallowed_error"]
    rule = config.rules[0]
    assert (rule.id, rule.severity, rule.threshold, rule.applies_to) == (
        "billing-needs-tests",
        "critical",
        0.7,
        ["source"],
    )


def test_invalid_yaml_falls_back_with_error():
    config, error = parse_config("mode: [unclosed")
    assert config == RepoConfig()
    assert error is not None and error.startswith("invalid YAML")


def test_unknown_keys_and_bad_values_are_rejected_with_readable_error():
    config, error = parse_config("mode: block\nsurprise: true\n")
    assert config == RepoConfig()
    assert error is not None
    assert error.startswith("invalid config:")
    assert "mode" in error
    assert "surprise" in error


def test_non_mapping_yaml_is_rejected():
    assert parse_config("- just\n- a list\n")[1] == "the config file must be a YAML mapping"


def test_is_ignored_supports_recursive_globs():
    patterns = ["docs/**", "**/*.md"]
    assert is_ignored("docs/guide/setup.txt", patterns)
    assert is_ignored("README.md", patterns)
    assert is_ignored("src/pkg/NOTES.md", patterns)
    assert not is_ignored("src/pkg/main.py", patterns)
    assert not is_ignored("src/pkg/main.py", [])
