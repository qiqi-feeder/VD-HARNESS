"""Built-in subagent configurations.

Subagents are pure config objects (SubagentConfig), not classes.
All execution logic lives in SubagentExecutor.
"""

from vdflow.subagents.registry import get_subagent_config

__all__ = ["get_subagent_config"]
