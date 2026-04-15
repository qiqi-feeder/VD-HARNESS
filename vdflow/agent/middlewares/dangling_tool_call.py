"""Middleware to fix dangling tool calls in message history.

A dangling tool call occurs when an AIMessage contains tool_calls but there are
no corresponding ToolMessages in the history (e.g., due to user interruption or
request cancellation). This causes LLM errors due to incomplete message format.

This middleware intercepts the model call to detect and patch such gaps by
inserting synthetic ToolMessages with an error indicator immediately after the
AIMessage that made the tool calls, ensuring correct message ordering.

Ported from DeerFlow's DanglingToolCallMiddleware.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing_extensions import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import ToolMessage

logger = logging.getLogger(__name__)


class DanglingToolCallMiddleware(AgentMiddleware[AgentState]):
    """Inserts placeholder ToolMessages for dangling tool calls before model invocation.

    Scans the message history for AIMessages whose tool_calls lack corresponding
    ToolMessages, and injects synthetic error responses immediately after the
    offending AIMessage so the LLM receives a well-formed conversation.
    """

    def _build_patched_messages(self, messages: list) -> list | None:
        """Return a new message list with patches inserted at the correct positions.

        Handles two cases:
        1. AIMessages with dangling tool_calls (no corresponding ToolMessage) →
           inject synthetic ToolMessages immediately after those AIMessages.
        2. ToolMessages whose tool_call_id has no matching AIMessage tool_call →
           remove them (orphaned tool output causes API 400 errors on some providers).

        Returns None if no patches are needed.
        """
        # Collect IDs of all existing ToolMessages
        existing_tool_msg_ids: set[str] = set()
        for msg in messages:
            if isinstance(msg, ToolMessage):
                existing_tool_msg_ids.add(msg.tool_call_id)

        # Collect all AIMessage tool_call IDs
        ai_tool_call_ids: set[str] = set()
        for msg in messages:
            if getattr(msg, "type", None) != "ai":
                continue
            for tc in getattr(msg, "tool_calls", None) or []:
                tc_id = tc.get("id")
                if tc_id:
                    ai_tool_call_ids.add(tc_id)

        # Check: dangling tool calls (AIMessage has tool_calls but no ToolMessage)
        has_dangling_calls = False
        for msg in messages:
            if getattr(msg, "type", None) != "ai":
                continue
            for tc in getattr(msg, "tool_calls", None) or []:
                tc_id = tc.get("id")
                if tc_id and tc_id not in existing_tool_msg_ids:
                    has_dangling_calls = True
                    break
            if has_dangling_calls:
                break

        # Check: orphaned tool messages (ToolMessage with no matching AIMessage tool_call)
        orphaned_tool_msg_ids: set[str] = set()
        for msg in messages:
            if isinstance(msg, ToolMessage):
                if msg.tool_call_id and msg.tool_call_id not in ai_tool_call_ids:
                    orphaned_tool_msg_ids.add(msg.tool_call_id)

        if not has_dangling_calls and not orphaned_tool_msg_ids:
            return None

        # Build new list with patches
        patched: list = []
        patched_ids: set[str] = set()
        patch_count = 0
        orphan_count = 0

        for msg in messages:
            # Skip orphaned ToolMessages
            if isinstance(msg, ToolMessage) and msg.tool_call_id in orphaned_tool_msg_ids:
                orphan_count += 1
                continue

            patched.append(msg)

            # Inject synthetic ToolMessages for dangling tool calls
            if getattr(msg, "type", None) != "ai":
                continue
            for tc in getattr(msg, "tool_calls", None) or []:
                tc_id = tc.get("id")
                if tc_id and tc_id not in existing_tool_msg_ids and tc_id not in patched_ids:
                    patched.append(
                        ToolMessage(
                            content="[Tool call was interrupted and did not return a result.]",
                            tool_call_id=tc_id,
                            name=tc.get("name", "unknown"),
                            status="error",
                        )
                    )
                    patched_ids.add(tc_id)
                    patch_count += 1

        if patch_count:
            logger.warning("Injecting %d placeholder ToolMessage(s) for dangling tool calls", patch_count)
        if orphan_count:
            logger.warning("Removing %d orphaned ToolMessage(s) with no matching tool_calls", orphan_count)
        return patched

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        patched = self._build_patched_messages(request.messages)
        if patched is not None:
            request = request.override(messages=patched)
        return handler(request)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        patched = self._build_patched_messages(request.messages)
        if patched is not None:
            request = request.override(messages=patched)
        return await handler(request)
