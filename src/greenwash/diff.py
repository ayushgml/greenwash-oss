"""Classify changed files and split GitHub patches into hunks."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from .models import FileKind, Hunk

MAX_HUNK_CHARS = 8_000

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
_CI_PREFIXES = (".github/workflows/", ".circleci/", ".buildkite/")
_CI_NAMES = {
    ".gitlab-ci.yml",
    "jenkinsfile",
    "azure-pipelines.yml",
    "bitbucket-pipelines.yml",
    ".travis.yml",
}
_LINT_CONFIG_NAMES = {
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml",
    ".eslintrc.yaml", "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
    "eslint.config.ts", "tsconfig.json", ".flake8", "setup.cfg", "mypy.ini", ".mypy.ini",
    ".pylintrc", "pylintrc", "ruff.toml", ".ruff.toml", "pyproject.toml", ".golangci.yml",
    ".golangci.yaml", "biome.json", "pytest.ini", "tox.ini", "jest.config.js",
    "jest.config.ts", "vitest.config.ts", "vitest.config.js", ".rubocop.yml",
    "phpstan.neon", "detekt.yml", "clippy.toml",
}
_TSCONFIG_VARIANT = re.compile(r"tsconfig\..+\.json")
_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testing"}
_TEST_NAME_PATTERNS = (
    re.compile(r"test_.+\.py"),
    re.compile(r".+_test\.(py|go|rb|exs?)"),
    re.compile(r"conftest\.py"),
    re.compile(r".+\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs|mts|cts)"),
    re.compile(r".+(Test|Tests|Spec)\.(java|kt|scala|swift|cs|php)"),
    re.compile(r".+_spec\.rb"),
)
_SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts", ".go", ".rs",
    ".java", ".kt", ".kts", ".scala", ".rb", ".php", ".cs", ".c", ".h", ".cc", ".cpp",
    ".hpp", ".swift", ".m", ".mm", ".ex", ".exs", ".erl", ".clj", ".dart", ".lua", ".sh",
    ".sql", ".vue", ".svelte",
}


def classify_file(path: str) -> FileKind:
    """Decide what role a changed file plays, using only its path."""
    pure = PurePosixPath(path)
    name = pure.name
    lower_name = name.lower()
    lower_dirs = tuple(part.lower() for part in pure.parts[:-1])

    if "__snapshots__" in lower_dirs or "golden" in lower_dirs or lower_name.endswith((".snap", ".golden")):
        return "snapshot"
    if path.lower().startswith(_CI_PREFIXES) or lower_name in _CI_NAMES:
        return "ci"
    if lower_name in _LINT_CONFIG_NAMES or _TSCONFIG_VARIANT.fullmatch(lower_name):
        return "lint_config"
    if any(part in _TEST_DIRS for part in lower_dirs) or any(p.fullmatch(name) for p in _TEST_NAME_PATTERNS):
        return "test"
    if pure.suffix.lower() in _SOURCE_EXTENSIONS:
        return "source"
    return "other"


def parse_patch(path: str, patch: str) -> list[Hunk]:
    """Split a GitHub file patch into hunks, tracking new-file line numbers of added lines."""
    file_kind = classify_file(path)
    hunks: list[Hunk] = []
    header: str | None = None
    body: list[str] = []
    added: list[int] = []
    new_start = 0
    new_line = 0

    def flush() -> None:
        if header is None:
            return
        diff = "\n".join(body)
        truncated = len(diff) > MAX_HUNK_CHARS
        hunks.append(
            Hunk(
                path=path,
                file_kind=file_kind,
                header=header,
                diff=diff[:MAX_HUNK_CHARS],
                new_start=new_start,
                added_lines=tuple(added),
                truncated=truncated,
            )
        )

    for line in patch.splitlines():
        match = _HUNK_HEADER.match(line)
        if match:
            flush()
            header, body, added = line, [], []
            new_start = new_line = int(match.group(3))
            continue
        if header is None:
            continue  # text before the first hunk header (e.g. binary notices)
        body.append(line)
        if line.startswith("+"):
            added.append(new_line)
            new_line += 1
        elif line.startswith(("-", "\\")):
            continue  # removed line or "\ No newline at end of file"
        else:
            new_line += 1  # context line
    flush()
    return hunks
