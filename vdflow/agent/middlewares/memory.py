"""Memory injection and async update middleware.

Enhanced with DeerFlow-inspired and Hermes-inspired features:
- **Correction detection**: Detects user phrases and flags memory re-extraction.
- **Reinforcement detection**: Detects positive signals to strengthen facts.
- **Debounce**: Skips memory updates if the last update was within debounce_seconds.
- **Message filtering**: Only sends human + final AI messages to the memory updater.
- **Frozen Snapshot**: Memory context is frozen on first before_model call to prevent
  mid-conversation context drift.
- **Injection Protection**: Scans memory content for prompt injection patterns.
- **Size Limiting**: Enforces a max_chars limit on injected memory context.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from copy import copy
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from vdflow.agent.middlewares._utils import _state_get
from vdflow.agent.state import ThreadState
from vdflow.memory import MemoryStorage, MemoryUpdater

logger = logging.getLogger(__name__)

MEMORY_MARKER = "<user_context>"

_UPLOAD_BLOCK_RE = re.compile(r"<uploaded_files>[\s\S]*?</uploaded_files>\n*", re.IGNORECASE)

_CORRECTION_PATTERNS = (
    re.compile(r"\bthat(?:'s| is) (?:wrong|incorrect)\b", re.IGNORECASE),
    re.compile(r"\byou misunderstood\b", re.IGNORECASE),
    re.compile(r"\btry again\b", re.IGNORECASE),
    re.compile(r"\bredo\b", re.IGNORECASE),
    re.compile(r"不对"),
    re.compile(r"你理解错了"),
    re.compile(r"你理解有误"),
    re.compile(r"重试"),
    re.compile(r"重新来"),
    re.compile(r"换一种"),
    re.compile(r"改用"),
)

_REINFORCEMENT_PATTERNS = (
    re.compile(r"\byes[,.]?\s+(?:exactly|perfect|that(?:'s| is) (?:right|correct|it))\b", re.IGNORECASE),
    re.compile(r"\bperfect(?:[.!?]|$)", re.IGNORECASE),
    re.compile(r"\bthat(?:'s| is)\s+(?:exactly\s+)?(?:right|correct)\b", re.IGNORECASE),
    re.compile(r"\bkeep\s+(?:doing\s+)?that\b", re.IGNORECASE),
    re.compile(r"对[，,]?\s*就是这样(?:[。！？!?.]|$)"),
    re.compile(r"完全正确(?:[。！？!?.]|$)"),
    re.compile(r"(?:对[，,]?\s*)?就是这个意思(?:[。！？!?.]|$)"),
    re.compile(r"正是我想要的(?:[。！？!?.]|$)"),
    re.compile(r"继续保持(?:[。！？!?.]|$)"),
)


def _extract_message_text(message: Any) -> str:
    """Extract plain text from message content."""
    content = getattr(message, "content", "")
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text_val = part.get("text")
                if isinstance(text_val, str):
                    parts.append(text_val)
        return " ".join(parts)
    return str(content)


def filter_messages_for_memory(messages: list[Any]) -> list[Any]:
    """Filter messages to keep only user inputs and final assistant responses.

    Removes: tool calls, system messages, upload blocks.
    Keeps: human messages (cleaned), AI messages without tool_calls.
    """
    filtered: list[Any] = []
    skip_next_ai = False

    for msg in messages:
        msg_type = getattr(msg, "type", None)

        if msg_type == "human":
            content_str = _extract_message_text(msg)
            if "<uploaded_files>" in content_str:
                stripped = _UPLOAD_BLOCK_RE.sub("", content_str).strip()
                if not stripped:
                    skip_next_ai = True
                    continue
                clean_msg = copy(msg)
                clean_msg.content = stripped
                filtered.append(clean_msg)
                skip_next_ai = False
            else:
                filtered.append(msg)
                skip_next_ai = False
        elif msg_type == "ai":
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                if skip_next_ai:
                    skip_next_ai = False
                    continue
                filtered.append(msg)
        # Skip tool messages and AI messages with tool_calls

    return filtered


def detect_correction(messages: list[Any]) -> bool:
    """Detect explicit user corrections in recent conversation turns."""
    recent_user_msgs = [msg for msg in messages[-6:] if getattr(msg, "type", None) == "human"]
    for msg in recent_user_msgs:
        content = _extract_message_text(msg).strip()
        if not content:
            continue
        if any(pattern.search(content) for pattern in _CORRECTION_PATTERNS):
            return True
    return False


def detect_reinforcement(messages: list[Any]) -> bool:
    """Detect positive reinforcement signals in recent conversation turns."""
    recent_user_msgs = [msg for msg in messages[-6:] if getattr(msg, "type", None) == "human"]
    for msg in recent_user_msgs:
        content = _extract_message_text(msg).strip()
        if not content:
            continue
        if any(pattern.search(content) for pattern in _REINFORCEMENT_PATTERNS):
            return True
    return False


# ---------------------------------------------------------------------------
# Injection protection patterns
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = (
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    re.compile(
        r"\b(?:you (?:are|must)|ignore (?:all|previous|above)|disregard|forget)\b"
        r".*(?:instructions?|rules?|constraints?)",
        re.IGNORECASE,
    ),
    re.compile(r"\brole\s*[:=]\s*(?:system|admin|root)\b", re.IGNORECASE),
    re.compile(r"\b(?:SYSTEM|ADMIN|ROOT)\s*(?:OVERRIDE|ACCESS|MODE)\b"),
    re.compile(
        r"\b(?:exfiltrate|leak|dump|extract)\b.*(?:credentials?|secrets?|api.?keys?|passwords?)",
        re.IGNORECASE,
    ),
)


def _scan_for_injection(content: str) -> bool:
    """Return True if content contains potential prompt injection."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(content):
            return True
    return False


