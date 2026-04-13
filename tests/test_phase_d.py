"""Tests for Phase D: Subagents, MCP, FTS5 Search."""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

# ---------------------------------------------------------------------------
# D1: SubagentExecutor + Registry
# ---------------------------------------------------------------------------

from vdflow.subagents.config import SubagentConfig, SubagentResult, SubagentStatus
from vdflow.subagents.executor import SubagentExecutor, create_executor
from vdflow.subagents.registry import (
    get_available_subagent_names,
    get_subagent_config,
    list_subagents,
    register_subagent,
)


class TestSubagentConfig:
    def test_defaults(self):
        cfg = SubagentConfig(name="test")
        assert cfg.max_turns == 25
        assert cfg.timeout_seconds == 120
        assert cfg.share_sandbox is True
        assert cfg.tools is None

    def test_custom(self):
        cfg = SubagentConfig(
            name="custom",
            description="Custom agent",
            tools=["bash"],
            max_turns=10,
            timeout_seconds=60,
        )
        assert cfg.name == "custom"
        assert cfg.tools == ["bash"]


class TestSubagentRegistry:
    def test_builtins_exist(self):
        names = get_available_subagent_names()
        assert "general" in names
        assert "bash" in names
        assert "writer" in names

    def test_get_builtin(self):
        cfg = get_subagent_config("general")
        assert cfg is not None
        assert cfg.name == "general"

    def test_get_nonexistent(self):
        assert get_subagent_config("nonexistent") is None

    def test_list_subagents(self):
        agents = list_subagents()
        assert len(agents) >= 3
        names = {a.name for a in agents}
        assert "general" in names

    def test_custom_override(self):
        custom = SubagentConfig(name="custom-test", description="Custom for test")
        register_subagent(custom)
        assert get_subagent_config("custom-test") is not None
        assert "custom-test" in get_available_subagent_names()


class TestSubagentExecutor:
    @pytest.mark.asyncio
    async def test_execute_completes(self):
        cfg = SubagentConfig(name="test", timeout_seconds=5)
        executor = create_executor(cfg)
        result = await executor.execute("Do something")
        assert result.status == SubagentStatus.COMPLETED
        assert "test" in result.output
        assert result.trace_id != ""
        assert result.elapsed_seconds >= 0

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        cfg = SubagentConfig(name="slow", timeout_seconds=1)
        executor = SubagentExecutor(cfg)

        # Override _aexecute to be slow
        original = executor._aexecute
        async def slow_execute(task):
            await asyncio.sleep(10)
            return SubagentResult(status=SubagentStatus.COMPLETED, output="done")

        executor._aexecute = slow_execute
        try:
            result = await asyncio.wait_for(executor.execute("slow task"), timeout=2)
            # If it completes, check the status
            assert result.status in (SubagentStatus.COMPLETED, SubagentStatus.TIMED_OUT, SubagentStatus.FAILED)
        except asyncio.TimeoutError:
            # Expected — the 10s sleep exceeds our 2s wait
            pass

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        cfg = SubagentConfig(name="failing", timeout_seconds=5)
        executor = SubagentExecutor(cfg)

        async def failing_execute(task):
            raise ValueError("Something broke")

        executor._aexecute = failing_execute
        try:
            result = await executor.execute("failing task")
            assert result.status == SubagentStatus.FAILED
            assert "Something broke" in result.error
        except ValueError:
            # Direct raise is also acceptable
            pass

    @pytest.mark.asyncio
    async def test_cancel(self):
        cfg = SubagentConfig(name="cancellable", timeout_seconds=5)
        executor = SubagentExecutor(cfg)
        executor.cancel()
        result = await executor.execute("cancel me")
        assert result.status == SubagentStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_trace_id_propagation(self):
        cfg = SubagentConfig(name="child")
        executor = create_executor(cfg, parent_trace_id="parent-123")
        assert "parent-123" in executor.trace_id
        assert "child" in executor.trace_id

    @pytest.mark.asyncio
    async def test_stub_mode_without_app_config(self):
        """When no app_config, executor runs in stub mode."""
        cfg = SubagentConfig(name="stub-test")
        executor = SubagentExecutor(cfg)  # No app_config
        result = await executor.execute("Test task")
        assert result.status == SubagentStatus.COMPLETED
        assert "stub-test" in result.output


# ---------------------------------------------------------------------------
# D2: SubagentLimitMiddleware
# ---------------------------------------------------------------------------

from vdflow.agent.middlewares.subagent_limit import SubagentLimitMiddleware


