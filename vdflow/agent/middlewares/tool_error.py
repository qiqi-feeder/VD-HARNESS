"""Middleware to convert tool exceptions into tool messages."""

from __future__ import annotations

import logging
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from vdflow.agent.state import ThreadState

logger = logging.getLogger(__name__)


class ToolErrorMiddleware(AgentMiddleware[ThreadState]):
    """Convert tool exceptions into tool messages instead of crashing the run."""

    state_schema = ThreadState

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        try:
            return handler(request)
        except Exception as exc:
            logger.exception("Tool call failed: %s", exc)
            return ToolMessage(
                content=f"Error: {exc}",
                tool_call_id=request.tool_call.get("id", ""),
                name=request.tool_call.get("name", "tool"),
            )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> ToolMessage | Command[Any]:
        try:
            return await handler(request)
        except Exception as exc:
            logger.exception("Async tool call failed: %s", exc)
            return ToolMessage(
                content=f"Error: {exc}",
                tool_call_id=request.tool_call.get("id", ""),
                name=request.tool_call.get("name", "tool"),
            )
