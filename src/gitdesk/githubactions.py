"""GitHub Actions detail helpers for workflow jobs, artifacts, and annotations."""

from __future__ import annotations

# Standard-library helpers parse timestamps, keep step lookup efficient, and validate canonical URLs.
import re
from bisect import bisect_right
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

# Requests supplies the same authenticated session transport used by the shared GitHub API client.
import requests

# Project services provide safe errors, timeout policy, and repository-path validation.
from gitdesk.errors import AppError
from gitdesk.githubapi import REQUEST_TIMEOUT_SECONDS
from gitdesk.githubserializers import clean_repository_pair


# GitHub paginated detail endpoints all cap per_page at 100.
DETAIL_PAGE_SIZE = 100

# GitHub prefixes downloadable job-log lines with RFC 3339 timestamps that can be matched to reported step times.
LOG_LINE_PATTERN = re.compile(
    r"^\ufeff?(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))"
    r"\s(?P<text>.*)$"
)

# Runner output may contain terminal color and title sequences that have no useful visual meaning in the WebView.
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")

# These conclusions identify the step that owns runner-generated failure records at a shared time boundary.
FAILED_STEP_CONCLUSIONS = {"failure", "cancelled", "timed_out", "startup_failure"}


# Validates a workflow run or check run id before it becomes a REST path segment.
def clean_numeric_id(value: Any, field_name: str, error_code: str) -> int:
    """Return a positive integer id for GitHub detail endpoints."""

    try:
        numeric_id = int(value)
    except (TypeError, ValueError) as error:
        raise AppError(f"A valid {field_name} is required.", error_code) from error
    if numeric_id <= 0:
        raise AppError(f"A valid {field_name} is required.", error_code)
    return numeric_id


# Extracts the check-run identifier from GitHub's canonical URL instead of assuming it equals the workflow job id.
def check_run_id_for_job(job: dict[str, Any]) -> int:
    """Return the check-run id attached to one workflow job."""

    check_run_url = str(job.get("check_run_url") or "").strip()
    path_parts = [part for part in urlparse(check_run_url).path.split("/") if part]
    if len(path_parts) < 2 or path_parts[-2] != "check-runs":
        raise AppError(
            "GitHub did not provide a check run for this workflow job.",
            "WORKFLOW_CHECK_RUN_MISSING",
        )
    return clean_numeric_id(path_parts[-1], "check run id", "WORKFLOW_CHECK_RUN_ID_INVALID")


# Condenses a workflow job step into the fields needed for the live Actions graph.
def serialize_step(step: dict[str, Any]) -> dict[str, Any]:
    """Return a compact workflow job step record."""

    return {
        "name": step.get("name", ""),
        "status": step.get("status", ""),
        "conclusion": step.get("conclusion", ""),
        "number": step.get("number"),
        "started_at": step.get("started_at", ""),
        "completed_at": step.get("completed_at", ""),
    }


# Converts GitHub's RFC 3339 values to comparable UTC instants while tolerating runner fractional precision.
def timestamp_value(value: Any) -> float | None:
    """Return a Unix timestamp for a GitHub time value, or None when the value is invalid."""

    clean_value = str(value or "").strip()
    if not clean_value:
        return None
    normalized = f"{clean_value[:-1]}+00:00" if clean_value.endswith("Z") else clean_value
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


# Converts one downloaded log line into safe display data without discarding its original global line number.
def serialize_log_line(line: str, line_number: int) -> tuple[dict[str, Any], float | None]:
    """Return one displayable job-log line and its parsed timestamp when present."""

    match = LOG_LINE_PATTERN.match(line.rstrip("\r"))
    timestamp_text = match.group("timestamp") if match else ""
    output_text = match.group("text") if match else line.rstrip("\r")
    clean_text = ANSI_ESCAPE_PATTERN.sub("", output_text)
    return {
        "number": line_number,
        "timestamp": timestamp_text,
        "text": clean_text,
    }, timestamp_value(timestamp_text)


