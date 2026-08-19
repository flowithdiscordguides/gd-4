"""Local repository operations implemented through GitPython."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo

from gitdesk.branchops import create_local_branch, repository_has_commits, validate_branch_name
from gitdesk.cloneops import clone_github_repository
from gitdesk.errors import AppError
from gitdesk.gitauth import git_auth_environment, git_remote_argument
from gitdesk.giterrors import git_error_details, git_failure_message
from gitdesk.gitidentity import configure_repository_identity, git_commit_environment
from gitdesk.gitstaging import selected_status_paths, serialized_git_commit
from gitdesk.gitstaging import stage_git_paths, stageable_git_paths
from gitdesk.gitstatus import parse_porcelain_status, summarize_status
from gitdesk.gittransport import push_git_command
from gitdesk.giturls import parse_github_remote, redact_url_credentials


# Resolves a repository path and verifies that it points to an existing directory.
def normalize_repository_path(path_value: str) -> Path:
    """Return a resolved repository path after rejecting empty or non-directory inputs."""
    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        raise AppError("Repository path is required.", "REPOSITORY_PATH_EMPTY")
    repository_path = Path(cleaned_path).expanduser().resolve()
    if not repository_path.exists() or not repository_path.is_dir():
        raise AppError("Repository path must point to an existing directory.", "REPOSITORY_PATH_INVALID")
    return repository_path


# Opens a GitPython repository and normalizes repository-specific exceptions into app errors.
def open_repository(path_value: str) -> Repo:
    """Return a GitPython Repo for a valid non-bare repository path."""
    repository_path = normalize_repository_path(path_value)
    try:
        repo = Repo(repository_path)
    except NoSuchPathError as error:
        raise AppError("Repository path does not exist.", "REPOSITORY_NOT_FOUND") from error
    except InvalidGitRepositoryError as error:
        raise AppError("The selected folder is not a Git repository.", "REPOSITORY_INVALID") from error
    if repo.bare:
        raise AppError("Bare repositories are not supported by this desktop client.", "REPOSITORY_BARE")
    return repo


# Initializes a Git repository in an existing directory and returns the opened Repo.
def initialize_repository(path_value: str) -> Repo:
    """Create a Git repository in an existing directory and return the initialized Repo."""
    repository_path = normalize_repository_path(path_value)
    try:
        return Repo.init(repository_path)
    except GitCommandError as error:
        raise AppError("Git could not initialize the selected folder.", "GIT_INIT_FAILED") from error


# Builds a readable branch name while tolerating detached HEAD repositories.
def active_branch_name(repo: Repo) -> str:
    """Return the active branch name, or a detached-HEAD marker when no branch is checked out."""
    try:
        return repo.active_branch.name
    except TypeError:
        return "DETACHED"


# Returns the origin URL or an empty string when the repository has no origin remote.
def origin_remote_url(repo: Repo) -> str:
    """Return the configured origin URL for a repository."""
    return next((remote.url for remote in repo.remotes if remote.name == "origin"), "")


# Supplies a saved-token account only when origin uses GitHub HTTPS transport.
def auth_login_for_origin(repo: Repo, auth_login: str | None) -> str | None:
    """Return an account login for HTTPS GitHub origin remotes, or None for SSH/public flows."""
    origin_url = origin_remote_url(repo)
    if auth_login and redact_url_credentials(origin_url).startswith("https://github.com/"):
        return auth_login
    return None


# Derives repository metadata from an already validated GitPython handle.
def repository_summary_from_repo(repo: Repo, path_value: str) -> dict[str, Any]:
    """Return repository summary metadata without reopening the working tree."""

    remotes = [{"name": remote.name, "url": redact_url_credentials(remote.url)} for remote in repo.remotes]
    origin_url = origin_remote_url(repo)
    github_remote = parse_github_remote(origin_url)
    return {
        "path": str(Path(repo.working_tree_dir or path_value).resolve()),
        "branch": active_branch_name(repo),
        "remotes": remotes,
        "github_owner": github_remote["owner"],
        "github_repo": github_remote["repo"],
        "has_origin": bool(origin_url),
    }


# Reads working-tree changes from an existing repository handle and a matching summary.
def repository_status_from_repo(repo: Repo, summary: dict[str, Any]) -> dict[str, Any]:
    """Return status data without reopening the repository for its summary."""

    try:
        raw_status = repo.git.status("--porcelain=v1", "-z", "--untracked-files=all")
    except GitCommandError as error:
        raise AppError("Unable to read repository status.", "GIT_STATUS_FAILED") from error
    entries = parse_porcelain_status(raw_status)
    return {"repository": summary, "files": entries, "summary": summarize_status(entries)}


# Builds branch metadata from the same repository handle used for selection status.
def repository_branches_from_repo(repo: Repo) -> dict[str, Any]:
    """Return local branch data without reopening the repository."""

    current_branch = active_branch_name(repo)
    branches = [{"name": head.name, "active": head.name == current_branch} for head in repo.heads]
    return {"current": current_branch, "branches": branches, "has_commits": repository_has_commits(repo)}


# Ensures frontend-supplied paths cannot escape the selected repository.
def validate_relative_git_path(path_value: str) -> str:
    """Return a safe Git-relative path for staging operations."""
    normalized = str(path_value or "").replace("\\", "/").strip()
    path_parts = PurePosixPath(normalized).parts
    starts_with_drive = len(normalized) >= 2 and normalized[1] == ":"
    escapes_repository = ".." in path_parts or normalized.startswith("/")

    if not normalized or normalized == "." or starts_with_drive or escapes_repository:
        raise AppError("A selected file path is outside the repository.", "UNSAFE_REPOSITORY_PATH")
    return normalized


# Creates a commit through native Git plumbing so large trees avoid GitPython's pure-Python object traversal.
def create_native_commit(
    repo: Repo,
    message: str,
    account: dict[str, Any] | None,
) -> Any:
    """Write the staged tree, create its commit object, and atomically advance HEAD."""

    parent_sha = repo.head.commit.hexsha if repository_has_commits(repo) else ""
    tree_sha = repo.git.write_tree().strip()
    commit_arguments = [tree_sha, "-m", message]
    if parent_sha:
        commit_arguments.extend(["-p", parent_sha])
    commit_sha = repo.git.commit_tree(
        *commit_arguments,
        env=git_commit_environment(account),
    ).strip()
    reflog_message = f"commit: {message.splitlines()[0]}"
    update_arguments = ["-m", reflog_message, "HEAD", commit_sha]
    if parent_sha:
        update_arguments.append(parent_sha)
    repo.git.update_ref(*update_arguments)
    return repo.head.commit


# GitService is the UI-facing local Git facade for status, branches, commits, pushes, and pulls.
class GitService:
    """Provide local Git operations while converting GitPython failures into AppError values."""

    # Clones a GitHub repository and returns its opened metadata for immediate desktop use.
    def clone_repository(
        self,
        clone_url: str,
        parent_path: str,
        folder_name: str = "",
        auth_login: str | None = None,
        account: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Clone a GitHub repository and return repository metadata for the cloned working tree."""

        repo = clone_github_repository(clone_url, parent_path, folder_name, auth_login)
        configure_repository_identity(repo, account)
        return self.repository_summary(str(repo.working_tree_dir or ""))

    # Creates a Git repository in an existing folder and returns its initial metadata.
    def init_repository(self, path_value: str) -> dict[str, Any]:
        """Initialize a repository in the selected directory and return repository metadata."""

        repo = initialize_repository(path_value)
        return self.repository_summary(str(repo.working_tree_dir or path_value))

    # Collects repository metadata that is useful immediately after a repository path is selected.
    def repository_summary(self, path_value: str) -> dict[str, Any]:
        """Return branch, remote, and inferred GitHub repository metadata for a local repository."""

        repo = open_repository(path_value)
        return repository_summary_from_repo(repo, path_value)

    # Reads repository status using porcelain output so all states map cleanly to the UI.
    def status(self, path_value: str) -> dict[str, Any]:
        """Return the current working tree status for a selected repository."""

        repo = open_repository(path_value)
        summary = repository_summary_from_repo(repo, path_value)
        return repository_status_from_repo(repo, summary)

    # Lists local branches and marks the currently checked-out branch.
    def branches(self, path_value: str) -> dict[str, Any]:
        """Return local branches for branch management UI rendering."""

        repo = open_repository(path_value)
        return repository_branches_from_repo(repo)

    # Opens a dropdown-selected repository once for summary, status, and branch rendering.
    def repository_selection_state(self, path_value: str) -> dict[str, Any]:
        """Return the complete fresh repository state from one validated repository handle."""

        repo = open_repository(path_value)
        summary = repository_summary_from_repo(repo, path_value)
        return {
            "repository": summary,
            "status": repository_status_from_repo(repo, summary),
            "branches": repository_branches_from_repo(repo),
        }

    # Checks out an existing local branch and lets Git reject unsafe working-tree transitions.
    def checkout_branch(self, path_value: str, branch_name: str) -> dict[str, Any]:
        """Checkout an existing local branch and return refreshed branch metadata."""

        repo = open_repository(path_value)
        cleaned_name = branch_name.strip()
        if not cleaned_name:
            raise AppError("Branch name is required.", "BRANCH_NAME_EMPTY")

        matching_heads = [head for head in repo.heads if head.name == cleaned_name]
        if not matching_heads:
            raise AppError("The requested local branch does not exist.", "BRANCH_NOT_FOUND")

        try:
            matching_heads[0].checkout()
        except GitCommandError as error:
            raise AppError("Git could not checkout the requested branch.", "GIT_CHECKOUT_FAILED") from error

        return self.branches(path_value)

    # Creates a local branch from the current HEAD and optionally checks it out.
    def create_branch(self, path_value: str, branch_name: str, checkout: bool = True) -> dict[str, Any]:
        """Create a new local branch and return refreshed branch metadata."""

        repo = open_repository(path_value)
        cleaned_name = branch_name.strip()
        if not cleaned_name:
            raise AppError("Branch name is required.", "BRANCH_NAME_EMPTY")

        validate_branch_name(repo, cleaned_name)
        create_local_branch(repo, cleaned_name, checkout)

        try:
            return self.branches(path_value)
        except Exception as error:
            message = "Branch was created, but branch list refresh failed."
            raise AppError(message, "GIT_BRANCH_REFRESH_FAILED") from error

    # Stages selected files, creates a commit, and optionally pushes the active branch to origin.
    @serialized_git_commit
    def commit(
        self,
        path_value: str,
        message: str,
        files: list[str],
        push_after: bool = False,
        auth_login: str | None = None,
        account: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a commit from selected files and return commit metadata plus optional push results."""

        repo = open_repository(path_value)
        cleaned_message = message.strip()
        if not cleaned_message:
            raise AppError("Commit message is required.", "COMMIT_MESSAGE_EMPTY")
        if not files:
            raise AppError("Select at least one changed file to commit.", "COMMIT_FILES_EMPTY")

        selected_files = [validate_relative_git_path(file_path) for file_path in files]
        try:
            current_paths, used_full_status = selected_status_paths(repo, selected_files)
        except GitCommandError as error:
            raise AppError("Unable to read selected file status.", "GIT_STATUS_FAILED") from error
        safe_files = stageable_git_paths(repo, selected_files, current_paths)
        if not safe_files:
            current_status = self.status(path_value)
            return {
                "hexsha": "", "short_sha": "", "message": "", "pushed": None,
                "status": current_status, "noop": True,
            }
        try:
            stage_git_paths(repo, safe_files, current_paths, used_full_status)
            staged_names = repo.git.diff("--cached", "--name-only")
        except GitCommandError as error:
            message_text = git_failure_message("Git could not stage the selected files.", error)
            raise AppError(message_text, "GIT_STAGE_FAILED", git_error_details(error)) from error
        if not staged_names.strip():
            raise AppError("No staged changes are available to commit.", "COMMIT_NOTHING_STAGED")
        try:
            commit = create_native_commit(repo, cleaned_message, account)
        except GitCommandError as error:
            message_text = git_failure_message("Git could not create the commit.", error)
            raise AppError(message_text, "GIT_COMMIT_FAILED", git_error_details(error)) from error

        push_result = None
        if push_after:
            try:
                push_result = self.push(path_value, auth_login)
            except AppError as error:
                short_sha = commit.hexsha[:7]
                message = f"Commit {short_sha} was created, but push failed. {error.message}"
                details = {"commit": commit.hexsha, "short_sha": short_sha, "status": self.status(path_value)}
                raise AppError(message, "COMMIT_PUSH_FAILED", details) from error
        final_status = push_result["status"] if push_result else self.status(path_value)
        return {
            "hexsha": commit.hexsha,
            "short_sha": commit.hexsha[:7],
            "message": commit.message.strip(),
            "pushed": push_result,
            "status": final_status,
        }

    # Pushes the active local branch to origin with optional saved-token authentication for HTTPS.
    def push(self, path_value: str, auth_login: str | None = None) -> dict[str, Any]:
        """Push the active branch to origin and return serialized push details."""

        repo = open_repository(path_value)
        branch = active_branch_name(repo)
        if branch == "DETACHED":
            raise AppError("Cannot push while HEAD is detached.", "GIT_DETACHED_HEAD")
        origin_url = origin_remote_url(repo)
        if not origin_url:
            raise AppError("No origin remote is configured for this repository.", "GIT_ORIGIN_MISSING")

        git_login = auth_login_for_origin(repo, auth_login)
        output = push_git_command(
            repo,
            git_remote_argument(origin_url, git_login),
            f"{branch}:{branch}",
            git_auth_environment(git_login),
        )

        return {
            "branch": branch,
            "head_sha": repo.head.commit.hexsha,
            "messages": [output] if output else [],
            "status": self.status(path_value),
        }

    # Pulls the active branch from origin to update the working tree from the remote.
    def pull(self, path_value: str, auth_login: str | None = None) -> dict[str, Any]:
        """Pull from origin for the active branch and return refreshed status details."""

        repo = open_repository(path_value)
        branch = active_branch_name(repo)
        if branch == "DETACHED":
            raise AppError("Cannot pull while HEAD is detached.", "GIT_DETACHED_HEAD")
        origin_url = origin_remote_url(repo)
        if not origin_url:
            raise AppError("No origin remote is configured for this repository.", "GIT_ORIGIN_MISSING")
        try:
            repo.git.rev_parse("--verify", f"refs/remotes/origin/{branch}")
        except GitCommandError as error:
            raise AppError(
                f"Origin does not have a fetched {branch} branch. Push this branch first or fetch remote branches.",
                "GIT_REMOTE_BRANCH_MISSING",
                {"branch": branch},
            ) from error

        git_login = auth_login_for_origin(repo, auth_login)
        try:
            output = repo.git.pull(
                git_remote_argument(origin_url, git_login),
                branch,
                env=git_auth_environment(git_login),
            )
        except GitCommandError as error:
            message = git_failure_message("Git could not pull from origin.", error)
            raise AppError(message, "GIT_PULL_FAILED", git_error_details(error)) from error

        return {
            "messages": [output] if output else [],
            "status": self.status(path_value),
        }
