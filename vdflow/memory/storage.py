"""SQLite-backed memory storage for VD-Flow."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vdflow.config.models import MemoryConfig

logger = logging.getLogger(__name__)


class MemoryStorage:
    """SQLite-backed memory storage."""

    def __init__(self, config: MemoryConfig, sqlite_path: str | None = None):
        self.config = config
        self.sqlite_path = Path(sqlite_path or config.sqlite_path)
        self.storage_path = self.sqlite_path
        self._ensure_schema()

    def _utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _create_empty_memory(self) -> dict[str, Any]:
        return {
            "version": "1.0",
            "storageBackend": "sqlite",
            "lastUpdated": self._utc_now_iso(),
            "preferences": {},
            "conversation_history": [],
            "facts": [],
        }

    def _connect(self) -> sqlite3.Connection:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_preferences (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_facts (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.commit()

    def _get_meta(self, connection: sqlite3.Connection, key: str) -> str | None:
        row = connection.execute("SELECT value FROM memory_meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def _set_meta(self, connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            """
            INSERT INTO memory_meta(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def _touch_last_updated(self, connection: sqlite3.Connection) -> str:
        timestamp = self._utc_now_iso()
        self._set_meta(connection, "lastUpdated", timestamp)
        self._set_meta(connection, "version", "1.0")
        return timestamp

    def load(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            preferences_rows = connection.execute(
                "SELECT key, value_json FROM memory_preferences ORDER BY key"
            ).fetchall()
            conversation_rows = connection.execute(
                """
                SELECT summary, thread_id, timestamp
                FROM memory_conversations
                ORDER BY id ASC
                """
            ).fetchall()
            fact_rows = connection.execute(
                """
                SELECT id, content, category, confidence, created_at
                FROM memory_facts
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
            last_updated = self._get_meta(connection, "lastUpdated") or self._utc_now_iso()
            version = self._get_meta(connection, "version") or "1.0"

        return {
            "version": version,
            "storageBackend": "sqlite",
            "lastUpdated": last_updated,
            "preferences": {
                str(row["key"]): json.loads(str(row["value_json"]))
                for row in preferences_rows
            },
            "conversation_history": [
                {
                    "summary": str(row["summary"]),
                    "thread_id": str(row["thread_id"]),
                    "timestamp": str(row["timestamp"]),
                }
                for row in conversation_rows
            ],
            "facts": [
                {
                    "id": str(row["id"]),
                    "content": str(row["content"]),
                    "category": str(row["category"]),
                    "confidence": float(row["confidence"]),
                    "createdAt": str(row["created_at"]),
                }
                for row in fact_rows
            ],
        }

    def save(self, memory_data: dict[str, Any]) -> bool:
        snapshot = {
            **self._create_empty_memory(),
            **dict(memory_data or {}),
        }
        preferences = dict(snapshot.get("preferences") or {})
        conversations = list(snapshot.get("conversation_history") or [])
        facts = list(snapshot.get("facts") or [])

        deduped_facts: list[dict[str, Any]] = []
        seen_fact_contents: set[str] = set()
        for index, fact in enumerate(facts, start=1):
            content = str(fact.get("content", "")).strip()
            if not content or content in seen_fact_contents:
                continue
            seen_fact_contents.add(content)
            deduped_facts.append(
                {
                    "id": str(fact.get("id") or f"fact_{index}"),
                    "content": content,
                    "category": str(fact.get("category") or "knowledge"),
                    "confidence": float(fact.get("confidence", 1.0)),
                    "createdAt": str(fact.get("createdAt") or self._utc_now_iso()),
                }
            )

        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN")
                connection.execute("DELETE FROM memory_preferences")
                connection.execute("DELETE FROM memory_conversations")
                connection.execute("DELETE FROM memory_facts")

                for key, value in preferences.items():
                    connection.execute(
                        "INSERT INTO memory_preferences(key, value_json) VALUES (?, ?)",
                        (str(key), json.dumps(value, ensure_ascii=False)),
                    )

                for item in conversations:
                    connection.execute(
                        """
                        INSERT INTO memory_conversations(summary, thread_id, timestamp)
                        VALUES (?, ?, ?)
                        """,
                        (
                            str(item.get("summary", "")),
                            str(item.get("thread_id", "")),
                            str(item.get("timestamp") or self._utc_now_iso()),
                        ),
                    )

                for fact in deduped_facts:
                    connection.execute(
                        """
                        INSERT INTO memory_facts(id, content, category, confidence, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            fact["id"],
                            fact["content"],
                            fact["category"],
                            fact["confidence"],
                            fact["createdAt"],
                        ),
                    )

                self._touch_last_updated(connection)
                connection.commit()
            logger.info("Memory saved successfully to sqlite")
            return True
        except Exception as exc:
            logger.error("Failed to save memory: %s", exc)
            return False

    def update_preference(self, key: str, value: Any) -> bool:
        try:
            with closing(self._connect()) as connection:
                connection.execute(
                    """
                    INSERT INTO memory_preferences(key, value_json)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
                    """,
                    (key, json.dumps(value, ensure_ascii=False)),
                )
                self._touch_last_updated(connection)
                connection.commit()
            return True
        except Exception as exc:
            logger.error("Failed to update preference %s: %s", key, exc)
            return False

    def add_conversation(self, summary: str, thread_id: str) -> bool:
        try:
            with closing(self._connect()) as connection:
                connection.execute(
                    """
                    INSERT INTO memory_conversations(summary, thread_id, timestamp)
                    VALUES (?, ?, ?)
                    """,
                    (summary, thread_id, self._utc_now_iso()),
                )
                connection.execute(
                    """
                    DELETE FROM memory_conversations
                    WHERE id NOT IN (
                        SELECT id FROM memory_conversations
                        ORDER BY id DESC
                        LIMIT 10
                    )
                    """
                )
                self._touch_last_updated(connection)
                connection.commit()
            return True
        except Exception as exc:
            logger.error("Failed to add conversation summary: %s", exc)
            return False

    def add_fact(self, content: str, category: str = "knowledge", confidence: float = 1.0) -> bool:
        try:
            with closing(self._connect()) as connection:
                existing = connection.execute(
                    "SELECT 1 FROM memory_facts WHERE content = ?",
                    (content,),
                ).fetchone()
                if existing:
                    return True

                next_id = connection.execute("SELECT COUNT(*) FROM memory_facts").fetchone()[0] + 1
                connection.execute(
                    """
                    INSERT INTO memory_facts(id, content, category, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (f"fact_{next_id}", content, category, confidence, self._utc_now_iso()),
                )

                keep_rows = connection.execute(
                    """
                    SELECT id
                    FROM memory_facts
                    ORDER BY confidence DESC, created_at ASC
                    LIMIT ?
                    """,
                    (self.config.max_facts,),
                ).fetchall()
                keep_ids = [str(row["id"]) for row in keep_rows]
                if keep_ids:
                    placeholders = ", ".join("?" for _ in keep_ids)
                    connection.execute(
                        f"DELETE FROM memory_facts WHERE id NOT IN ({placeholders})",
                        keep_ids,
                    )

                self._touch_last_updated(connection)
                connection.commit()
            return True
        except Exception as exc:
            logger.error("Failed to add fact: %s", exc)
            return False

    def get_relevant_facts(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_words = set(query.lower().split())
        if not query_words:
            return []

        with closing(self._connect()) as connection:
            fact_rows = connection.execute(
                """
                SELECT id, content, category, confidence, created_at
                FROM memory_facts
                ORDER BY confidence DESC, created_at ASC
                """
            ).fetchall()

        scored_facts: list[tuple[int, dict[str, Any]]] = []
        for row in fact_rows:
            content = str(row["content"])
            score = len(query_words & set(content.lower().split()))
            if score <= 0:
                continue
            scored_facts.append(
                (
                    score,
                    {
                        "id": str(row["id"]),
                        "content": content,
                        "category": str(row["category"]),
                        "confidence": float(row["confidence"]),
                        "createdAt": str(row["created_at"]),
                    },
                )
            )

        scored_facts.sort(key=lambda item: item[0], reverse=True)
        return [fact for _, fact in scored_facts[:limit]]
