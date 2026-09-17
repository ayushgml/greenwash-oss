# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-17

### Added

- GitHub App webhook service with signature verification, a landing page, and a health check.
- Eight model-answered checks: weakened test assertion, test skipped or disabled, expected value
  rewritten, hard-coded answer for specific inputs, logic replaced with a placeholder, error
  silently swallowed, type or lint check suppressed, and CI step removed or made non-blocking.
- Two code rules: test file deleted, and snapshot updated without any source change.
- Check runs with line annotations and a sticky pull request comment.
- Repository configuration through `.github/greenwash.yml`, read from the base commit: `mode`,
  `ignore_paths`, `disabled_checks`, and plain-English custom `rules`.
- Labeled evaluation set (32 cases) and a live scoring script.
- Dockerfile for self-hosting.

[Unreleased]: https://github.com/ayushgml/greenwash-oss/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ayushgml/greenwash-oss/releases/tag/v0.1.0
