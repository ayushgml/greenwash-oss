"""Load `.github/greenwash.yml`."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import FileKind, Severity

CONFIG_PATH = ".github/greenwash.yml"


class CustomRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=64)
    title: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=1000)
    applies_to: list[FileKind] = Field(default_factory=lambda: ["source"], min_length=1)
    severity: Severity = "warning"
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class RepoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["comment", "check"] = "comment"
    ignore_paths: list[str] = Field(default_factory=list)
    disabled_checks: list[str] = Field(default_factory=list)
    rules: list[CustomRule] = Field(default_factory=list)


def parse_config(text: str | None) -> tuple[RepoConfig, str | None]:
    """Parse the config file. Invalid config falls back to defaults plus an error message."""
    if text is None or not text.strip():
        return RepoConfig(), None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return RepoConfig(), f"invalid YAML: {exc}"
    if data is None:
        return RepoConfig(), None
    if not isinstance(data, dict):
        return RepoConfig(), "the config file must be a YAML mapping"
    try:
        return RepoConfig.model_validate(data), None
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or '(root)'}: {error['msg']}"
            for error in exc.errors()
        )
        return RepoConfig(), f"invalid config: {problems}"


def is_ignored(path: str, patterns: list[str]) -> bool:
    """True when the path matches any `ignore_paths` glob (`**` matches any number of folders)."""
    pure = PurePosixPath(path)
    return any(pure.full_match(pattern) for pattern in patterns)
