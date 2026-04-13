"""Tests for Phase 2 middlewares: Summarization integration + Token usage tracking."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from vdflow.agent.middlewares.token_usage import TokenUsageMiddleware
from vdflow.config.models import Config, ContextSizeSpec, SummarizationConfig


class TokenUsageMiddlewareTest(unittest.TestCase):
    def test_logs_usage_from_ai_message(self):
        middleware = TokenUsageMiddleware()
        usage = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        ai_msg = AIMessage(content="hello", usage_metadata=usage)
        state = {"messages": [HumanMessage(content="hi"), ai_msg]}

        with patch("vdflow.agent.middlewares.token_usage.logger") as mock_logger:
            result = middleware._track_usage(state)
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            self.assertIn("100", str(call_args))
            self.assertIn("50", str(call_args))
            self.assertIn("150", str(call_args))

        self.assertIsNotNone(result)
        self.assertIn("token_usage", result)
        self.assertEqual(result["token_usage"]["input_tokens"], 100)

    def test_no_action_without_usage(self):
        middleware = TokenUsageMiddleware()
        ai_msg = AIMessage(content="hello")
        state = {"messages": [ai_msg]}
        result = middleware._track_usage(state)
        self.assertIsNone(result)

    def test_no_action_for_human_message(self):
        middleware = TokenUsageMiddleware()
        state = {"messages": [HumanMessage(content="hi")]}
        result = middleware._track_usage(state)
        self.assertIsNone(result)

    def test_handles_detailed_token_breakdown(self):
        middleware = TokenUsageMiddleware()
        usage = {
            "input_tokens": 200,
            "output_tokens": 100,
            "total_tokens": 300,
            "input_token_details": {"cache_read": 50},
            "output_token_details": {"reasoning": 30},
        }
        ai_msg = AIMessage(content="response", usage_metadata=usage)
        state = {"messages": [ai_msg]}

        with patch("vdflow.agent.middlewares.token_usage.logger") as mock_logger:
            middleware._track_usage(state)
            call_args = str(mock_logger.info.call_args)
            self.assertIn("30", call_args)  # reasoning tokens
            self.assertIn("50", call_args)  # cache_read


class SummarizationConfigTest(unittest.TestCase):
    def test_default_config_is_enabled(self):
        config = SummarizationConfig()
        self.assertTrue(config.enabled)

    def test_default_trigger_tokens(self):
        config = SummarizationConfig()
        triggers = config.trigger
        self.assertIsInstance(triggers, list)
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].type, "tokens")
        self.assertEqual(triggers[0].value, 15564)

    def test_default_keep_messages(self):
        config = SummarizationConfig()
        self.assertEqual(config.keep.type, "messages")
        self.assertEqual(config.keep.value, 10)

    def test_context_size_to_tuple(self):
        spec = ContextSizeSpec(type="tokens", value=5000)
        self.assertEqual(spec.to_tuple(), ("tokens", 5000))

        spec = ContextSizeSpec(type="fraction", value=0.8)
        self.assertEqual(spec.to_tuple(), ("fraction", 0.8))

        spec = ContextSizeSpec(type="messages", value=50)
        self.assertEqual(spec.to_tuple(), ("messages", 50))

    def test_config_yaml_loads_summarization(self):
        config = Config.from_yaml("config.yaml")
        self.assertTrue(config.summarization.enabled)
        self.assertIsNotNone(config.summarization.trigger)

    def test_disabled_config(self):
        config = SummarizationConfig(enabled=False)
        self.assertFalse(config.enabled)


class BuildMiddlewaresWithSummarizationTest(unittest.TestCase):
    def test_summarization_middleware_created_when_model_provided(self):
        from vdflow.agent.middlewares import _create_summarization_middleware

        config = SummarizationConfig(enabled=True)
        model = MagicMock()

        with patch(
            "vdflow.agent.middlewares.SummarizationMiddleware",
            create=True,
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            result = _create_summarization_middleware(config, model)
            # SummarizationMiddleware should have been instantiated
            self.assertIsNotNone(result)

    def test_summarization_disabled_returns_none(self):
        from vdflow.agent.middlewares import _create_summarization_middleware

        config = SummarizationConfig(enabled=False)
        model = MagicMock()
        result = _create_summarization_middleware(config, model)
        self.assertIsNone(result)

    def test_build_middlewares_includes_token_usage(self):
        from vdflow.agent.middlewares import build_middlewares

        config = Config()
        config.summarization.enabled = False  # skip summarization for this test

        middlewares = build_middlewares(config)
        class_names = [m.__class__.__name__ for m in middlewares]
        self.assertIn("TokenUsageMiddleware", class_names)

    def test_token_usage_disabled(self):
        from vdflow.agent.middlewares import build_middlewares

        config = Config()
        config.middleware.token_usage_enabled = False
        config.summarization.enabled = False

        middlewares = build_middlewares(config)
        class_names = [m.__class__.__name__ for m in middlewares]
        self.assertNotIn("TokenUsageMiddleware", class_names)


if __name__ == "__main__":
    unittest.main()
