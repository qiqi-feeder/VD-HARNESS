"""Unit tests for web streaming helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from vdflow.web.streaming import (
    build_model_runtime_options,
    build_phase_message,
    extract_chunk_parts,
    normalize_think_level,
)


class StreamingHelpersTest(unittest.TestCase):
    def test_normalize_think_level_defaults_to_normal(self) -> None:
        self.assertEqual(normalize_think_level(None), "normal")
        self.assertEqual(normalize_think_level("unexpected"), "normal")
        self.assertEqual(normalize_think_level("thorough"), "thorough")

    def test_extract_chunk_parts_from_plain_text(self) -> None:
        chunk = SimpleNamespace(content="你好，世界", additional_kwargs={}, response_metadata={})
        answer, thinking = extract_chunk_parts(chunk)
        self.assertEqual(answer, "你好，世界")
        self.assertEqual(thinking, "")

    def test_extract_chunk_parts_separates_reasoning_blocks(self) -> None:
        chunk = SimpleNamespace(
            content=[
                {"type": "reasoning", "text": "先查一下资料。"},
                {"type": "text", "text": "这是最终回答。"},
            ],
            additional_kwargs={},
            response_metadata={},
        )
        answer, thinking = extract_chunk_parts(chunk)
        self.assertEqual(answer, "这是最终回答。")
        self.assertEqual(thinking, "先查一下资料。")

    def test_extract_chunk_parts_reads_reasoning_from_metadata(self) -> None:
        chunk = SimpleNamespace(
            content="",
            additional_kwargs={"reasoning_content": [{"text": "分析中"}]},
            response_metadata={},
        )
        answer, thinking = extract_chunk_parts(chunk)
        self.assertEqual(answer, "")
        self.assertEqual(thinking, "分析中")

    def test_build_phase_message_respects_level(self) -> None:
        self.assertIsNone(build_phase_message("start", "fast"))
        self.assertIn("分析", build_phase_message("start", "normal") or "")
        self.assertIn("整合", build_phase_message("tool_end", "thorough", "web_search") or "")

    def test_build_model_runtime_options_requires_opt_in(self) -> None:
        model_config = SimpleNamespace(supports_thinking=False, use="langchain_openai:ChatOpenAI", base_url="")
        self.assertEqual(build_model_runtime_options(model_config, mode="pro"), {})

    def test_build_model_runtime_options_uses_openai_reasoning_effort(self) -> None:
        model_config = SimpleNamespace(supports_thinking=True, use="langchain_openai:ChatOpenAI", base_url="")
        self.assertEqual(
            build_model_runtime_options(model_config, mode="pro", reasoning_effort="on"),
            {"reasoning_effort": "medium"},
        )
        # flash returns empty for OpenAI
        self.assertEqual(build_model_runtime_options(model_config, mode="flash"), {})
        # toggle off returns empty for OpenAI
        self.assertEqual(build_model_runtime_options(model_config, mode="pro", reasoning_effort="off"), {})

    def test_build_model_runtime_options_jd_cloud_thinking(self) -> None:
        model_config = SimpleNamespace(
            supports_thinking=True,
            use="langchain_openai:ChatOpenAI",
            base_url="https://modelservice.jdcloud.com/coding/openai/v1",
        )
        # non-flash → enabled
        result = build_model_runtime_options(model_config, mode="pro")
        self.assertEqual(result, {"extra_body": {"thinking": {"type": "enabled", "budget_tokens": 8192}}})
        # flash → disabled
        result = build_model_runtime_options(model_config, mode="flash")
        self.assertEqual(result, {"extra_body": {"thinking": {"type": "disabled"}}})
        # toggle off → disabled
        result = build_model_runtime_options(model_config, mode="pro", reasoning_effort="off")
        self.assertEqual(result, {"extra_body": {"thinking": {"type": "disabled"}}})


if __name__ == "__main__":
    unittest.main()
