"""Organization membership discovery for GitDesk's GitHub repository catalog."""

from __future__ import annotations

from typing import Any

from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient


# GitHub permits one hundred organization memberships per request, minimizing pagination round trips.
ORGANIZATION_PAGE_SIZE = 100


# Condenses one active membership into the organization identity needed by owner selectors.
def serialize_organization_membership(membership: dict[str, Any]) -> dict[str, str] | None:
    """Return frontend-safe organization membership fields, or None for an unusable record."""

    organization = membership.get("organization") or {}
    login = str(organization.get("login") or "").strip()
    # Membership entries without a login cannot become safe owner-selector values.
    if not login:
        return None
    return {
        "login": login,
        "role": str(membership.get("role") or "member").strip(),
        "avatar_url": str(organization.get("avatar_url") or "").strip(),
        "html_url": str(organization.get("html_url") or "").strip(),
    }


# Lists active organization memberships while distinguishing a scope limitation from catalog failure.
def organization_memberships(client: GitHubApiClient) -> dict[str, Any]:
    """Return active organizations and whether GitHub allowed complete membership discovery."""

    organizations: list[dict[str, str]] = []
    page = 1
    try:
        while True:
            payload = client.request(
                "GET",
                "/user/memberships/orgs",
                params={
                    "state": "active",
                    "per_page": ORGANIZATION_PAGE_SIZE,
                    "page": page,
                },
            )
            # A non-list response cannot be paginated or exposed as membership data safely.
            if not isinstance(payload, list):
                raise AppError(
                    "GitHub returned an unexpected organization memberships response.",
                    "GITHUB_RESPONSE_INVALID",
                )

            # Pending memberships are excluded by the request because they cannot own new repositories yet.
            for membership in payload:
                # Ignore malformed list members while preserving valid memberships from the same page.
                if isinstance(membership, dict):
                    organization = serialize_organization_membership(membership)
                    # Only serialized organizations with a non-empty login belong in owner selectors.
                    if organization:
                        organizations.append(organization)
            # A short page is GitHub's pagination terminator; a full page requires the next request.
            if len(payload) < ORGANIZATION_PAGE_SIZE:
                break
            page += 1
    except AppError as error:
        # Classic PATs without read:org may still list repositories, so preserve clone access and explain the limit.
        if error.details.get("status") == 403:
            return {"organizations": [], "access": "repositories_only"}
        raise

    unique = {organization["login"].lower(): organization for organization in organizations}
    return {
        "organizations": sorted(unique.values(), key=lambda item: item["login"].lower()),
        "access": "complete",
    }
