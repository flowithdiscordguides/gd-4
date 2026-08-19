"""GitHub Pull Request listing, review, conversation, and merge services."""

from __future__ import annotations

# Type helpers define sanitized JSON payloads passed across the native bridge.
from typing import Any

# Existing GitHub validation and errors keep PR requests inside the selected repository.
from gitdesk.errors import AppError
from gitdesk.githubserializers import clean_repository_pair


# Lists remain bounded so one repository cannot flood the desktop WebView.
PULL_REQUEST_PAGE_SIZE = 50
PULL_REQUEST_DETAIL_LIMIT = 100
MAX_PULL_REQUEST_TEXT = 65536
MAX_PATCH_TEXT = 120000

# GitHub accepts these review and merge values exactly.
REVIEW_EVENTS = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}
MERGE_METHODS = {"merge", "squash", "rebase"}


# Parses one positive GitHub numeric identifier without accepting booleans or empty strings.
def positive_identifier(value: Any, label: str, code: str) -> int:
    """Return a positive integer identifier or raise a structured validation error."""

    try:
        identifier = int(value)
    except (TypeError, ValueError) as error:
        raise AppError(f"A valid {label} is required.", code) from error
    if isinstance(value, bool) or identifier <= 0:
        raise AppError(f"A valid {label} is required.", code)
    return identifier


# Returns bounded text while preserving newlines used in GitHub Markdown bodies.
def bounded_text(value: Any, label: str, required: bool = False) -> str:
    """Return stripped bounded text and enforce required content when requested."""

    text = str(value or "").strip()
    if required and not text:
        raise AppError(f"{label} is required.", "PULL_REQUEST_TEXT_REQUIRED")
    if len(text) > MAX_PULL_REQUEST_TEXT:
        raise AppError(f"{label} is too long.", "PULL_REQUEST_TEXT_TOO_LONG")
    return text


# Converts GitHub user objects into the minimal frontend identity shape.
def serialize_user(value: Any) -> dict[str, str]:
    """Return safe login and profile URL fields for a GitHub user."""

    user = value if isinstance(value, dict) else {}
    return {
        "login": str(user.get("login") or "").strip(),
        "html_url": str(user.get("html_url") or "").strip(),
    }


# Converts one Pull Request into the compact list and detail identity shared by the UI.
def serialize_pull_request(value: Any) -> dict[str, Any]:
    """Return a bounded Pull Request record from a GitHub response object."""

    item = value if isinstance(value, dict) else {}
    head = item.get("head") if isinstance(item.get("head"), dict) else {}
    base = item.get("base") if isinstance(item.get("base"), dict) else {}
    return {
        "number": int(item.get("number") or 0),
        "title": str(item.get("title") or "")[:500],
        "body": str(item.get("body") or "")[:MAX_PULL_REQUEST_TEXT],
        "state": str(item.get("state") or ""),
        "draft": item.get("draft") is True,
        "merged": item.get("merged") is True,
        "mergeable": item.get("mergeable"),
        "mergeable_state": str(item.get("mergeable_state") or ""),
        "html_url": str(item.get("html_url") or ""),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "user": serialize_user(item.get("user")),
        "head": {
            "label": str(head.get("label") or ""),
            "ref": str(head.get("ref") or ""),
            "sha": str(head.get("sha") or ""),
        },
        "base": {
            "label": str(base.get("label") or ""),
            "ref": str(base.get("ref") or ""),
            "sha": str(base.get("sha") or ""),
        },
        "commits": max(0, int(item.get("commits") or 0)),
        "additions": max(0, int(item.get("additions") or 0)),
        "deletions": max(0, int(item.get("deletions") or 0)),
        "changed_files": max(0, int(item.get("changed_files") or 0)),
    }


# Converts one PR commit into a compact chronology record.
def serialize_commit(value: Any) -> dict[str, Any]:
    """Return one Pull Request commit with author and subject metadata."""

    item = value if isinstance(value, dict) else {}
    commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
    author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
    message = str(commit.get("message") or "")
    return {
        "sha": str(item.get("sha") or ""),
        "subject": message.splitlines()[0][:500] if message else "",
        "message": message[:MAX_PULL_REQUEST_TEXT],
        "author": str(author.get("name") or ""),
        "date": str(author.get("date") or ""),
        "user": serialize_user(item.get("author")),
    }


