"""webui2 bridge between the bundled frontend and Python services."""

from __future__ import annotations

# Standard-library JSON and type definitions support bridge dispatch.
import json
from typing import Any, Callable

# WebUI supplies the native desktop callback surface.
from webui import webui

# Feature bridge registries keep the central controller below its file-size ceiling.
from gitdesk.action_jingle_bridge import action_jingle_handlers, action_jingle_settings
from gitdesk.actions_bridge import actions_handlers
from gitdesk.activity_tracker_bridge import activity_tracker_handlers
from gitdesk.authrecovery import settings_with_token_accounts
from gitdesk.backup_bridge import backup_handlers
from gitdesk.aiskill_bridge import ai_skill_handlers
from gitdesk.config import SettingsStore
from gitdesk.desktop_clipboard_bridge import desktop_clipboard_handlers
from gitdesk.dialogs import choose_directory
from gitdesk.documentbuilder_bridge import document_builder_handlers
from gitdesk.editor_settings_bridge import editor_settings_handlers
from gitdesk.errors import AppError, safe_unexpected_error
from gitdesk.credential_profiles import AccountBridgeMixin, repository_pair_from_origin
from gitdesk.gitbasics_bridge import git_basic_handlers
from gitdesk.gitops import GitService
from gitdesk.giturls import parse_github_remote
from gitdesk.localproject_bridge import local_project_handlers
from gitdesk.managedrepo_bridge import managed_repository_handlers
from gitdesk.managedrepos import repositories_for_account, repository_settings_update
from gitdesk.media_bridge import media_handlers
from gitdesk.pages_bridge import pages_handlers
from gitdesk.projecthub_bridge import project_hub_handlers
from gitdesk.pullrequest_bridge import pull_request_handlers
from gitdesk.publishops_bridge import publish_handlers
from gitdesk.repoaction_bridge import repository_action_handlers
from gitdesk.repositoryrepair import repair_cloned_repository_metadata
from gitdesk.releases_bridge import release_handlers
from gitdesk.repositorysetup_bridge import repository_setup_handlers
from gitdesk.secrets import TokenStore
from gitdesk.sharedresource_bridge import shared_resource_handlers
from gitdesk.syncchain_bridge import sync_chain_handlers
from gitdesk.syncignore_bridge import sync_ignore_handlers
from gitdesk.theme_profile_bridge import theme_profile_handlers
from gitdesk.updater_bridge import updater_handlers
from gitdesk.versioncompare_bridge import version_compare_handlers


# Handler functions accept a JSON-like payload and return JSON-serializable data.
BridgeHandler = Callable[[dict[str, Any]], Any]


