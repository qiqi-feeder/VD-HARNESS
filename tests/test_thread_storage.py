"""Tests for LangGraph-backed thread index management."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from vdflow.threads import ThreadManager


class FakeStore:
    def __init__(self) -> None:
        self._data: dict[tuple[str, ...], dict[str, dict]] = {}

    async def aput(self, namespace: tuple[str, ...], key: str, value: dict) -> None:
        self._data.setdefault(namespace, {})[key] = dict(value)

    async def aget(self, namespace: tuple[str, ...], key: str):
        value = self._data.get(namespace, {}).get(key)
        if value is None:
            return None
        return SimpleNamespace(key=key, value=dict(value))

    async def asearch(self, namespace: tuple[str, ...], limit: int | None = None):
        items = [
            SimpleNamespace(key=key, value=dict(value))
            for key, value in self._data.get(namespace, {}).items()
        ]
        return items[:limit] if limit is not None else items

    async def adelete(self, namespace: tuple[str, ...], key: str) -> None:
        self._data.get(namespace, {}).pop(key, None)


class FakeCheckpointer:
    def __init__(self) -> None:
        self.deleted_threads: list[str] = []

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted_threads.append(thread_id)


class ThreadManagerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.store = FakeStore()
        self.checkpointer = FakeCheckpointer()
        self.manager = ThreadManager(
            checkpointer=self.checkpointer,
            store=self.store,
            sqlite_path=":memory:",
            max_threads=20,
        )

    async def test_create_thread_writes_store_index(self) -> None:
        thread = await self.manager.create_thread(model="demo-model")

        self.assertEqual(thread["model"], "demo-model")
        stored = await self.store.aget(("threads",), thread["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored.value["thread_id"], thread["id"])
        self.assertEqual(stored.value["message_count"], 0)

    async def test_touch_thread_updates_index_fields(self) -> None:
        thread = await self.manager.create_thread()

        updated = await self.manager.touch_thread(
            thread["id"],
            title="帮我总结一下最近这段对话",
            status="busy",
            preview="这是最后一条消息",
            message_count=3,
            metadata={"user_id": "u-1"},
        )

        self.assertEqual(updated["status"], "busy")
        self.assertEqual(updated["preview"], "这是最后一条消息")
        self.assertEqual(updated["message_count"], 3)
        self.assertEqual(updated["metadata"]["user_id"], "u-1")
        self.assertEqual(updated["title"], "帮我总结一下最近这段对话")

    async def test_get_thread_rehydrates_summary_from_state(self) -> None:
        thread = await self.manager.create_thread()

        async def state_loader(_: str) -> dict:
            return {
                "exists": True,
                "updated_at": 200.0,
                "messages": [
                    {
                        "role": "user",
                        "content": "帮我总结这段代码",
                        "created_at": 100.0,
                        "status": "completed",
                    },
                    {
                        "role": "assistant",
                        "content": "这是总结",
                        "created_at": 200.0,
                        "status": "completed",
                    },
                ],
            }

        payload = await self.manager.get_thread(thread["id"], state_loader)

        self.assertEqual(payload["thread"]["title"], "帮我总结这段代码")
        self.assertEqual(payload["thread"]["preview"], "这是总结")
        self.assertEqual(payload["thread"]["message_count"], 2)
        self.assertEqual(len(payload["messages"]), 2)

    async def test_list_threads_sorts_and_backfills_missing_indexes(self) -> None:
        first = await self.manager.create_thread(title="第一个")
        second = await self.manager.create_thread(title="第二个")
        await self.manager.touch_thread(first["id"], preview="较早消息", message_count=1)
        await self.manager.touch_thread(second["id"], preview="较新消息", message_count=2)

        missing_thread_id = "missing-thread"

        async def fake_checkpoint_ids() -> list[str]:
            return [missing_thread_id]

        self.manager._list_checkpoint_thread_ids = fake_checkpoint_ids  # type: ignore[method-assign]

        async def state_loader(thread_id: str) -> dict:
            if thread_id != missing_thread_id:
                return {"exists": False, "messages": []}
            return {
                "exists": True,
                "updated_at": 99_999_999_999.0,
                "messages": [
                    {
                        "role": "user",
                        "content": "第三个会话",
                        "created_at": 99_999_999_999.0,
                        "status": "completed",
                    }
                ],
            }

        threads = await self.manager.list_threads(state_loader=state_loader)

        self.assertEqual(threads[0]["id"], missing_thread_id)
        self.assertTrue(any(item["id"] == first["id"] for item in threads))
        self.assertTrue(any(item["id"] == second["id"] for item in threads))

    async def test_delete_thread_removes_store_and_checkpoints(self) -> None:
        thread = await self.manager.create_thread()

        await self.manager.delete_thread(thread["id"])

        self.assertIsNone(await self.store.aget(("threads",), thread["id"]))
        self.assertEqual(self.checkpointer.deleted_threads, [thread["id"]])

    async def test_rename_thread_updates_title(self) -> None:
        thread = await self.manager.create_thread(title="旧标题")

        updated = await self.manager.rename_thread(thread["id"], "新标题")

        self.assertEqual(updated["title"], "新标题")
        stored = await self.store.aget(("threads",), thread["id"])
        self.assertEqual(stored.value["title"], "新标题")


if __name__ == "__main__":
    unittest.main()
