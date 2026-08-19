"""Regression coverage for GitHub Actions annotations and expandable workflow job logs."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from gitdesk.errors import AppError
from gitdesk.githubactions import partition_job_log, workflow_job_logs, workflow_run_detail


# FakeActionsClient returns one workflow job whose canonical check-run id differs from its job id.
class FakeActionsClient:
    """Record detail API paths and return deterministic jobs, annotations, and artifacts."""

    # Initializes an empty request log used to verify the exact check-run endpoint.
    def __init__(self, fail_annotations: bool = False) -> None:
        """Create a fake client with optional annotation permission failure."""

        self.paths: list[str] = []
        self.fail_annotations = fail_annotations

    # Returns the minimal GitHub payload for each workflow detail endpoint.
    def request(self, method: str, path: str, params: dict | None = None) -> object:
        """Record one request and return the matching Actions or Checks response."""

        self.paths.append(path)
        if path.endswith("/actions/runs/7/jobs"):
            return {
                "jobs": [{
                    "id": 11,
                    "name": "build",
                    "status": "completed",
                    "conclusion": "failure",
                    "check_run_url": "https://api.github.com/repos/octocat/example/check-runs/22",
                    "steps": [],
                }],
            }
        if path.endswith("/check-runs/22/annotations"):
            if self.fail_annotations:
                raise AppError("Resource not accessible by personal access token", "GITHUB_API_FAILED", {
                    "status": 403,
                })
            return [
                {"annotation_level": "warning", "message": "Deprecated API", "path": "app.py"},
                {"annotation_level": "failure", "message": "Test failed", "path": "tests/test_app.py"},
            ]
        if path.endswith("/actions/runs/7/artifacts"):
            return {"artifacts": []}
        raise AssertionError(f"Unexpected workflow detail endpoint: {path}")


# FakeLogResponse provides the requests fields consumed by the authenticated plain-text download boundary.
class FakeLogResponse:
    """Represent one deterministic workflow job-log HTTP response."""

    # Stores a status and UTF-8 body without exposing any credential-bearing request metadata.
    def __init__(self, status_code: int, body: str = "") -> None:
        """Create a fake response from an HTTP status and plain-text body."""

        self.status_code = status_code
        self.content = body.encode("utf-8")


# FakeLogSession records the official job-log URL and returns a configured plain-text response.
class FakeLogSession:
    """Provide the requests-session surface used by workflow job-log downloads."""

    # Initializes one response and an empty URL record for endpoint assertions.
    def __init__(self, response: FakeLogResponse) -> None:
        """Create a fake session that always returns the supplied response."""

        self.response = response
        self.urls: list[str] = []

    # Records redirect and timeout options so regression coverage protects the expiring download flow.
    def get(self, url: str, allow_redirects: bool, timeout: int) -> FakeLogResponse:
        """Return the configured job-log response after recording its request URL."""

        self.urls.append(url)
        if not allow_redirects or timeout <= 0:
            raise AssertionError("Workflow job logs must follow redirects with a finite timeout.")
        return self.response


# FakeLogClient returns authoritative step timing and delegates the plain-text download to FakeLogSession.
class FakeLogClient:
    """Provide the GitHub client surfaces needed to fetch and partition one workflow job log."""

    # Creates two sequential steps and a configurable job-log HTTP response.
    def __init__(self, status_code: int = 200, body: str = "") -> None:
        """Create a fake client for one job-log request."""

        self.session = FakeLogSession(FakeLogResponse(status_code, body))
        self.paths: list[str] = []

    # Returns job metadata from the official job endpoint so UI-provided step timing is never trusted.
    def request(self, method: str, path: str, params: dict | None = None) -> object:
        """Return two ordered workflow steps for job 11."""

        self.paths.append(path)
        if method == "GET" and path.endswith("/actions/jobs/11"):
            return {
                "id": 11,
                "steps": [
                    {
                        "name": "Set up job",
                        "number": 1,
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": "2026-07-15T10:00:00Z",
                        "completed_at": "2026-07-15T10:00:02Z",
                    },
                    {
                        "name": "Run tests",
                        "number": 2,
                        "status": "completed",
                        "conclusion": "failure",
                        "started_at": "2026-07-15T10:00:02Z",
                        "completed_at": "2026-07-15T10:00:04Z",
                    },
                ],
            }
        raise AssertionError(f"Unexpected workflow job endpoint: {path}")

    # Returns a safe generic message for unexpected HTTP failures outside the explicit expiry branch.
    def error_message(self, response: FakeLogResponse) -> str:
        """Return a deterministic safe error message for a failed fake response."""

        return f"GitHub API request failed with HTTP {response.status_code}."


# WorkflowRunDetailTests protects the data path that fills the Actions warnings and errors field.
class WorkflowRunDetailTests(unittest.TestCase):
    """Verify check-run annotations remain visible with their correct severity."""

    # Confirms the canonical check_run_url id, rather than the workflow job id, owns annotations.
    def test_detail_uses_check_run_url_and_counts_warning_levels(self) -> None:
        """Fetch annotations from check run 22 and preserve one warning plus one failure."""

        client = FakeActionsClient()

        detail = workflow_run_detail(client, "octocat", "example", 7)

        self.assertIn("/repos/octocat/example/check-runs/22/annotations", client.paths)
        self.assertNotIn("/repos/octocat/example/check-runs/11/annotations", client.paths)
        self.assertEqual(detail["warning_count"], 1)
        self.assertEqual(detail["error_count"], 1)
        self.assertEqual(len(detail["jobs"][0]["annotations"]), 2)
        self.assertEqual(detail["annotation_errors"], [])

    # Confirms permission failures reach the frontend instead of looking like an empty warning list.
    def test_detail_preserves_annotation_api_error(self) -> None:
        """Return a visible per-job annotation error when GitHub rejects Checks access."""

        detail = workflow_run_detail(FakeActionsClient(fail_annotations=True), "octocat", "example", 7)

        expected_error = "GitHub denied check annotations. Fine-grained PATs cannot access the Checks API."
        self.assertEqual(detail["jobs"][0]["annotations"], [])
        self.assertEqual(detail["jobs"][0]["annotation_error"], expected_error)
        self.assertEqual(detail["annotation_errors"], [{"job": "build", "message": expected_error}])


# WorkflowJobLogTests protects the on-demand download and timestamp-to-step mapping used by disclosures.
class WorkflowJobLogTests(unittest.TestCase):
    """Verify real job output is downloaded once and assigned to the correct reported step."""

    # Confirms preamble, continuation, group, and ANSI-colored lines retain order under the correct steps.
    def test_job_log_download_partitions_output_by_step_start_time(self) -> None:
        """Download the official plain-text job log and partition it using GitHub step timestamps."""

        body = "\n".join([
            "2026-07-15T09:59:59.9000000Z Prepare runner",
            "continued setup output",
            "2026-07-15T10:00:02.0000000Z ##[group]Run tests",
            "2026-07-15T10:00:03Z \x1b[31m##[error]Tests failed\x1b[0m",
        ])
        client = FakeLogClient(body=body)

        result = workflow_job_logs(client, "octocat", "example", 11)

        expected_url = "https://api.github.com/repos/octocat/example/actions/jobs/11/logs"
        self.assertEqual(client.paths, ["/repos/octocat/example/actions/jobs/11"])
        self.assertEqual(client.session.urls, [expected_url])
        self.assertEqual([line["number"] for line in result["steps"][0]["lines"]], [1, 2])
        self.assertEqual(result["steps"][0]["lines"][1]["text"], "continued setup output")
        self.assertEqual(result["steps"][1]["lines"][0]["text"], "##[group]Run tests")
        self.assertEqual(result["steps"][1]["lines"][1]["text"], "##[error]Tests failed")

    # Confirms the pure partitioner returns honest empty output instead of inventing console content.
    def test_empty_job_log_preserves_reported_steps(self) -> None:
        """Return every reported step with an empty line list when GitHub's job log is empty."""

        client = FakeLogClient()
        job = client.request("GET", "/repos/octocat/example/actions/jobs/11")

        outputs = partition_job_log(job["steps"], "")

        self.assertEqual([output["number"] for output in outputs], [1, 2])
        self.assertEqual([output["lines"] for output in outputs], [[], []])

    # Protects plain framework diagnostics before the final runner error at a shared cleanup boundary.
    def test_failed_step_keeps_errors_at_shared_cleanup_boundary(self) -> None:
        """Keep unittest diagnostics and the exit-code record under the failed test step."""

        steps = [
            {
                "name": "Run Python tests",
                "number": 1,
                "status": "completed",
                "conclusion": "failure",
                "started_at": "2026-07-15T10:00:00Z",
                "completed_at": "2026-07-15T10:00:03Z",
            },
            {
                "name": "Complete job",
                "number": 2,
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-07-15T10:00:03Z",
                "completed_at": "2026-07-15T10:00:04Z",
            },
        ]
        body = "\n".join([
            "2026-07-15T10:00:02.900Z Running project regression tests",
            "2026-07-15T10:00:03.010Z FAIL: test_rendered_error (tests.test_actions.ActionsTests)",
            "2026-07-15T10:00:03.020Z AssertionError: expected rendered error output",
            "2026-07-15T10:00:03.050Z ##[error]Process completed with exit code 1.",
            "2026-07-15T10:00:03.060Z ##[group]Run cleanup",
            "2026-07-15T10:00:03.100Z Cleanup complete",
        ])

        outputs = partition_job_log(steps, body)

        self.assertEqual([line["number"] for line in outputs[0]["lines"]], [1, 2, 3, 4])
        self.assertEqual([line["number"] for line in outputs[1]["lines"]], [5, 6])
        self.assertEqual(outputs[0]["lines"][-1]["text"], "##[error]Process completed with exit code 1.")

    # Confirms the complete returned step log participates in page flow instead of a short nested viewport.
    def test_step_log_styles_do_not_cap_failure_output_height(self) -> None:
        """Keep every expanded console line visible through the containing Actions page scroll."""

        css_path = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui" / "actions-step-logs.css"
        stylesheet = css_path.read_text(encoding="utf-8")
        log_blocks = re.findall(r"\.action-step-log-lines\s*\{(?P<body>.*?)\}", stylesheet, flags=re.DOTALL)

        self.assertTrue(log_blocks)
        self.assertTrue(all("max-height" not in block for block in log_blocks))
        self.assertIn("overflow: auto", log_blocks[0])

    # Confirms expired logs produce the localized code consumed by the disclosure's retryable error state.
    def test_expired_job_log_returns_specific_unavailable_error(self) -> None:
        """Raise WORKFLOW_JOB_LOG_UNAVAILABLE when GitHub reports an expired job log."""

        with self.assertRaises(AppError) as context:
            workflow_job_logs(FakeLogClient(status_code=410), "octocat", "example", 11)

        self.assertEqual(context.exception.code, "WORKFLOW_JOB_LOG_UNAVAILABLE")
        self.assertEqual(context.exception.details, {"status": 410})


