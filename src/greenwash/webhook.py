"""Parse GitHub webhooks."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .models import PullRequest

HANDLED_ACTIONS = frozenset({"opened", "synchronize", "reopened", "ready_for_review"})


def sign_payload(secret: str, body: bytes) -> str:
    """The `X-Hub-Signature-256` value GitHub sends for this body."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def pull_request_from_event(event_name: str, payload: dict[str, Any]) -> PullRequest | None:
    """The pull request to analyze, or None when this event should be ignored."""
    if event_name != "pull_request" or payload.get("action") not in HANDLED_ACTIONS:
        return None
    pull = payload["pull_request"]
    if pull.get("state") != "open":
        return None
    return PullRequest(
        owner=payload["repository"]["owner"]["login"],
        repo=payload["repository"]["name"],
        number=int(pull["number"]),
        title=pull.get("title") or "",
        body=pull.get("body") or "",
        head_sha=pull["head"]["sha"],
        base_sha=pull["base"]["sha"],
        installation_id=int(payload["installation"]["id"]),
    )
