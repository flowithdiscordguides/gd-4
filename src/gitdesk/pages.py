"""GitHub Pages workflow file management for local GitDesk repositories."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from gitdesk.branchops import repository_has_commits
from gitdesk.errors import AppError
from gitdesk.gitops import active_branch_name, open_repository


# GitDesk owns one workflow file so repeated saves update the same Pages automation.
PAGES_WORKFLOW_PATH = Path(".github") / "workflows" / "gitdesk-pages.yml"

# GitHub's branch publishing UI supports root and /docs; the workflow mirrors those choices.
SOURCE_FOLDERS = {
    "/": ".",
    "/docs": "docs",
}

# The custom entry field is a filename, not a shell path, so the workflow cannot be injected.
PAGE_FILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.html?$", re.IGNORECASE)


# Returns the Pages workflow path inside the selected repository.
def workflow_file_path(path_value: str) -> Path:
    """Return the absolute path to GitDesk's Pages workflow file."""

    repo = open_repository(path_value)
    root = Path(repo.working_tree_dir or path_value).resolve()
    return root / PAGES_WORKFLOW_PATH


# Normalizes the source folder dropdown into the folder checked by the workflow.
def clean_source_folder(value: str) -> tuple[str, str]:
    """Return the public Pages source label and repository-relative folder."""

    source = str(value or "/").strip() or "/"
    if source not in SOURCE_FOLDERS:
        raise AppError("GitHub Pages source folder must be / or /docs.", "PAGES_SOURCE_INVALID")
    return source, SOURCE_FOLDERS[source]


# Validates the entry filename before it is written into a GitHub Actions workflow.
def clean_page_file(value: str) -> str:
    """Return a safe HTML filename for the Pages entry file."""

    page_file = str(value or "index.html").strip() or "index.html"
    if "/" in page_file or "\\" in page_file or not PAGE_FILE_PATTERN.match(page_file):
        raise AppError("GitHub Pages file must be an HTML filename.", "PAGES_FILE_INVALID")
    return page_file


# Extracts a previously saved GitDesk Pages config from the generated workflow comments.
def read_pages_config(path_value: str) -> dict[str, str]:
    """Return saved Pages workflow settings, or defaults when no workflow exists."""

    workflow_path = workflow_file_path(path_value)
    config = {"branch": "", "source_folder": "/", "page_file": "index.html"}
    if not workflow_path.exists():
        return config

    for line in workflow_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# GitDesk-Pages-Branch:"):
            config["branch"] = line.split(":", 1)[1].strip()
        elif line.startswith("# GitDesk-Pages-Source:"):
            config["source_folder"] = line.split(":", 1)[1].strip()
        elif line.startswith("# GitDesk-Pages-File:"):
            config["page_file"] = line.split(":", 1)[1].strip()
    return config


# Builds the local branch list and saved Pages config for the frontend panel.
def pages_state(path_value: str) -> dict[str, Any]:
    """Return local branch and saved workflow state for the Pages panel."""

    repo = open_repository(path_value)
    return {
        "current_branch": active_branch_name(repo),
        "has_commits": repository_has_commits(repo),
        "branches": [head.name for head in repo.heads],
        "config": read_pages_config(path_value),
        "workflow_files": pages_workflow_files(path_value),
        "workflow_path": str(workflow_file_path(path_value)),
    }


# Lists only workflow files GitHub recognizes so Actions mode can preserve and report user-owned automation.
def pages_workflow_files(path_value: str) -> list[str]:
    """Return repository-relative YAML workflow paths from .github/workflows."""

    repo = open_repository(path_value)
    root = Path(repo.working_tree_dir or path_value).resolve()
    workflows_path = root / ".github" / "workflows"
    if not workflows_path.is_dir():
        return []
    return sorted(
        path.relative_to(root).as_posix()
        for path in workflows_path.iterdir()
        if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
    )


# Validates the local fields required by GitHub's legacy branch publishing source.
def prepare_pages_source(path_value: str, branch: str, source_folder: str) -> dict[str, str]:
    """Return validated branch and folder values for remote Pages branch publishing."""

    repo = open_repository(path_value)
    branch_name = str(branch or "").strip()
    if not branch_name:
        raise AppError("Select a branch before saving GitHub Pages.", "PAGES_BRANCH_EMPTY")
    if branch_name not in [head.name for head in repo.heads]:
        raise AppError("The selected Pages branch does not exist locally.", "PAGES_BRANCH_MISSING")
    if not repository_has_commits(repo):
        raise AppError("Create the first commit before setting up GitHub Pages.", "PAGES_UNBORN_HEAD")
    clean_source, _relative_source = clean_source_folder(source_folder)
    return {"branch": branch_name, "source_folder": clean_source}