# Recognizes runner error commands that GitHub prints in the log and also promotes to annotations.
def is_runner_error(text: str) -> bool:
    """Return whether one plain-text log line is a GitHub runner error command."""

    clean_text = text.lower()
    return "##[error]" in clean_text or clean_text.startswith("::error")


# Recognizes a new run-command group so a shared timestamp can advance from one completed step to the next.
def starts_run_group(text: str) -> bool:
    """Return whether one runner log line clearly starts a new run step."""

    clean_text = text.lower()
    return clean_text.startswith("##[group]run ") or clean_text.startswith("::group::run ")


# Uses step state and explicit runner groups to preserve complete failure output at shared time boundaries.
def partition_job_log(steps: list[dict[str, Any]], log_text: str) -> list[dict[str, Any]]:
    """Return each GitHub step with the downloaded log lines that occurred during that step."""

    serialized_steps = [serialize_step(step) for step in steps if isinstance(step, dict)]
    line_buckets: list[list[dict[str, Any]]] = [[] for _step in serialized_steps]
    if not serialized_steps:
        return []

    step_starts = []
    step_windows = []
    for index, step in enumerate(serialized_steps):
        started_at = timestamp_value(step.get("started_at"))
        if started_at is not None:
            step_starts.append((started_at, index))
            step_windows.append({
                "completed_at": timestamp_value(step.get("completed_at")),
                "conclusion": str(step.get("conclusion") or "").lower(),
                "index": index,
                "started_at": started_at,
            })
    step_starts.sort()
    step_windows.sort(key=lambda item: (item["started_at"], item["index"]))
    start_times = [item[0] for item in step_starts]

    active_index: int | None = None
    preamble: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(log_text.splitlines(), start=1):
        line, line_timestamp = serialize_log_line(raw_line, line_number)
        if line_timestamp is not None:
            candidates = [
                item for item in step_windows
                if item["started_at"] <= line_timestamp
                and (item["completed_at"] is None or line_timestamp <= item["completed_at"])
            ]
            candidate_indices = [item["index"] for item in candidates]
            failed_indices = [
                item["index"] for item in candidates
                if item["conclusion"] in FAILED_STEP_CONCLUSIONS
            ]
            active_failed = (
                active_index is not None
                and serialized_steps[active_index].get("conclusion") in FAILED_STEP_CONCLUSIONS
            )
            if starts_run_group(line["text"]) and candidate_indices:
                active_index = candidate_indices[-1]
            elif active_failed:
                # Framework diagnostics precede the final runner error, so only a new Run group ends this tail.
                pass
            elif is_runner_error(line["text"]) and failed_indices:
                active_index = failed_indices[-1]
            elif active_index not in candidate_indices:
                matched_position = bisect_right(start_times, line_timestamp) - 1
                if matched_position >= 0:
                    active_index = step_starts[matched_position][1]
        if active_index is None:
            preamble.append(line)
        else:
            line_buckets[active_index].append(line)

    # GitHub's runner setup lines can precede the first reported step by milliseconds; keep them with step one.
    if preamble:
        first_index = step_starts[0][1] if step_starts else 0
        line_buckets[first_index] = preamble + line_buckets[first_index]

    return [
        {
            "number": step.get("number"),
            "name": step.get("name", ""),
            "lines": line_buckets[index],
        }
        for index, step in enumerate(serialized_steps)
    ]


