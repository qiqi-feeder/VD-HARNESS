"""LangGraph-backed thread index management."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

THREADS_NAMESPACE = ("threads",)
DEFAULT_THREAD_TITLE = "新对话"
STORE_FETCH_LIMIT = 500

ThreadStateLoader = Callable[[str], Awaitable[dict[str, Any]]]


def utc_now_timestamp() -> float:
    """Return the current UTC timestamp in seconds."""

    return datetime.now(timezone.utc).timestamp()


class ThreadManager:
    """Manage thread index records stored alongside LangGraph checkpoints."""

    def __init__(
        self,
        *,
        checkpointer: Any,
        store: Any,
        sqlite_path: str,
        max_threads: int = 100,
        search_index: Any | None = None,
    ):
        self.checkpointer = checkpointer
        self.store = store
        self.sqlite_path = Path(sqlite_path)
        self.max_threads = max_threads
        self._search_index = search_index

    async def create_thread(
        self,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Create a new thread index entry."""

        thread_id = uuid4().hex
        now = utc_now_timestamp()
        summary = {
            "thread_id": thread_id,
            "title": self._normalize_title(title),
            "status": "idle",
            "created_at": now,
            "updated_at": now,
            "preview": "",
            "message_count": 0,
            "model": model or "",
            "metadata": dict(metadata or {}),
        }
        await self._put_summary(summary)
        return self._public_summary(summary)

    async def get_thread(
        self,
        thread_id: str,
        state_loader: ThreadStateLoader,
    ) -> dict[str, Any]:
        """Load a thread summary and its visible messages."""

        summary = await self._get_summary(thread_id)
        if summary is None:
            summary = await self.ensure_thread_index(thread_id, state_loader)
            if summary is None:
                raise FileNotFoundError(f"Thread '{thread_id}' not found")

        state = await state_loader(thread_id)
        messages = list(state.get("messages", []))
        if state.get("exists"):
            refreshed = self._merge_summary_from_state(summary, state)
            if refreshed != summary:
                await self._put_summary(refreshed)
                summary = refreshed

        # Index messages for FTS5 cross-session search
        self._index_messages_for_search(thread_id, messages)

        return {
            "thread": self._public_summary(summary),
            "messages": messages,
        }

    async def list_threads(
        self,
        query: str | None = None,
        limit: int | None = None,
        state_loader: ThreadStateLoader | None = None,
    ) -> list[dict[str, Any]]:
        """List thread summaries."""

        if state_loader is not None:
            await self._hydrate_missing_threads(state_loader)

        summaries = await self._list_store_summaries(limit=max(limit or self.max_threads, STORE_FETCH_LIMIT))
        needle = (query or "").strip().lower()

        if needle:
            summaries = [
                item
                for item in summaries
                if needle in item.get("title", "").lower() or needle in item.get("preview", "").lower()
            ]

        summaries.sort(key=lambda item: float(item.get("updated_at") or 0), reverse=True)
        return [self._public_summary(item) for item in summaries[: limit or self.max_threads]]

    async def touch_thread(
        self,
        thread_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        preview: str | None = None,
        message_count: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing thread index entry."""

        summary = await self._get_summary(thread_id)
        if summary is None:
            raise FileNotFoundError(f"Thread '{thread_id}' not found")

        if status is not None:
            summary["status"] = status
        if model is not None:
            summary["model"] = model
        if metadata:
            summary["metadata"] = {**dict(summary.get("metadata") or {}), **metadata}
        if preview is not None:
            summary["preview"] = self._truncate(preview, 56)
        if message_count is not None:
            summary["message_count"] = max(0, int(message_count))
        if title:
            current_title = (summary.get("title") or "").strip()
            if not current_title or current_title == DEFAULT_THREAD_TITLE:
                summary["title"] = self._truncate(title, 28) or DEFAULT_THREAD_TITLE

        summary["updated_at"] = utc_now_timestamp()
        await self._put_summary(summary)
        return self._public_summary(summary)

    async def rename_thread(self, thread_id: str, title: str) -> dict[str, Any]:
        """Explicitly rename a thread."""

        summary = await self._get_summary(thread_id)
        if summary is None:
            raise FileNotFoundError(f"Thread '{thread_id}' not found")

        summary["title"] = self._normalize_title(title)
        summary["updated_at"] = utc_now_timestamp()
        await self._put_summary(summary)
        return self._public_summary(summary)

    async def ensure_thread_index(
        self,
        thread_id: str,
        state_loader: ThreadStateLoader,
    ) -> dict[str, Any] | None:
        """Backfill a missing thread index entry from checkpoint state."""

        existing = await self._get_summary(thread_id)
        if existing is not None:
            return existing

        state = await state_loader(thread_id)
        if not state.get("exists"):
            return None

        summary = self._merge_summary_from_state(
            {
                "thread_id": thread_id,
                "title": DEFAULT_THREAD_TITLE,
                "status": "idle",
                "created_at": state.get("updated_at") or utc_now_timestamp(),
                "updated_at": state.get("updated_at") or utc_now_timestamp(),
                "preview": "",
                "message_count": 0,
                "model": state.get("model", ""),
                "metadata": dict(state.get("metadata") or {}),
            },
            state,
        )
        await self._put_summary(summary)
        return summary

    async def delete_thread(self, thread_id: str) -> None:
        """Delete the store index and checkpoint history for a thread."""

        if hasattr(self.store, "adelete"):
            await self.store.adelete(THREADS_NAMESPACE, thread_id)
        if hasattr(self.checkpointer, "adelete_thread"):
            await self.checkpointer.adelete_thread(thread_id)
        elif hasattr(self.checkpointer, "delete_thread"):
            self.checkpointer.delete_thread(thread_id)

        # Clean up FTS5 search index
        if self._search_index is not None:
            try:
                self._search_index.delete_thread(thread_id)
            except Exception as exc:
                logger.debug("Failed to clean search index for thread %s: %s", thread_id, exc)

    def search_threads(self, query: str, *, max_results: int = 20) -> list[dict[str, Any]]:
        """Full-text search across all indexed thread messages via FTS5."""
        if self._search_index is None:
            logger.debug("Search index not configured")
            return []
        return self._search_index.search(query, max_results=max_results)

    def _index_messages_for_search(self, thread_id: str, messages: list[Any]) -> None:
        """Index thread messages into the FTS5 search index."""
        if self._search_index is None:
            return
        try:
            # Check if already indexed
            existing_count = self._search_index.count(thread_id)
            if existing_count >= len(messages):
                return  # Already indexed

            # Batch index all messages (idempotent — re-index if count changed)
            if existing_count > 0:
                self._search_index.delete_thread(thread_id)

            batch = []
            for msg in messages:
                content = ""
                role = ""
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                    role = msg.get("role", "")
                else:
                    content = getattr(msg, "content", "")
                    role = getattr(msg, "type", "")
                if isinstance(content, str) and content.strip():
                    batch.append({
                        "thread_id": thread_id,
                        "role": role,
                        "content": content,
                    })
            if batch:
                self._search_index.index_messages_batch(batch)
        except Exception as exc:
            logger.debug("Failed to index messages for search: %s", exc)

    async def _hydrate_missing_threads(self, state_loader: ThreadStateLoader) -> None:
        indexed_ids = {item["thread_id"] for item in await self._list_store_summaries(limit=STORE_FETCH_LIMIT)}
        checkpoint_ids = await self._list_checkpoint_thread_ids()

        missing_ids = [thread_id for thread_id in checkpoint_ids if thread_id not in indexed_ids]
        for thread_id in missing_ids:
            try:
                await self.ensure_thread_index(thread_id, state_loader)
            except Exception as exc:
                logger.warning("Failed to hydrate thread index for %s: %s", thread_id, exc)

    async def _list_store_summaries(self, *, limit: int) -> list[dict[str, Any]]:
        search_limit = max(1, limit)
        try:
            items = await self.store.asearch(THREADS_NAMESPACE, limit=search_limit)
        except TypeError:
            items = await self.store.asearch(THREADS_NAMESPACE)

        summaries: list[dict[str, Any]] = []
        for item in items:
            summary = self._coerce_summary(item)
            if summary is not None:
                summaries.append(summary)
        return summaries

    async def _get_summary(self, thread_id: str) -> dict[str, Any] | None:
        item = await self.store.aget(THREADS_NAMESPACE, thread_id)
        return self._coerce_summary(item)

    async def _put_summary(self, summary: dict[str, Any]) -> None:
        await self.store.aput(THREADS_NAMESPACE, summary["thread_id"], summary)

    async def _list_checkpoint_thread_ids(self) -> list[str]:
        try:
            import aiosqlite
        except ImportError:
            logger.warning("aiosqlite is not installed; checkpoint hydration is disabled")
            return []

        if not self.sqlite_path.parent.exists():
            return []

        query = "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id IS NOT NULL"
        try:
            async with aiosqlite.connect(self.sqlite_path) as connection:
                async with connection.execute(query) as cursor:
                    rows = await cursor.fetchall()
        except Exception as exc:
            logger.debug("Could not scan checkpoint table for thread IDs: %s", exc)
            return []

        return [str(row[0]) for row in rows if row and row[0]]

    def _merge_summary_from_state(
        self,
        summary: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        messages = list(state.get("messages", []))
        merged = dict(summary)

        if not (merged.get("title") or "").strip() or merged.get("title") == DEFAULT_THREAD_TITLE:
            merged["title"] = self._normalize_title(state.get("title") or self._derive_title(messages))

        merged["preview"] = self._derive_preview(messages)
        merged["message_count"] = len(messages)
        merged["updated_at"] = self._latest_message_timestamp(messages) or state.get("updated_at") or utc_now_timestamp()
        merged["created_at"] = merged.get("created_at") or merged["updated_at"]

        if state.get("model") and not merged.get("model"):
            merged["model"] = state["model"]

        metadata = dict(merged.get("metadata") or {})
        if state.get("metadata"):
            metadata.update(state["metadata"])
        merged["metadata"] = metadata
        return merged

    def _coerce_summary(self, item: Any) -> dict[str, Any] | None:
        if item is None:
            return None

        key = None
        value = item
        if hasattr(item, "key"):
            key = getattr(item, "key")
        elif isinstance(item, dict):
            key = item.get("key")

        if hasattr(item, "value"):
            value = getattr(item, "value")
        elif isinstance(item, dict) and "value" in item:
            value = item["value"]

        if not isinstance(value, dict):
            return None

        summary = dict(value)
        summary["thread_id"] = str(summary.get("thread_id") or key or "")
        if not summary["thread_id"]:
            return None

        summary["title"] = self._normalize_title(summary.get("title"))
        summary["status"] = str(summary.get("status") or "idle")
        summary["created_at"] = self._coerce_timestamp(summary.get("created_at")) or utc_now_timestamp()
        summary["updated_at"] = self._coerce_timestamp(summary.get("updated_at")) or summary["created_at"]
        summary["preview"] = self._truncate(str(summary.get("preview") or ""), 56)
        summary["message_count"] = max(0, int(summary.get("message_count") or 0))
        summary["model"] = str(summary.get("model") or "")
        summary["metadata"] = dict(summary.get("metadata") or {})
        return summary

    @staticmethod
    def _normalize_title(title: Any) -> str:
        text = ThreadManager._truncate(str(title or ""), 28)
        return text or DEFAULT_THREAD_TITLE

    @staticmethod
    def _derive_title(messages: list[dict[str, Any]]) -> str:
        first_user = next(
            (
                message.get("content", "")
                for message in messages
                if message.get("role") == "user" and message.get("content")
            ),
            "",
        )
        return ThreadManager._truncate(first_user, 28) or DEFAULT_THREAD_TITLE

    @staticmethod
    def _derive_preview(messages: list[dict[str, Any]]) -> str:
        latest_text = next(
            (
                message.get("content", "")
                for message in reversed(messages)
                if message.get("content")
            ),
            "",
        )
        return ThreadManager._truncate(latest_text, 56)

    @staticmethod
    def _latest_message_timestamp(messages: list[dict[str, Any]]) -> float | None:
        for message in reversed(messages):
            timestamp = ThreadManager._coerce_timestamp(message.get("created_at"))
            if timestamp is not None:
                return timestamp
        return None

    @staticmethod
    def _coerce_timestamp(value: Any) -> float | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                normalized = value.replace("Z", "+00:00")
                try:
                    return datetime.fromisoformat(normalized).timestamp()
                except ValueError:
                    return None
        return None

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        stripped = " ".join(text.strip().split())
        if len(stripped) <= limit:
            return stripped
        return stripped[: limit - 1] + "…"

    @staticmethod
    def _public_summary(summary: dict[str, Any]) -> dict[str, Any]:
        thread_id = summary["thread_id"]
        return {
            "id": thread_id,
            "thread_id": thread_id,
            "title": summary.get("title", DEFAULT_THREAD_TITLE),
            "status": summary.get("status", "idle"),
            "preview": summary.get("preview", ""),
            "updated_at": summary.get("updated_at"),
            "created_at": summary.get("created_at"),
            "model": summary.get("model", ""),
            "message_count": summary.get("message_count", 0),
            "metadata": dict(summary.get("metadata") or {}),
        }


__all__ = [
    "DEFAULT_THREAD_TITLE",
    "THREADS_NAMESPACE",
    "ThreadManager",
    "utc_now_timestamp",
]