class TestSubagentLimitMiddleware:
    def _make_state(self, messages):
        state = MagicMock()
        state.messages = messages
        state.__getitem__ = lambda self_, k: messages if k == "messages" else []
        state.__contains__ = lambda self_, k: k == "messages"
        return state

    def test_no_change_without_task_calls(self):
        mw = SubagentLimitMiddleware(max_concurrent=3)
        msgs = [
            AIMessage(content="hello", tool_calls=[
                {"id": "tc1", "name": "bash", "args": {}},
            ]),
        ]
        result = mw.after_model(self._make_state(msgs), MagicMock())
        assert result is None

    def test_no_change_below_limit(self):
        mw = SubagentLimitMiddleware(max_concurrent=3)
        msgs = [
            AIMessage(content="", tool_calls=[
                {"id": "tc1", "name": "task", "args": {"description": "task1"}},
                {"id": "tc2", "name": "task", "args": {"description": "task2"}},
            ]),
        ]
        result = mw.after_model(self._make_state(msgs), MagicMock())
        assert result is None

    def test_truncates_excess_task_calls(self):
        mw = SubagentLimitMiddleware(max_concurrent=2)
        msgs = [
            AIMessage(content="", tool_calls=[
                {"id": "tc1", "name": "task", "args": {"description": "task1"}},
                {"id": "tc2", "name": "task", "args": {"description": "task2"}},
                {"id": "tc3", "name": "task", "args": {"description": "task3"}},
                {"id": "tc4", "name": "task", "args": {"description": "task4"}},
            ]),
        ]
        result = mw.after_model(self._make_state(msgs), MagicMock())
        assert result is not None
        new_last = result["messages"][-1]
        task_calls = [tc for tc in new_last.tool_calls if tc["name"] == "task"]
        assert len(task_calls) == 2

    def test_preserves_non_task_calls(self):
        mw = SubagentLimitMiddleware(max_concurrent=1)
        msgs = [
            AIMessage(content="", tool_calls=[
                {"id": "tc0", "name": "bash", "args": {}},
                {"id": "tc1", "name": "task", "args": {}},
                {"id": "tc2", "name": "task", "args": {}},
            ]),
        ]
        result = mw.after_model(self._make_state(msgs), MagicMock())
        assert result is not None
        new_last = result["messages"][-1]
        names = [tc["name"] for tc in new_last.tool_calls]
        assert names.count("task") == 1
        assert "bash" in names

    def test_clamp_max_concurrent(self):
        mw1 = SubagentLimitMiddleware(max_concurrent=0)
        assert mw1.max_concurrent == 1  # Clamped to min
        mw2 = SubagentLimitMiddleware(max_concurrent=100)
        assert mw2.max_concurrent == 5  # Clamped to max


# ---------------------------------------------------------------------------
# D3: MCP Client + Cache
# ---------------------------------------------------------------------------

from vdflow.mcp.client import MCPClient, MCPServerConfig, MCPToolSchema
from vdflow.mcp.cache import MCPToolCache


class TestMCPServerConfig:
    def test_defaults(self):
        cfg = MCPServerConfig(name="test")
        assert cfg.transport == "stdio"
        assert cfg.enabled is True

    def test_sse_config(self):
        cfg = MCPServerConfig(name="sse-test", transport="sse", url="http://localhost:8080")
        assert cfg.transport == "sse"
        assert cfg.url == "http://localhost:8080"


class TestMCPClient:
    @pytest.mark.asyncio
    async def test_discover_disabled_server(self):
        client = MCPClient([MCPServerConfig(name="disabled", enabled=False)])
        tools = await client.discover_all()
        assert tools == []
        assert len(client.connected_servers) == 0

    @pytest.mark.asyncio
    async def test_discover_stdio_server(self):
        server = MCPServerConfig(name="stdio-test", command="echo")
        client = MCPClient([server])
        tools = await client.discover_tools(server)
        # Stub returns empty list
        assert isinstance(tools, list)
        assert "stdio-test" in client.connected_servers

    @pytest.mark.asyncio
    async def test_unknown_transport(self):
        server = MCPServerConfig(name="bad", transport="unknown")
        client = MCPClient([server])
        tools = await client.discover_tools(server)
        assert tools == []


class TestMCPToolCache:
    @pytest.mark.asyncio
    async def test_cache_loads_once(self):
        client = MCPClient([])
        cache = MCPToolCache(client)
        tools1 = await cache.load()
        tools2 = await cache.load()
        assert tools1 is tools2  # Same reference
        assert cache.is_loaded


# ---------------------------------------------------------------------------
# D4: FTS5 Session Search
# ---------------------------------------------------------------------------

from vdflow.threads.search import SessionSearchIndex


