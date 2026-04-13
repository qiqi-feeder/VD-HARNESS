"""FTS5 cross-session search — full-text search across thread messages.

Uses SQLite FTS5 virtual tables for high-performance text search.
Creates the FTS index on first use and maintains it via triggers.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FTS_TABLE = "messages_fts"
_SOURCE_TABLE = "messages_index"

# Schema for the flat messages index used by FTS
_CREATE_INDEX_TABLE = """
CREATE TABLE IF NOT EXISTS {source} (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    created_at REAL DEFAULT 0
)
"""

_CREATE_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS {fts} USING fts5(
    content,
    thread_id UNINDEXED,
    role UNINDEXED,
    content={source},
    content_rowid=rowid,
    tokenize='unicode61'
)
"""

# Triggers to keep FTS in sync
_CREATE_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS {source}_ai AFTER INSERT ON {source} BEGIN
    INSERT INTO {fts}(rowid, content, thread_id, role)
    VALUES (new.rowid, new.content, new.thread_id, new.role);
END;

CREATE TRIGGER IF NOT EXISTS {source}_ad AFTER DELETE ON {source} BEGIN
    INSERT INTO {fts}({fts}, rowid, content, thread_id, role)
    VALUES ('delete', old.rowid, old.content, old.thread_id, old.role);
END;

CREATE TRIGGER IF NOT EXISTS {source}_au AFTER UPDATE ON {source} BEGIN
    INSERT INTO {fts}({fts}, rowid, content, thread_id, role)
    VALUES ('delete', old.rowid, old.content, old.thread_id, old.role);
    INSERT INTO {fts}(rowid, content, thread_id, role)
    VALUES (new.rowid, new.content, new.thread_id, new.role);
END;
"""


class SessionSearchIndex:
    """SQLite FTS5-based cross-session message search."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._initialized = False

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Create tables, FTS index, and triggers if needed."""
        if self._initialized:
            return
        conn.executescript(
            _CREATE_INDEX_TABLE.format(source=_SOURCE_TABLE)
        )
        conn.executescript(
            _CREATE_FTS_TABLE.format(fts=_FTS_TABLE, source=_SOURCE_TABLE)
        )
        conn.executescript(
            _CREATE_TRIGGERS.format(fts=_FTS_TABLE, source=_SOURCE_TABLE)
        )
        self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self._ensure_schema(conn)
        return conn

    def index_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        created_at: float = 0.0,
    ) -> None:
        """Add a message to the search index."""
        if not content.strip():
            return
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT INTO {_SOURCE_TABLE} (thread_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (thread_id, role, content, created_at),
            )
            conn.commit()
        finally:
            conn.close()

    def index_messages_batch(
        self,
        messages: list[dict[str, Any]],
    ) -> int:
        """Batch index multiple messages. Each dict needs: thread_id, role, content."""
        if not messages:
            return 0
        conn = self._connect()
        try:
            rows = [
                (m["thread_id"], m.get("role", ""), m.get("content", ""), m.get("created_at", 0.0))
                for m in messages
                if m.get("content", "").strip()
            ]
            conn.executemany(
                f"INSERT INTO {_SOURCE_TABLE} (thread_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    def search(
        self,
        query: str,
        *,
        max_results: int = 20,
        thread_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Full-text search across indexed messages.

        Args:
            query: Search query (supports FTS5 syntax: AND, OR, NOT, phrases).
            max_results: Maximum number of results.
            thread_id: Optional filter to search within a specific thread.

        Returns:
            List of matching messages with thread_id, role, content, and rank.
        """
        if not query.strip():
            return []

        conn = self._connect()
        try:
            if thread_id:
                sql = f"""
                    SELECT s.thread_id, s.role, s.content, s.created_at,
                           rank
                    FROM {_FTS_TABLE} f
                    JOIN {_SOURCE_TABLE} s ON f.rowid = s.rowid
                    WHERE {_FTS_TABLE} MATCH ?
                      AND s.thread_id = ?
                    ORDER BY rank
                    LIMIT ?
                """
                cursor = conn.execute(sql, (query, thread_id, max_results))
            else:
                sql = f"""
                    SELECT s.thread_id, s.role, s.content, s.created_at,
                           rank
                    FROM {_FTS_TABLE} f
                    JOIN {_SOURCE_TABLE} s ON f.rowid = s.rowid
                    WHERE {_FTS_TABLE} MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """
                cursor = conn.execute(sql, (query, max_results))

            results = []
            for row in cursor:
                results.append({
                    "thread_id": row["thread_id"],
                    "role": row["role"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "rank": row["rank"],
                })
            return results
        except sqlite3.OperationalError as exc:
            logger.warning("FTS5 search failed: %s", exc)
            return []
        finally:
            conn.close()

    def delete_thread(self, thread_id: str) -> int:
        """Remove all indexed messages for a thread."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                f"DELETE FROM {_SOURCE_TABLE} WHERE thread_id = ?",
                (thread_id,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def count(self, thread_id: str | None = None) -> int:
        """Count indexed messages."""
        conn = self._connect()
        try:
            if thread_id:
                cursor = conn.execute(
                    f"SELECT COUNT(*) FROM {_SOURCE_TABLE} WHERE thread_id = ?",
                    (thread_id,),
                )
            else:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {_SOURCE_TABLE}")
            return cursor.fetchone()[0]
        finally:
            conn.close()
