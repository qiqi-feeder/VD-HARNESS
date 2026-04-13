"""skill_manage tool — Agent 用此工具对 custom skills 进行 CRUD 操作。

6 种 action: create / edit / delete / write_file / remove_file / list
每个写操作都经过 SecurityScanner 扫描。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from vdflow.skills.manager import SkillManager
from vdflow.skills.scanner import SkillSecurityScanner

logger = logging.getLogger(__name__)

# Module-level references (set during app init)
_manager: SkillManager | None = None
_scanner: SkillSecurityScanner | None = None
_on_skills_changed: Any = None  # callback to refresh system prompt cache


def configure_skill_manage(
    manager: SkillManager,
    scanner: SkillSecurityScanner | None = None,
    on_skills_changed: Any = None,
) -> None:
    """Wire up the skill_manage tool with its dependencies."""
    global _manager, _scanner, _on_skills_changed
    _manager = manager
    _scanner = scanner or SkillSecurityScanner()
    _on_skills_changed = on_skills_changed


def _get_manager() -> SkillManager:
    if _manager is None:
        raise RuntimeError("skill_manage tool not configured — call configure_skill_manage() first")
    return _manager


@tool
async def skill_manage(action: str, name: str = "", content: str = "", filename: str = "") -> str:
    """Manage custom skills (create, edit, delete, list, write support files).

    Args:
        action: One of: create, edit, delete, list, write_file, remove_file.
        name: Skill name (hyphen-case, e.g. 'deploy-docker'). Required for all except 'list'.
        content: Skill content (YAML frontmatter + markdown). Required for create/edit/write_file.
        filename: Support file path (relative to skill dir). Required for write_file/remove_file.
    """
    mgr = _get_manager()

    if action == "list":
        skills = mgr.list_skills()
        if not skills:
            return "No custom skills found."
        return "Custom skills:\n" + "\n".join(f"  - {s}" for s in skills)

    if not name:
        return "Error: 'name' is required for this action."

    if action == "create":
        if not content:
            return "Error: 'content' is required for create. Must include YAML frontmatter (---\\nname: ...\\ndescription: ...\\n---)."
        result = await mgr.create(name, content, scanner=_scanner)
        if "error" in result:
            return f"Error: {result['error']}"
        _notify_change()
        return f"Skill '{name}' created successfully."

    elif action == "edit":
        if not content:
            return "Error: 'content' is required for edit."
        result = await mgr.edit(name, content, scanner=_scanner)
        if "error" in result:
            return f"Error: {result['error']}"
        _notify_change()
        return f"Skill '{name}' updated successfully."

    elif action == "delete":
        result = await mgr.delete(name)
        if "error" in result:
            return f"Error: {result['error']}"
        _notify_change()
        return f"Skill '{name}' deleted."

    elif action == "write_file":
        if not filename or not content:
            return "Error: 'filename' and 'content' are required for write_file."
        result = await mgr.write_support_file(name, filename, content, scanner=_scanner)
        if "error" in result:
            return f"Error: {result['error']}"
        return f"File '{filename}' written to skill '{name}'."

    elif action == "remove_file":
        if not filename:
            return "Error: 'filename' is required for remove_file."
        skill_dir = mgr.get_skill_dir(name)
        from vdflow.skills.manager import ensure_safe_path
        target = ensure_safe_path(skill_dir, filename)
        if target is None:
            return "Error: path traversal detected."
        if not target.exists():
            return f"Error: file '{filename}' not found in skill '{name}'."
        target.unlink()
        return f"File '{filename}' removed from skill '{name}'."

    else:
        return f"Error: unknown action '{action}'. Use: create, edit, delete, list, write_file, remove_file."


def _notify_change() -> None:
    if _on_skills_changed is not None:
        try:
            _on_skills_changed()
        except Exception:
            logger.debug("Skills change callback failed", exc_info=True)
