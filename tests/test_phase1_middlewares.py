"""Tests for Phase 1 defensive middlewares."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from vdflow.agent.middlewares.dangling_tool_call import DanglingToolCallMiddleware
from vdflow.agent.middlewares.llm_error_handling import LLMErrorHandlingMiddleware
from vdflow.agent.middlewares.loop_detection import LoopDetectionMiddleware


class DanglingToolCallTest(unittest.TestCase):
    def test_no_patch_needed_when_all_tool_calls_have_responses(self):
        middleware = DanglingToolCallMiddleware()
        messages = [
            HumanMessage(content="hello"),
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "search", "args": {}}]),
            ToolMessage(content="result", tool_call_id="tc1", name="search"),
        ]
        result = middleware._build_patched_messages(messages)
        self.assertIsNone(result)

    def test_patches_dangling_tool_call(self):
        middleware = DanglingToolCallMiddleware()
        messages = [
            HumanMessage(content="hello"),
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "search", "args": {}}]),
            # No ToolMessage for tc1 — this is the dangling call
        ]
        result = middleware._build_patched_messages(messages)
        self.assertIsNotNone(result)
        # Should have 3 messages: Human, AI, synthetic ToolMessage
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result[2], ToolMessage)
        self.assertEqual(result[2].tool_call_id, "tc1")
        self.assertEqual(result[2].status, "error")

    def test_patches_multiple_dangling_calls(self):
        middleware = DanglingToolCallMiddleware()
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "tc1", "name": "search", "args": {}},
                    {"id": "tc2", "name": "fetch", "args": {}},
                ],
            ),
        ]
        result = middleware._build_patched_messages(messages)
        self.assertIsNotNone(result)
        tool_msgs = [m for m in result if isinstance(m, ToolMessage)]
        self.assertEqual(len(tool_msgs), 2)

    def test_wrap_model_call_passes_patched_messages(self):
        middleware = DanglingToolCallMiddleware()
        ai_msg = AIMessage(content="", tool_calls=[{"id": "tc1", "name": "search", "args": {}}])
        request = MagicMock()
        request.messages = [HumanMessage(content="hi"), ai_msg]
        request.override = MagicMock(return_value=request)

        handler = MagicMock(return_value="response")
        middleware.wrap_model_call(request, handler)

        request.override.assert_called_once()
        patched = request.override.call_args[1]["messages"]
        self.assertEqual(len(patched), 3)


class LoopDetectionTest(unittest.TestCase):
    def test_no_action_below_threshold(self):
        middleware = LoopDetectionMiddleware(warn_threshold=3, hard_limit=5)
        messages = [
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "search", "args": {"query": "test"}}]),
            ToolMessage(content="ok", tool_call_id="tc1", name="search"),
            AIMessage(content="", tool_calls=[{"id": "tc2", "name": "search", "args": {"query": "test"}}]),
        ]
        state = {"messages": messages}
        result = middleware._detect_loops(state)
        self.assertIsNone(result)

    def test_warn_at_threshold(self):
        middleware = LoopDetectionMiddleware(warn_threshold=2, hard_limit=4)
        messages = []
        for i in range(2):
            messages.append(
                AIMessage(content="", tool_calls=[{"id": f"tc{i}", "name": "search", "args": {"query": "same"}}])
            )
            messages.append(ToolMessage(content="ok", tool_call_id=f"tc{i}", name="search"))
        # Add the message that triggers warning
        messages.append(
            AIMessage(content="", tool_calls=[{"id": "tc_warn", "name": "search", "args": {"query": "same"}}])
        )
        state = {"messages": messages}
        result = middleware._detect_loops(state)
        self.assertIsNotNone(result)
        self.assertIn("messages", result)
        # Should be a HumanMessage warning
        injected = result["messages"]
        self.assertTrue(any("注意" in getattr(m, "content", "") for m in injected))

    def test_hard_limit_strips_tool_calls(self):
        middleware = LoopDetectionMiddleware(warn_threshold=2, hard_limit=3)
        messages = []
        for i in range(3):
            messages.append(
                AIMessage(content="", tool_calls=[{"id": f"tc{i}", "name": "bash", "args": {"command": "ls"}}])
            )
            messages.append(ToolMessage(content="ok", tool_call_id=f"tc{i}", name="bash"))
        # The final AI message triggers hard limit
        messages.append(
            AIMessage(content="", tool_calls=[{"id": "tc_final", "name": "bash", "args": {"command": "ls"}}])
        )
        state = {"messages": messages}
        result = middleware._detect_loops(state)
        self.assertIsNotNone(result)
        # First message should be AI with stripped tool_calls
        updated_ai = result["messages"][0]
        self.assertIsInstance(updated_ai, AIMessage)
        self.assertEqual(updated_ai.tool_calls, [])

    def test_different_args_not_detected(self):
        middleware = LoopDetectionMiddleware(warn_threshold=2, hard_limit=4)
        messages = []
        for i in range(3):
            messages.append(
                AIMessage(content="", tool_calls=[{"id": f"tc{i}", "name": "search", "args": {"query": f"query-{i}"}}])
            )
            messages.append(ToolMessage(content="ok", tool_call_id=f"tc{i}", name="search"))
        messages.append(
            AIMessage(content="", tool_calls=[{"id": "tc_last", "name": "search", "args": {"query": "query-unique"}}])
        )
        state = {"messages": messages}
        result = middleware._detect_loops(state)
        self.assertIsNone(result)


class LLMErrorHandlingTest(unittest.TestCase):
    def test_returns_fallback_on_exception(self):
        middleware = LLMErrorHandlingMiddleware()
        # Use a non-retriable error to avoid retry delays in tests
        def broken_handler(request):
            raise RuntimeError("something unexpected happened")

        request = MagicMock()
        result = middleware.wrap_model_call(request, broken_handler)
        # New API returns AIMessage directly (not ModelResponse)
        self.assertIsInstance(result, AIMessage)
        self.assertIn("模型请求失败", result.content)

    def test_passes_through_on_success(self):
        middleware = LLMErrorHandlingMiddleware()
        expected = MagicMock()
        handler = MagicMock(return_value=expected)
        request = MagicMock()

        result = middleware.wrap_model_call(request, handler)
        self.assertEqual(result, expected)

    def test_auth_error_not_retried(self):
        middleware = LLMErrorHandlingMiddleware()

        call_count = 0
        def auth_handler(request):
            nonlocal call_count
            call_count += 1
            raise ValueError("Unauthorized: invalid api key")

        request = MagicMock()
        result = middleware.wrap_model_call(request, auth_handler)
        # Auth errors should not be retried
        self.assertEqual(call_count, 1)
        self.assertIsInstance(result, AIMessage)
        self.assertIn("鉴权", result.content)


if __name__ == "__main__":
    unittest.main()

