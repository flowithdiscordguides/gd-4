"""GitHub Pages configuration and deployment-status services for Repo Mode."""

from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse

from gitdesk.errors import AppError
from gitdesk.githubapi import is_token_permission_error
from gitdesk.githubserializers import clean_repository_pair
from gitdesk.githubworkflow import source_uses_pages_deployment


# GitHub exposes these exact values for the mutually exclusive Pages publishing sources.
PAGES_BUILD_TYPES = {"legacy", "workflow"}

# GitHub's official Pages Actions templates deploy through this environment.
PAGES_ENVIRONMENT = "github-pages"

# Deployment and status endpoints allow at most one hundred records per request.
DEPLOYMENT_PAGE_SIZE = 100

# These terminal states mean the selected Pages deployment did not publish a usable site.
FAILED_DEPLOYMENT_STATES = {"error", "failure"}

# These transient states keep the result non-interactive until GitHub reports completion.
ACTIVE_DEPLOYMENT_STATES = {"in_progress", "pending", "queued"}

# These workflow conclusions represent a completed run that could not publish its Pages site.
FAILED_WORKFLOW_CONCLUSIONS = {"action_required", "cancelled", "failure", "startup_failure", "timed_out"}


# Validates a Pages build type before it becomes GitHub API mutation data.
def clean_build_type(value: Any) -> str:
    """Return either GitHub's legacy or workflow Pages build type."""

    build_type = str(value or "").strip().lower()
    if build_type not in PAGES_BUILD_TYPES:
        raise AppError("Select a valid GitHub Pages source.", "PAGES_BUILD_TYPE_INVALID")
    return build_type


