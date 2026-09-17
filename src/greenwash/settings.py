"""Configuration from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

REQUIRED = ("GITHUB_APP_ID", "GITHUB_PRIVATE_KEY", "GITHUB_WEBHOOK_SECRET", "TYPESAFE_API_KEY")


@dataclass(frozen=True)
class Settings:
    github_app_id: str
    github_private_key: str
    github_webhook_secret: str
    github_app_slug: str
    typesafe_model: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        missing = [name for name in REQUIRED if not env.get(name, "").strip()]
        if missing:
            raise ValueError(f"missing required environment variables: {', '.join(missing)}")
        return cls(
            github_app_id=env["GITHUB_APP_ID"].strip(),
            # Hosting dashboards often store multi-line PEM keys with literal "\n" sequences.
            github_private_key=env["GITHUB_PRIVATE_KEY"].replace("\\n", "\n"),
            github_webhook_secret=env["GITHUB_WEBHOOK_SECRET"],
            github_app_slug=env.get("GITHUB_APP_SLUG", "").strip() or "greenwash",
            typesafe_model=env.get("TYPESAFE_MODEL", "").strip() or None,
        )
