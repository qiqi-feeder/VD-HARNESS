"""Subagent system for VD-Flow."""

from vdflow.subagents.config import SubagentConfig, SubagentResult, SubagentStatus
from vdflow.subagents.executor import SubagentExecutor, create_executor
from vdflow.subagents.registry import (
    get_available_subagent_names,
    get_subagent_config,
    list_subagents,
    register_subagent,
)

__all__ = [
    "SubagentConfig",
    "SubagentExecutor",
    "SubagentResult",
    "SubagentStatus",
    "create_executor",
    "get_available_subagent_names",
    "get_subagent_config",
    "list_subagents",
    "register_subagent",
]
