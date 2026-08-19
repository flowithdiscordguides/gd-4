"""Branch creation helpers for GitDesk local repository operations."""

from __future__ import annotations

from git import GitCommandError, Repo

from gitdesk.errors import AppError


# Branches created from the UI should start at the repository's current commit.
BRANCH_START_POINT = "HEAD"


# Checks whether the repository has an initial commit for new branches to point at.
def repository_has_commits(repo: Repo) -> bool:
    """Return True when HEAD resolves to a commit object."""

    try:
        repo.git.rev_parse("--verify", f"{BRANCH_START_POINT}^{{commit}}")
        return True
    except GitCommandError:
        return False


# Stops branch creation in empty repositories where HEAD is still unborn.
def ensure_branch_start_point_exists(repo: Repo) -> None:
    """Raise AppError when there is no current commit to branch from."""

    if repository_has_commits(repo):
        return
    message = "Create the first commit on the current branch before creating another branch."
    raise AppError(message, "GIT_BRANCH_UNBORN_HEAD")


# Removes GitPython's stdout/stderr labels from command failure lines.
def clean_git_failure_line(line: str) -> str:
    """Return a displayable Git error line without GitPython's wrapper labels."""

    cleaned = line.strip().strip("'\"")
    for prefix in ("stderr:", "stdout:"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip().strip("'\"")
    return cleaned


# Extracts Git's safe stderr/stdout reason without exposing Python stack traces.
def git_failure_message(error: GitCommandError, fallback: str) -> str:
    """Return a concise Git failure message for display in the UI."""

    raw_output = "\n".join(str(part or "") for part in (error.stderr, error.stdout, error))
    lines = [clean_git_failure_line(line) for line in raw_output.splitlines() if line.strip()]
    fallback_lines = []
    for line in lines:
        lowered = line.lower()
        if lowered.startswith("fatal:") or lowered.startswith("error:"):
            return line
        if line and not lowered.startswith(("cmdline:", "cmd(")):
            fallback_lines.append(line)
    return fallback_lines[-1] if fallback_lines else fallback


# Gives non-GitCommandError failures enough context without exposing a Python stack trace.
def fallback_failure_message(error: Exception, fallback: str) -> str:
    """Return a concise fallback message for unexpected branch operation failures."""

    detail = " ".join(str(error).split())
    if not detail:
        return fallback
    return f"{fallback} ({error.__class__.__name__}: {detail})"


# Validates a branch name with Git's own ref-format checker before creation.
def validate_branch_name(repo: Repo, cleaned_name: str) -> None:
    """Raise AppError when Git rejects a requested branch name."""

    try:
        repo.git.check_ref_format("--branch", cleaned_name)
    except GitCommandError as error:
        raise AppError(git_failure_message(error, "Branch name is not valid."), "BRANCH_NAME_INVALID") from error
    except Exception as error:
        raise AppError("Branch name is not valid.", "BRANCH_NAME_INVALID") from error


# Creates the branch with native Git commands and optionally checks it out.
def create_local_branch(repo: Repo, cleaned_name: str, checkout: bool) -> None:
    """Create a local branch and optionally checkout the new branch."""

    try:
        if cleaned_name in [head.name for head in repo.heads]:
            raise AppError("A branch with that name already exists.", "BRANCH_ALREADY_EXISTS")
        ensure_branch_start_point_exists(repo)
        if checkout:
            repo.git.checkout("-b", cleaned_name, BRANCH_START_POINT)
        else:
            repo.git.branch(cleaned_name, BRANCH_START_POINT)
    except AppError:
        raise
    except GitCommandError as error:
        fallback = "Git could not create the requested branch."
        raise AppError(git_failure_message(error, fallback), "GIT_BRANCH_CREATE_FAILED") from error
    except Exception as error:
        fallback = "Git could not create the requested branch."
        raise AppError(fallback_failure_message(error, fallback), "GIT_BRANCH_CREATE_FAILED") from error
