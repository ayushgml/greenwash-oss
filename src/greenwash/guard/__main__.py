"""`python -m greenwash.guard`: hook payload on stdin, one JSON decision on stdout.

Exit status is always 0 when a decision was produced; the Failproof policy treats anything
else (crash, timeout, unparsable output) as a deny.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

from ..judge import TypeSafeJudge
from .core import JUDGE_DEADLINE_S, Record, append_record, guard, load_context


def _judge_factory():
    model = os.environ.get("TYPESAFE_MODEL", "").strip() or "jev-latest"
    client = AsyncTypeSafeClient(timeout=JUDGE_DEADLINE_S, retry=RetryPolicy(max_retries=1, backoff_initial=0.3, timeout=JUDGE_DEADLINE_S)
    )
    return TypeSafeJudge(client, model=model)


def main() -> int:
    env = dict(os.environ)
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except ValueError:
        payload = {}
    record: Record = asyncio.run(guard(payload, load_context(env), _judge_factory))
    try:
        append_record(env, record)
    except OSError:
        pass  # the decision still stands; the app reports the missing record
    print(json.dumps({"decision": record.decision, "reason": record.reason, "attempt_id": record.attempt_id}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
