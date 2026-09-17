"""Send a signed pull_request webhook to a running Greenwash server.

Usage:
  GITHUB_WEBHOOK_SECRET=... uv run python scripts/replay_webhook.py PAYLOAD.json URL

Example:
  uv run python scripts/replay_webhook.py tests/fixtures/pull_request_opened.json \\
      http://127.0.0.1:8000/api/github/webhook
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import httpx

from greenwash.webhook import sign_payload


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    body = Path(sys.argv[1]).read_bytes()
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    if not secret:
        print("GITHUB_WEBHOOK_SECRET is not set")
        return 2
    response = httpx.post(
        sys.argv[2],
        content=body,
        headers={
            "content-type": "application/json",
            "x-github-event": "pull_request",
            "x-github-delivery": str(uuid.uuid4()),
            "x-hub-signature-256": sign_payload(secret, body),
        },
        timeout=30,
    )
    print(response.status_code, response.text)
    return 0 if response.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
