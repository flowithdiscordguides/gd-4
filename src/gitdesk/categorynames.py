"""Shared validation for repository and Local Mode category names."""

from __future__ import annotations

import re
from typing import Any

from gitdesk.errors import AppError


# Category-organized Local Mode projects always live below this explicit parent-folder container.
CATEGORY_CONTAINER_NAME = "categories"

# Category labels may become folder names, so separators and hidden/control-like values are rejected.
CATEGORY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")


# Normalizes a category label while allowing an empty label for Uncategorized.
def clean_category_name(value: Any) -> str:
    """Return a safe category label, or an empty string for uncategorized records."""

    category = str(value or "").strip()
    if not category:
        return ""
    if "/" in category or "\\" in category or category in {".", ".."} or not CATEGORY_PATTERN.match(category):
        raise AppError("Category name contains invalid characters.", "REPOSITORY_CATEGORY_INVALID")
    return category
