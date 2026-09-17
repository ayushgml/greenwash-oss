"""Analyze one pull request end to end and publish the results."""

from __future__ import annotations

import logging

from .analyze import analyze
from .checks import active_checks, code_rule_findings
from .config import CONFIG_PATH, is_ignored, parse_config
from .diff import parse_patch
from .github import GitHubPort
from .judge import Judge
from .models import PullRequest
from .report import build_annotations, decide_conclusion, headline, render_comment, render_report

logger = logging.getLogger("greenwash")


async def process_pull_request(pr: PullRequest, github: GitHubPort, judge: Judge) -> None:
    check_run_id = await github.start_check_run(pr)
    try:
        # Read config from the base commit so a pull request cannot switch off its own checks.
        config, config_error = parse_config(await github.read_file(pr, CONFIG_PATH, pr.base_sha))
        files = [
            changed
            for changed in await github.list_changed_files(pr)
            if not is_ignored(changed.path, config.ignore_paths)
        ]
        hunks = [
            hunk
            for changed in files
            if changed.status != "removed" and changed.patch
            for hunk in parse_patch(changed.path, changed.patch)
        ]
        result = await analyze(hunks, pr, active_checks(config), judge)
        result = result.with_findings(code_rule_findings(files, config.disabled_checks))
        conclusion = decide_conclusion(result.findings, config.mode)

        await github.upsert_comment(pr, render_comment(pr, result, config_error))
        await github.complete_check_run(
            pr,
            check_run_id,
            conclusion=conclusion,
            title=headline(result),
            summary=render_report(pr, result, config_error),
            annotations=build_annotations(result.findings),
        )
        logger.info(
            "analyzed %s/%s#%s: conclusion=%s findings=%d hunks=%d input_tokens=%d models=%s",
            pr.owner,
            pr.repo,
            pr.number,
            conclusion,
            len(result.findings),
            result.stats.hunks_analyzed,
            result.stats.input_tokens,
            ",".join(result.stats.models),
        )
    except Exception as exc:
        logger.exception("greenwash failed on %s/%s#%s", pr.owner, pr.repo, pr.number)
        await github.complete_check_run(
            pr,
            check_run_id,
            conclusion="neutral",
            title="Greenwash could not finish",
            summary=(
                "Greenwash hit an error and did not block this pull request.\n\n"
                f"`{type(exc).__name__}: {exc}`"
            ),
            annotations=[],
        )
