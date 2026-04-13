"""Middleware to detect and break repetitive tool-call loops.

Ported from DeerFlow's LoopDetectionMiddleware. Uses a sliding window of
tool-call hashes to detect when the LLM keeps making the same tool calls,
injecting warnings and eventually forcing termination.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from typing import Any

from typing_extensions import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# Fields that are most likely to indicate the "identity" of a tool call
_SALIENT_FIELDS = ("path", "url", "query", "command", "pattern", "glob", "cmd", "file_path")


def _stable_hash(tool_name: str, args: dict[str, Any]) -> str:
    """Compute a stable hash for a tool call.

    For most tools we only hash *salient* fields (path, url, query, etc.).
    If none of those exist, fall back to hashing all args.
    """
    salient = {k: v for k, v in args.items() if k in _SALIENT_FIELDS}
    hashable = salient if salient else args
    raw = json.dumps({"name": tool_name, "args": hashable}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class LoopDetectionMiddleware(AgentMiddleware[AgentState]):
    """Detect and mitigate repetitive tool-call loops.

    Tracks a sliding window of tool-call hashes. When the same hash appears
    ``warn_threshold`` times, a warning message is injected. At
    ``hard_limit`` repetitions, all tool_calls are stripped from the last AI
    message so the model is forced to produce a text response.

    Args:
        warn_threshold: Number of repetitions before injecting a warning.
        hard_limit: Number of repetitions before forcefully stopping tool calls.
        window_size: Number of recent tool calls to keep in the window.
    """

    def __init__(
        self,
        warn_threshold: int = 3,
        hard_limit: int = 5,
        window_size: int = 20,
    ):
        super().__init__()
        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self.window_size = window_size

    def _analyze_tool_calls(self, messages: list[Any]) -> dict[str, int]:
        """Build a frequency map of tool-call hashes from the recent message window."""
        freq: dict[str, int] = defaultdict(int)
        window: list[str] = []

        for msg in messages:
            if getattr(msg, "type", None) != "ai":
                continue
            for tc in getattr(msg, "tool_calls", None) or []:
                h = _stable_hash(tc.get("name", ""), tc.get("args", {}))
                window.append(h)

        # Trim to window_size
        window = window[-self.window_size:]
        for h in window:
            freq[h] += 1
        return freq

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        return self._detect_loops(state)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        return self._detect_loops(state)

    def _detect_loops(self, state: AgentState) -> dict[str, Any] | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if getattr(last_msg, "type", None) != "ai":
            return None

        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None

        freq = self._analyze_tool_calls(messages)

        # Check if any current tool call exceeds thresholds
        for tc in tool_calls:
            h = _stable_hash(tc.get("name", ""), tc.get("args", {}))
            count = freq.get(h, 0)

            if count >= self.hard_limit:
                # Force stop: strip all tool_calls from the last message
                logger.error(
                    "Loop hard limit reached (%d repetitions) for tool '%s'. "
                    "Stripping tool_calls to force text response.",
                    count,
                    tc.get("name", "unknown"),
                )
                updated_msg = last_msg.model_copy(update={"tool_calls": []})
                return {
                    "messages": [
                        updated_msg,
                        HumanMessage(
                            content=(
                                "[System] 检测到工具调用循环（同一调用重复 "
                                f"{count} 次）。请停止重复调用，直接基于已有信息回答用户。"
                            )
                        ),
                    ]
                }

            if count >= self.warn_threshold:
                logger.warning(
                    "Loop warning: tool '%s' called %d times with same args.",
                    tc.get("name", "unknown"),
                    count,
                )
                return {
                    "messages": [
                        HumanMessage(
                            content=(
                                "[System] 注意：工具 '"
                                + tc.get("name", "unknown")
                                + f"' 已被以相同参数调用 {count} 次。"
                                "如果你得到的结果不符合预期，请换一种方式或直接回答。"
                            )
                        )
                    ]
                }

        return None
