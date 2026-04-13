"""Tests for sqlite-backed memory storage."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vdflow.config.models import MemoryConfig
from vdflow.memory import MemoryStorage


class MemoryStorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.sqlite_path = self.base / "agent.db"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_load_returns_empty_sqlite_snapshot_by_default(self) -> None:
        storage = MemoryStorage(MemoryConfig(sqlite_path=str(self.sqlite_path)))
        snapshot = storage.load()

        self.assertEqual(snapshot["storageBackend"], "sqlite")
        self.assertEqual(snapshot["preferences"], {})
        self.assertEqual(snapshot["conversation_history"], [])
        self.assertEqual(snapshot["facts"], [])
        self.assertTrue(self.sqlite_path.exists())

    def test_updates_persist_in_sqlite(self) -> None:
        storage = MemoryStorage(MemoryConfig(sqlite_path=str(self.sqlite_path)))

        self.assertTrue(storage.update_preference("language", "Chinese"))
        self.assertTrue(storage.add_fact("User wants sqlite-backed memory", category="goal", confidence=0.9))
        self.assertTrue(storage.add_conversation("把 memory 迁进 sqlite", "thread-42"))

        reloaded = MemoryStorage(MemoryConfig(sqlite_path=str(self.sqlite_path)))
        snapshot = reloaded.load()

        self.assertEqual(snapshot["preferences"]["language"], "Chinese")
        self.assertEqual(snapshot["conversation_history"][0]["thread_id"], "thread-42")
        self.assertEqual(snapshot["facts"][0]["category"], "goal")


if __name__ == "__main__":
    unittest.main()