# Converts one changed file while bounding GitHub's optional patch text.
def serialize_file(value: Any) -> dict[str, Any]:
    """Return one changed-file summary and bounded unified patch."""

    item = value if isinstance(value, dict) else {}
    return {
        "filename": str(item.get("filename") or ""),
        "status": str(item.get("status") or ""),
        "additions": max(0, int(item.get("additions") or 0)),
        "deletions": max(0, int(item.get("deletions") or 0)),
        "changes": max(0, int(item.get("changes") or 0)),
        "previous_filename": str(item.get("previous_filename") or ""),
        "patch": str(item.get("patch") or "")[:MAX_PATCH_TEXT],
    }


# Converts one review into a chronological decision record.
def serialize_review(value: Any) -> dict[str, Any]:
    """Return one submitted review with bounded text."""

    item = value if isinstance(value, dict) else {}
    return {
        "id": int(item.get("id") or 0),
        "state": str(item.get("state") or ""),
        "body": str(item.get("body") or "")[:MAX_PULL_REQUEST_TEXT],
        "submitted_at": str(item.get("submitted_at") or ""),
        "commit_id": str(item.get("commit_id") or ""),
        "user": serialize_user(item.get("user")),
    }


# Converts issue or review comments into one shared conversation shape.
def serialize_comment(value: Any, kind: str) -> dict[str, Any]:
    """Return one escaped-by-frontend conversation record."""

    item = value if isinstance(value, dict) else {}
    return {
        "id": int(item.get("id") or 0),
        "kind": kind,
        "body": str(item.get("body") or "")[:MAX_PULL_REQUEST_TEXT],
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "path": str(item.get("path") or ""),
        "line": item.get("line"),
        "diff_hunk": str(item.get("diff_hunk") or "")[:MAX_PATCH_TEXT],
        "user": serialize_user(item.get("user")),
    }


# Requires list-shaped GitHub responses before serializing them.
def response_list(value: Any, label: str) -> list[Any]:
    """Return a GitHub list response or raise when its shape is unexpected."""

    if not isinstance(value, list):
        raise AppError(f"GitHub returned unexpected {label} data.", "GITHUB_RESPONSE_INVALID")
    return value


# Lists open Pull Requests for the selected repository.
def list_pull_requests(client: Any, owner: str, repo: str) -> dict[str, Any]:
    """Return recent open Pull Requests and the repository default branch."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    repository = client.request("GET", f"/repos/{clean_owner}/{clean_repo}")
    pulls = client.request(
        "GET",
        f"/repos/{clean_owner}/{clean_repo}/pulls",
        params={"state": "open", "sort": "updated", "direction": "desc", "per_page": PULL_REQUEST_PAGE_SIZE},
    )
    if not isinstance(repository, dict):
        raise AppError("GitHub returned unexpected repository data.", "GITHUB_RESPONSE_INVALID")
    return {
        "owner": clean_owner,
        "repo": clean_repo,
        "default_branch": str(repository.get("default_branch") or ""),
        "pull_requests": [serialize_pull_request(item) for item in response_list(pulls, "Pull Request")],
    }


# Loads the complete reviewable detail without depending on unsupported Checks API access.
def pull_request_detail(client: Any, owner: str, repo: str, number_value: Any) -> dict[str, Any]:
    """Return PR identity, files, commits, reviews, requests, and conversation."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    number = positive_identifier(number_value, "Pull Request number", "PULL_REQUEST_NUMBER_INVALID")
    root = f"/repos/{clean_owner}/{clean_repo}/pulls/{number}"
    pull = client.request("GET", root)
    commits = response_list(
        client.request("GET", f"{root}/commits", params={"per_page": PULL_REQUEST_DETAIL_LIMIT}),
        "Pull Request commit",
    )
    files = response_list(
        client.request("GET", f"{root}/files", params={"per_page": PULL_REQUEST_DETAIL_LIMIT}),
        "Pull Request file",
    )
    reviews = response_list(
        client.request("GET", f"{root}/reviews", params={"per_page": PULL_REQUEST_DETAIL_LIMIT}),
        "Pull Request review",
    )
    issue_comments = response_list(
        client.request(
            "GET",
            f"/repos/{clean_owner}/{clean_repo}/issues/{number}/comments",
            params={"per_page": PULL_REQUEST_DETAIL_LIMIT},
        ),
        "Pull Request comment",
    )
    review_comments = response_list(
        client.request("GET", f"{root}/comments", params={"per_page": PULL_REQUEST_DETAIL_LIMIT}),
        "review comment",
    )
    requested = client.request("GET", f"{root}/requested_reviewers")
    if not isinstance(pull, dict) or not isinstance(requested, dict):
        raise AppError("GitHub returned unexpected Pull Request detail.", "GITHUB_RESPONSE_INVALID")
    conversation = [
        *[serialize_comment(item, "comment") for item in issue_comments],
        *[serialize_comment(item, "review_comment") for item in review_comments],
    ]
    conversation.sort(key=lambda item: (item["created_at"], item["id"]))
    return {
        "pull_request": serialize_pull_request(pull),
        "commits": [serialize_commit(item) for item in commits],
        "files": [serialize_file(item) for item in files],
        "reviews": [serialize_review(item) for item in reviews],
        "conversation": conversation,
        "requested_reviewers": [serialize_user(item) for item in requested.get("users", [])],
        "requested_teams": [
            {"name": str(item.get("name") or ""), "slug": str(item.get("slug") or "")}
            for item in requested.get("teams", [])
            if isinstance(item, dict)
        ],
    }


