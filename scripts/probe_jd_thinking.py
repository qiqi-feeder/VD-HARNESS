#!/usr/bin/env python3
"""Probe JD Cloud OpenAI-compatible models for thinking support."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vdflow.config.models import Config, ModelConfig

JD_CLOUD_BASE_URL = "https://modelservice.jdcloud.com/coding/openai/v1"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_BUDGET_TOKENS = 1024

UNSUPPORTED_PARAM_TOKENS = (
    "unsupported",
    "unknown field",
    "unknown parameter",
    "extra inputs",
    "not allowed",
    "invalid parameter",
    "unexpected field",
    "does not support",
    "unrecognized",
)


@dataclass(frozen=True)
class ProbeVariant:
    """A single payload strategy used to probe thinking support."""

    name: str
    payload_updates: dict[str, Any]


@dataclass
class ProbeResult:
    """Normalized result for one model + probe variant run."""

    model: str
    probe_variant: str
    status: str
    thinking_detected: bool
    evidence: str
    error_summary: str
    http_status: int | None = None


def load_jd_cloud_models(config_path: str = "config.yaml") -> list[ModelConfig]:
    """Load only JD Cloud OpenAI-compatible chat models from config."""

    config = Config.from_yaml(config_path)
    return [
        model
        for model in config.models
        if model.base_url == JD_CLOUD_BASE_URL and model.use == "langchain_openai:ChatOpenAI"
    ]


def build_probe_variants() -> list[ProbeVariant]:
    """Return the fixed probe sequence."""

    thinking_payload = {"type": "enabled", "budgetTokens": DEFAULT_BUDGET_TOKENS}
    return [
        ProbeVariant(name="baseline", payload_updates={}),
        ProbeVariant(name="thinking_top_level", payload_updates={"thinking": thinking_payload}),
        ProbeVariant(
            name="extra_body_thinking",
            payload_updates={"extra_body": {"thinking": thinking_payload}},
        ),
        ProbeVariant(name="enable_thinking", payload_updates={"enable_thinking": True}),
    ]


def deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge updates into a copy of base."""

    merged = dict(base)
    for key, value in updates.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def build_payload(model: ModelConfig, variant: ProbeVariant) -> dict[str, Any]:
    """Build the OpenAI-compatible request payload."""

    base_payload = {
        "model": model.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a capability probe. "
                    "If the provider supports separate thinking/reasoning output, emit it normally."
                ),
            },
            {
                "role": "user",
                "content": (
                    "请先仔细思考，再回答 37 * 43 等于多少。"
                    "如果你的接口支持独立的 reasoning/thinking 返回，请保持默认行为。"
                ),
            },
        ],
        "temperature": model.temperature,
        "max_tokens": min(model.max_tokens, 256),
        "stream": False,
    }
    return deep_merge(base_payload, variant.payload_updates)


def extract_error_message(data: Any, fallback_text: str = "") -> str:
    """Extract a human-readable error summary from a response body."""

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            for key in ("message", "detail", "type", "code"):
                value = error.get(key)
                if value:
                    return str(value)
        for key in ("message", "detail", "error_description"):
            value = data.get(key)
            if value:
                return str(value)
    return fallback_text.strip()


def is_unsupported_param_error(message: str) -> bool:
    """Return whether an error looks like parameter rejection."""

    normalized = message.lower()
    return any(token in normalized for token in UNSUPPORTED_PARAM_TOKENS)


