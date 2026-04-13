"""Tool loading utilities for VD-Flow."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from langchain_core.tools import BaseTool

from vdflow.config.models import Config
from vdflow.tools.builtins import BUILTIN_TOOLS, ask_clarification_tool, get_builtin_tools

logger = logging.getLogger(__name__)


def _resolve_variable(import_path: str) -> Any:
    module_path, attr_name = import_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


def _tool_name(tool: Any) -> str:
    return getattr(tool, "name", getattr(tool, "__name__", ""))


def _inject_harness_tools(config: Config, *, subagent_enabled: bool = False) -> list[Any]:
    """Conditionally inject Phase C/D tools based on config."""
    extra: list[Any] = []
    mw = config.middleware

    # D2: task tool — only when subagent_enabled (Ultra mode)
    if subagent_enabled:
        try:
            from vdflow.tools.task import task
            extra.append(task)
            logger.info("Injected task tool (subagent_enabled=True)")
        except ImportError:
            logger.debug("task tool unavailable")

    # C2: skill_manage tool — CRUD on custom skills
    if mw.skill_evolution_enabled:
        try:
            from vdflow.tools.skill_manage import skill_manage
            extra.append(skill_manage)
        except ImportError:
            logger.debug("skill_manage tool unavailable")

    # D4: search_past_sessions tool — cross-session FTS5 search
    try:
        from vdflow.tools.session_search import search_past_sessions
        extra.append(search_past_sessions)
    except ImportError:
        logger.debug("search_past_sessions tool unavailable")

    return extra


def get_available_tools(
    config: Config,
    *,
    model_name: str | None = None,
    subagent_enabled: bool = False,
    extra_tools: list[Any] | None = None,
) -> list[Any]:
    """Load tools from config and merge with built-ins + harness tools.

    Args:
        config: Application configuration.
        model_name: Optional model name for vision-tool filtering.
        subagent_enabled: If True, inject the task tool for subagent dispatch.
            Set to True for Ultra mode (lead agent), False for subagents.
    """

    loaded_tools: list[Any] = []
    for tool_config in config.tools:
        if not tool_config.enabled:
            continue
        if not config.is_tool_group_enabled(tool_config.group):
            continue
        if tool_config.group == "bash" and not config.runtime.allow_host_bash:
            continue
        if tool_config.requires_vision:
            model_config = next((model for model in config.models if model.name == model_name), None)
            if model_config is None or not model_config.supports_vision:
                continue
        loaded_tools.append(_resolve_variable(tool_config.use))

    builtins = list(BUILTIN_TOOLS)
    if ask_clarification_tool not in builtins:
        builtins.append(ask_clarification_tool)

    # Inject harness tools (task, skill_manage, search_past_sessions)
    harness_tools = _inject_harness_tools(config, subagent_enabled=subagent_enabled)

    deduped: dict[str, Any] = {}
    for tool in loaded_tools + builtins + harness_tools + list(extra_tools or []):
        name = _tool_name(tool)
        if not name:
            continue
        deduped[name] = tool
    return list(deduped.values())


__all__ = ["BUILTIN_TOOLS", "get_available_tools", "get_builtin_tools"]
