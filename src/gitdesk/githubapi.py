"""GitHub REST API integration for repositories, workflow runs, and releases."""

from __future__ import annotations

from typing import Any

import requests

from gitdesk.accounts import clean_login
from gitdesk.errors import AppError
from gitdesk.githubrelease import release_payload
from gitdesk.githubserializers import (
    clean_commit_sha, clean_repository_pair, clean_tag_name,
    serialize_commit, serialize_pages_site, serialize_release,
    serialize_repository, serialize_tag_result, serialize_workflow_run,
)
from gitdesk.patstatus import token_expiration_from_headers


# GitHub keeps REST behavior stable through explicit API version headers.
GITHUB_API_VERSION = "2022-11-28"

# Network calls need a timeout so a hung connection cannot pin a worker thread forever.
REQUEST_TIMEOUT_SECONDS = 25

# GitHub uses this generic message when a fine-grained PAT lacks an endpoint permission.
TOKEN_PERMISSION_MESSAGE = "Resource not accessible by personal access token"


# Detects GitHub's fine-grained PAT permission failure so feature methods can explain the fix.
def is_token_permission_error(error: AppError) -> bool:
    """Return True when GitHub rejected the active token for missing permissions."""

    return error.code == "GITHUB_API_FAILED" and TOKEN_PERMISSION_MESSAGE in error.message


