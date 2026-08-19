"""Bridge handlers for AI skill category management."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk import aiskills


# Keeps AI skill folder actions outside the main BridgeController class.
def ai_skill_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for AI skill category management."""

    return {
        "listAISkillCategories": lambda payload: handle_list_categories(controller, payload),
        "createAISkillCategory": lambda payload: handle_create_category(controller, payload),
        "openAISkillCategory": lambda payload: handle_open_category(controller, payload),
        "addAISkillCategoryToRepo": lambda payload: handle_add_category_to_repo(controller, payload),
        "saveAISkillSelection": lambda payload: handle_save_selection(controller, payload),
    }


# Returns category folders plus the saved active category selection.
def handle_list_categories(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return AI skill categories and saved selection state."""

    settings = controller.settings_store.load()
    data = aiskills.list_categories()
    data["selected"] = settings.get("active_ai_skill_categories", [])
    return data


# Creates a new category folder and returns a refreshed category list.
def handle_create_category(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create one AI skill category folder."""

    aiskills.create_category(str(payload.get("name") or ""))
    return handle_list_categories(controller, payload)


# Opens a category folder so skill files can be added by the user.
def handle_open_category(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Open one AI skill category folder."""

    return aiskills.open_category(str(payload.get("name") or ""))


# Copies a category folder into the currently active repository.
def handle_add_category_to_repo(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Copy one AI skill category into the active repository."""

    path = controller.repository_path_from_payload(payload)
    result = aiskills.add_category_to_repository(str(payload.get("name") or ""), path)
    result["status"] = controller.git_service.status(path)
    return result


# Persists selected Overview AI skill categories.
def handle_save_selection(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Save selected AI skill category names."""

    selected = payload.get("categories") or []
    settings = controller.settings_store.save({"active_ai_skill_categories": selected})
    data = aiskills.list_categories()
    data["selected"] = settings["active_ai_skill_categories"]
    return data
