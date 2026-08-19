"""Bridge handlers for selected-repository Pull Request workflows."""

from __future__ import annotations

# Callable typing describes the handler registry plugged into BridgeController.
from typing import Any, Callable

# The focused service owns GitHub payload validation and serialization.
from gitdesk import pullrequests


# Registers all Pull Request actions without expanding the central bridge controller.
def pull_request_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for Pull Request listing, review, and merge."""

    return {
        "listPullRequests": lambda payload: handle_list_pull_requests(controller, payload),
        "pullRequestDetail": lambda payload: handle_pull_request_detail(controller, payload),
        "createPullRequest": lambda payload: handle_create_pull_request(controller, payload),
        "commentPullRequest": lambda payload: handle_comment_pull_request(controller, payload),
        "reviewPullRequest": lambda payload: handle_review_pull_request(controller, payload),
        "mergePullRequest": lambda payload: handle_merge_pull_request(controller, payload),
    }


# Resolves one API client and owner/repository pair from the same selected-path payload.
def request_context(controller: Any, payload: dict[str, Any]) -> tuple[Any, str, str]:
    """Return the exact owner-routed client and repository pair for payload."""

    owner, repo = controller.github_pair_from_payload(payload)
    return controller.github_client(payload), owner, repo


# Lists open Pull Requests for the selected managed repository.
def handle_list_pull_requests(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return open Pull Requests and default branch context."""

    client, owner, repo = request_context(controller, payload)
    return pullrequests.list_pull_requests(client, owner, repo)


# Loads the reviewable detail for one Pull Request.
def handle_pull_request_detail(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return files, commits, reviews, and conversation for one Pull Request."""

    client, owner, repo = request_context(controller, payload)
    return pullrequests.pull_request_detail(client, owner, repo, payload.get("number"))


# Creates one Pull Request from explicit form values.
def handle_create_pull_request(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a Pull Request and return its serialized identity."""

    client, owner, repo = request_context(controller, payload)
    return {"pull_request": pullrequests.create_pull_request(client, owner, repo, payload)}


# Adds one normal conversation comment.
def handle_comment_pull_request(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a Pull Request comment and return it."""

    client, owner, repo = request_context(controller, payload)
    comment = pullrequests.add_pull_request_comment(
        client,
        owner,
        repo,
        payload.get("number"),
        payload.get("body"),
    )
    return {"comment": comment}


# Submits an approve, request-changes, or comment review.
def handle_review_pull_request(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Submit one Pull Request review and return it."""

    client, owner, repo = request_context(controller, payload)
    review = pullrequests.submit_pull_request_review(
        client,
        owner,
        repo,
        payload.get("number"),
        payload.get("event"),
        payload.get("body"),
    )
    return {"review": review}


# Merges one Pull Request using the user-selected GitHub strategy.
def handle_merge_pull_request(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Merge one Pull Request and return GitHub's result."""

    client, owner, repo = request_context(controller, payload)
    return pullrequests.merge_pull_request(
        client,
        owner,
        repo,
        payload.get("number"),
        payload.get("merge_method"),
    )
