"""Tests for Phase 3: Declarative thinking config + LLM title generation."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from vdflow.agent.middlewares.title import TitleMiddleware, _derive_title
from vdflow.web.streaming import build_model_runtime_options


class DeclarativeThinkingTest(unittest.TestCase):
    """Test that when_thinking_enabled/disabled config takes priority."""

    def test_declarative_enabled(self):
        model_config = SimpleNamespace(
            supports_thinking=True,
            when_thinking_enabled={"extra_body": {"thinking": {"type": "enabled", "budget_tokens": 8192}}},
            when_thinking_disabled={"extra_body": {"thinking": {"type": "disabled"}}},
        )
        result = build_model_runtime_options(model_config, mode="pro")
        self.assertEqual(result, {"extra_body": {"thinking": {"type": "enabled", "budget_tokens": 8192}}})

    def test_declarative_disabled_on_flash(self):
        model_config = SimpleNamespace(
            supports_thinking=True,
            when_thinking_enabled={"extra_body": {"thinking": {"type": "enabled", "budget_tokens": 8192}}},
            when_thinking_disabled={"extra_body": {"thinking": {"type": "disabled"}}},
        )
        result = build_model_runtime_options(model_config, mode="flash")
        self.assertEqual(result, {"extra_body": {"thinking": {"type": "disabled"}}})

    def test_declarative_disabled_on_effort_off(self):
        model_config = SimpleNamespace(
            supports_thinking=True,
            when_thinking_enabled={"reasoning_effort": "high"},
            when_thinking_disabled={},
        )
        result = build_model_runtime_options(model_config, mode="pro", reasoning_effort="off")
        self.assertEqual(result, {})

    def test_declarative_with_only_enabled(self):
        """If only when_thinking_enabled is set, flash returns {}."""
        model_config = SimpleNamespace(
            supports_thinking=True,
            when_thinking_enabled={"reasoning_effort": "medium"},
            when_thinking_disabled=None,
        )
        result = build_model_runtime_options(model_config, mode="flash")
        self.assertEqual(result, {})

    def test_legacy_fallback_still_works_for_jdcloud(self):
        """Models without declarative config still use base_url detection."""
        model_config = SimpleNamespace(
            supports_thinking=True,
            base_url="https://modelservice.jdcloud.com/coding/openai/v1",
            use="langchain_openai:ChatOpenAI",
        )
        result = build_model_runtime_options(model_config, mode="pro")
        self.assertEqual(result, {"extra_body": {"thinking": {"type": "enabled", "budget_tokens": 8192}}})

    def test_legacy_fallback_still_works_for_openai(self):
        """Models without declarative config still use use= detection."""
        model_config = SimpleNamespace(
            supports_thinking=True,
            base_url="",
            use="langchain_openai:ChatOpenAI",
        )
        result = build_model_runtime_options(model_config, mode="pro", reasoning_effort="on")
        self.assertEqual(result, {"reasoning_effort": "medium"})

    def test_config_yaml_declarative_fields_loaded(self):
        """Verify config.yaml models have when_thinking_enabled loaded."""
        from vdflow.config.models import Config

        config = Config.from_yaml("config.yaml")
        jd_models = [m for m in config.models if m.supports_thinking and m.when_thinking_enabled]
        # At least the 4 JD models with supports_thinking should have declarative config
        self.assertGreaterEqual(len(jd_models), 4)
        for m in jd_models:
            self.assertIn("extra_body", m.when_thinking_enabled)
            self.assertIn("extra_body", m.when_thinking_disabled)


class TitleMiddlewareLLMTest(unittest.TestCase):
    """Test TitleMiddleware with LLM support."""

    def test_fallback_truncation(self):
        """Without model, uses truncation."""
        mw = TitleMiddleware(model=None, use_llm=False)
        messages = [MagicMock(type="human", content="这是一个很长很长的标题测试文本用来验证截断功能")]
        result = mw._generate_title(messages)
        self.assertTrue(len(result) <= 50)

    def test_llm_title_generation(self):
        """With model, calls LLM for title."""
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="VD-Flow 架构升级")

        mw = TitleMiddleware(model=mock_model, use_llm=True)
        messages = [MagicMock(type="human", content="帮我把 vd-flow 升级成 deerflow 那套中间件架构")]
        result = mw._generate_title(messages)
        self.assertEqual(result, "VD-Flow 架构升级")
        mock_model.invoke.assert_called_once()

    def test_llm_failure_falls_back(self):
        """If LLM call fails, uses truncation."""
        mock_model = MagicMock()
        mock_model.invoke.side_effect = RuntimeError("API down")

        mw = TitleMiddleware(model=mock_model, use_llm=True)
        messages = [MagicMock(type="human", content="测试消息")]
        result = mw._generate_title(messages)
        self.assertEqual(result, "测试消息")

    def test_llm_too_long_title_truncated(self):
        """If LLM returns title > max_chars, truncate it."""
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(content="这个标题实在是太长了需要被截断掉否则会超过最大字符限制导致显示不正常哦")

        mw = TitleMiddleware(model=mock_model, use_llm=True, max_chars=20)
        messages = [MagicMock(type="human", content="test")]
        result = mw._generate_title(messages)
        self.assertTrue(len(result) <= 20)

    def test_derive_title_basic(self):
        """Test the truncation helper directly."""
        messages = [MagicMock(type="human", content="短标题")]
        self.assertEqual(_derive_title(messages), "短标题")

        messages = [MagicMock(type="human", content="a" * 50)]
        result = _derive_title(messages, max_chars=28)
        self.assertTrue(result.endswith("…"))
        self.assertTrue(len(result) <= 28)

    def test_use_llm_false_skips_model(self):
        """use_llm=False should never call model."""
        mock_model = MagicMock()
        mw = TitleMiddleware(model=mock_model, use_llm=False)
        messages = [MagicMock(type="human", content="hello")]
        mw._generate_title(messages)
        mock_model.invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
