"""Ownership-aware cleanup for Shared Resource release updates."""

from __future__ import annotations

# Standard-library paths and callables keep this helper independent from resource catalog storage.
from pathlib import Path
from typing import Callable


# Removes retired release paths only when their current bytes still match the prior owned installation.
def retire_removed_paths(
    destination: Path,
    previous_files: dict[str, str],
    next_files: dict[str, str],
    target_for: Callable[[Path, str], Path],
    digest_for: Callable[[Path], str],
) -> dict[str, int]:
    """Retire unchanged owned paths omitted by a newer release while preserving user edits."""

    removed = 0
    preserved = 0
    retired_paths = set(previous_files) - set(next_files)
    # Only paths owned by the prior manifest can be considered for release retirement.
    for relative_path in sorted(retired_paths, key=str.casefold):
        target = target_for(destination, relative_path)
        expected_digest = previous_files[relative_path]
        matches_owned_bytes = (
            target.is_file()
            and not target.is_symlink()
            and digest_for(target) == expected_digest
        )
        # Matching bytes remain app-owned; changed or replaced paths belong to the user and must survive.
        if matches_owned_bytes:
            target.unlink()
            removed += 1
        elif target.exists() or target.is_symlink():
            preserved += 1
        parent = target.parent
        # Empty parents are pruned only within the destination boundary.
        while parent != destination:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    return {"retired_file_count": removed, "preserved_retired_file_count": preserved}