# Configures Pages without writing or replacing any repository-owned workflow file.
def configure_pages_site(
    client: Any,
    owner: str,
    repo: str,
    build_type_value: Any,
    branch: str = "",
    source_path: str = "/",
) -> dict[str, Any]:
    """Create or update the remote Pages source and return its refreshed configuration."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    build_type = clean_build_type(build_type_value)
    request_body: dict[str, Any] = {"build_type": build_type}
    # Branch publishing requires both source fields, while workflow mode deliberately omits source.
    if build_type == "legacy":
        clean_branch = str(branch or "").strip()
        if not clean_branch or source_path not in {"/", "/docs"}:
            raise AppError("Select a valid Pages branch and folder.", "PAGES_SOURCE_INVALID")
        request_body["source"] = {"branch": clean_branch, "path": source_path}

    try:
        current = client.pages_site(clean_owner, clean_repo)
        method = "PUT" if current.get("configured") else "POST"
        client.request(method, f"/repos/{clean_owner}/{clean_repo}/pages", json_body=request_body)
        return client.pages_site(clean_owner, clean_repo)
    except AppError as error:
        # Pages mutations need both Pages and Administration write permissions on fine-grained PATs.
        if is_token_permission_error(error):
            message = "GitHub rejected this token for Pages. Use GitDesk token setup for repository permissions."
            raise AppError(message, "PAGES_TOKEN_PERMISSION_FAILED") from error
        raise


# Converts GitHub timestamps into sortable values without trusting response order.
def timestamp_value(value: Any) -> float:
    """Return a sortable Unix timestamp, or zero for an absent or invalid GitHub timestamp."""

    clean_value = str(value or "").strip()
    if not clean_value:
        return 0
    normalized = f"{clean_value[:-1]}+00:00" if clean_value.endswith("Z") else clean_value
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return 0


# Reads every Pages-environment deployment needed for exact run matching and latest-state selection.
def pages_deployments(client: Any, owner: str, repo: str, sha: str = "") -> list[dict[str, Any]]:
    """Return repository deployments for the github-pages environment, optionally filtered by SHA."""

    deployments: list[dict[str, Any]] = []
    page = 1
    while True:
        params: dict[str, Any] = {
            "environment": PAGES_ENVIRONMENT,
            "per_page": DEPLOYMENT_PAGE_SIZE,
            "page": page,
        }
        # GitHub performs exact server-side SHA filtering when a selected workflow run is supplied.
        if sha:
            params["sha"] = sha
        payload = client.request("GET", f"/repos/{owner}/{repo}/deployments", params=params)
        if not isinstance(payload, list):
            raise AppError("GitHub returned unexpected deployment data.", "GITHUB_RESPONSE_INVALID")
        rows = [item for item in payload if isinstance(item, dict)]
        deployments.extend(rows)
        if len(payload) < DEPLOYMENT_PAGE_SIZE:
            return deployments
        page += 1


# Reads every status for one deployment so result selection never depends on implicit API ordering.
def deployment_statuses(client: Any, owner: str, repo: str, deployment_id: Any) -> list[dict[str, Any]]:
    """Return all statuses for one GitHub deployment."""

    try:
        clean_id = int(deployment_id)
    except (TypeError, ValueError) as error:
        raise AppError("GitHub returned an invalid deployment id.", "GITHUB_RESPONSE_INVALID") from error
    if clean_id <= 0:
        raise AppError("GitHub returned an invalid deployment id.", "GITHUB_RESPONSE_INVALID")

    statuses: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = client.request(
            "GET",
            f"/repos/{owner}/{repo}/deployments/{clean_id}/statuses",
            params={"per_page": DEPLOYMENT_PAGE_SIZE, "page": page},
        )
        if not isinstance(payload, list):
            raise AppError("GitHub returned unexpected deployment status data.", "GITHUB_RESPONSE_INVALID")
        statuses.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < DEPLOYMENT_PAGE_SIZE:
            return statuses
        page += 1


# Accepts only browser-safe GitHub-provided HTTP targets before they enter an anchor element.
def safe_public_url(value: Any) -> str:
    """Return an HTTP(S) URL suitable for display, or an empty string for any other scheme."""

    candidate = str(value or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return candidate


# Extracts the workflow-run id from a deployment status output link.
def workflow_run_id_from_url(value: Any) -> int | None:
    """Return the run id from a canonical GitHub Actions run or job URL."""

    parsed = urlparse(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    # Canonical run and job links share owner/repo/actions/runs/<id> as their first five path segments.
    if len(parts) < 5 or parts[2:4] != ["actions", "runs"]:
        return None
    try:
        run_id = int(parts[4])
    except ValueError:
        return None
    return run_id if run_id > 0 else None


# Reads the exact workflow revision so a build failure before deployment can still be identified as Pages work.
def workflow_uses_pages_deployment(client: Any, owner: str, repo: str, run: dict[str, Any]) -> bool:
    """Return whether a workflow run's YAML invokes GitHub's official deploy-pages action."""

    run_path = str(run.get("path") or "").strip()
    workflow_path = run_path.rsplit("@", 1)[0]
    # GitHub executes repository workflows only from this directory and these YAML extensions.
    if not workflow_path.startswith(".github/workflows/"):
        return False
    if not workflow_path.lower().endswith((".yml", ".yaml")):
        return False

    encoded_path = quote(workflow_path, safe="/")
    try:
        payload = client.request(
            "GET",
            f"/repos/{owner}/{repo}/contents/{encoded_path}",
            params={"ref": str(run.get("head_sha") or "")},
        )
    except AppError as error:
        # Deleted workflow revisions or missing Contents access cannot establish Pages intent, so avoid guessing.
        if error.details.get("status") in {403, 404}:
            return False
        raise
    if not isinstance(payload, dict) or payload.get("encoding") != "base64":
        raise AppError("GitHub returned unexpected workflow file data.", "GITHUB_RESPONSE_INVALID")
    try:
        encoded_content = re.sub(r"\s+", "", str(payload.get("content") or ""))
        source = base64.b64decode(encoded_content, validate=True).decode("utf-8", errors="replace")
    except (binascii.Error, ValueError) as error:
        raise AppError("GitHub returned invalid workflow file content.", "GITHUB_RESPONSE_INVALID") from error

    return source_uses_pages_deployment(source)


# Finds the newest workflow run whose exact YAML revision deploys through GitHub Pages.
def latest_pages_workflow_run(client: Any, owner: str, repo: str) -> dict[str, Any]:
    """Return the newest recent run that invokes actions/deploy-pages, or an empty record."""

    payload = client.request(
        "GET",
        f"/repos/{owner}/{repo}/actions/runs",
        params={"per_page": 25},
    )
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise AppError("GitHub returned unexpected workflow run data.", "GITHUB_RESPONSE_INVALID")
    ordered_runs = sorted(
        (run for run in runs if isinstance(run, dict)),
        key=lambda item: timestamp_value(item.get("updated_at") or item.get("created_at")),
        reverse=True,
    )
    # The first source-confirmed Pages workflow is the previous action relevant to the setup screen.
    for run in ordered_runs:
        if workflow_uses_pages_deployment(client, owner, repo, run):
            return run
    return {}


# Maps GitHub's deployment status vocabulary into the smaller UI state contract.
def deployment_result(status: dict[str, Any], site: dict[str, Any]) -> dict[str, Any]:
    """Return a safe Pages deployment result with a URL only for successful publication."""

    github_state = str(status.get("state") or "").strip().lower()
    updated_at = status.get("updated_at") or status.get("created_at") or ""
    linked_run_id = workflow_run_id_from_url(status.get("log_url"))
    linked_run_id = linked_run_id or workflow_run_id_from_url(status.get("target_url"))
    if github_state == "success":
        site_url = safe_public_url(status.get("environment_url")) or safe_public_url(site.get("html_url"))
        return {"state": "success", "url": site_url, "updated_at": updated_at, "run_id": linked_run_id}
    if github_state in FAILED_DEPLOYMENT_STATES:
        return {"state": "failure", "url": "", "updated_at": updated_at, "run_id": linked_run_id}
    if github_state in ACTIVE_DEPLOYMENT_STATES:
        return {"state": "building", "url": "", "updated_at": updated_at, "run_id": linked_run_id}
    return {"state": github_state, "url": "", "updated_at": updated_at, "run_id": linked_run_id}


# Falls back to the Pages site status only when no environment deployment exists yet.
def site_status_result(site: dict[str, Any]) -> dict[str, Any]:
    """Return a deployment-like result from GitHub's Pages site status."""

    site_status = str(site.get("status") or "").strip().lower()
    if site_status == "built":
        return {"state": "success", "url": safe_public_url(site.get("html_url")), "updated_at": ""}
    if site_status == "errored":
        return {"state": "failure", "url": "", "updated_at": ""}
    if site_status in {"building", "queued"}:
        return {"state": "building", "url": "", "updated_at": ""}
    return {"state": "", "url": "", "updated_at": ""}