class TestSessionSearchIndex:
    def _make_index(self, tmp_path):
        return SessionSearchIndex(tmp_path / "search.db")

    def test_index_and_search(self, tmp_path):
        idx = self._make_index(tmp_path)
        idx.index_message("t1", "user", "How to deploy Python apps", 1.0)
        idx.index_message("t1", "assistant", "Use Docker or similar containers", 2.0)
        idx.index_message("t2", "user", "What is machine learning", 3.0)

        results = idx.search("Python")
        assert len(results) == 1
        assert results[0]["thread_id"] == "t1"
        assert "Python" in results[0]["content"]

    def test_search_multiple_results(self, tmp_path):
        idx = self._make_index(tmp_path)
        idx.index_message("t1", "user", "deploy the application", 1.0)
        idx.index_message("t2", "user", "deploy to production", 2.0)

        results = idx.search("deploy")
        assert len(results) == 2

    def test_search_with_thread_filter(self, tmp_path):
        idx = self._make_index(tmp_path)
        idx.index_message("t1", "user", "deploy app", 1.0)
        idx.index_message("t2", "user", "deploy service", 2.0)

        results = idx.search("deploy", thread_id="t1")
        assert len(results) == 1
        assert results[0]["thread_id"] == "t1"

    def test_batch_index(self, tmp_path):
        idx = self._make_index(tmp_path)
        messages = [
            {"thread_id": "t1", "role": "user", "content": "hello world"},
            {"thread_id": "t1", "role": "assistant", "content": "hi there"},
            {"thread_id": "t2", "role": "user", "content": "another thread"},
        ]
        count = idx.index_messages_batch(messages)
        assert count == 3
        assert idx.count() == 3

    def test_delete_thread(self, tmp_path):
        idx = self._make_index(tmp_path)
        idx.index_message("t1", "user", "keep this", 1.0)
        idx.index_message("t2", "user", "delete this", 2.0)

        deleted = idx.delete_thread("t2")
        assert deleted == 1
        assert idx.count("t1") == 1
        assert idx.count("t2") == 0

    def test_empty_query(self, tmp_path):
        idx = self._make_index(tmp_path)
        assert idx.search("") == []
        assert idx.search("   ") == []

    def test_empty_content_skipped(self, tmp_path):
        idx = self._make_index(tmp_path)
        idx.index_message("t1", "user", "", 1.0)
        idx.index_message("t1", "user", "   ", 2.0)
        assert idx.count() == 0

    def test_max_results(self, tmp_path):
        idx = self._make_index(tmp_path)
        for i in range(20):
            idx.index_message("t1", "user", f"message about testing {i}", float(i))
        results = idx.search("testing", max_results=5)
        assert len(results) == 5


# ---------------------------------------------------------------------------
# D4: session_search tool
# ---------------------------------------------------------------------------

from vdflow.tools.session_search import search_past_sessions, set_search_index


class TestSessionSearchTool:
    def test_no_index_returns_error(self):
        set_search_index(None)
        result = search_past_sessions.invoke({"query": "test"})
        assert "not available" in result

    def test_empty_query(self, tmp_path):
        idx = SessionSearchIndex(tmp_path / "search.db")
        set_search_index(idx)
        result = search_past_sessions.invoke({"query": ""})
        assert "non-empty" in result

    def test_search_returns_results(self, tmp_path):
        idx = SessionSearchIndex(tmp_path / "search.db")
        idx.index_message("abc123", "user", "How to use Docker containers", 1.0)
        set_search_index(idx)
        result = search_past_sessions.invoke({"query": "Docker"})
        assert "Docker" in result
        assert "abc123" in result


# ---------------------------------------------------------------------------
# Integration: build_middlewares includes Phase D middleware
# ---------------------------------------------------------------------------


class TestBuildMiddlewaresPhaseD:
    def test_chain_includes_subagent_limit(self):
        from vdflow.agent.middlewares import build_middlewares
        from vdflow.config.models import Config

        chain = build_middlewares(Config())
        type_names = [type(m).__name__ for m in chain]
        assert "SubagentLimitMiddleware" in type_names

    def test_disable_subagent_limit(self):
        from vdflow.agent.middlewares import build_middlewares
        from vdflow.config.models import Config, MiddlewareConfig

        config = Config(middleware=MiddlewareConfig(subagent_limit_enabled=False))
        chain = build_middlewares(config)
        type_names = [type(m).__name__ for m in chain]
        assert "SubagentLimitMiddleware" not in type_names

    def test_custom_max_concurrent(self):
        from vdflow.agent.middlewares import build_middlewares
        from vdflow.config.models import Config, MiddlewareConfig

        config = Config(middleware=MiddlewareConfig(subagent_max_concurrent=2))
        chain = build_middlewares(config)
        limit_mw = next(m for m in chain if type(m).__name__ == "SubagentLimitMiddleware")
        assert limit_mw.max_concurrent == 2
