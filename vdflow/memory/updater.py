"""Memory update logic for VD-Flow"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from vdflow.memory.storage import MemoryStorage

logger = logging.getLogger(__name__)

# Memory extraction prompt
MEMORY_EXTRACTION_PROMPT = """You are a memory extraction assistant. Analyze the conversation and extract important information about the user.

Extract:
1. User preferences (e.g., preferred language, topics of interest, communication style)
2. Important facts (e.g., name, occupation, goals, constraints)
3. Key context (e.g., ongoing projects, recurring themes)

Conversation:
{conversation}

Return a JSON object with this structure:
{{
  "preferences": {{"key": "value"}},
  "facts": [
    {{"content": "fact content", "category": "preference/knowledge/context/behavior/goal", "confidence": 0.0-1.0}}
  ],
  "summary": "Brief conversation summary in one sentence"
}}

Only extract meaningful, non-trivial information. Return empty objects/lists if nothing significant is found.
"""


class MemoryUpdater:
    """Updates memory based on conversation"""

    def __init__(self, storage: MemoryStorage, model: BaseChatModel):
        """Initialize memory updater

        Args:
            storage: Memory storage instance
            model: LLM model for extraction
        """
        self.storage = storage
        self.model = model

    async def update_from_conversation(self, messages: list[Any], thread_id: str) -> bool:
        """Extract and update memory from a conversation

        Args:
            messages: List of conversation messages
            thread_id: Thread identifier

        Returns:
            True if successful
        """
        try:
            # Format conversation
            conversation_text = self._format_conversation(messages)

            # Extract memory updates using LLM
            extraction_messages = [
                SystemMessage(content=MEMORY_EXTRACTION_PROMPT.format(conversation=conversation_text))
            ]

            response = await self.model.ainvoke(extraction_messages)

            # Parse LLM response
            import json

            try:
                # Try to extract JSON from response
                content = response.content
                # Find JSON object in response
                if "{" in content and "}" in content:
                    start = content.index("{")
                    end = content.rindex("}") + 1
                    json_str = content[start:end]
                    updates = json.loads(json_str)
                else:
                    logger.warning("No JSON found in LLM response")
                    return False
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse LLM response: {e}")
                return False

            # Apply updates
            return self._apply_updates(updates, thread_id)

        except Exception as e:
            logger.error(f"Memory update failed: {e}")
            return False

    def _format_conversation(self, messages: list[Any]) -> str:
        """Format messages into conversation text

        Args:
            messages: List of messages

        Returns:
            Formatted conversation string
        """
        lines = []
        for msg in messages:
            role = msg.__class__.__name__.replace("Message", "").upper()
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def _apply_updates(self, updates: dict, thread_id: str) -> bool:
        """Apply extracted updates to memory

        Args:
            updates: Extracted updates dictionary
            thread_id: Thread identifier

        Returns:
            True if successful
        """
        success = True

        # Update preferences
        if updates.get("preferences"):
            for key, value in updates["preferences"].items():
                if not self.storage.update_preference(key, value):
                    success = False

        # Add facts
        if updates.get("facts"):
            for fact in updates["facts"]:
                content = fact.get("content", "")
                category = fact.get("category", "knowledge")
                confidence = fact.get("confidence", 0.8)

                if content:
                    if not self.storage.add_fact(content, category, confidence):
                        success = False

        # Add conversation summary
        if updates.get("summary"):
            if not self.storage.add_conversation(updates["summary"], thread_id):
                success = False

        return success
