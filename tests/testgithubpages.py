"""Regression coverage for GitHub Pages sources and Actions deployment-result matching."""

from __future__ import annotations

import base64
import unittest

from gitdesk.errors import AppError
from gitdesk.githubpages import (
    configure_pages_site,
    latest_pages_deployment,
    latest_pages_status,
    pages_deployment_for_run,
    workflow_run_id_from_url,
)


# FakePagesClient records exact REST calls while returning deterministic Pages and deployment data.
class FakePagesClient:
    """Provide the authenticated client surface used by the GitHub Pages service."""

    # Stores configured response fixtures and every request for contract assertions.
    def __init__(self, configured: bool = True) -> None:
        """Initialize a fake Pages client with an optional existing remote site."""

        self.configured = configured
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []
        self.deployments: list[dict] = []
        self.statuses: dict[int, list[dict]] = {}
        self.run_sha = "a" * 40
        self.run_conclusion = "success"
        self.run_path = ".github/workflows/pages.yml@main"
        self.workflow_source = ""
        self.recent_runs: list[dict] = []
        self.deployment_error: AppError | None = None

    # Returns the compact site shape produced by GitHubApiClient.pages_site.
    def pages_site(self, owner: str, repo: str) -> dict:
        """Return one configured or unconfigured Pages site fixture."""

        if not self.configured:
            return {"configured": False}
        return {
            "configured": True,
            "status": "built",
            "html_url": "https://octocat.github.io/example/",
            "build_type": "workflow",
            "source": {"branch": "", "path": ""},
        }

    # Routes only the documented Pages, Actions, deployment, and deployment-status requests under test.
    def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> object:
        """Record one request and return its configured fake payload."""

        self.calls.append((method, path, params, json_body))
        if path.endswith("/pages") and method in {"POST", "PUT"}:
            self.configured = True
            return {}
        if path.endswith("/actions/runs/77"):
            return {
                "id": 77,
                "head_sha": self.run_sha,
                "path": self.run_path,
                "conclusion": self.run_conclusion,
            }
        if path.endswith("/actions/runs"):
            return {"workflow_runs": self.recent_runs}
        if "/contents/.github/workflows/" in path:
            encoded = base64.b64encode(self.workflow_source.encode("utf-8")).decode("ascii")
            return {"encoding": "base64", "content": encoded}
        if path.endswith("/deployments"):
            if self.deployment_error:
                raise self.deployment_error
            return self.deployments
        if "/deployments/" in path and path.endswith("/statuses"):
            deployment_id = int(path.split("/")[-2])
            return self.statuses.get(deployment_id, [])
        raise AssertionError(f"Unexpected GitHub Pages endpoint: {method} {path}")


# GitHubPagesConfigurationTests protects the mutually exclusive request bodies GitHub documents.
class GitHubPagesConfigurationTests(unittest.TestCase):
    """Verify branch publishing and workflow publishing send distinct remote configurations."""

    # Confirms Actions mode creates Pages without a misleading source branch payload.
    def test_workflow_source_omits_branch_and_path(self) -> None:
        """Send only build_type workflow when a repository uses existing YAML automation."""

        client = FakePagesClient(configured=False)

        configure_pages_site(client, "octocat", "example", "workflow", "main", "/docs")

        mutation = client.calls[0]
        self.assertEqual(mutation[:2], ("POST", "/repos/octocat/example/pages"))
        self.assertEqual(mutation[3], {"build_type": "workflow"})

    # Confirms branch mode updates both fields GitHub requires for legacy publishing.
    def test_legacy_source_includes_branch_and_path(self) -> None:
        """Send build_type legacy with the selected branch and supported source folder."""

        client = FakePagesClient(configured=True)

        configure_pages_site(client, "octocat", "example", "legacy", "main", "/docs")

        mutation = client.calls[0]
        self.assertEqual(mutation[:2], ("PUT", "/repos/octocat/example/pages"))
        self.assertEqual(mutation[3], {
            "build_type": "legacy",
            "source": {"branch": "main", "path": "/docs"},
        })


