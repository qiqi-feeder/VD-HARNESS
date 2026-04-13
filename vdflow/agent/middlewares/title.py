"""Title generation middleware.

Supports two modes:
1. **LLM mode** (default): Calls the model to generate a concise title from
   the first user message. This produces natural, meaningful titles.
2. **Truncation fallback**: If no model is provided or LLM call fails,
   truncates the user message to ``max_chars`` characters.

Ported from DeerFlow's TitleMiddleware pattern.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage as LCHumanMessage
from langgraph.runtime import Runtime

from vdflow.agent.middlewares._utils import _state_get
from vdflow.agent.state import ThreadState

logger = logging.getLogger(__name__)

_TITLE_PROMPT = (
    "请为以下对话的第一条用户消息生成一个简短的标题（不超过{max_words}个词，"
    "最多{max_chars}个字符）。只返回标题，不要解释。\n\n"
    "用户消息: {message}"
)


def _latest_human_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "human" and getattr(message, "content", ""):
            return str(message.content)
    return ""


def _derive_title(messages: list[Any], max_chars: int = 28) -> str:
    """Fallback: truncate the user message."""
    latest = _latest_human_text(messages)
    normalized = " ".join(latest.split()).strip()
    if not normalized:
        return ""
    return normalized[: max_chars - 1] + "…" if len(normalized) > max_chars else normalized


class TitleMiddleware(AgentMiddleware[ThreadState]):
    """Generate a title for new conversations.

    When ``model`` is provided, uses the LLM to generate a natural title.
    Falls back to truncation if the LLM call fails or if no model is given.
    """

    state_schema = ThreadState

    def __init__(
        self,
        model: BaseChatModel | None = None,
        *,
        use_llm: bool = True,
        max_words: int = 6,
        max_chars: int = 50,
    ):
        super().__init__()
        self.model = model
        self.use_llm = use_llm and model is not None
        self.max_words = max_words
        self.max_chars = max_chars

    def after_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        title = _state_get(state, "title", "")
        messages = _state_get(state, "messages", [])
        if title and title != "新对话":
            return None

        derived_title = self._generate_title(messages)
        if not derived_title:
            return None
        return {"title": derived_title}

    async def aafter_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        title = _state_get(state, "title", "")
        messages = _state_get(state, "messages", [])
        if title and title != "新对话":
            return None

        derived_title = await self._agenerate_title(messages)
        if not derived_title:
            return None
        return {"title": derived_title}

    def _generate_title(self, messages: list[Any]) -> str:
        """Sync: try LLM, fallback to truncation."""
        if not self.use_llm or self.model is None:
            return _derive_title(messages, self.max_chars)

        user_text = _latest_human_text(messages)
        if not user_text:
            return ""

        try:
            prompt = _TITLE_PROMPT.format(
                max_words=self.max_words,
                max_chars=self.max_chars,
                message=user_text[:500],
            )
            response = self.model.invoke([LCHumanMessage(content=prompt)])
            title = response.content.strip().strip('"').strip("'").strip("《》")
            if title and len(title) <= self.max_chars:
                return title
            # title too long → truncate it
            return title[: self.max_chars - 1] + "…" if title else _derive_title(messages, self.max_chars)
        except Exception as exc:
            logger.warning("LLM title generation failed, using fallback: %s", exc)
            return _derive_title(messages, self.max_chars)

    async def _agenerate_title(self, messages: list[Any]) -> str:
        """Async: try LLM, fallback to truncation."""
        if not self.use_llm or self.model is None:
            return _derive_title(messages, self.max_chars)

        user_text = _latest_human_text(messages)
        if not user_text:
            return ""

        try:
            prompt = _TITLE_PROMPT.format(
                max_words=self.max_words,
                max_chars=self.max_chars,
                message=user_text[:500],
            )
            response = await self.model.ainvoke([LCHumanMessage(content=prompt)])
            title = response.content.strip().strip('"').strip("'").strip("《》")
            if title and len(title) <= self.max_chars:
                return title
            return title[: self.max_chars - 1] + "…" if title else _derive_title(messages, self.max_chars)
        except Exception as exc:
            logger.warning("LLM title generation failed, using fallback: %s", exc)
            return _derive_title(messages, self.max_chars)
