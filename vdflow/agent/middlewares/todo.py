"""TodoMiddleware — detect and recover from task-list context loss.

When SummarizationMiddleware truncates early messages, the write_todos tool_call
that created the task list may be evicted from the context window.  The Agent
then "forgets" it has an active todo list.

This middleware checks for that specific situation and injects a
<system_reminder> to restore the Agent's awareness.

Ported from DeerFlow's TodoMiddleware.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.runtime import Runtime

from vdflow.agent.middlewares._utils import _state_get
from vdflow.agent.state import ThreadState

logger = logging.getLogger(__name__)

_REMINDER_NAME = "todo_reminder"
_TODO_TOOL_NAMES = {"write_todos", "update_todos", "manage_todos"}


def _todos_in_messages(messages: list[BaseMessage]) -> bool:
    """Check if a write_todos tool_call is still visible in the messages."""
    for msg in messages:
        for tc in getattr(msg, "tool_calls", []) or []:
            if tc.get("name") in _TODO_TOOL_NAMES:
                return True
    return False


def _reminder_already_injected(messages: list[BaseMessage]) -> bool:
    """Check if a todo_reminder was already injected recently (last 5 messages)."""
    for msg in messages[-5:]:
        if getattr(msg, "name", None) == _REMINDER_NAME:
            return True
    return False


def _format_todos(todos: list[dict[str, Any]]) -> str:
    """Format todos into a readable list for the system reminder."""
    lines = ["<system_reminder>", "You have an active task list:"]
    for i, todo in enumerate(todos, 1):
        status = todo.get("status", "pending")
        title = todo.get("title", todo.get("content", f"Task {i}"))
        marker = "✅" if status == "done" else "⬜"
        lines.append(f"  {marker} {i}. {title}")
    lines.append("")
    lines.append("Continue working on incomplete tasks. Use write_todos to update progress.")
    lines.append("</system_reminder>")
    return "\n".join(lines)


class TodoMiddleware(AgentMiddleware[ThreadState]):
    """Detect task-list context loss and inject a reminder.

    Activated only when:
    1. state["todos"] is non-empty (a task list exists)
    2. No write_todos tool_call is visible in current messages
    3. No reminder was recently injected
    """

    state_schema = ThreadState

    def before_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        todos = _state_get(state, "todos", [])
        if not todos:
            return None

        messages: list[BaseMessage] = _state_get(state, "messages", [])

        # If the write_todos call is still in the context, no action needed
        if _todos_in_messages(messages):
            return None

        # If we already injected a reminder recently, don't spam
        if _reminder_already_injected(messages):
            return None

        # Inject a reminder
        reminder_text = _format_todos(todos)
        logger.info("TodoMiddleware: injecting task-list reminder (%d todos)", len(todos))
        return {
            "messages": [
                HumanMessage(
                    content=reminder_text,
                    name=_REMINDER_NAME,
                )
            ]
        }