# Creates a Pull Request from explicit head/base branches and bounded Markdown text.
def create_pull_request(client: Any, owner: str, repo: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create and return one Pull Request."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    payload = {
        "title": bounded_text(data.get("title"), "Pull Request title", required=True),
        "body": bounded_text(data.get("body"), "Pull Request body"),
        "head": bounded_text(data.get("head"), "Head branch", required=True),
        "base": bounded_text(data.get("base"), "Base branch", required=True),
        "draft": data.get("draft") is True,
    }
    created = client.request("POST", f"/repos/{clean_owner}/{clean_repo}/pulls", json_body=payload)
    if not isinstance(created, dict):
        raise AppError("GitHub returned unexpected Pull Request data.", "GITHUB_RESPONSE_INVALID")
    return serialize_pull_request(created)


# Adds a normal Pull Request conversation comment through its issue-compatible endpoint.
def add_pull_request_comment(client: Any, owner: str, repo: str, number_value: Any, body_value: Any) -> dict[str, Any]:
    """Create and return one Pull Request conversation comment."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    number = positive_identifier(number_value, "Pull Request number", "PULL_REQUEST_NUMBER_INVALID")
    body = bounded_text(body_value, "Comment", required=True)
    created = client.request(
        "POST",
        f"/repos/{clean_owner}/{clean_repo}/issues/{number}/comments",
        json_body={"body": body},
    )
    if not isinstance(created, dict):
        raise AppError("GitHub returned unexpected comment data.", "GITHUB_RESPONSE_INVALID")
    return serialize_comment(created, "comment")


# Submits one complete approve, request-changes, or comment review decision.
def submit_pull_request_review(
    client: Any,
    owner: str,
    repo: str,
    number_value: Any,
    event_value: Any,
    body_value: Any,
) -> dict[str, Any]:
    """Create and return one submitted Pull Request review."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    number = positive_identifier(number_value, "Pull Request number", "PULL_REQUEST_NUMBER_INVALID")
    event = str(event_value or "").strip().upper()
    if event not in REVIEW_EVENTS:
        raise AppError("Choose a valid Pull Request review decision.", "PULL_REQUEST_REVIEW_INVALID")
    body = bounded_text(body_value, "Review", required=event != "APPROVE")
    created = client.request(
        "POST",
        f"/repos/{clean_owner}/{clean_repo}/pulls/{number}/reviews",
        json_body={"event": event, "body": body},
    )
    if not isinstance(created, dict):
        raise AppError("GitHub returned unexpected review data.", "GITHUB_RESPONSE_INVALID")
    return serialize_review(created)


# Merges a Pull Request only through GitHub's explicit supported merge strategies.
def merge_pull_request(
    client: Any,
    owner: str,
    repo: str,
    number_value: Any,
    method_value: Any,
) -> dict[str, Any]:
    """Merge one Pull Request and return GitHub's result."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    number = positive_identifier(number_value, "Pull Request number", "PULL_REQUEST_NUMBER_INVALID")
    method = str(method_value or "merge").strip().lower()
    if method not in MERGE_METHODS:
        raise AppError("Choose merge, squash, or rebase.", "PULL_REQUEST_MERGE_METHOD_INVALID")
    result = client.request(
        "PUT",
        f"/repos/{clean_owner}/{clean_repo}/pulls/{number}/merge",
        json_body={"merge_method": method},
    )
    if not isinstance(result, dict):
        raise AppError("GitHub returned unexpected merge data.", "GITHUB_RESPONSE_INVALID")
    return {
        "merged": result.get("merged") is True,
        "message": str(result.get("message") or ""),
        "sha": str(result.get("sha") or ""),
    }
