"""SubagentLimitMiddleware — cap concurrent subagent spawns.

Prevents the lead agent from spawning too many subagents in a single turn.
If the AI message contains more `task` tool_calls than MAX_CONCURRENT,
the excess calls are removed and a warning is injected.

Ported from DeerFlow's SubagentLimitMiddleware.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.runtime import Runtime

from vdflow.agent.middlewares._utils import _state_get
from vdflow.agent.state import ThreadState

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONCURRENT = 3
_MIN_CONCURRENT = 1
_MAX_CONCURRENT_CAP = 5
_TASK_TOOL_NAME = "task"


class SubagentLimitMiddleware(AgentMiddleware[ThreadState]):
    """Cap the number of concurrent subagent task calls per turn.

    If the AI proposes more task tool_calls than max_concurrent,
    the excess are dropped and a warning is logged.
    """

    state_schema = ThreadState

    def __init__(self, *, max_concurrent: int = _DEFAULT_MAX_CONCURRENT):
        super().__init__()
        self.max_concurrent = max(
            _MIN_CONCURRENT, min(max_concurrent, _MAX_CONCURRENT_CAP)
        )

    def after_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        messages: list[BaseMessage] = _state_get(state, "messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return None

        tool_calls = getattr(last_msg, "tool_calls", None) or []
        if not tool_calls:
            return None

        # Separate task calls from other calls
        task_calls = [tc for tc in tool_calls if tc.get("name") == _TASK_TOOL_NAME]
        other_calls = [tc for tc in tool_calls if tc.get("name") != _TASK_TOOL_NAME]

        if len(task_calls) <= self.max_concurrent:
            return None

        # Truncate excess task calls
        kept = task_calls[: self.max_concurrent]
        dropped = task_calls[self.max_concurrent :]

        logger.warning(
            "SubagentLimit: truncated %d/%d task calls (max_concurrent=%d)",
            len(dropped),
            len(task_calls),
            self.max_concurrent,
        )

        # Rebuild the AI message with truncated tool_calls
        new_tool_calls = other_calls + kept
        new_msg = AIMessage(
            content=last_msg.content,
            tool_calls=new_tool_calls,
            response_metadata=getattr(last_msg, "response_metadata", {}),
        )

        # Replace the last message
        new_messages = list(messages[:-1]) + [new_msg]
        return {"messages": new_messages}