# ActionsRefreshSourceTests protects the desktop-only refresh lifecycle without executing browser JavaScript.
class ActionsRefreshSourceTests(unittest.TestCase):
    """Verify post-push refreshes remain bounded, exact, queued, and correctly assembled."""

    # Confirms pushed revisions use bounded backoff and exact workflow-run SHA matching.
    def test_post_push_refresh_uses_bounded_exact_sha_reconciliation(self) -> None:
        """Require finite retry delays and a normalized exact-SHA completion boundary."""

        root = Path(__file__).resolve().parents[1]
        source = (root / "src/gitdesk/ui/actions-refresh.js").read_text(encoding="utf-8")

        self.assertIn("const POST_PUSH_RETRY_MS = [1500, 3000, 5000, 8000, 13000, 21000];", source)
        self.assertIn("runs.some((run) => normalizeSha(run.sha) === expectedSha)", source)
        self.assertIn("retryIndex >= POST_PUSH_RETRY_MS.length", source)

    # Confirms a refresh requested during another native Actions call is replayed after it settles.
    def test_actions_controller_queues_busy_refresh_requests(self) -> None:
        """Require post-push and tab refresh requests to survive an in-flight list request."""

        root = Path(__file__).resolve().parents[1]
        source = (root / "src/gitdesk/ui/actions.js").read_text(encoding="utf-8")

        self.assertIn("if (options.queueIfBusy) state.refreshQueued = true;", source)
        self.assertIn("if (state.refreshQueued)", source)
        self.assertIn("refreshCoordinator.refreshSettled();", source)

    # Confirms every push caller supplies a commit SHA and both frontend entry paths load the coordinator first.
    def test_push_sha_and_refresh_asset_wiring(self) -> None:
        """Keep exact revision handoff and classic-script dependency order synchronized."""

        root = Path(__file__).resolve().parents[1]
        overview = (root / "src/gitdesk/ui/overview.js").read_text(encoding="utf-8")
        pages = (root / "src/gitdesk/ui/pages.js").read_text(encoding="utf-8")
        index_source = (root / "src/gitdesk/ui/index.html").read_text(encoding="utf-8")
        frontend = (root / "src/gitdesk/frontend.py").read_text(encoding="utf-8")

        self.assertIn('refreshAfterPush(data.hexsha || "")', overview)
        self.assertIn('refreshAfterPush(data.head_sha || "")', overview)
        self.assertIn("refreshAfterPush(selectedCommit)", pages)
        self.assertLess(index_source.index("actions-refresh.js"), index_source.index('src="./actions.js"'))
        self.assertLess(frontend.index('"actions-refresh.js"'), frontend.index('"actions.js"'))


if __name__ == "__main__":
    unittest.main()