class MemoryMiddleware(AgentMiddleware[ThreadState]):
    """Inject memory context and schedule memory updates.

    Enhanced with correction/reinforcement detection, debounce,
    frozen snapshots, injection protection, and size limiting.
    """

    state_schema = ThreadState

    def __init__(
        self,
        storage: MemoryStorage,
        updater: MemoryUpdater | None = None,
        *,
        debounce_seconds: float = 30.0,
        max_context_chars: int = 3000,
        nudge_interval: int = 10,
    ):
        self.storage = storage
        self.updater = updater
        self.debounce_seconds = debounce_seconds
        self.max_context_chars = max_context_chars
        self.nudge_interval = nudge_interval
        self._last_update_times: dict[str, float] = {}
        # Frozen snapshot: loaded once per agent run, not refreshed mid-conversation
        self._frozen_context: str | None = None
        self._frozen_loaded: bool = False
        # Nudge counter: counts turns since last review
        self._turns_since_review: int = 0

    def _format_memory_context(self, memory_data: dict[str, Any]) -> str:
        parts: list[str] = []
        preferences = memory_data.get("preferences") or {}
        if preferences:
            parts.append("User Preferences:")
            for key, value in preferences.items():
                parts.append(f"- {key}: {value}")

        facts = memory_data.get("facts") or []
        if facts:
            parts.append("")
            parts.append("Known Facts:")
            for fact in facts[:5]:
                parts.append(f"- {fact.get('content', '')}")

        history = memory_data.get("conversation_history") or []
        if history:
            parts.append("")
            parts.append("Recent History:")
            for conversation in history[-3:]:
                parts.append(f"- {conversation.get('summary', '')}")

        return "\n".join(parts).strip()

    def before_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        # Frozen Snapshot: load memory once per agent run, not mid-conversation
        if not self._frozen_loaded:
            raw_context = self._format_memory_context(self.storage.load())
            # Injection protection: scan before freezing
            if raw_context and _scan_for_injection(raw_context):
                logger.warning("Potential prompt injection detected in memory — skipping injection")
                raw_context = ""
            # Size limiting
            if len(raw_context) > self.max_context_chars:
                raw_context = raw_context[: self.max_context_chars] + "\n[Memory truncated]"
            self._frozen_context = raw_context
            self._frozen_loaded = True

        memory_context = self._frozen_context or ""
        if not memory_context:
            return {"memory_context": ""}

        updates: dict[str, Any] = {"memory_context": memory_context}
        messages = _state_get(state, "messages", [])
        current_memory_context = _state_get(state, "memory_context", "")
        already_injected = any(
            getattr(message, "type", "") == "system"
            and MEMORY_MARKER in str(getattr(message, "content", ""))
            for message in messages
        )
        if (current_memory_context != memory_context) or not already_injected:
            updates["messages"] = [SystemMessage(content=f"{MEMORY_MARKER}\n{memory_context}\n</user_context>")]
        return updates

    def _should_debounce(self, thread_id: str) -> bool:
        """Check if we should skip this update due to debounce."""
        now = time.monotonic()
        last_update = self._last_update_times.get(thread_id, 0.0)
        return (now - last_update) < self.debounce_seconds

    def _record_update_time(self, thread_id: str) -> None:
        self._last_update_times[thread_id] = time.monotonic()

    def after_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        if self.updater is None:
            return None

        messages = _state_get(state, "messages", [])
        thread_id = _state_get(state, "thread_id", "")

        if not messages or not thread_id:
            return None

        # --- Nudge counter ---
        self._turns_since_review += 1

        # Debounce: skip if updated recently
        if self._should_debounce(thread_id):
            logger.debug("Memory update debounced for thread %s", thread_id)
            return None

        # Filter messages for memory (human + final AI only)
        filtered = filter_messages_for_memory(messages)
        user_msgs = [m for m in filtered if getattr(m, "type", None) == "human"]
        ai_msgs = [m for m in filtered if getattr(m, "type", None) == "ai"]

        if not user_msgs or not ai_msgs:
            return None

        # Detect correction/reinforcement signals
        correction = detect_correction(filtered)
        reinforcement = not correction and detect_reinforcement(filtered)

        if correction:
            logger.info("Correction signal detected in thread %s — forcing memory re-extraction", thread_id)
        elif reinforcement:
            logger.info("Reinforcement signal detected in thread %s", thread_id)

        self._record_update_time(thread_id)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.updater.update_from_conversation(filtered, thread_id))
        except RuntimeError:
            logger.debug("No running event loop available for memory update task")

        # --- Nudge: trigger background comparative review ---
        if (
            self.nudge_interval > 0
            and self._turns_since_review >= self.nudge_interval
        ):
            self._turns_since_review = 0
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._background_review(messages, thread_id)
                )
                logger.info(
                    "Memory nudge triggered for thread %s (interval=%d)",
                    thread_id,
                    self.nudge_interval,
                )
            except RuntimeError:
                logger.debug("No running event loop available for memory review task")

        return None

    # ------------------------------------------------------------------
    # Background comparative review (Hermes-inspired)
    # ------------------------------------------------------------------

    async def _background_review(self, messages: list[Any], thread_id: str) -> None:
        """Compare existing memory against recent conversation and update.

        Uses a single LLM call to compare old memory vs new conversation content,
        producing structured add/replace/remove operations.
        """
        if self.updater is None or self.updater.model is None:
            return

        try:
            existing_memory = self._format_memory_context(self.storage.load())
            recent = filter_messages_for_memory(messages[-20:])
            if not recent:
                return

            conversation_text = "\n".join(
                f"[{getattr(m, 'type', 'unknown')}]: {_extract_message_text(m)[:300]}"
                for m in recent
            )

            review_prompt = _REVIEW_PROMPT.format(
                existing_memory=existing_memory or "(empty)",
                conversation=conversation_text,
            )

            from langchain_core.messages import HumanMessage as HM
            from langchain_core.messages import SystemMessage as SM

            result = await self.updater.model.ainvoke([
                SM(content="You are a memory review assistant. Output valid JSON only."),
                HM(content=review_prompt),
            ])

            import json
            content = result.content if isinstance(result.content, str) else str(result.content)
            # Extract JSON from possible markdown code block
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            ops = json.loads(content)
            if not isinstance(ops, list):
                ops = ops.get("operations", [])

            applied = 0
            for op in ops:
                action = op.get("action")
                target = op.get("target", "")
                value = op.get("content", op.get("value", ""))
                if not action or not target:
                    continue
                # Injection check on new values
                if value and _scan_for_injection(str(value)):
                    logger.warning("Injection detected in review result — skipping op: %s", target)
                    continue
                if action == "add" and value:
                    self.storage.add_fact(str(value), category="review")
                    applied += 1
                elif action == "replace" and value:
                    self.storage.update_preference(target, value)
                    applied += 1
                elif action == "remove":
                    # Remove matching facts
                    mem = self.storage.load()
                    mem["facts"] = [f for f in mem.get("facts", []) if target not in f.get("content", "")]
                    self.storage.save(mem)
                    applied += 1

            if applied:
                logger.info("Memory review applied %d operations for thread %s", applied, thread_id)
                # Unfreeze so next agent run picks up changes
                self._frozen_loaded = False
        except Exception:
            logger.debug("Background memory review failed", exc_info=True)


# ---------------------------------------------------------------------------
# Review prompt template
# ---------------------------------------------------------------------------

_REVIEW_PROMPT = """Compare the existing user memory with this recent conversation.
Identify information that should be added, updated, or removed.

## Existing Memory
{existing_memory}

## Recent Conversation
{conversation}

Return a JSON array of operations:
[
  {{"action": "add", "target": "facts", "content": "new fact to remember"}},
  {{"action": "replace", "target": "preference_key", "content": "new value"}},
  {{"action": "remove", "target": "outdated fact text"}}
]

Rules:
- Only include meaningful, non-trivial changes
- Do NOT add information already in memory
- Remove facts contradicted by the conversation
- Return [] if no changes needed
"""

