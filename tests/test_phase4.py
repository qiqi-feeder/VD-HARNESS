"""Tests for Phase 4: Memory enhancement + Token usage SSE."""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from vdflow.agent.middlewares.memory import (
    MemoryMiddleware,
    detect_correction,
    detect_reinforcement,
    filter_messages_for_memory,
)
from vdflow.agent.middlewares.token_usage import TokenUsageMiddleware


class CorrectionDetectionTest(unittest.TestCase):
    def test_detects_chinese_correction(self):
        msgs = [MagicMock(type="human", content="不对，你理解错了")]
        self.assertTrue(detect_correction(msgs))

    def test_detects_english_correction(self):
        msgs = [MagicMock(type="human", content="That's wrong, try again")]
        self.assertTrue(detect_correction(msgs))

    def test_no_correction_in_normal_text(self):
        msgs = [MagicMock(type="human", content="帮我分析一下这段代码")]
        self.assertFalse(detect_correction(msgs))

    def test_detects_retry_pattern(self):
        msgs = [MagicMock(type="human", content="重试一下")]
        self.assertTrue(detect_correction(msgs))

    def test_detects_switch_approach(self):
        msgs = [MagicMock(type="human", content="换一种方法")]
        self.assertTrue(detect_correction(msgs))

    def test_only_checks_recent_messages(self):
        # Old correction in msg[0], followed by 7 normal msgs → should not detect
        old = [MagicMock(type="human", content="不对")]
        normal = [MagicMock(type="human", content=f"问题 {i}") for i in range(7)]
        self.assertFalse(detect_correction(old + normal))


class ReinforcementDetectionTest(unittest.TestCase):
    def test_detects_chinese_reinforcement(self):
        msgs = [MagicMock(type="human", content="完全正确！")]
        self.assertTrue(detect_reinforcement(msgs))

    def test_detects_english_reinforcement(self):
        msgs = [MagicMock(type="human", content="Perfect!")]
        self.assertTrue(detect_reinforcement(msgs))

    def test_detects_keep_doing(self):
        msgs = [MagicMock(type="human", content="keep doing that")]
        self.assertTrue(detect_reinforcement(msgs))

    def test_no_reinforcement_in_normal_text(self):
        msgs = [MagicMock(type="human", content="帮我看看这个文件")]
        self.assertFalse(detect_reinforcement(msgs))


class MessageFilteringTest(unittest.TestCase):
    def test_keeps_human_and_final_ai(self):
        msgs = [
            HumanMessage(content="hello"),
            AIMessage(content="hi there"),
        ]
        filtered = filter_messages_for_memory(msgs)
        self.assertEqual(len(filtered), 2)

    def test_removes_tool_messages(self):
        msgs = [
            HumanMessage(content="search for X"),
            AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"q": "X"}, "id": "1"}]),
            ToolMessage(content="result", tool_call_id="1"),
            AIMessage(content="Here's what I found"),
        ]
        filtered = filter_messages_for_memory(msgs)
        self.assertEqual(len(filtered), 2)  # human + final AI
        self.assertEqual(filtered[0].type, "human")
        self.assertEqual(filtered[1].type, "ai")
        self.assertEqual(filtered[1].content, "Here's what I found")

    def test_strips_upload_blocks(self):
        msgs = [
            MagicMock(type="human", content="<uploaded_files>file1.txt</uploaded_files>\n分析这个文件"),
            AIMessage(content="done"),
        ]
        filtered = filter_messages_for_memory(msgs)
        self.assertEqual(len(filtered), 2)
        # Upload block should be stripped
        self.assertNotIn("<uploaded_files>", str(filtered[0].content))

    def test_skips_upload_only_messages(self):
        msgs = [
            MagicMock(type="human", content="<uploaded_files>file1.txt</uploaded_files>"),
            AIMessage(content="I see the file"),
        ]
        filtered = filter_messages_for_memory(msgs)
        # Both should be skipped (upload-only human + its paired AI)
        self.assertEqual(len(filtered), 0)


class MemoryDebounceTest(unittest.TestCase):
    def test_debounce_skips_rapid_updates(self):
        storage = MagicMock()
        storage.load.return_value = {"preferences": {}, "facts": [], "conversation_history": []}
        updater = MagicMock()

        mw = MemoryMiddleware(storage, updater, debounce_seconds=60.0)

        state = {
            "messages": [HumanMessage(content="hi"), AIMessage(content="hello")],
            "thread_id": "t1",
            "title": "",
            "memory_context": "",
        }
        runtime = MagicMock()

        # First call goes through
        mw._record_update_time("t1")
        # Immediate second call should be debounced
        self.assertTrue(mw._should_debounce("t1"))

    def test_no_debounce_after_interval(self):
        storage = MagicMock()
        storage.load.return_value = {"preferences": {}, "facts": [], "conversation_history": []}

        mw = MemoryMiddleware(storage, debounce_seconds=0.01)
        mw._record_update_time("t1")
        time.sleep(0.02)
        self.assertFalse(mw._should_debounce("t1"))

    def test_no_debounce_for_new_thread(self):
        storage = MagicMock()
        storage.load.return_value = {"preferences": {}, "facts": [], "conversation_history": []}

        mw = MemoryMiddleware(storage, debounce_seconds=60.0)
        self.assertFalse(mw._should_debounce("new_thread"))


class TokenUsageCumulativeTest(unittest.TestCase):
    def test_cumulative_tracking(self):
        mw = TokenUsageMiddleware()

        usage1 = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        msg1 = AIMessage(content="a", usage_metadata=usage1)
        result1 = mw._track_usage({"messages": [msg1]})
        self.assertIsNotNone(result1)
        self.assertEqual(result1["token_usage"]["input_tokens"], 100)
        self.assertEqual(result1["token_usage"]["total_input_tokens"], 100)
        self.assertEqual(result1["token_usage"]["call_count"], 1)

        usage2 = {"input_tokens": 200, "output_tokens": 100, "total_tokens": 300}
        msg2 = AIMessage(content="b", usage_metadata=usage2)
        result2 = mw._track_usage({"messages": [msg2]})
        self.assertEqual(result2["token_usage"]["input_tokens"], 200)
        self.assertEqual(result2["token_usage"]["total_input_tokens"], 300)
        self.assertEqual(result2["token_usage"]["total_tokens"], 450)
        self.assertEqual(result2["token_usage"]["call_count"], 2)

    def test_returns_state_update(self):
        mw = TokenUsageMiddleware()
        usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        msg = AIMessage(content="x", usage_metadata=usage)
        result = mw._track_usage({"messages": [msg]})
        self.assertIn("token_usage", result)
        tu = result["token_usage"]
        self.assertEqual(tu["input_tokens"], 10)
        self.assertEqual(tu["output_tokens"], 5)


if __name__ == "__main__":
    unittest.main()