# Returns the newest repository-wide Pages result for the setup screen.
def latest_pages_deployment(client: Any, owner: str, repo: str, site: dict[str, Any]) -> dict[str, Any]:
    """Return the latest github-pages deployment result without exposing stale URLs after failure."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    try:
        deployments = pages_deployments(client, clean_owner, clean_repo)
        if not deployments:
            return site_status_result(site)
        latest = max(deployments, key=lambda item: timestamp_value(item.get("created_at")))
        statuses = deployment_statuses(client, clean_owner, clean_repo, latest.get("id"))
        if not statuses:
            return site_status_result(site)
        latest_status = max(statuses, key=lambda item: timestamp_value(item.get("created_at")))
        return deployment_result(latest_status, site)
    except AppError as error:
        # Existing tokens may predate Deployments read; keep Pages configuration usable and explain the gap.
        if error.details.get("status") == 403:
            return {
                "state": "unavailable",
                "url": "",
                "error": "Grant Deployments read permission to show the latest Pages deployment.",
            }
        raise


# Reconciles the latest deployment with a newer Pages workflow that may have failed before deployment creation.
def latest_pages_status(client: Any, owner: str, repo: str, site: dict[str, Any]) -> dict[str, Any]:
    """Return the latest Pages action state, exposing a URL only after successful deployment."""
    if not site.get("configured"):
        return {"state": "", "url": ""}
    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    deployment = latest_pages_deployment(client, clean_owner, clean_repo, site)
    # Legacy publishing has no user-owned deploy-pages workflow to supersede its deployment result.
    if site.get("build_type") != "workflow":
        return deployment
    try:
        run = latest_pages_workflow_run(client, clean_owner, clean_repo)
    except AppError as error:
        # Existing Deployments permission guidance remains more useful than replacing it with enrichment failure.
        if error.details.get("status") == 403:
            return deployment
        raise
    if not run:
        return deployment
    try:
        run_id = int(run.get("id"))
    except (TypeError, ValueError):
        run_id = 0
    # A status linked directly to this run is authoritative even when run completion updates a few seconds later.
    if run_id > 0 and deployment.get("run_id") == run_id:
        return deployment
    run_time = timestamp_value(run.get("updated_at") or run.get("created_at"))
    deployment_time = timestamp_value(deployment.get("updated_at"))
    # An older run must not replace the result of a newer successful or failed deployment.
    if run_time < deployment_time:
        return deployment
    run_status = str(run.get("status") or "").strip().lower()
    conclusion = str(run.get("conclusion") or "").strip().lower()
    if run_status and run_status != "completed":
        return {"state": "building", "url": "", "updated_at": run.get("updated_at", "")}
    if conclusion in FAILED_WORKFLOW_CONCLUSIONS:
        return {"state": "failure", "url": "", "updated_at": run.get("updated_at", "")}
    if conclusion == "success":
        if deployment.get("state") == "unavailable":
            return deployment
        return {"state": "building", "url": "", "updated_at": run.get("updated_at", "")}
    return deployment


# Resolves one selected workflow run to the exact Pages deployment status whose log points back to that run.
def pages_deployment_for_run(client: Any, owner: str, repo: str, run_id_value: Any) -> dict[str, Any]:
    """Return the selected run's Pages result, or an empty result when it did not deploy Pages."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    try:
        run_id = int(run_id_value)
    except (TypeError, ValueError) as error:
        raise AppError("A valid workflow run id is required.", "WORKFLOW_RUN_ID_INVALID") from error
    if run_id <= 0:
        raise AppError("A valid workflow run id is required.", "WORKFLOW_RUN_ID_INVALID")

    run = client.request("GET", f"/repos/{clean_owner}/{clean_repo}/actions/runs/{run_id}")
    if not isinstance(run, dict) or not str(run.get("head_sha") or "").strip():
        raise AppError("GitHub returned unexpected workflow run data.", "GITHUB_RESPONSE_INVALID")

    try:
        deployments = pages_deployments(client, clean_owner, clean_repo, str(run["head_sha"]))
        site = client.pages_site(clean_owner, clean_repo)
        ordered = sorted(deployments, key=lambda item: timestamp_value(item.get("created_at")), reverse=True)
        # A shared commit can run many workflows, so only a deployment status linked to this run is authoritative.
        for deployment in ordered:
            statuses = deployment_statuses(client, clean_owner, clean_repo, deployment.get("id"))
            ordered_statuses = sorted(
                statuses,
                key=lambda item: timestamp_value(item.get("created_at")),
                reverse=True,
            )
            for status in ordered_statuses:
                linked_run_id = workflow_run_id_from_url(status.get("log_url"))
                linked_run_id = linked_run_id or workflow_run_id_from_url(status.get("target_url"))
                if linked_run_id == run_id:
                    return deployment_result(status, site)
        # A build job can fail before the environment job creates a deployment, so verify the run's exact YAML.
        conclusion = str(run.get("conclusion") or "").strip().lower()
        if conclusion in FAILED_WORKFLOW_CONCLUSIONS and workflow_uses_pages_deployment(
            client,
            clean_owner,
            clean_repo,
            run,
        ):
            return {"state": "failure", "url": ""}
        return {"state": "", "url": ""}
    except AppError as error:
        # Deployment enrichment is supplemental; old tokens must not hide otherwise readable run details.
        if error.details.get("status") == 403:
            return {
                "state": "unavailable",
                "url": "",
                "error": "Grant Deployments read permission to show this Pages deployment.",
            }
        raise
