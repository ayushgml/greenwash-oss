"""`python -m greenwash.live serve` starts the app; `run <scenario> --mode <mode>` runs headless."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from typesafe_sdk import AsyncTypeSafeClient

from ..judge import TypeSafeJudge
from .scenarios import MODES, load_scenarios


def judge_factory():
    return TypeSafeJudge(AsyncTypeSafeClient(timeout=8.0), model="jev-latest")


def main() -> int:
    parser = argparse.ArgumentParser(prog="greenwash-live")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one scenario headless and print the summary")
    run.add_argument("scenario")
    run.add_argument("--mode", choices=MODES, default="natural")
    run.add_argument("--pr", action="store_true", help="open a PR in the sandbox repo for Greenwash App review")
    serve = sub.add_parser("serve", help="start the Greenwash Live web app")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.command == "run":
        from .runner import Runner

        scenario = load_scenarios()[args.scenario]
        runner = Runner(scenario, args.mode, judge_factory, open_pr=args.pr)
        print(f"run {runner.run_id} → {runner.run_dir}", file=sys.stderr)
        summary = asyncio.run(runner.run())
        print(json.dumps(summary, indent=2))
        return 0 if summary.get("status") == "repaired" else 1

    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(judge_factory), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