# Ensures the selected Pages source exists in the active working tree before saving.
def validate_pages_source(path_value: str, source_folder: str, page_file: str) -> None:
    """Raise AppError when the requested Pages entry file does not exist locally."""

    repo = open_repository(path_value)
    root = Path(repo.working_tree_dir or path_value).resolve()
    _, relative_source = clean_source_folder(source_folder)
    source_path = (root / relative_source).resolve()
    try:
        source_path.relative_to(root)
    except ValueError as error:
        raise AppError("GitHub Pages source folder is outside the repository.", "PAGES_SOURCE_INVALID") from error

    entry_path = source_path / clean_page_file(page_file)
    if not source_path.is_dir() or not entry_path.is_file():
        raise AppError("The selected Pages HTML file does not exist.", "PAGES_FILE_MISSING")


# Validates the requested Pages settings without writing files.
def prepare_pages_settings(path_value: str, branch: str, source_folder: str, page_file: str) -> dict[str, str]:
    """Return validated Pages settings for GitHub and workflow creation."""

    repo = open_repository(path_value)
    branch_name = str(branch or "").strip()
    if not branch_name:
        raise AppError("Select a branch before saving GitHub Pages.", "PAGES_BRANCH_EMPTY")
    if branch_name not in [head.name for head in repo.heads]:
        raise AppError("The selected Pages branch does not exist locally.", "PAGES_BRANCH_MISSING")
    if active_branch_name(repo) != branch_name:
        raise AppError("Checkout the selected Pages branch before saving.", "PAGES_BRANCH_NOT_ACTIVE")
    if not repository_has_commits(repo):
        raise AppError("Create the first commit before setting up GitHub Pages.", "PAGES_UNBORN_HEAD")

    clean_source, relative_source = clean_source_folder(source_folder)
    clean_file = clean_page_file(page_file)
    validate_pages_source(path_value, clean_source, clean_file)

    return {
        "branch": branch_name,
        "source_folder": clean_source,
        "relative_source": relative_source,
        "page_file": clean_file,
        "workflow_path": str(workflow_file_path(path_value)),
    }


# Writes the workflow that deploys the selected folder and entry file through GitHub Pages.
def write_prepared_pages_workflow(path_value: str, settings: dict[str, str]) -> dict[str, str]:
    """Create or update the local GitDesk Pages workflow file from validated settings."""

    workflow_path = workflow_file_path(path_value)
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(
        pages_workflow_source(
            settings["branch"],
            settings["source_folder"],
            settings["relative_source"],
            settings["page_file"],
        ),
        encoding="utf-8",
    )
    return {
        "branch": settings["branch"],
        "source_folder": settings["source_folder"],
        "page_file": settings["page_file"],
        "workflow_path": str(workflow_path),
    }


# Writes a workflow after validating the user-facing Pages form fields.
def write_pages_workflow(path_value: str, branch: str, source_folder: str, page_file: str) -> dict[str, str]:
    """Validate and create the local GitDesk Pages workflow file."""

    settings = prepare_pages_settings(path_value, branch, source_folder, page_file)
    return write_prepared_pages_workflow(path_value, settings)


# Produces a workflow using JSON-quoted values so branch/file names stay data, not shell.
def pages_workflow_source(branch: str, source_folder: str, relative_source: str, page_file: str) -> str:
    """Return the GitHub Actions workflow YAML used for Pages deployment."""

    branch_value = json.dumps(branch)
    source_value = json.dumps(relative_source)
    file_value = json.dumps(page_file)
    return f"""# GitDesk-Pages-Branch: {branch}
# GitDesk-Pages-Source: {source_folder}
# GitDesk-Pages-File: {page_file}
name: GitDesk Pages

on:
  push:
    branches:
      - {branch_value}
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: gitdesk-pages
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{{{ steps.deployment.outputs.page_url }}}}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v6
      - name: Prepare site
        env:
          GITDESK_PAGES_SOURCE: {source_value}
          GITDESK_PAGES_FILE: {file_value}
        run: |
          python3 - <<'PY'
          from pathlib import Path
          import os
          import shutil

          workspace = Path.cwd().resolve()
          source = (workspace / os.environ["GITDESK_PAGES_SOURCE"]).resolve()
          source.relative_to(workspace)
          entry = source / os.environ["GITDESK_PAGES_FILE"]
          if not entry.is_file():
              raise SystemExit(f"Missing Pages entry file: {{entry}}")
          output = Path(os.environ["RUNNER_TEMP"]).resolve() / "gitdesk_pages_site"
          if output.exists():
              shutil.rmtree(output)
          ignored = shutil.ignore_patterns(".git", ".github", "node_modules", "venv", ".venv", "env")
          shutil.copytree(source, output, ignore=ignored)
          if entry.name != "index.html":
              shutil.copy2(entry, output / "index.html")
          PY
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v4
        with:
          path: ${{{{ runner.temp }}}}/gitdesk_pages_site
      - name: Deploy
        id: deployment
        uses: actions/deploy-pages@v4
"""