# Downloads one official plain-text job log while keeping temporary redirect URLs and credentials out of errors.
def download_job_log(client: Any, owner: str, repo: str, job_id: int) -> str:
    """Return the UTF-8 plain-text log for a GitHub workflow job."""

    url = f"https://api.github.com/repos/{owner}/{repo}/actions/jobs/{job_id}/logs"
    try:
        response = client.session.get(url, allow_redirects=True, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as error:
        raise AppError("Unable to reach the GitHub API.", "GITHUB_NETWORK_FAILED") from error

    if response.status_code == 401:
        message = "GitHub rejected this PAT as invalid, expired, or revoked. Generate a new PAT and paste its value."
        raise AppError(message, "GITHUB_TOKEN_REJECTED", {"status": response.status_code})
    if response.status_code in {404, 410}:
        message = "GitHub job logs are unavailable or have expired."
        raise AppError(message, "WORKFLOW_JOB_LOG_UNAVAILABLE", {"status": response.status_code})
    if response.status_code >= 400:
        message = client.error_message(response)
        raise AppError(message, "GITHUB_API_FAILED", {"status": response.status_code})
    if response.status_code != 200:
        message = "GitHub did not return the workflow job log."
        raise AppError(message, "GITHUB_RESPONSE_INVALID", {"status": response.status_code})
    return response.content.decode("utf-8", errors="replace")


# Fetches current step timing before downloading a job log so output is partitioned without trusting UI metadata.
def workflow_job_logs(client: Any, owner: str, repo: str, job_id_value: Any) -> dict[str, Any]:
    """Return one workflow job's downloaded output partitioned into its reported steps."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    job_id = clean_numeric_id(job_id_value, "workflow job id", "WORKFLOW_JOB_ID_INVALID")
    job = client.request("GET", f"/repos/{clean_owner}/{clean_repo}/actions/jobs/{job_id}")
    if not isinstance(job, dict):
        raise AppError("GitHub returned an unexpected workflow job response.", "GITHUB_RESPONSE_INVALID")
    steps = job.get("steps") or []
    if not isinstance(steps, list):
        raise AppError("GitHub returned unexpected workflow step data.", "GITHUB_RESPONSE_INVALID")
    log_text = download_job_log(client, clean_owner, clean_repo, job_id)
    return {
        "job_id": job_id,
        "steps": partition_job_log(steps, log_text),
    }


# Condenses an annotation into the warning/error fields shown in the Actions detail panel.
def serialize_annotation(annotation: dict[str, Any]) -> dict[str, Any]:
    """Return a compact check-run annotation record."""

    return {
        "path": annotation.get("path", ""),
        "start_line": annotation.get("start_line"),
        "end_line": annotation.get("end_line"),
        "annotation_level": annotation.get("annotation_level", ""),
        "title": annotation.get("title", ""),
        "message": annotation.get("message", ""),
        "raw_details": annotation.get("raw_details", ""),
    }


# Condenses a workflow job while preserving step and annotation detail.
def serialize_job(job: dict[str, Any], annotations: list[dict[str, Any]], annotation_error: str = "") -> dict[str, Any]:
    """Return a compact workflow job record with steps and warnings."""

    steps = job.get("steps") or []
    labels = job.get("labels") or []
    return {
        "id": job.get("id"),
        "name": job.get("name", ""),
        "status": job.get("status", ""),
        "conclusion": job.get("conclusion", ""),
        "started_at": job.get("started_at", ""),
        "completed_at": job.get("completed_at", ""),
        "html_url": job.get("html_url", ""),
        "runner_name": job.get("runner_name", ""),
        "labels": [str(label) for label in labels],
        "steps": [serialize_step(step) for step in steps if isinstance(step, dict)],
        "annotations": annotations,
        "annotation_error": annotation_error,
    }


# Condenses workflow artifacts into the fields needed to show uploaded build outputs.
def serialize_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return a compact workflow-run artifact record."""

    return {
        "id": artifact.get("id"),
        "name": artifact.get("name", ""),
        "size": int(artifact.get("size_in_bytes") or 0),
        "expired": bool(artifact.get("expired", False)),
        "created_at": artifact.get("created_at", ""),
        "updated_at": artifact.get("updated_at", ""),
        "expires_at": artifact.get("expires_at", ""),
        "archive_download_url": artifact.get("archive_download_url", ""),
    }


# Fetches current jobs for a workflow run, including each job's step state.
def workflow_jobs(client: Any, owner: str, repo: str, run_id: int) -> list[dict[str, Any]]:
    """Return workflow jobs for a run from GitHub's Actions jobs endpoint."""

    jobs: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = client.request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
            params={"filter": "latest", "per_page": DETAIL_PAGE_SIZE, "page": page},
        )
        if not isinstance(payload, dict):
            raise AppError("GitHub returned an unexpected workflow jobs response.", "GITHUB_RESPONSE_INVALID")
        page_jobs = payload.get("jobs") or []
        jobs.extend(job for job in page_jobs if isinstance(job, dict))
        if len(page_jobs) < DETAIL_PAGE_SIZE:
            return jobs
        page += 1


