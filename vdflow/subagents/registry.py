"""Subagent registry — built-in and custom subagent configurations."""

from __future__ import annotations

import logging

from vdflow.subagents.config import SubagentConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in subagent definitions (pure config, no class)
# ---------------------------------------------------------------------------

_BUILTIN_SUBAGENTS: dict[str, SubagentConfig] = {
    "general": SubagentConfig(
        name="general",
        description=(
            "A capable agent for complex, multi-step tasks that require "
            "both exploration and action. Use when the task requires complex "
            "reasoning, multiple dependent steps, or would benefit from "
            "isolated context."
        ),
        system_prompt=(
            "You are a general-purpose subagent working on a delegated task. "
            "Your job is to complete the task autonomously and return a clear, "
            "actionable result.\n\n"
            "Guidelines:\n"
            "- Focus on completing the delegated task efficiently\n"
            "- Use available tools as needed to accomplish the goal\n"
            "- Think step by step but act decisively\n"
            "- If you encounter issues, explain them clearly in your response\n"
            "- Return a concise summary of what you accomplished\n"
            "- Do NOT ask for clarification — work with the information provided\n"
            "- Do NOT delegate to other subagents\n\n"
            "When you complete the task, provide:\n"
            "1. A brief summary of what was accomplished\n"
            "2. Key findings or results\n"
            "3. Any relevant file paths, data, or artifacts created\n"
            "4. Issues encountered (if any)"
        ),
        disallowed_tools=["task", "ask_clarification"],
        max_turns=25,
        timeout_seconds=120,
    ),
    "bash": SubagentConfig(
        name="bash",
        description=(
            "Command execution specialist for running bash commands. "
            "Use for system administration, file operations, and build tasks."
        ),
        system_prompt=(
            "You are a system administration assistant operating as a subagent.\n\n"
            "Rules:\n"
            "- Execute the assigned command-line tasks safely\n"
            "- Report results clearly including exit codes and relevant output\n"
            "- Do NOT run destructive commands (rm -rf /, dd, mkfs, etc.)\n"
            "- Do NOT access sensitive files (/etc/shadow, .ssh/, .env, etc.)\n"
            "- If a command fails, explain why and suggest alternatives\n"
            "- Be concise"
        ),
        tools=["bash_tool"],
        disallowed_tools=["task", "ask_clarification"],
        max_turns=10,
        timeout_seconds=60,
    ),
    "writer": SubagentConfig(
        name="writer",
        description=(
            "Content writing and editing subagent. "
            "Use for creating or editing text, documentation, and reports."
        ),
        system_prompt=(
            "You are a skilled writer operating as a subagent.\n\n"
            "Rules:\n"
            "- Create or edit content as specified\n"
            "- Focus on clarity, accuracy, and appropriate tone\n"
            "- Use read_file / write_file tools to work with files\n"
            "- Be concise in your response"
        ),
        tools=["write_file_tool", "read_file_tool"],
        disallowed_tools=["task", "ask_clarification"],
        max_turns=10,
        timeout_seconds=90,
    ),
}

# User overrides (loaded from config)
_custom_subagents: dict[str, SubagentConfig] = {}


def register_subagent(config: SubagentConfig) -> None:
    """Register a custom subagent configuration."""
    _custom_subagents[config.name] = config
    logger.info("Registered custom subagent: %s", config.name)


def get_subagent_config(name: str) -> SubagentConfig | None:
    """Get subagent config by name. Custom overrides take priority."""
    return _custom_subagents.get(name) or _BUILTIN_SUBAGENTS.get(name)


def list_subagents() -> list[SubagentConfig]:
    """List all available subagent configs (builtins + custom)."""
    merged = {**_BUILTIN_SUBAGENTS, **_custom_subagents}
    return list(merged.values())


def get_available_subagent_names() -> list[str]:
    """Get names of all available subagents."""
    merged = {**_BUILTIN_SUBAGENTS, **_custom_subagents}
    return sorted(merged.keys())
