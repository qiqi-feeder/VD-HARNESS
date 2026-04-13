"""Middleware to track and log token usage from model responses.

Extracts ``usage_metadata`` from each ``AIMessage`` produced by the model
and logs the prompt/completion/total token counts. Writes a summary dict
to the ``token_usage`` state key so downstream consumers (SSE stream) can
emit a ``token_usage`` event to the frontend.
"""

from __future__ import annotations

import logging
from typing import Any

from typing_extensions import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class TokenUsageMiddleware(AgentMiddleware[AgentState]):
    """Log and accumulate token usage after each model call.

    After each model invocation, writes the latest token stats to
    ``state["token_usage"]`` so the SSE stream can pick them up.
    """

    def __init__(self) -> None:
        super().__init__()
        self._cumulative: dict[str, int] = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_reasoning_tokens": 0,
            "call_count": 0,
        }

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        return self._track_usage(state)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        return self._track_usage(state)

    def _track_usage(self, state: AgentState) -> dict[str, Any] | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if not isinstance(last_msg, AIMessage):
            return None

        usage = getattr(last_msg, "usage_metadata", None)
        if not usage:
            return None

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        # Detailed breakdown
        input_detail = usage.get("input_token_details", {}) or {}
        output_detail = usage.get("output_token_details", {}) or {}
        cache_read = input_detail.get("cache_read", 0) or 0
        reasoning_tokens = output_detail.get("reasoning", 0) or 0

        logger.info(
            "Token usage — input: %d, output: %d (reasoning: %d), total: %d, cache_read: %d",
            input_tokens,
            output_tokens,
            reasoning_tokens,
            total_tokens,
            cache_read,
        )

        # Update cumulative counters
        self._cumulative["total_input_tokens"] += input_tokens
        self._cumulative["total_output_tokens"] += output_tokens
        self._cumulative["total_tokens"] += total_tokens
        self._cumulative["total_reasoning_tokens"] += reasoning_tokens
        self._cumulative["call_count"] += 1

        # Build per-call snapshot for downstream SSE
        token_usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "reasoning_tokens": reasoning_tokens,
            "cache_read_tokens": cache_read,
            **self._cumulative,
        }

        return {"token_usage": token_usage}
