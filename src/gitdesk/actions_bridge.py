"""Bridge handlers for GitHub Actions run lists and run details."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk import githubactions, githubpages


# Keeps Actions handlers out of the main BridgeController class.
def actions_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for GitHub Actions workflows."""

    return {
        "listWorkflowRuns": lambda payload: handle_list_workflow_runs(controller, payload),
        "workflowRunDetails": lambda payload: handle_workflow_run_details(controller, payload),
        "workflowJobLogs": lambda payload: handle_workflow_job_logs(controller, payload),
    }


# Fetches recent GitHub Actions runs for the configured owner/repo pair.
def handle_list_workflow_runs(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return recent GitHub Actions workflow runs."""

    owner, repo = controller.github_pair_from_payload(payload)
    return controller.github_client(payload).workflow_runs(owner, repo)


# Fetches jobs, artifacts, and annotations for a selected workflow run.
def handle_workflow_run_details(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return live detail for one GitHub Actions workflow run."""

    owner, repo = controller.github_pair_from_payload(payload)
    client = controller.github_client(payload)
    detail = githubactions.workflow_run_detail(
        client,
        owner,
        repo,
        payload.get("run_id"),
    )
    # Deployment records are terminal output; defer their fan-out while the existing two-second live poll is active.
    if bool(payload.get("run_completed")):
        detail["pages_deployment"] = githubpages.pages_deployment_for_run(
            client,
            owner,
            repo,
            payload.get("run_id"),
        )
    else:
        detail["pages_deployment"] = {"state": "", "url": ""}
    return detail


# Downloads one selected job's output only after the user opens a step disclosure.
def handle_workflow_job_logs(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return one GitHub Actions job log partitioned into step output."""

    owner, repo = controller.github_pair_from_payload(payload)
    return githubactions.workflow_job_logs(
        controller.github_client(payload),
        owner,
        repo,
        payload.get("job_id"),
    )
