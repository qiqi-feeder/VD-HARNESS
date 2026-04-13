"""Tests for DeerFlow-style middleware behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from vdflow.agent.middlewares import ClarificationMiddleware, ThreadDataMiddleware, build_middlewares
from vdflow.agent.state import ThreadState
from vdflow.config.models import Config
from vdflow.runtime_context import clear_thread_data
from vdflow.skills import Skill


class MiddlewareTest(unittest.TestCase):
    def tearDown(self) -> None:
        clear_thread_data()

    def test_build_middlewares_keeps_clarification_last(self) -> None:
        middlewares = build_middlewares(Config(), skills=[])
        self.assertEqual(middlewares[-1].__class__.__name__, "ClarificationMiddleware")

    def test_thread_data_middleware_creates_thread_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            middleware = ThreadDataMiddleware(tempdir, skills=[])
            state = ThreadState(messages=[HumanMessage(content="hello")])
            runtime = SimpleNamespace(context={"thread_id": "thread-1"})

            update = middleware.before_agent(state, runtime)

            self.assertEqual(update["thread_id"], "thread-1")
            thread_data = update["thread_data"]
            self.assertTrue(Path(thread_data.workspace_path).exists())
            self.assertTrue(Path(thread_data.uploads_path).exists())
            self.assertTrue(Path(thread_data.outputs_path).exists())

    def test_thread_data_middleware_matches_skills_from_latest_message(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            skill = Skill(
                name="quick_research",
                description="快速调研某个研究方向",
                content="demo",
                path="/tmp/quick_research/SKILL.md",
            )
            middleware = ThreadDataMiddleware(tempdir, skills=[skill])
            state = ThreadState(messages=[HumanMessage(content="帮我调研一下智能体框架")])
            runtime = SimpleNamespace(context={"thread_id": "thread-2"})

            update = middleware.before_agent(state, runtime)

            self.assertIn("quick_research", update["active_skills"])

    def test_clarification_middleware_interrupts_execution(self) -> None:
        middleware = ClarificationMiddleware()
        request = SimpleNamespace(
            tool_call={
                "name": "ask_clarification",
                "id": "tool-1",
                "args": {
                    "question": "你想用哪个环境？",
                    "clarification_type": "approach_choice",
                    "context": "部署前需要目标环境信息",
                    "options": ["staging", "production"],
                },
            }
        )

        result = middleware.wrap_tool_call(request, lambda _: None)

        self.assertIsInstance(result, Command)
        self.assertEqual(result.goto, "__end__")
        pending = result.update["pending_clarification"]
        self.assertEqual(pending.question, "你想用哪个环境？")
        self.assertEqual(pending.options, ["staging", "production"])


if __name__ == "__main__":
    unittest.main()
