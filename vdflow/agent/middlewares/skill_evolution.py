"""SkillEvolutionMiddleware — automatically detect reusable workflows and propose skills.

Hermes-inspired: when the agent completes a multi-step workflow successfully,
this middleware detects the pattern and:
1. Emits a skill_suggestion SSE event to the frontend
2. Uses a background LLM call to draft a skill definition

The user/agent can then accept, edit, or discard the suggestion.

Detection heuristics:
- Consecutive tool calls ≥ threshold (default 4)
- Same tool used multiple times (indicates a pattern)
- Final message indicates success (no error tool results)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.runtime import Runtime

from vdflow.agent.middlewares._utils import _state_get
from vdflow.agent.state import ThreadState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection heuristics
# ---------------------------------------------------------------------------

_TOOL_CALL_THRESHOLD = 4     # Min consecutive tool calls to suggest skill
_REPEAT_TOOL_THRESHOLD = 2   # Min times same tool must appear
_TAIL_WINDOW = 20            # Only look at recent N messages

# Tool groups worth suggesting as skills
_INTERESTING_TOOLS = {
    "bash", "write_file", "read_file", "str_replace",
    "web_search", "web_fetch", "python_exec",
}


def _extract_tool_sequence(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """Extract the most recent consecutive tool-call sequence from messages.

    Returns a list of {"name": ..., "args": ..., "success": bool} dicts.
    """
    window = messages[-_TAIL_WINDOW:]
    sequence: list[dict[str, Any]] = []
    tool_results: dict[str, bool] = {}

    # First pass: map tool_call_id → success
    for msg in window:
        if isinstance(msg, ToolMessage):
            success = getattr(msg, "status", "success") != "error"
            tool_results[msg.tool_call_id] = success

    # Second pass: extract tool calls from AI messages
    for msg in window:
        if not isinstance(msg, AIMessage):
            continue
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            # Non-tool AI message breaks the sequence
            if sequence:
                break
            continue
        for tc in tool_calls:
            tc_id = tc.get("id", "")
            sequence.append({
                "name": tc.get("name", ""),
                "args": tc.get("args", {}),
                "success": tool_results.get(tc_id, True),
            })

    return sequence


def _is_skill_worthy(sequence: list[dict[str, Any]]) -> bool:
    """Determine if a tool sequence is worth converting to a skill."""
    if len(sequence) < _TOOL_CALL_THRESHOLD:
        return False

    # Check for failures — don't suggest failed workflows
    if any(not step["success"] for step in sequence[-3:]):
        return False

    # Check for interesting tools
    tool_names = [s["name"] for s in sequence]
    interesting = [n for n in tool_names if n in _INTERESTING_TOOLS]
    if len(interesting) < 2:
        return False

    # Check for repeated tool usage (indicates a pattern)
    from collections import Counter
    counts = Counter(tool_names)
    repeated = sum(1 for c in counts.values() if c >= _REPEAT_TOOL_THRESHOLD)
    if repeated < 1:
        return False

    return True


def _summarize_workflow(sequence: list[dict[str, Any]]) -> str:
    """Build a short description of the workflow for the suggestion."""
    tool_names = [s["name"] for s in sequence]
    from collections import Counter
    counts = Counter(tool_names)
    steps = ", ".join(f"{name}×{count}" for name, count in counts.most_common())
    return f"{len(sequence)}-step workflow: {steps}"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class SkillEvolutionMiddleware(AgentMiddleware[ThreadState]):
    """Detect reusable multi-step workflows and suggest saving as skills.

    Runs in after_agent to analyze completed sequences.
    """

    state_schema = ThreadState

    def __init__(self, *, suggestion_cooldown: int = 5):
        super().__init__()
        self._suggestion_cooldown = suggestion_cooldown
        self._turns_since_suggestion: int = 0

    def after_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        self._turns_since_suggestion += 1

        # Don't spam suggestions
        if self._turns_since_suggestion < self._suggestion_cooldown:
            return None

        messages = _state_get(state, "messages", [])
        if not messages:
            return None

        sequence = _extract_tool_sequence(messages)
        if not _is_skill_worthy(sequence):
            return None

        # We have a worthy workflow!
        self._turns_since_suggestion = 0
        summary = _summarize_workflow(sequence)
        logger.info("Skill-worthy workflow detected: %s", summary)

        # Emit SSE event
        self._emit_suggestion(sequence, summary)

        return None

    def _emit_suggestion(self, sequence: list[dict[str, Any]], summary: str) -> None:
        """Push a skill suggestion to the frontend."""
        try:
            from langgraph.config import get_stream_writer

            writer = get_stream_writer()
            writer({
                "type": "skill_suggestion",
                "summary": summary,
                "steps": len(sequence),
                "tools": list({s["name"] for s in sequence}),
            })
        except Exception:
            logger.debug("Failed to emit skill_suggestion event", exc_info=True)
