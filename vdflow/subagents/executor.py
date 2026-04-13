"""Subagent executor — run child agents with timeout, cancellation, and isolation.

Creates a real LangGraph agent per subagent execution, with a slim middleware
chain (security + error handling only).  Follows DeerFlow's SubagentExecutor
architecture: dual thread pool, cooperative cancellation, trace-id propagation.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any

from vdflow.subagents.config import SubagentConfig, SubagentResult, SubagentStatus

logger = logging.getLogger(__name__)

# Thread pools
_scheduler_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-sched")
_execution_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-exec")
# Dedicated pool for sync execute() calls made from an already-running event loop.
_isolated_loop_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="subagent-isolated")

# Global background task storage
_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()


def _tool_name(tool: Any) -> str:
    return getattr(tool, "name", getattr(tool, "__name__", ""))


class SubagentExecutor:
    """Execute subagents with timeout, cancellation, and resource isolation.

    Unlike the previous stub, this creates a real LangGraph agent via
    ``create_agent()`` with filtered tools and a slim middleware chain.
    """

    def __init__(
        self,
        config: SubagentConfig,
        *,
        app_config: Any = None,
        parent_model_name: str | None = None,
        parent_trace_id: str = "",
    ):
        self.config = config
        self._app_config = app_config
        self._parent_model_name = parent_model_name
        self.trace_id = (
            f"{parent_trace_id}/{config.name}/{uuid.uuid4().hex[:8]}"
            if parent_trace_id
            else f"{config.name}/{uuid.uuid4().hex[:8]}"
        )
        self._cancel_event = threading.Event()
        self._task_id: str | None = None  # set by execute_async

    def _update_ai_messages(self, messages: list[str]) -> None:
        """Update the background task result with collected AI messages."""
        if self._task_id is None:
            return
        with _background_tasks_lock:
            result = _background_tasks.get(self._task_id)
            if result is not None:
                result.ai_messages = list(messages)

    # ------------------------------------------------------------------
    # Agent creation
    # ------------------------------------------------------------------

    def _create_agent(self):
        """Create a real LangGraph agent for this subagent."""
        from langchain.agents import create_agent as create_langchain_agent

        from vdflow.agent.factory import create_chat_model, resolve_model_config
        from vdflow.agent.middlewares import build_subagent_middlewares
        from vdflow.agent.state import ThreadState
        from vdflow.tools import get_available_tools

        # Resolve model (inherit from parent or use own)
        model_name = self.config.model or self._parent_model_name
        model_config = resolve_model_config(self._app_config, model_name)
        model = create_chat_model(model_config)

        # Get tools — subagent_enabled=False prevents recursive task tool injection
        all_tools = get_available_tools(
            self._app_config, subagent_enabled=False,
        )
        # Apply config-level tool filtering
        disallowed = set(self.config.disallowed_tools or [])
        if self.config.tools is not None:
            allowed = set(self.config.tools)
            tools = [t for t in all_tools if _tool_name(t) in allowed and _tool_name(t) not in disallowed]
        else:
            tools = [t for t in all_tools if _tool_name(t) not in disallowed]

        # Slim middleware chain (security + error handling only)
        middlewares = build_subagent_middlewares(self._app_config)

        agent = create_langchain_agent(
            model=model,
            tools=tools,
            middleware=middlewares,
            system_prompt=self.config.system_prompt,
            state_schema=ThreadState,
        )
        logger.info(
            "[trace=%s] Created subagent '%s' with %d tools, %d middlewares",
            self.trace_id, self.config.name, len(tools), len(middlewares),
        )
        return agent

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(self, task: str) -> SubagentResult:
        """Execute a task — async entry point."""
        return await self._aexecute(task)

    async def _aexecute(self, task: str) -> SubagentResult:
        """Execute a task asynchronously with a real agent."""
        from langchain_core.messages import HumanMessage

        start = time.monotonic()

        try:
            if self._cancel_event.is_set():
                return SubagentResult(
                    status=SubagentStatus.CANCELLED,
                    error="Cancelled before start",
                    trace_id=self.trace_id,
                )

            # When no app_config, fall back to lightweight stub (for testing)
            if self._app_config is None:
                logger.info(
                    "[trace=%s] Subagent '%s' running in stub mode (no app_config)",
                    self.trace_id, self.config.name,
                )
                return SubagentResult(
                    status=SubagentStatus.COMPLETED,
                    output=f"[{self.config.name}] Task completed: {task[:500]}",
                    elapsed_seconds=time.monotonic() - start,
                    trace_id=self.trace_id,
                )

            agent = self._create_agent()
            state = {"messages": [HumanMessage(content=task)]}
            run_config = {"recursion_limit": self.config.max_turns}

            final_state = None
            collected_messages: list[str] = []
            async for chunk in agent.astream(
                state, config=run_config, stream_mode="values",
            ):
                # Cooperative cancellation at stream boundary
                if self._cancel_event.is_set():
                    elapsed = time.monotonic() - start
                    logger.info(
                        "[trace=%s] Subagent '%s' cancelled during stream",
                        self.trace_id, self.config.name,
                    )
                    return SubagentResult(
                        status=SubagentStatus.CANCELLED,
                        error="Cancelled by parent",
                        elapsed_seconds=elapsed,
                        trace_id=self.trace_id,
                    )
                final_state = chunk

                # Collect AI messages for real-time progress
                from langchain_core.messages import AIMessage as _AIMsg
                messages = chunk.get("messages", []) if isinstance(chunk, dict) else []
                for msg in messages:
                    if isinstance(msg, _AIMsg) and msg.content:
                        text = msg.content if isinstance(msg.content, str) else str(msg.content)
                        if text and text not in collected_messages:
                            collected_messages.append(text)
                            # Update background task result for polling
                            self._update_ai_messages(collected_messages)

            elapsed = time.monotonic() - start

            # Extract result from final state
            output = self._extract_result(final_state)
            logger.info(
                "[trace=%s] Subagent '%s' completed in %.1fs",
                self.trace_id, self.config.name, elapsed,
            )
            return SubagentResult(
                status=SubagentStatus.COMPLETED,
                output=output,
                elapsed_seconds=elapsed,
                trace_id=self.trace_id,
                ai_messages=collected_messages,
            )

        except asyncio.CancelledError:
            elapsed = time.monotonic() - start
            return SubagentResult(
                status=SubagentStatus.CANCELLED,
                error="Subagent was cancelled",
                elapsed_seconds=elapsed,
                trace_id=self.trace_id,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.exception(
                "[trace=%s] Subagent '%s' failed", self.trace_id, self.config.name,
            )
            return SubagentResult(
                status=SubagentStatus.FAILED,
                error=str(exc),
                elapsed_seconds=elapsed,
                trace_id=self.trace_id,
            )

    @staticmethod
    def _extract_result(final_state: dict[str, Any] | None) -> str:
        """Extract the last AIMessage content from agent final state."""
        from langchain_core.messages import AIMessage

        if final_state is None:
            return "No response generated"

        messages = final_state.get("messages", [])
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                content = msg.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, str):
                            parts.append(block)
                        elif isinstance(block, dict):
                            text = block.get("text")
                            if isinstance(text, str):
                                parts.append(text)
                    return "\n".join(parts) if parts else "No text content"
                return str(content)
        return "No response generated"

    def _execute_in_isolated_loop(self, task: str) -> SubagentResult:
        """Execute the subagent in a completely fresh event loop.

        Runs in a separate thread to ensure complete isolation from any parent
        event loop, preventing conflicts with asyncio primitives (e.g., httpx
        clients) that may be bound to the parent loop.

        Ported from DeerFlow's SubagentExecutor._execute_in_isolated_loop().
        """
        try:
            previous_loop = asyncio.get_event_loop()
        except RuntimeError:
            previous_loop = None

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._aexecute(task))
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                if pending:
                    for task_obj in pending:
                        task_obj.cancel()
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(loop.shutdown_default_executor())
            except Exception:
                logger.debug(
                    "[trace=%s] Failed while cleaning up isolated event loop for subagent '%s'",
                    self.trace_id, self.config.name,
                    exc_info=True,
                )
            finally:
                try:
                    loop.close()
                finally:
                    asyncio.set_event_loop(previous_loop)

    def execute_sync(self, task: str) -> SubagentResult:
        """Execute synchronously — handles event loop isolation.

        When called from within an already-running event loop (e.g., LangGraph
        async runtime), isolates execution in a separate thread with a fresh
        event loop to avoid 'Event loop is closed' and nested loop errors.
        """
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                logger.debug(
                    "[trace=%s] Subagent '%s' detected running event loop, using isolated thread",
                    self.trace_id, self.config.name,
                )
                future = _isolated_loop_pool.submit(self._execute_in_isolated_loop, task)
                return future.result()

            # Standard path: no running event loop, use asyncio.run
            return asyncio.run(self._aexecute(task))
        except Exception as exc:
            logger.exception(
                "[trace=%s] Subagent '%s' sync execution failed",
                self.trace_id, self.config.name,
            )
            return SubagentResult(
                status=SubagentStatus.FAILED,
                error=str(exc),
                trace_id=self.trace_id,
            )

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        """Start background execution. Returns task_id for polling."""
        if task_id is None:
            task_id = uuid.uuid4().hex[:8]

        self._task_id = task_id  # for _update_ai_messages

        result = SubagentResult(
            status=SubagentStatus.PENDING,
            trace_id=self.trace_id,
        )
        with _background_tasks_lock:
            _background_tasks[task_id] = result

        logger.info(
            "[trace=%s] Subagent '%s' starting async, task_id=%s, timeout=%ds",
            self.trace_id, self.config.name, task_id, self.config.timeout_seconds,
        )

        def run_task():
            with _background_tasks_lock:
                _background_tasks[task_id].status = SubagentStatus.RUNNING

            try:
                future: Future = _execution_pool.submit(self.execute_sync, task)
                try:
                    exec_result = future.result(timeout=self.config.timeout_seconds)
                    with _background_tasks_lock:
                        r = _background_tasks[task_id]
                        r.status = exec_result.status
                        r.output = exec_result.output
                        r.error = exec_result.error
                        r.elapsed_seconds = exec_result.elapsed_seconds
                except FuturesTimeoutError:
                    logger.error(
                        "[trace=%s] Subagent '%s' timed out after %ds",
                        self.trace_id, self.config.name, self.config.timeout_seconds,
                    )
                    self._cancel_event.set()
                    future.cancel()
                    with _background_tasks_lock:
                        r = _background_tasks[task_id]
                        if r.status == SubagentStatus.RUNNING:
                            r.status = SubagentStatus.TIMED_OUT
                            r.error = f"Timed out after {self.config.timeout_seconds}s"
            except Exception as exc:
                logger.exception(
                    "[trace=%s] Subagent '%s' async failed",
                    self.trace_id, self.config.name,
                )
                with _background_tasks_lock:
                    r = _background_tasks[task_id]
                    r.status = SubagentStatus.FAILED
                    r.error = str(exc)

        _scheduler_pool.submit(run_task)
        return task_id

    def cancel(self) -> None:
        """Request cooperative cancellation."""
        self._cancel_event.set()


# ---------------------------------------------------------------------------
# Background task management (module-level)
# ---------------------------------------------------------------------------


def get_background_task_result(task_id: str) -> SubagentResult | None:
    with _background_tasks_lock:
        return _background_tasks.get(task_id)


def cleanup_background_task(task_id: str) -> None:
    """Remove a terminal task to prevent memory leaks."""
    terminal = {
        SubagentStatus.COMPLETED, SubagentStatus.FAILED,
        SubagentStatus.CANCELLED, SubagentStatus.TIMED_OUT,
    }
    with _background_tasks_lock:
        result = _background_tasks.get(task_id)
        if result is not None and result.status in terminal:
            del _background_tasks[task_id]


def request_cancel_background_task(task_id: str) -> None:
    with _background_tasks_lock:
        result = _background_tasks.get(task_id)
        if result is not None:
            # The cancel_event lives on the executor, not the result.
            # For background tasks we mark the status directly.
            result.status = SubagentStatus.CANCELLED
            result.error = "Cancelled by user"
            logger.info("Requested cancellation for task %s", task_id)


def create_executor(
    config: SubagentConfig,
    *,
    app_config: Any = None,
    parent_model_name: str | None = None,
    parent_trace_id: str = "",
) -> SubagentExecutor:
    """Factory function."""
    return SubagentExecutor(
        config,
        app_config=app_config,
        parent_model_name=parent_model_name,
        parent_trace_id=parent_trace_id,
    )
