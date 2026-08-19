"""Parsing and aggregation for Git's stable porcelain working-tree status."""

from __future__ import annotations

from typing import Any


# Converts Git's porcelain status codes into labels that are useful in a desktop changes list.
STATUS_LABELS = {
    "A": "added",
    "D": "deleted",
    "M": "modified",
    "R": "renamed",
    "C": "copied",
    "U": "unmerged",
    "?": "untracked",
}


# Converts a two-character porcelain code into stage/worktree labels.
def describe_status(index_code: str, worktree_code: str) -> dict[str, Any]:
    """Return a structured status description for a porcelain status entry."""

    conflict_pair = f"{index_code}{worktree_code}"
    is_conflict = "U" in (index_code, worktree_code) or conflict_pair in {"AA", "DD", "AU", "UA", "DU", "UD"}
    is_untracked = index_code == "?" and worktree_code == "?"
    staged = not is_untracked and index_code != " "
    unstaged = not is_untracked and worktree_code != " "
    label_code = "?" if is_untracked else index_code if index_code != " " else worktree_code

    return {
        "label": STATUS_LABELS.get(label_code, "changed"),
        "staged": staged,
        "unstaged": unstaged,
        "conflict": is_conflict,
        "untracked": is_untracked,
    }


# Parses `git status --porcelain=v1 -z` because that output is stable and machine-readable.
def parse_porcelain_status(status_output: str) -> list[dict[str, Any]]:
    """Return status entries from NUL-delimited Git porcelain output."""

    entries: list[dict[str, Any]] = []
    parts = status_output.split("\0")
    index = 0

    # Porcelain rename and copy records consume a second path entry from the NUL-delimited stream.
    while index < len(parts):
        record = parts[index]
        if not record:
            index += 1
            continue

        index_code = record[0] if len(record) > 0 else " "
        worktree_code = record[1] if len(record) > 1 else " "
        path = record[3:] if len(record) > 3 else ""
        original_path = ""

        if index_code in {"R", "C"} or worktree_code in {"R", "C"}:
            index += 1
            original_path = parts[index] if index < len(parts) else ""

        description = describe_status(index_code, worktree_code)
        entries.append(
            {
                "path": path,
                "original_path": original_path,
                "index_status": index_code,
                "worktree_status": worktree_code,
                **description,
            }
        )
        index += 1

    return entries


# Summarizes status counts for the header without making the frontend recalculate business logic.
def summarize_status(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Return aggregate counts for changed, staged, unstaged, untracked, and conflicted files."""

    return {
        "changed": len(entries),
        "staged": sum(1 for entry in entries if entry["staged"]),
        "unstaged": sum(1 for entry in entries if entry["unstaged"]),
        "untracked": sum(1 for entry in entries if entry["untracked"]),
        "conflicts": sum(1 for entry in entries if entry["conflict"]),
    }