# Fetches artifacts uploaded by the workflow run so the app can show build outputs as they appear.
def workflow_artifacts(client: Any, owner: str, repo: str, run_id: int) -> list[dict[str, Any]]:
    """Return artifacts for a workflow run from GitHub's Actions artifacts endpoint."""

    artifacts: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = client.request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts",
            params={"per_page": DETAIL_PAGE_SIZE, "direction": "desc", "page": page},
        )
        if not isinstance(payload, dict):
            raise AppError("GitHub returned an unexpected workflow artifacts response.", "GITHUB_RESPONSE_INVALID")
        page_artifacts = payload.get("artifacts") or []
        artifacts.extend(serialize_artifact(item) for item in page_artifacts if isinstance(item, dict))
        if len(page_artifacts) < DETAIL_PAGE_SIZE:
            return artifacts
        page += 1


# Fetches check-run annotations for one job, returning a readable permission error without hiding jobs.
def job_annotations(client: Any, owner: str, repo: str, check_run_id: int) -> tuple[list[dict[str, Any]], str]:
    """Return annotations for one workflow job and a non-empty error message when unavailable."""

    annotations: list[dict[str, Any]] = []
    page = 1
    try:
        while True:
            payload = client.request(
                "GET",
                f"/repos/{owner}/{repo}/check-runs/{check_run_id}/annotations",
                params={"per_page": DETAIL_PAGE_SIZE, "page": page},
            )
            if not isinstance(payload, list):
                raise AppError("GitHub returned an unexpected check annotations response.", "GITHUB_RESPONSE_INVALID")
            annotations.extend(serialize_annotation(item) for item in payload if isinstance(item, dict))
            if len(payload) < DETAIL_PAGE_SIZE:
                return annotations, ""
            page += 1
    except AppError as error:
        # Fine-grained PATs cannot call the Checks API, so preserve supported Actions data without false guidance.
        if error.details.get("status") == 403:
            message = "GitHub denied check annotations. Fine-grained PATs cannot access the Checks API."
            return [], message
        return [], error.message


# Builds the full live detail payload for the selected workflow run.
def workflow_run_detail(client: Any, owner: str, repo: str, run_id_value: Any) -> dict[str, Any]:
    """Return jobs, artifacts, and annotations for one workflow run."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    run_id = clean_numeric_id(run_id_value, "workflow run id", "WORKFLOW_RUN_ID_INVALID")
    jobs = []
    annotation_errors = []
    for job in workflow_jobs(client, clean_owner, clean_repo, run_id):
        clean_numeric_id(job.get("id"), "workflow job id", "WORKFLOW_JOB_ID_INVALID")
        try:
            check_run_id = check_run_id_for_job(job)
            annotations, annotation_error = job_annotations(client, clean_owner, clean_repo, check_run_id)
        except AppError as error:
            annotations = []
            annotation_error = error.message
        if annotation_error:
            annotation_errors.append({"job": job.get("name", ""), "message": annotation_error})
        jobs.append(serialize_job(job, annotations, annotation_error))

    artifacts = workflow_artifacts(client, clean_owner, clean_repo, run_id)
    annotation_levels = [
        str(annotation.get("annotation_level") or "").lower()
        for job in jobs
        for annotation in job["annotations"]
    ]
    return {
        "run_id": run_id,
        "jobs": jobs,
        "artifacts": artifacts,
        "warning_count": annotation_levels.count("warning"),
        "error_count": annotation_levels.count("failure"),
        "notice_count": annotation_levels.count("notice"),
        "annotation_errors": annotation_errors,
    }
