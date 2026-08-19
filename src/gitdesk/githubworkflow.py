"""Structural inspection helpers for GitHub Actions workflow YAML."""

from __future__ import annotations

import re
from typing import Any

import yaml


# GitHub's official Pages deployment action is valid only when pinned to a non-empty action ref.
DEPLOY_PAGES_ACTION_PATTERN = re.compile(
    r"^actions/deploy-pages@[A-Za-z0-9._/-]+$",
    re.IGNORECASE,
)


# Traverses the parsed workflow instead of mistaking text inside run scripts or comments for executable Actions steps.
def source_uses_pages_deployment(source: str) -> bool:
    """Return whether parsed workflow jobs contain an actions/deploy-pages step."""

    try:
        workflow = yaml.safe_load(source)
    except yaml.YAMLError:
        return False
    if not isinstance(workflow, dict):
        return False
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return False

    for job in jobs.values():
        steps = job.get("steps") if isinstance(job, dict) else None
        if not isinstance(steps, list):
            continue
        for step in steps:
            uses = step.get("uses") if isinstance(step, dict) else None
            if DEPLOY_PAGES_ACTION_PATTERN.fullmatch(str(uses or "").strip()):
                return True
    return False
