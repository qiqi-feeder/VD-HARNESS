"""ContextCompressorMiddleware — zero-cost pre-trimming of old tool outputs.

Runs BEFORE SummarizationMiddleware to reduce token waste:
1. Truncates non-recent tool outputs (> tail_protect_messages) that exceed
   max_chars to "[Previous tool output truncated]".
2. Removes orphaned ToolMessages whose corresponding AI tool_call was stripped.

This is a lightweight, deterministic pass — no LLM calls needed.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.runtime import Runtime

from vdflow.agent.middlewares._utils import _state_get
from vdflow.agent.state import ThreadState

logger = logging.getLogger(__name__)

# Defaults
_DEFAULT_TOOL_OUTPUT_MAX_CHARS = 500
_DEFAULT_TAIL_PROTECT_MESSAGES = 6  # last N messages are never compressed
_TRUNCATION_MARKER = "[Previous tool output truncated — {original_chars} chars]"


class ContextCompressorMiddleware(AgentMiddleware[ThreadState]):
    """Pre-trim old tool outputs before SummarizationMiddleware.

    This middleware:
    - Truncates old tool outputs that are very long (saves tokens without LLM calls)
    - Fixes orphan tool messages (tool responses without a corresponding tool_call)
    """

    state_schema = ThreadState

    def __init__(
        self,
        *,
        tool_output_max_chars: int = _DEFAULT_TOOL_OUTPUT_MAX_CHARS,
        tail_protect_messages: int = _DEFAULT_TAIL_PROTECT_MESSAGES,
    ):
        super().__init__()
        self.tool_output_max_chars = tool_output_max_chars
        self.tail_protect_messages = tail_protect_messages

    # ------------------------------------------------------------------
    # before_model: compress old tool outputs
    # ------------------------------------------------------------------

    def before_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        messages: list[BaseMessage] = _state_get(state, "messages", [])
        if not messages:
            return None

        # Determine the protection boundary
        protect_from = max(0, len(messages) - self.tail_protect_messages)
        modified = False
        new_messages: list[BaseMessage] = []

        # Collect all tool_call IDs that exist in AI messages
        live_tool_call_ids: set[str] = set()
        for msg in messages:
            if isinstance(msg, AIMessage):
                for tc in getattr(msg, "tool_calls", []) or []:
                    tc_id = tc.get("id")
                    if tc_id:
                        live_tool_call_ids.add(tc_id)

        for idx, msg in enumerate(messages):
            # --- Truncate old, long tool outputs ---
            if (
                isinstance(msg, ToolMessage)
                and idx < protect_from
                and isinstance(msg.content, str)
                and len(msg.content) > self.tool_output_max_chars
            ):
                original_len = len(msg.content)
                truncated = ToolMessage(
                    content=_TRUNCATION_MARKER.format(original_chars=original_len),
                    tool_call_id=msg.tool_call_id,
                    name=msg.name or "tool",
                    status=msg.status,
                )
                new_messages.append(truncated)
                modified = True
                continue

            # --- Fix orphan ToolMessages ---
            if isinstance(msg, ToolMessage):
                tc_id = msg.tool_call_id
                if tc_id and tc_id not in live_tool_call_ids:
                    # This ToolMessage has no parent AI tool_call — skip it
                    logger.debug(
                        "Removing orphan ToolMessage: tool_call_id=%s name=%s",
                        tc_id,
                        msg.name,
                    )
                    modified = True
                    continue

            new_messages.append(msg)

        if not modified:
            return None

        logger.info(
            "ContextCompressor: compressed %d messages → %d messages",
            len(messages),
            len(new_messages),
        )
        return {"messages": new_messages}