# BridgeController owns the native callback and dispatches UI actions to backend service methods.
class BridgeController(AccountBridgeMixin):
    """Translate frontend requests on the non-blocking event threads supplied by WebUI."""

    # Initializes services and the action routing table used by JavaScript request payloads.
    def __init__(
        self,
        window: webui.Window,
        settings_store: SettingsStore,
        token_store: TokenStore,
        git_service: GitService,
    ) -> None:
        self.window = window
        self.settings_store = settings_store
        self.token_store = token_store
        self.git_service = git_service
        self.handlers: dict[str, BridgeHandler] = {
            "bootstrap": self.handle_bootstrap,
            "saveAccount": self.handle_save_account,
            "clearAccount": self.handle_clear_account,
            "selectAccount": self.handle_select_account,
            "saveSettings": self.handle_save_settings,
            "chooseCloneDestination": self.handle_choose_clone_destination,
            "cloneRepository": self.handle_clone_repository,
            "refreshStatus": self.handle_refresh_status,
            "listBranches": self.handle_list_branches,
            "checkoutBranch": self.handle_checkout_branch,
            "createBranch": self.handle_create_branch,
            "commit": self.handle_commit,
            "push": self.handle_push,
            "pull": self.handle_pull,
        }
        self.handlers.update(managed_repository_handlers(self))
        self.handlers.update(backup_handlers(self))
        self.handlers.update(repository_setup_handlers(self))
        self.handlers.update(repository_action_handlers(self))
        self.handlers.update(actions_handlers(self))
        self.handlers.update(action_jingle_handlers(self))
        self.handlers.update(activity_tracker_handlers(self))
        self.handlers.update(project_hub_handlers(self))
        self.handlers.update(pull_request_handlers(self))
        self.handlers.update(publish_handlers(self))
        self.handlers.update(release_handlers(self))
        self.handlers.update(git_basic_handlers(self))
        self.handlers.update(ai_skill_handlers(self))
        self.handlers.update(shared_resource_handlers(self))
        self.handlers.update(pages_handlers(self))
        self.handlers.update(local_project_handlers(self))
        self.handlers.update(desktop_clipboard_handlers(self))
        self.handlers.update(media_handlers(self))
        self.handlers.update(document_builder_handlers(self))
        self.handlers.update(editor_settings_handlers(self))
        self.handlers.update(sync_chain_handlers(self))
        self.handlers.update(sync_ignore_handlers(self))
        self.handlers.update(theme_profile_handlers(self))
        self.handlers.update(updater_handlers(self))
        self.handlers.update(version_compare_handlers(self))

    # Registers the single frontend-to-backend function exposed by webui.js.
    def bind(self) -> None:
        """Bind the nativeInvoke JavaScript function to the WebUI window."""

        self.window.bind("nativeInvoke", self.handle_native_invoke)

    # Processes one request on the non-blocking event thread already created by WebUI.
    def handle_native_invoke(self, event: webui.Event) -> None:
        """Accept a JSON request from JavaScript and return a structured JSON response."""

        raw_request = event.get_string()
        response = self.process_request(raw_request)
        event.return_string(json.dumps(response))

    # Parses the request envelope and returns either an action result or a structured error.
    def process_request(self, raw_request: str) -> dict[str, Any]:
        """Decode a frontend request, dispatch it, and return a response envelope."""

        request_id = "unknown"
        try:
            request = json.loads(raw_request)
            if not isinstance(request, dict):
                raise AppError("Native request must be a JSON object.", "BRIDGE_REQUEST_INVALID")

            request_id = str(request.get("requestId") or "unknown")
            action = str(request.get("action") or "")
            payload = request.get("payload") or {}
            if not isinstance(payload, dict):
                raise AppError("Native request payload must be a JSON object.", "BRIDGE_PAYLOAD_INVALID")

            handler = self.handlers.get(action)
            if handler is None:
                raise AppError("Unknown native action requested.", "BRIDGE_ACTION_UNKNOWN", {"action": action})

            data = handler(payload)
            return {"requestId": request_id, "ok": True, "data": data}
        except AppError as error:
            return {"requestId": request_id, "ok": False, "error": error.to_payload()}
        except Exception as error:
            return {"requestId": request_id, "ok": False, "error": safe_unexpected_error(error)}

    # Returns initial app state without exposing any saved token value.
    def handle_bootstrap(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return settings, token presence, and settings location for initial UI rendering."""

        settings = settings_with_token_accounts(self.settings_store, self.token_store)
        return {
            "settings": settings,
            "auth": self.auth_state(settings),
            "action_jingles": action_jingle_settings(),
            "settings_location": self.settings_store.location(),
        }

    # Persists non-secret settings such as repository path and GitHub owner/repo fields.
    def handle_save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist non-secret settings and return the saved values."""

        return {"settings": self.settings_store.save(payload)}

    # Opens the native folder picker so clone destinations can be selected instead of typed.
    def handle_choose_clone_destination(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the selected clone destination folder path, or an empty path when cancelled."""

        initial_path = str(payload.get("initial_path") or "")
        selected_path = choose_directory(initial_path, "Choose clone destination folder")
        return {"path": selected_path}

    # Clones a GitHub repository, opens the clone, and saves it as the active repository.
    def handle_clone_repository(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Clone a GitHub repository and return opened repository state."""

        clone_url = str(payload.get("url") or "")
        parent_path = str(payload.get("parent_path") or "")
        folder_name = str(payload.get("folder_name") or "")
        use_saved_token = bool(payload.get("use_saved_token", False))
        remote_owner = parse_github_remote(clone_url).get("owner", "")
        owner = str(payload.get("repository_owner") or remote_owner).strip()
        account = self.account_for_owner(owner, payload, use_saved_token)
        auth_login = (
            account["login"]
            if account and use_saved_token and clone_url.strip().startswith("https://")
            else None
        )

        summary = self.git_service.clone_repository(clone_url, parent_path, folder_name, auth_login, account)
        settings_update = (
            repository_settings_update(self.settings_store.load(), account["login"], summary, "cloned")
            if account
            else {"repository_path": summary["path"]}
        )
        if not account and summary["github_owner"] and summary["github_repo"]:
            settings_update["github_owner"] = summary["github_owner"]
            settings_update["github_repo"] = summary["github_repo"]

        if account:
            settings_update["active_account"] = account["login"]
        settings = self.settings_store.save(settings_update)
        return {
            "auth": self.auth_state(settings),
            "repository": summary,
            "settings": settings,
            "status": self.git_service.status(summary["path"]),
            "branches": self.git_service.branches(summary["path"]),
        }

    # Refreshes local Git status for the active repository path.
    def handle_refresh_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return current local Git status for the requested repository path."""

        path = self.repository_path_from_payload(payload)
        try:
            return self.git_service.status(path)
        except AppError as error:
            if error.code != "REPOSITORY_INVALID":
                raise
        record = self.managed_repository_record(payload, path)
        owner = str((record or {}).get("owner") or "")
        account = self.account_for_owner(owner, payload, required=False)
        auth_login = account["login"] if account else None
        repair_cloned_repository_metadata(path, record or {}, auth_login)
        return self.git_service.status(path)

    # Returns local branch data for the current repository.
    def handle_list_branches(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return local branches for the requested repository path."""

        return self.git_service.branches(self.repository_path_from_payload(payload))

    # Checks out a local branch and returns refreshed branch and status data.
    def handle_checkout_branch(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Checkout a local branch and return refreshed repository data."""

        path = self.repository_path_from_payload(payload)
        branches = self.git_service.checkout_branch(path, str(payload.get("branch") or ""))
        return {"branches": branches, "status": self.git_service.status(path)}

    # Creates a new branch and returns refreshed branch and status data.
    def handle_create_branch(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a branch and return refreshed repository data."""

        path = self.repository_path_from_payload(payload)
        checkout = bool(payload.get("checkout", True))
        branches = self.git_service.create_branch(path, str(payload.get("branch") or ""), checkout)
        try:
            status = self.git_service.status(path)
        except AppError as error:
            raise AppError("Branch was created, but status refresh failed.", error.code) from error
        except Exception as error:
            raise AppError("Branch was created, but status refresh failed.", "GIT_STATUS_FAILED") from error
        return {"branches": branches, "status": status}

    # Creates a commit from selected files and optionally pushes it to origin.
    def handle_commit(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Commit selected files and optionally push the active branch."""

        files = payload.get("files") or []
        if not isinstance(files, list):
            raise AppError("Commit files must be sent as a list.", "COMMIT_FILES_INVALID")
        return self.git_service.commit(
            self.repository_path_from_payload(payload),
            str(payload.get("message") or ""),
            [str(file_path) for file_path in files],
            bool(payload.get("push", False)),
            self.optional_auth_login(payload),
            self.account_for_repository(payload, required=False),
        )

    # Pushes the active branch using the user's normal Git authentication.
    def handle_push(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Push the active branch to origin."""

        return self.git_service.push(self.repository_path_from_payload(payload), self.optional_auth_login(payload))

    # Pulls from origin and returns the refreshed status payload.
    def handle_pull(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Pull from origin for the active repository."""

        return self.git_service.pull(self.repository_path_from_payload(payload), self.optional_auth_login(payload))

    # Reads the active repository path from the request or saved settings.
    def repository_path_from_payload(self, payload: dict[str, Any]) -> str:
        """Return the active repository path from payload values or persisted settings."""

        path = str(payload.get("path") or "").strip()
        settings = self.settings_store.load()
        path = path or str(settings.get("repository_path") or "")
        login = str(payload.get("account_login") or settings.get("active_account") or "").strip()
        if login and path:
            allowed_paths = [record["path"] for record in repositories_for_account(settings, login)]
            if path not in allowed_paths:
                raise AppError("That repository is not managed by the active account.", "MANAGED_REPOSITORY_FORBIDDEN")
        return path

    # Finds the exact saved record used to authorize metadata recovery for an app-cloned repository.
    def managed_repository_record(self, payload: dict[str, Any], path: str) -> dict[str, Any] | None:
        """Return the active account's managed record for an exact local path."""

        settings = self.settings_store.load()
        login = str(payload.get("account_login") or settings.get("active_account") or "").strip()
        if not login:
            return None
        return next(
            (record for record in repositories_for_account(settings, login) if record["path"] == path),
            None,
        )

    # Reads the GitHub owner/repo pair from the request or saved settings.
    def github_pair_from_payload(self, payload: dict[str, Any]) -> tuple[str, str]:
        """Return the GitHub owner and repo names from payload values or persisted settings."""

        requested_path = str(payload.get("path") or "").strip()
        if requested_path:
            path = self.repository_path_from_payload(payload)
            owner, repo = repository_pair_from_origin(self.git_service, path)
            if owner and repo:
                return owner, repo
        settings = self.settings_store.load()
        owner = str(payload.get("owner") or settings.get("github_owner") or "")
        repo = str(payload.get("repo") or settings.get("github_repo") or "")
        return owner, repo