# GitHubPagesDeploymentTests protects link gating and exact workflow-run association.
class GitHubPagesDeploymentTests(unittest.TestCase):
    """Verify only successful, authoritative Pages deployments expose a published-site link."""

    # Confirms a removed or never-created Pages site cannot expose a historical deployment link.
    def test_unconfigured_site_has_no_deployment_result(self) -> None:
        """Return no publication state without querying historical deployments."""

        client = FakePagesClient(configured=False)

        result = latest_pages_status(client, "octocat", "example", client.pages_site("octocat", "example"))

        self.assertEqual(result, {"state": "", "url": ""})
        self.assertEqual(client.calls, [])

    # Confirms a failed latest deployment suppresses the older site's otherwise valid URL.
    def test_latest_failure_never_returns_stale_site_link(self) -> None:
        """Return failure with an empty URL when GitHub's newest deployment status failed."""

        client = FakePagesClient()
        client.deployments = [{"id": 10, "created_at": "2026-07-15T10:00:00Z"}]
        client.statuses[10] = [{
            "state": "failure",
            "environment_url": "https://octocat.github.io/example/",
            "created_at": "2026-07-15T10:01:00Z",
        }]
        site = client.pages_site("octocat", "example")

        result = latest_pages_deployment(client, "octocat", "example", site)

        self.assertEqual(result["state"], "failure")
        self.assertEqual(result["url"], "")

    # Confirms shared-SHA deployments are distinguished by the status link to the selected workflow run.
    def test_selected_run_uses_only_its_linked_deployment_status(self) -> None:
        """Return the site URL from the deployment whose log_url names workflow run 77."""

        client = FakePagesClient()
        client.deployments = [
            {"id": 10, "created_at": "2026-07-15T10:00:00Z"},
            {"id": 11, "created_at": "2026-07-15T10:02:00Z"},
        ]
        client.statuses[10] = [{
            "state": "failure",
            "log_url": "https://github.com/octocat/example/actions/runs/66",
            "created_at": "2026-07-15T10:01:00Z",
        }]
        client.statuses[11] = [{
            "state": "success",
            "environment_url": "https://octocat.github.io/example/",
            "log_url": "https://github.com/octocat/example/actions/runs/77/job/99",
            "created_at": "2026-07-15T10:03:00Z",
        }]

        result = pages_deployment_for_run(client, "octocat", "example", 77)

        self.assertEqual(result["state"], "success")
        self.assertEqual(result["url"], "https://octocat.github.io/example/")

    # Confirms the workflow source identifies a Pages failure before any deployment record exists.
    def test_failed_pages_build_without_deployment_returns_failure(self) -> None:
        """Return failure when the selected run's exact YAML uses actions/deploy-pages."""

        client = FakePagesClient()
        client.run_conclusion = "failure"
        client.workflow_source = "jobs:\n  deploy:\n    steps:\n      - uses: actions/deploy-pages@v4\n"

        result = pages_deployment_for_run(client, "octocat", "example", 77)

        self.assertEqual(result, {"state": "failure", "url": ""})

    # Confirms text inside a shell script is not mistaken for an executable workflow action step.
    def test_failed_run_script_mention_is_not_a_pages_deployment(self) -> None:
        """Ignore actions/deploy-pages text inside a multiline run script."""

        client = FakePagesClient()
        client.run_conclusion = "failure"
        client.workflow_source = (
            "jobs:\n  build:\n    steps:\n      - run: |\n"
            "          - uses: actions/deploy-pages@v4\n"
        )

        result = pages_deployment_for_run(client, "octocat", "example", 77)

        self.assertEqual(result, {"state": "", "url": ""})

    # Confirms malformed workflow source cannot break the selected run detail screen.
    def test_invalid_yaml_does_not_claim_pages_failure(self) -> None:
        """Treat structurally invalid YAML as unproven Pages intent."""

        client = FakePagesClient()
        client.run_conclusion = "failure"
        client.workflow_source = "jobs: [unterminated"

        result = pages_deployment_for_run(client, "octocat", "example", 77)

        self.assertEqual(result, {"state": "", "url": ""})

    # Confirms a newer failed Pages action overrides the URL from an older successful deployment on setup.
    def test_latest_pages_action_failure_overrides_older_deployment(self) -> None:
        """Show failure when the newest source-confirmed Pages workflow completed unsuccessfully."""

        client = FakePagesClient()
        client.deployments = [{"id": 10, "created_at": "2026-07-15T10:00:00Z"}]
        client.statuses[10] = [{
            "state": "success",
            "environment_url": "https://octocat.github.io/example/",
            "created_at": "2026-07-15T10:01:00Z",
        }]
        client.workflow_source = "jobs:\n  deploy:\n    steps:\n      - uses: actions/deploy-pages@v4\n"
        client.recent_runs = [{
            "id": 77,
            "head_sha": client.run_sha,
            "path": client.run_path,
            "status": "completed",
            "conclusion": "failure",
            "updated_at": "2026-07-15T10:05:00Z",
        }]
        site = client.pages_site("octocat", "example")

        result = latest_pages_status(client, "octocat", "example", site)

        self.assertEqual(result["state"], "failure")
        self.assertEqual(result["url"], "")

    # Confirms the setup page receives the published URL when the latest status links to the latest Pages run.
    def test_latest_pages_action_success_returns_clickable_target(self) -> None:
        """Keep the successful environment URL when the deployment status names the latest workflow run."""

        client = FakePagesClient()
        client.deployments = [{"id": 10, "created_at": "2026-07-15T10:00:00Z"}]
        client.statuses[10] = [{
            "state": "success",
            "environment_url": "https://octocat.github.io/example/",
            "log_url": "https://github.com/octocat/example/actions/runs/77",
            "created_at": "2026-07-15T10:01:00Z",
        }]
        client.workflow_source = "jobs:\n  deploy:\n    steps:\n      - uses: actions/deploy-pages@v4\n"
        client.recent_runs = [{
            "id": 77,
            "head_sha": client.run_sha,
            "path": client.run_path,
            "status": "completed",
            "conclusion": "success",
            "updated_at": "2026-07-15T10:02:00Z",
        }]
        site = client.pages_site("octocat", "example")

        result = latest_pages_status(client, "octocat", "example", site)

        self.assertEqual(result["state"], "success")
        self.assertEqual(result["url"], "https://octocat.github.io/example/")

    # Confirms older PATs produce an actionable supplemental state instead of hiding workflow details.
    def test_deployment_permission_failure_is_non_fatal(self) -> None:
        """Return unavailable when GitHub denies Deployments read permission."""

        client = FakePagesClient()
        client.deployment_error = AppError(
            "Resource not accessible by personal access token",
            "GITHUB_API_FAILED",
            {"status": 403},
        )

        result = pages_deployment_for_run(client, "octocat", "example", 77)

        self.assertEqual(result["state"], "unavailable")
        self.assertIn("Deployments read", result["error"])

    # Confirms Actions data can still prove failure when an older PAT cannot read deployment records.
    def test_latest_source_confirmed_failure_survives_missing_deployments_permission(self) -> None:
        """Return failure for the newest Pages workflow even when deployment enrichment is unavailable."""

        client = FakePagesClient()
        client.deployment_error = AppError(
            "Resource not accessible by personal access token",
            "GITHUB_API_FAILED",
            {"status": 403},
        )
        client.workflow_source = "jobs:\n  deploy:\n    steps:\n      - uses: actions/deploy-pages@v4\n"
        client.recent_runs = [{
            "id": 77,
            "head_sha": client.run_sha,
            "path": client.run_path,
            "status": "completed",
            "conclusion": "failure",
            "updated_at": "2026-07-15T10:05:00Z",
        }]

        result = latest_pages_status(client, "octocat", "example", client.pages_site("octocat", "example"))

        self.assertEqual(result["state"], "failure")
        self.assertEqual(result["url"], "")

    # Confirms both workflow-run and workflow-job links resolve to the owning run id.
    def test_workflow_run_url_parser_accepts_job_links(self) -> None:
        """Extract run 77 from the canonical deployment log URL used by GitHub Actions."""

        url = "https://github.com/octocat/example/actions/runs/77/job/99"

        self.assertEqual(workflow_run_id_from_url(url), 77)


if __name__ == "__main__":
    unittest.main()
