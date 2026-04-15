"""Helpers for normalizing streamed model output for the web UI."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import re

# Memory keys that indicate a leaked memory extraction block
_MEMORY_JSON_KEYS = {'"preferences"', '"facts"', '"summary"'}


def strip_leaked_memory_json(text: str) -> str:
    """Remove memory extraction JSON leaked by model at end of response.

    Some models see <user_context> in the system prompt and spontaneously
    output a memory JSON block (preferences/facts/summary) at the end of
    their real answer. This strips it out.
    """
    if not text:
        return text

    # Quick check: only process if memory keys appear in the tail
    if '"preferences"' not in text[-1500:] and '"facts"' not in text[-1500:]:
        return text

    # Look for a JSON object that starts with one of the memory keys.
    # Typical patterns: {"preferences":  or { "preferences":
    import re
    # Match a '{' followed by optional whitespace then a memory key
    m = re.search(
        r'\{\s*"(?:preferences|facts|summary)"\s*:',
        text[max(0, len(text) - 1500):],
    )
    if not m:
        return text

    # Calculate absolute position
    offset = max(0, len(text) - 1500)
    cut_pos = offset + m.start()

    # Verify the block has at least 2 memory keys
    candidate = text[cut_pos:]
    key_count = sum(1 for k in _MEMORY_JSON_KEYS if k in candidate)
    if key_count < 2:
        return text

    prefix = text[:cut_pos].rstrip()
    # Also strip trailing markdown code fence markers
    if prefix.endswith("```json") or prefix.endswith("```"):
        prefix = prefix[: prefix.rfind("```")].rstrip()
    return prefix

THINK_LEVELS = {"fast", "normal", "thorough"}
MODES = {"flash", "thinking", "pro", "ultra"}
REASONING_EFFORTS = {"minimal", "low", "medium", "high"}

MODE_DEFAULT_EFFORT: dict[str, str] = {
    "flash": "minimal",
    "thinking": "low",
    "pro": "medium",
    "ultra": "high",
}

MODE_TO_THINK_LEVEL: dict[str, str] = {
    "flash": "fast",
    "thinking": "normal",
    "pro": "normal",
    "ultra": "thorough",
}

_REASONING_TYPE_TOKENS = (
    "reasoning",
    "thinking",
    "thought",
    "reason",
)
_REASONING_KEYS = (
    "reasoning",
    "reasoning_content",
    "reasoning_text",
    "thinking",
    "thinking_content",
    "thinking_text",
    "summary",
)
_TEXT_KEYS = ("text", "content", "value", "message")

_TOOL_LABELS = {
    "web_search": "搜索网络",
    "web_search_tool": "搜索网络",
    "web_fetch": "抓取网页",
    "web_fetch_tool": "抓取网页",
    "bash": "执行命令",
    "bash_tool": "执行命令",
    "read_file": "读取文件",
    "read_file_tool": "读取文件",
    "write_file": "写入文件",
    "write_file_tool": "写入文件",
    "ask_clarification": "请求澄清",
    "ask_clarification_tool": "请求澄清",
}


def normalize_think_level(value: str | None) -> str:
    """Normalize the requested think level."""

    if value in THINK_LEVELS:
        return value
    return "normal"


def normalize_mode(value: str | None) -> str:
    """Normalize the requested mode."""

    if value in MODES:
        return value
    return "pro"


def normalize_reasoning_effort(value: str | None) -> str:
    """Normalize the requested reasoning effort."""

    if value in REASONING_EFFORTS:
        return value
    return "medium"


def resolve_mode_and_effort(
    mode: str | None,
    reasoning_effort: str | None,
    think_level: str | None,
) -> tuple[str, str, str]:
    """Resolve (mode, reasoning_effort, think_level) from request params.

    Handles backward compatibility with the legacy *think_level* parameter.
    """

    if mode:
        m = normalize_mode(mode)
        e = normalize_reasoning_effort(reasoning_effort) if reasoning_effort else MODE_DEFAULT_EFFORT[m]
        return m, e, MODE_TO_THINK_LEVEL[m]

    if think_level:
        tl = normalize_think_level(think_level)
        mode_map = {"fast": "flash", "normal": "pro", "thorough": "pro"}
        effort_map = {"fast": "minimal", "normal": "medium", "thorough": "high"}
        return mode_map[tl], effort_map[tl], tl

    return "pro", "medium", "normal"


def build_model_runtime_options(
    model_config: Any,
    think_level: str = "",
    *,
    reasoning_effort: str = "",
    mode: str = "",
) -> dict[str, Any]:
    """Build provider-specific model kwargs.

    **Declarative mode** (preferred): If the model config provides
    ``when_thinking_enabled`` / ``when_thinking_disabled`` dicts, those
    are returned directly.  New providers never need code changes.

    **Fallback mode** (legacy): For models without declarative config,
    falls back to hardcoded provider detection (JD Cloud / OpenAI).
    """

    if not getattr(model_config, "supports_thinking", False):
        return {}

    # Thinking is off when mode is flash OR user toggled thinking off.
    thinking_off = mode == "flash" or reasoning_effort == "off"

    # --- Declarative path: config-driven ---
    when_enabled = getattr(model_config, "when_thinking_enabled", None)
    when_disabled = getattr(model_config, "when_thinking_disabled", None)

    if when_enabled is not None or when_disabled is not None:
        if thinking_off:
            return dict(when_disabled) if when_disabled else {}
        return dict(when_enabled) if when_enabled else {}

    # --- Legacy fallback: hardcoded provider detection ---
    base_url = getattr(model_config, "base_url", "") or ""
    if "jdcloud" in base_url:
        if thinking_off:
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        return {"extra_body": {"thinking": {"type": "enabled", "budget_tokens": 8192}}}

    if "langchain_openai" in getattr(model_config, "use", ""):
        if thinking_off:
            return {}
        return {"reasoning_effort": "medium"}

    return {}


def extract_chunk_parts(chunk: Any) -> tuple[str, str]:
    """Split a streamed chunk into answer text and reasoning text."""

    answer_parts: list[str] = []
    thinking_parts: list[str] = []

    _extract_from_content(getattr(chunk, "content", None), answer_parts, thinking_parts)

    for attr_name in ("additional_kwargs", "response_metadata"):
        metadata = getattr(chunk, attr_name, None)
        reasoning_text = _extract_reasoning_text(metadata)
        if reasoning_text and reasoning_text not in "".join(thinking_parts):
            thinking_parts.append(reasoning_text)

    return "".join(answer_parts), "".join(thinking_parts)


def build_phase_message(stage: str, think_level: str, tool_name: str | None = None) -> str | None:
    """Build a concise, user-facing phase update."""

    level = normalize_think_level(think_level)
    tool_label = describe_tool(tool_name) if tool_name else None

    if stage == "start":
        if level == "fast":
            return None
        if level == "thorough":
            return "正在拆解问题，并判断是否需要调用工具。"
        return "正在分析你的问题。"

    if stage == "tool_start":
        if not tool_label:
            return None
        if level == "thorough":
            return f"正在调用{tool_label}，并整理返回结果。"
        return f"正在{tool_label}。"

    if stage == "tool_end":
        if level == "fast" or not tool_label:
            return None
        if level == "thorough":
            return f"{tool_label}完成，正在整合新信息。"
        return f"{tool_label}完成。"

    if stage == "before_answer":
        if level == "fast":
            return "正在整理答案。"
        if level == "thorough":
            return "已完成分析，正在组织最终回答。"
        return "正在组织最终回答。"

    return None


def describe_tool(tool_name: str | None) -> str:
    """Convert an internal tool name into a readable label."""

    if not tool_name:
        return "处理请求"
    if tool_name in _TOOL_LABELS:
        return _TOOL_LABELS[tool_name]
    return tool_name.replace("_", " ").strip()


def _extract_from_content(content: Any, answer_parts: list[str], thinking_parts: list[str]) -> None:
    if content is None:
        return

    if isinstance(content, str):
        answer_parts.append(content)
        return

    if isinstance(content, list):
        for item in content:
            _extract_from_content(item, answer_parts, thinking_parts)
        return

    if isinstance(content, Mapping):
        text = _extract_text(content)
        if not text:
            return
        if _is_reasoning_block(content):
            thinking_parts.append(text)
        else:
            answer_parts.append(text)
        return

    answer_parts.append(str(content))


def _is_reasoning_block(block: Mapping[str, Any]) -> bool:
    block_type = str(block.get("type", "")).lower()
    if any(token in block_type for token in _REASONING_TYPE_TOKENS):
        return True

    role = str(block.get("role", "")).lower()
    if any(token in role for token in _REASONING_TYPE_TOKENS):
        return True

    return any(key in block for key in _REASONING_KEYS)


def _extract_reasoning_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        return "".join(_extract_reasoning_text(item) for item in value)

    if isinstance(value, Mapping):
        parts: list[str] = []
        for key in _REASONING_KEYS:
            if key in value:
                parts.append(_extract_reasoning_text(value[key]))
        if parts:
            return "".join(parts)
        if _is_reasoning_block(value):
            return _extract_text(value)
        return _extract_text(value)

    return str(value)


def _extract_text(block: Mapping[str, Any]) -> str:
    for key in _TEXT_KEYS:
        if key in block:
            value = block[key]
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return "".join(_extract_text(item) if isinstance(item, Mapping) else str(item) for item in value)
            if isinstance(value, Mapping):
                nested = _extract_reasoning_text(value) or _extract_text(value)
                if nested:
                    return nested

    # Handle nested content like {"summary": {"text": "..."}}
    for key in _REASONING_KEYS:
        if key in block:
            nested = _extract_reasoning_text(block[key])
            if nested:
                return nested

    return ""
