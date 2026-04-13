"""Task tool — dispatch work to subagents.

The lead agent calls this tool to delegate subtasks to specialized subagents.
Each call creates a SubagentExecutor, runs it in the background, and polls
for completion — matching DeerFlow's async-poll architecture.

Uses `get_stream_writer()` to emit fine-grained lifecycle events:
  task_started → task_running(×N) → task_completed / task_failed / task_timed_out
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import tool

from vdflow.subagents.config import SubagentStatus
from vdflow.subagents.executor import (
    SubagentExecutor,
    cleanup_background_task,
    get_background_task_result,
)
from vdflow.subagents.registry import get_available_subagent_names, get_subagent_config

logger = logging.getLogger(__name__)

# These are injected at agent startup via set_task_context()
_task_app_config = None
_task_parent_model_name: str | None = None

_TERMINAL_STATES = {
    SubagentStatus.COMPLETED,
    SubagentStatus.FAILED,
    SubagentStatus.CANCELLED,
    SubagentStatus.TIMED_OUT,
}


def set_task_context(app_config: Any, parent_model_name: str | None = None) -> None:
    """Set the app config and model name for task tool invocations.

    Called once at agent creation time so the task tool knows how to
    create subagent executors.
    """
    global _task_app_config, _task_parent_model_name
    _task_app_config = app_config
    _task_parent_model_name = parent_model_name


def _get_writer():
    """Get stream writer, returns a no-op if unavailable."""
    try:
        from langgraph.config import get_stream_writer
        return get_stream_writer()
    except Exception:
        return lambda _data: None


@tool("task")
async def task(description: str, prompt: str, subagent_type: str = "general") -> str:
    """Delegate a task to a specialized subagent that runs in its own context.

    Subagents help you:
    - Preserve context by keeping exploration and implementation separate
    - Handle complex multi-step tasks autonomously
    - Execute commands or operations in isolated contexts

    Available subagent types: general, bash, writer.

    When to use this tool:
    - Complex tasks requiring multiple steps or tools
    - Tasks that produce verbose output
    - When you want to isolate context from the main conversation

    When NOT to use this tool:
    - Simple, single-step operations (use tools directly)
    - Tasks requiring user interaction or clarification

    Args:
        description: Short (3-5 word) description of the task for logging.
        prompt: Detailed task description for the subagent. Be specific.
        subagent_type: Type of subagent to use (general, bash, writer).
    """
    config = get_subagent_config(subagent_type)
    if config is None:
        available = ", ".join(get_available_subagent_names())
        return f"Error: Unknown subagent type '{subagent_type}'. Available: {available}"

    if _task_app_config is None:
        return "Error: Task context not initialized. Cannot create subagent."

    # Get stream writer for lifecycle events
    writer = _get_writer()

    # Create executor with app config for real agent creation
    executor = SubagentExecutor(
        config,
        app_config=_task_app_config,
        parent_model_name=_task_parent_model_name,
    )

    logger.info(
        "[trace=%s] Task tool: dispatching '%s' to subagent '%s'",
        executor.trace_id, description, subagent_type,
    )

    # Start background execution
    task_id = executor.execute_async(prompt)

    # Emit task_started event
    writer({
        "type": "task_started",
        "task_id": task_id,
        "description": description,
        "subagent_type": subagent_type,
    })

    # Poll for completion (backend-driven, no LLM polling needed)
    poll_count = 0
    max_poll_count = (config.timeout_seconds + 60) // 3  # 3s poll interval
    last_status = None
    last_message_count = 0

    try:
        while True:
            result = get_background_task_result(task_id)

            if result is None:
                logger.error("[trace=%s] Task %s disappeared", executor.trace_id, task_id)
                writer({"type": "task_failed", "task_id": task_id, "error": "Task disappeared"})
                return f"Error: Task {task_id} disappeared from background tasks"

            # Log status changes
            if result.status != last_status:
                logger.info(
                    "[trace=%s] Task %s status: %s",
                    executor.trace_id, task_id, result.status.value,
                )
                last_status = result.status

            # Emit task_running events for new AI messages
            current_message_count = len(result.ai_messages)
            if current_message_count > last_message_count:
                for i in range(last_message_count, current_message_count):
                    writer({
                        "type": "task_running",
                        "task_id": task_id,
                        "message": result.ai_messages[i],
                        "message_index": i + 1,
                        "total_messages": current_message_count,
                    })
                last_message_count = current_message_count

            # Check terminal states
            if result.status in _TERMINAL_STATES:
                cleanup_background_task(task_id)

                if result.status == SubagentStatus.COMPLETED:
                    writer({
                        "type": "task_completed",
                        "task_id": task_id,
                        "result": (result.output or "")[:500],
                    })
                    logger.info(
                        "[trace=%s] Task %s completed (%.1fs)",
                        executor.trace_id, task_id, result.elapsed_seconds,
                    )
                    return f"Task completed. Result:\n{result.output}"

                elif result.status == SubagentStatus.TIMED_OUT:
                    writer({"type": "task_timed_out", "task_id": task_id, "error": result.error})
                    return f"Task timed out after {config.timeout_seconds}s. Error: {result.error}"

                elif result.status == SubagentStatus.CANCELLED:
                    writer({"type": "task_cancelled", "task_id": task_id})
                    return "Task was cancelled."

                else:
                    writer({"type": "task_failed", "task_id": task_id, "error": result.error})
                    return f"Task failed. Error: {result.error}"

            await asyncio.sleep(3)
            poll_count += 1

            if poll_count > max_poll_count:
                logger.error(
                    "[trace=%s] Task %s polling timed out after %d polls",
                    executor.trace_id, task_id, poll_count,
                )
                writer({"type": "task_timed_out", "task_id": task_id})
                return f"Task polling timed out. Status: {result.status.value}"

    except asyncio.CancelledError:
        # Parent cancelled — signal the subagent to stop
        executor.cancel()
        writer({"type": "task_cancelled", "task_id": task_id})
        raise