# GitHubApiClient wraps the REST endpoints needed by the desktop UI.
class GitHubApiClient:
    """Call GitHub REST endpoints with token authentication and structured error handling."""

    # Creates a requests session with GitHub's recommended headers and a bearer token.
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.token_expires_at = ""
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": "GitDesk/0.1",
            }
        )

    # Performs a REST request and returns decoded JSON while sanitizing HTTP and network failures.
    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Return decoded GitHub API JSON for a method/path request."""

        url = f"https://api.github.com{path}"
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as error:
            raise AppError("Unable to reach the GitHub API.", "GITHUB_NETWORK_FAILED") from error

        expiration = token_expiration_from_headers(response.headers)
        self.token_expires_at = expiration or self.token_expires_at

        # Authentication rejection means GitHub did not accept the PAT, independent of local credential storage.
        if response.status_code == 401:
            raise AppError(
                "GitHub rejected this PAT as invalid, expired, or revoked. Generate a new PAT and paste its value.",
                "GITHUB_TOKEN_REJECTED",
                {"status": response.status_code},
            )
        if response.status_code >= 400:
            message = self.error_message(response)
            raise AppError(message, "GITHUB_API_FAILED", {"status": response.status_code})

        if not response.content:
            return {}

        try:
            return response.json()
        except ValueError as error:
            raise AppError("GitHub returned a non-JSON response.", "GITHUB_RESPONSE_INVALID") from error

    # Extracts GitHub's error message without returning request headers or credential-bearing data.
    def error_message(self, response: requests.Response) -> str:
        """Return a safe GitHub error message from an HTTP response."""

        try:
            payload = response.json()
        except ValueError:
            return f"GitHub API request failed with HTTP {response.status_code}."

        message = payload.get("message") if isinstance(payload, dict) else ""
        if message:
            return f"GitHub API request failed: {message}"
        return f"GitHub API request failed with HTTP {response.status_code}."

    # Validates the stored token by asking GitHub for the authenticated user profile.
    def current_user(self) -> dict[str, Any]:
        """Return basic account information for the authenticated token."""

        payload = self.request("GET", "/user")
        return {
            "id": payload.get("id", ""), "login": payload.get("login", ""), "name": payload.get("name", ""),
            "email": payload.get("email", ""), "html_url": payload.get("html_url", ""),
        }

    # Resolves the explicit PAT target as either the authenticated user or a GitHub organization.
    def resource_owner(self, login: str) -> dict[str, str]:
        """Return canonical login, type, and profile URL for one PAT resource-owner slug."""

        cleaned_login = clean_login(login)
        payload = self.request("GET", f"/users/{cleaned_login}")
        if not isinstance(payload, dict):
            raise AppError("GitHub returned an unexpected resource owner response.", "GITHUB_RESPONSE_INVALID")
        owner_type = str(payload.get("type") or "").strip()
        if owner_type not in {"User", "Organization"}:
            raise AppError("GitHub returned an invalid PAT resource owner.", "PAT_RESOURCE_OWNER_INVALID")
        return {
            "login": clean_login(str(payload.get("login") or cleaned_login)),
            "type": owner_type, "html_url": str(payload.get("html_url") or "").strip(),
        }

    # Lists every repository visible to the authenticated user, following GitHub pagination.
    def repositories(self) -> list[dict[str, Any]]:
        """Return repositories accessible to the authenticated account."""

        repositories: list[dict[str, Any]] = []
        page = 1
        page_size = 100
        while True:
            payload = self.request(
                "GET",
                "/user/repos",
                params={
                    "visibility": "all",
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": page_size,
                    "page": page,
                },
            )
            if not isinstance(payload, list):
                raise AppError("GitHub returned an unexpected repositories response.", "GITHUB_RESPONSE_INVALID")

            repositories.extend(serialize_repository(repository) for repository in payload)
            if len(payload) < page_size:
                return repositories
            page += 1

    # Reads one repository by owner/name so publish flows can reuse existing repos safely.
    def repository(self, owner: str, repo: str) -> dict[str, Any]:
        """Return one GitHub repository record."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        payload = self.request("GET", f"/repos/{clean_owner}/{clean_repo}")
        if not isinstance(payload, dict):
            raise AppError("GitHub returned an unexpected repository response.", "GITHUB_RESPONSE_INVALID")
        return serialize_repository(payload)

    # Creates a repository for the authenticated user or an organization owner.
    def create_repository(self, owner: str, repo: str, private: bool = False) -> dict[str, Any]:
        """Create a GitHub repository and return its compact metadata."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        user = self.current_user()
        endpoint = "/user/repos" if user["login"].lower() == clean_owner.lower() else f"/orgs/{clean_owner}/repos"
        payload = self.request(
            "POST",
            endpoint,
            json_body={
                "name": clean_repo,
                "private": bool(private),
                "auto_init": False,
            },
        )
        if not isinstance(payload, dict):
            raise AppError("GitHub returned an unexpected repository creation response.", "GITHUB_RESPONSE_INVALID")
        return serialize_repository(payload)

    # Returns an existing repository or creates it when GitHub reports that it does not exist.
    def ensure_repository(self, owner: str, repo: str, private: bool = False) -> dict[str, Any]:
        """Return a GitHub repository, creating it when it is missing."""

        try:
            return self.repository(owner, repo)
        except AppError as error:
            if error.details.get("status") == 404:
                return self.create_repository(owner, repo, private)
            raise

    # Fetches recent workflow runs for CI/CD monitoring.
    def workflow_runs(self, owner: str, repo: str, per_page: int = 25) -> dict[str, Any]:
        """Return recent GitHub Actions workflow runs for a repository."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        bounded_page_size = max(1, min(int(per_page), 100))
        payload = self.request(
            "GET",
            f"/repos/{clean_owner}/{clean_repo}/actions/runs",
            params={"per_page": bounded_page_size},
        )

        runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
        return {
            "total_count": payload.get("total_count", len(runs)) if isinstance(payload, dict) else len(runs),
            "runs": [serialize_workflow_run(run) for run in runs],
        }

    # Fetches releases for the releases manager table.
    def releases(self, owner: str, repo: str, per_page: int = 25) -> list[dict[str, Any]]:
        """Return recent releases for a GitHub repository."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        payload = self.request(
            "GET",
            f"/repos/{clean_owner}/{clean_repo}/releases",
            params={"per_page": max(1, min(int(per_page), 100))},
        )

        if not isinstance(payload, list):
            raise AppError("GitHub returned an unexpected releases response.", "GITHUB_RESPONSE_INVALID")
        return [serialize_release(release) for release in payload]

    # Publishes a release through GitHub's official release creation endpoint.
    def create_release(self, owner: str, repo: str, release_data: dict[str, Any]) -> dict[str, Any]:
        """Create a GitHub release and return the serialized release payload."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        payload = release_payload(release_data, True)
        created = self.request("POST", f"/repos/{clean_owner}/{clean_repo}/releases", json_body=payload)
        if not isinstance(created, dict):
            raise AppError("GitHub returned an unexpected release creation response.", "GITHUB_RESPONSE_INVALID")
        return serialize_release(created)

    # Updates a draft release, usually setting draft false to publish it like GitHub.com's form.
    def update_release(
        self,
        owner: str,
        repo: str,
        release_id: int,
        release_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a GitHub release and return the serialized release payload."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        if release_id <= 0:
            raise AppError("A valid release id is required.", "RELEASE_ID_INVALID")

        payload = release_payload(release_data, False)
        updated = self.request(
            "PATCH",
            f"/repos/{clean_owner}/{clean_repo}/releases/{release_id}",
            json_body=payload,
        )
        if not isinstance(updated, dict):
            raise AppError("GitHub returned an unexpected release update response.", "GITHUB_RESPONSE_INVALID")
        return serialize_release(updated)

    # Reads the current Pages configuration, returning an explicit unconfigured state for 404.
    def pages_site(self, owner: str, repo: str) -> dict[str, Any]:
        """Return GitHub Pages configuration for a repository."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        try:
            payload = self.request("GET", f"/repos/{clean_owner}/{clean_repo}/pages")
        except AppError as error:
            if error.details.get("status") == 404:
                return {"configured": False}
            raise
        if not isinstance(payload, dict):
            raise AppError("GitHub returned an unexpected Pages response.", "GITHUB_RESPONSE_INVALID")
        return serialize_pages_site(payload)

    # Configures Pages to use a custom workflow so GitDesk can support non-index filenames.
    def configure_pages_workflow(self, owner: str, repo: str) -> dict[str, Any]:
        """Enable GitHub Pages with workflow-based deployment."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        try:
            current = self.pages_site(clean_owner, clean_repo)
            method = "PUT" if current.get("configured") else "POST"
            self.request(method, f"/repos/{clean_owner}/{clean_repo}/pages", json_body={"build_type": "workflow"})
            return self.pages_site(clean_owner, clean_repo)
        except AppError as error:
            if is_token_permission_error(error):
                message = "GitHub rejected this token for Pages. Use GitDesk token setup for repository permissions."
                raise AppError(message, "PAGES_TOKEN_PERMISSION_FAILED") from error
            raise

    # Fetches one commit by SHA so freshly pushed commits can be shown during branch-list lag.
    def commit(self, owner: str, repo: str, sha: str) -> dict[str, Any]:
        """Return one commit by SHA."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        payload = self.request("GET", f"/repos/{clean_owner}/{clean_repo}/commits/{clean_commit_sha(sha)}")
        if not isinstance(payload, dict):
            raise AppError("GitHub returned an unexpected commit response.", "GITHUB_RESPONSE_INVALID")
        return serialize_commit(payload)

    # Fetches recent commits so the UI can offer tag creation.
    def commits(self, owner: str, repo: str, branch: str = "", per_page: int = 25) -> list[dict[str, Any]]:
        """Return recent commits for a repository or branch."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        params: dict[str, Any] = {"per_page": max(1, min(int(per_page), 100))}
        clean_branch = str(branch or "").strip()
        if clean_branch:
            params["sha"] = clean_branch
        payload = self.request("GET", f"/repos/{clean_owner}/{clean_repo}/commits", params=params)
        if not isinstance(payload, list):
            raise AppError("GitHub returned an unexpected commits response.", "GITHUB_RESPONSE_INVALID")
        return [serialize_commit(commit) for commit in payload]

    # Creates an annotated Git tag object and publishes its refs/tags/<name> reference.
    def create_tag(self, owner: str, repo: str, tag_data: dict[str, Any]) -> dict[str, Any]:
        """Create and publish an annotated tag for a commit SHA."""

        clean_owner, clean_repo = clean_repository_pair(owner, repo)
        tag_name = clean_tag_name(str(tag_data.get("tag") or ""))
        target_sha = clean_commit_sha(str(tag_data.get("sha") or ""))
        message = str(tag_data.get("message") or tag_name).strip() or tag_name
        tag_payload = {
            "tag": tag_name,
            "message": message,
            "object": target_sha,
            "type": "commit",
        }
        try:
            tag_object = self.request("POST", f"/repos/{clean_owner}/{clean_repo}/git/tags", json_body=tag_payload)
            if not isinstance(tag_object, dict) or not tag_object.get("sha"):
                raise AppError("GitHub returned an unexpected tag response.", "GITHUB_RESPONSE_INVALID")

            ref_payload = {"ref": f"refs/tags/{tag_name}", "sha": tag_object["sha"]}
            created_ref = self.request("POST", f"/repos/{clean_owner}/{clean_repo}/git/refs", json_body=ref_payload)
            if not isinstance(created_ref, dict):
                raise AppError("GitHub returned an unexpected tag reference response.", "GITHUB_RESPONSE_INVALID")
            return serialize_tag_result(clean_owner, clean_repo, tag_name, target_sha, created_ref)
        except AppError as error:
            if is_token_permission_error(error):
                message = "GitHub rejected this token for tags. Use GitDesk token setup for repository permissions."
                raise AppError(message, "TAG_TOKEN_PERMISSION_FAILED") from error
            raise
