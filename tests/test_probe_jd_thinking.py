"""Unit tests for the JD Cloud thinking probe script."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts.probe_jd_thinking import (
    JD_CLOUD_BASE_URL,
    ProbeResult,
    ProbeVariant,
    build_payload,
    classify_response,
    detect_thinking_evidence,
    is_unsupported_param_error,
    summarize_model_verdict,
)
from vdflow.config.models import ModelConfig


class ProbeThinkingScriptTest(unittest.TestCase):
    def _model(self, **overrides):
        return ModelConfig(
            name="glm-5-jd",
            display_name="GLM-5 (JD Cloud)",
            use="langchain_openai:ChatOpenAI",
            model="GLM-5",
            api_key="test-key",
            base_url=JD_CLOUD_BASE_URL,
            max_tokens=8192,
            **overrides,
        )

    def test_build_payload_merges_probe_updates(self) -> None:
        model = self._model()
        variant = ProbeVariant(
            name="thinking_top_level",
            payload_updates={"thinking": {"type": "enabled", "budgetTokens": 1024}},
        )

        payload = build_payload(model, variant)

        self.assertEqual(payload["model"], "GLM-5")
        self.assertEqual(payload["thinking"]["type"], "enabled")
        self.assertEqual(payload["thinking"]["budgetTokens"], 1024)
        self.assertTrue(payload["messages"])

    def test_detect_thinking_evidence_finds_reasoning_field(self) -> None:
        data = {
            "choices": [
                {
                    "message": {
                        "reasoning_details": [{"text": "先分析，再回答"}],
                        "content": "1591",
                    }
                }
            ]
        }

        detected, evidence = detect_thinking_evidence(data)

        self.assertTrue(detected)
        self.assertIn("reasoning_details", evidence)

    def test_detect_thinking_evidence_finds_think_tag(self) -> None:
        data = {"choices": [{"message": {"content": "<think>计算中</think> 1591"}}]}

        detected, evidence = detect_thinking_evidence(data)

        self.assertTrue(detected)
        self.assertIn("<think>", evidence)

    def test_detect_thinking_evidence_ignores_zero_reasoning_tokens(self) -> None:
        data = {"usage": {"reasoning_tokens": 0}}

        detected, evidence = detect_thinking_evidence(data)

        self.assertFalse(detected)
        self.assertEqual(evidence, "")

    def test_is_unsupported_param_error_matches_common_messages(self) -> None:
        self.assertTrue(is_unsupported_param_error("Unknown parameter: thinking"))
        self.assertTrue(is_unsupported_param_error("This model does not support extra inputs"))
        self.assertFalse(is_unsupported_param_error("Request timed out"))

    def test_classify_response_marks_unsupported_parameters(self) -> None:
        response = SimpleNamespace(status_code=400, text='{"error":{"message":"Unknown parameter: thinking"}}')
        result = classify_response(
            model_name="glm-5-jd",
            variant_name="thinking_top_level",
            response=response,
            data={"error": {"message": "Unknown parameter: thinking"}},
        )

        self.assertEqual(result.status, "unsupported_param")
        self.assertFalse(result.thinking_detected)

    def test_classify_response_marks_detected_thinking(self) -> None:
        response = SimpleNamespace(status_code=200, text="")
        result = classify_response(
            model_name="glm-5-jd",
            variant_name="thinking_top_level",
            response=response,
            data={"choices": [{"message": {"reasoning": "先算乘法", "content": "1591"}}]},
        )

        self.assertEqual(result.status, "thinking_detected")
        self.assertTrue(result.thinking_detected)

    def test_summarize_model_verdict(self) -> None:
        detected = [
            ProbeResult("glm-5-jd", "baseline", "ok_no_evidence", False, "", ""),
            ProbeResult("glm-5-jd", "thinking_top_level", "thinking_detected", True, "x", ""),
        ]
        rejected = [
            ProbeResult("glm-5-jd", "baseline", "ok_no_evidence", False, "", ""),
            ProbeResult("glm-5-jd", "thinking_top_level", "unsupported_param", False, "", "bad"),
            ProbeResult("glm-5-jd", "extra_body_thinking", "unsupported_param", False, "", "bad"),
        ]
        inconclusive = [
            ProbeResult("glm-5-jd", "baseline", "ok_no_evidence", False, "", ""),
            ProbeResult("glm-5-jd", "thinking_top_level", "ok_no_evidence", False, "", ""),
        ]

        self.assertEqual(summarize_model_verdict(detected), "supported")
        self.assertEqual(summarize_model_verdict(rejected), "rejected")
        self.assertEqual(summarize_model_verdict(inconclusive), "inconclusive")


if __name__ == "__main__":
    unittest.main()