def _walk_values(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    hits = [(path, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            hits.extend(_walk_values(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_walk_values(child, f"{path}[{index}]"))
    return hits


def detect_thinking_evidence(data: Any) -> tuple[bool, str]:
    """Detect whether a response contains explicit thinking evidence."""

    if not isinstance(data, (dict, list)):
        return False, ""

    for path, value in _walk_values(data):
        leaf_key = path.rsplit(".", 1)[-1].lower()
        if any(token in leaf_key for token in ("reasoning", "thinking")):
            if value in (None, "", [], {}):
                continue
            if isinstance(value, (int, float)) and value <= 0:
                continue
            preview = str(value)
            return True, f"{path}={preview[:120]}"

        if isinstance(value, str):
            normalized = value.lower()
            if "<think>" in normalized or "</think>" in normalized:
                compact = value.replace("\n", " ")
                return True, f"{path} contains <think>: {compact[:120]}"

    return False, ""


def classify_response(
    *,
    model_name: str,
    variant_name: str,
    response: requests.Response | None = None,
    data: Any = None,
    network_error: str = "",
) -> ProbeResult:
    """Normalize HTTP or network outcomes into a single result shape."""

    if network_error:
        return ProbeResult(
            model=model_name,
            probe_variant=variant_name,
            status="network_error",
            thinking_detected=False,
            evidence="",
            error_summary=network_error,
        )

    if response is None:
        return ProbeResult(
            model=model_name,
            probe_variant=variant_name,
            status="unknown_error",
            thinking_detected=False,
            evidence="",
            error_summary="No response received",
        )

    error_text = extract_error_message(data, response.text[:200] if hasattr(response, "text") else "")
    thinking_detected, evidence = detect_thinking_evidence(data)

    if response.status_code >= 400:
        return ProbeResult(
            model=model_name,
            probe_variant=variant_name,
            status="unsupported_param" if is_unsupported_param_error(error_text) else "http_error",
            thinking_detected=False,
            evidence="",
            error_summary=error_text or f"HTTP {response.status_code}",
            http_status=response.status_code,
        )

    return ProbeResult(
        model=model_name,
        probe_variant=variant_name,
        status="thinking_detected" if thinking_detected else "ok_no_evidence",
        thinking_detected=thinking_detected,
        evidence=evidence,
        error_summary="",
        http_status=response.status_code,
    )


def run_probe(
    *,
    model: ModelConfig,
    variant: ProbeVariant,
    api_key: str,
    timeout: int,
) -> ProbeResult:
    """Execute a single probe request."""

    payload = build_payload(model, variant)
    url = model.base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        return classify_response(
            model_name=model.name,
            variant_name=variant.name,
            network_error=str(exc),
        )

    try:
        data = response.json()
    except ValueError:
        data = {"raw_text": response.text}

    return classify_response(
        model_name=model.name,
        variant_name=variant.name,
        response=response,
        data=data,
    )


def summarize_model_verdict(results: list[ProbeResult]) -> str:
    """Collapse per-variant results into a model-level verdict."""

    non_baseline = [item for item in results if item.probe_variant != "baseline"]
    if any(item.thinking_detected for item in non_baseline):
        return "supported"
    if non_baseline and all(item.status == "unsupported_param" for item in non_baseline):
        return "rejected"
    return "inconclusive"


def format_table(results: list[ProbeResult]) -> str:
    """Format result rows as a readable plain-text table."""

    headers = ["model", "probe_variant", "status", "thinking_detected", "evidence", "error_summary"]
    rows = [
        [
            item.model,
            item.probe_variant,
            item.status,
            "yes" if item.thinking_detected else "no",
            item.evidence or "-",
            item.error_summary or "-",
        ]
        for item in results
    ]
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))

    def render_row(row: list[str]) -> str:
        return " | ".join(str(cell).ljust(widths[index]) for index, cell in enumerate(row))

    separator = "-+-".join("-" * width for width in widths)
    lines = [render_row(headers), separator]
    lines.extend(render_row(row) for row in rows)
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Probe JD Cloud models for thinking support.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--model", help="Only run the named model from config")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    load_dotenv(REPO_ROOT / ".env")
    args = parse_args(argv)
    api_key = os.getenv("JDCODING_API_KEY", "").strip()
    if not api_key:
        print("Missing JDCODING_API_KEY. Export it before running this probe.", file=sys.stderr)
        print("Example: export JDCODING_API_KEY=your_key_here", file=sys.stderr)
        return 2

    models = load_jd_cloud_models(args.config)
    if args.model:
        models = [model for model in models if model.name == args.model]
        if not models:
            print(f"Model '{args.model}' not found among JD Cloud models in {args.config}.", file=sys.stderr)
            return 2

    if not models:
        print("No JD Cloud OpenAI-compatible models found in config.", file=sys.stderr)
        return 2

    results: list[ProbeResult] = []
    variants = build_probe_variants()

    for model in models:
        for variant in variants:
            result = run_probe(model=model, variant=variant, api_key=api_key, timeout=args.timeout)
            results.append(result)

    print("JD Cloud thinking probe results")
    print()
    print(format_table(results))
    print()
    print("Model verdicts")
    for model in models:
        model_results = [item for item in results if item.model == model.name]
        print(f"- {model.name}: {summarize_model_verdict(model_results)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
