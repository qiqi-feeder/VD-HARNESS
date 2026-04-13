"""Integration-style checks for chat stream SSE events."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest


FASTAPI_READY = (
    importlib.util.find_spec("fastapi") is not None
    and importlib.util.find_spec("langchain") is not None
    and importlib.util.find_spec("langchain_core") is not None
    and importlib.util.find_spec("langgraph") is not None
)


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


class FakeRawMessage(SimpleNamespace):
    pass


class FakeCheckpointer:
    def __init__(self, agent: "FakeAgent") -> None:
        self.agent = agent
        self.deleted_threads: list[str] = []

    async def aget_tuple(self, config):
        thread_id = config["configurable"]["thread_id"]
        if self.agent.state_by_thread.get(thread_id):
            return SimpleNamespace(config=config)
        return None

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted_threads.append(thread_id)
        self.agent.state_by_thread.pop(thread_id, None)


class FakeAgent:
    def __init__(self, extract_chunk_parts) -> None:
        self.extract_chunk_parts = extract_chunk_parts
        self.events: list[dict[str, object]] = []
        self.calls: list[dict[str, object]] = []
        self.state_by_thread: dict[str, list[FakeRawMessage]] = {}
        self.invoke_response = "同步回答"

    def set_events(self, events: list[dict[str, object]]) -> None:
        self.events = events

    async def astream_events(self, payload, *, config=None, version=None):
        thread_id = config["configurable"]["thread_id"]
        messages = payload["messages"]
        self.calls.append({"messages": messages, "config": config, "version": version})
        self._append_user_messages(thread_id, messages)

        answer_parts: list[str] = []
        thinking_parts: list[str] = []
        for event in self.events:
            if event.get("event") == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                answer_text, thinking_text = self.extract_chunk_parts(chunk)
                if answer_text:
                    answer_parts.append(answer_text)
                if thinking_text:
                    thinking_parts.append(thinking_text)
            yield event

        if answer_parts or thinking_parts:
            self._append_assistant_message(thread_id, "".join(answer_parts), "".join(thinking_parts))

    async def ainvoke(self, payload, *, config=None):
        thread_id = config["configurable"]["thread_id"]
        messages = payload["messages"]
        self.calls.append({"messages": messages, "config": config, "version": None})
        self._append_user_messages(thread_id, messages)
        self._append_assistant_message(thread_id, self.invoke_response, "")
        return {"messages": self.state_by_thread[thread_id]}

    async def aget_state(self, config):
        thread_id = config["configurable"]["thread_id"]
        return SimpleNamespace(values={"messages": list(self.state_by_thread.get(thread_id, []))})

    def _append_user_messages(self, thread_id: str, messages) -> None:
        thread_messages = list(self.state_by_thread.get(thread_id, []))
        for message in messages:
            thread_messages.append(
                FakeRawMessage(
                    id="",
                    type="human",
                    content=message.content,
                    additional_kwargs=dict(getattr(message, "additional_kwargs", {}) or {}),
                    response_metadata={},
                )
            )
        self.state_by_thread[thread_id] = thread_messages

    def _append_assistant_message(self, thread_id: str, content: str, thinking: str) -> None:
        thread_messages = list(self.state_by_thread.get(thread_id, []))
        response_metadata = {"thinking": thinking} if thinking else {}
        thread_messages.append(
            FakeRawMessage(
                id="",
                type="ai",
                content=content,
                additional_kwargs={},
                response_metadata=response_metadata,
                tool_calls=[],
            )
        )
        self.state_by_thread[thread_id] = thread_messages


@unittest.skipUnless(FASTAPI_READY, "fastapi/langchain/langchain_core/langgraph not installed")
class ChatStreamApiTest(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        import vdflow.web.app as web_app_module
        from vdflow.config.models import Config, ModelConfig
        from vdflow.agent_profiles import AgentProfileStore
        from vdflow.config.paths import reset_paths
        from vdflow.threads import ThreadManager

        self.web_app_module = web_app_module
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_config = web_app_module.config
        self.original_thread_manager = web_app_module.thread_manager
        self.original_thread_checkpointer = web_app_module.thread_checkpointer
        self.original_thread_store = web_app_module.thread_store
        self.original_agent = web_app_module.agent
        self.original_create_agent = web_app_module.create_agent
        self.original_get_available_tools = web_app_module.get_available_tools
        self.original_agent_profile_store = web_app_module.agent_profile_store
        self.original_run_records = dict(web_app_module.run_records)
        self.original_run_tasks = dict(web_app_module.run_tasks)

        self.fake_agent = FakeAgent(web_app_module.extract_chunk_parts)
        self.fake_store = FakeStore()
        self.fake_checkpointer = FakeCheckpointer(self.fake_agent)

        web_app_module.config = Config(
            models=[
                ModelConfig(
                    name="test-model",
                    display_name="Test Model",
                    use="langchain_openai:ChatOpenAI",
                    model="dummy-model",
                    api_key="sk-test",
                )
            ],
            threads={
                "backend": "sqlite",
                "sqlite_path": f"{self.tempdir.name}/agent.db",
                "max_threads": 20,
            },
        )
        web_app_module.thread_store = self.fake_store
        web_app_module.thread_checkpointer = self.fake_checkpointer
        web_app_module.thread_manager = ThreadManager(
            checkpointer=self.fake_checkpointer,
            store=self.fake_store,
            sqlite_path=f"{self.tempdir.name}/agent.db",
            max_threads=20,
        )
        web_app_module.agent = self.fake_agent
        web_app_module.create_agent = lambda *args, **kwargs: self.fake_agent
        web_app_module.get_available_tools = lambda *args, **kwargs: []
        web_app_module.agent_profile_store = AgentProfileStore(Path(self.tempdir.name) / "agents")
        web_app_module.run_records.clear()
        web_app_module.run_tasks.clear()
        reset_paths(Path(self.tempdir.name) / ".vd-flow")
        self.client = TestClient(web_app_module.app)

    def tearDown(self) -> None:
        self.web_app_module.config = self.original_config
        self.web_app_module.thread_manager = self.original_thread_manager
        self.web_app_module.thread_checkpointer = self.original_thread_checkpointer
        self.web_app_module.thread_store = self.original_thread_store
        self.web_app_module.agent = self.original_agent
        self.web_app_module.create_agent = self.original_create_agent
        self.web_app_module.get_available_tools = self.original_get_available_tools
        self.web_app_module.agent_profile_store = self.original_agent_profile_store
        self.web_app_module.run_records.clear()
        self.web_app_module.run_records.update(self.original_run_records)
        self.web_app_module.run_tasks.clear()
        self.web_app_module.run_tasks.update(self.original_run_tasks)
        from vdflow.config.paths import reset_paths
        reset_paths()
        self.tempdir.cleanup()

    def test_stream_emits_phase_fallback_events(self) -> None:
        self.fake_agent.set_events(
            [
                {"event": "on_tool_start", "name": "web_search"},
                {"event": "on_tool_end", "name": "web_search"},
                {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": make_chunk("这是最终答案。")},
                },
            ]
        )

        response = self.client.post(
            "/api/chat/stream",
            json={"message": "帮我查一下", "model": "test-model", "think_level": "normal"},
        )

        events = parse_sse_events(response.text)
        event_types = [event["type"] for event in events]

        self.assertIn("meta", event_types)
        self.assertIn("tool_start", event_types)
        self.assertIn("tool_end", event_types)
        self.assertIn("phase", event_types)
        self.assertIn("content", event_types)
        self.assertEqual(event_types[-1], "done")
        self.assertTrue(any(event.get("stage") == "before_answer" for event in events if event["type"] == "phase"))

        meta = next(event for event in events if event["type"] == "meta")
        thread_payload = self.client.get(f"/api/threads/{meta['thread_id']}").json()
        self.assertEqual(len(thread_payload["messages"]), 2)
        self.assertEqual(thread_payload["messages"][0]["role"], "user")
        self.assertEqual(thread_payload["messages"][1]["role"], "assistant")

    def test_stream_emits_native_thinking_events(self) -> None:
        self.fake_agent.set_events(
            [
                {
                    "event": "on_chat_model_stream",
                    "data": {
                        "chunk": make_chunk(
                            [
                                {"type": "reasoning", "text": "先分析证据。"},
                            ]
                        )
                    },
                },
                {
                    "event": "on_chat_model_stream",
                    "data": {
                        "chunk": make_chunk(
                            [
                                {"type": "text", "text": "这是最终回答。"},
                            ]
                        )
                    },
                },
            ]
        )

        response = self.client.post(
            "/api/chat/stream",
            json={"message": "总结一下", "model": "test-model", "think_level": "thorough"},
        )

        events = parse_sse_events(response.text)
        event_types = [event["type"] for event in events]

        self.assertIn("thinking_start", event_types)
        self.assertIn("thinking_delta", event_types)
        self.assertIn("thinking_end", event_types)
        self.assertIn("content", event_types)

        meta = next(event for event in events if event["type"] == "meta")
        thread_payload = self.client.get(f"/api/threads/{meta['thread_id']}").json()
        self.assertEqual(thread_payload["messages"][1]["thinking"], "先分析证据。")

    def test_stream_uses_thread_id_instead_of_manual_history_replay(self) -> None:
        thread = run_async(self.web_app_module.thread_manager.create_thread())
        self.fake_agent.state_by_thread[thread["id"]] = [
            FakeRawMessage(
                id="",
                type="human",
                content="第一轮问题",
                additional_kwargs={"created_at": "2025-01-01T00:00:00Z"},
                response_metadata={},
            ),
            FakeRawMessage(
                id="",
                type="ai",
                content="第一轮回答",
                additional_kwargs={},
                response_metadata={},
                tool_calls=[],
            ),
        ]
        self.fake_agent.set_events(
            [
                {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": make_chunk("第二轮回答")},
                }
            ]
        )

        self.client.post(
            "/api/chat/stream",
            json={
                "thread_id": thread["id"],
                "message": "第二轮问题",
                "model": "test-model",
                "think_level": "normal",
            },
        )

        sent_messages = self.fake_agent.calls[0]["messages"]
        self.assertEqual(len(sent_messages), 1)
        self.assertEqual(sent_messages[0].content, "第二轮问题")
        self.assertEqual(self.fake_agent.calls[0]["config"]["configurable"]["thread_id"], thread["id"])
        self.assertEqual(self.fake_agent.calls[0]["config"]["recursion_limit"], 500)

    def test_patch_thread_renames_title(self) -> None:
        thread = self.client.post("/api/threads", json={"title": "旧标题"}).json()["thread"]

        response = self.client.patch(
            f"/api/threads/{thread['id']}",
            json={"title": "新标题"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["thread"]["title"], "新标题")

        thread_payload = self.client.get(f"/api/threads/{thread['id']}").json()
        self.assertEqual(thread_payload["thread"]["title"], "新标题")

    def test_workspace_entry_redirects_to_next_app(self) -> None:
        root_response = self.client.get("/", follow_redirects=False)
        self.assertEqual(root_response.status_code, 307)
        self.assertEqual(root_response.headers["location"], "http://testserver:3000/workspace")

        workspace_response = self.client.get("/workspace/chats/new", follow_redirects=False)
        self.assertEqual(workspace_response.status_code, 307)
        self.assertEqual(workspace_response.headers["location"], "http://testserver:3000/workspace/chats/new")

    def test_agents_uploads_and_langgraph_stream_gateway(self) -> None:
        agent_response = self.client.post(
            "/api/agents",
            json={
                "name": "research-copilot",
                "description": "Research helper",
                "soul": "# Research Copilot\n\nBe precise.",
            },
        )
        self.assertEqual(agent_response.status_code, 200)
        self.assertTrue((Path(self.tempdir.name) / "agents" / "research-copilot" / "SOUL.md").exists())

        thread_response = self.client.post(
            "/api/langgraph/threads",
            json={"metadata": {"title": "SDK thread", "agent_name": "research-copilot"}},
        )
        self.assertEqual(thread_response.status_code, 200)
        thread_id = thread_response.json()["thread_id"]

        upload_response = self.client.post(
            f"/api/threads/{thread_id}/uploads",
            files=[("files", ("note.txt", b"hello", "text/plain"))],
        )
        self.assertEqual(upload_response.status_code, 200)
        uploaded = upload_response.json()["files"][0]
        self.assertEqual(uploaded["virtual_path"], "/mnt/user-data/uploads/note.txt")

        self.fake_agent.set_events(
            [
                {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": make_chunk("SDK answer")},
                }
            ]
        )
        stream_response = self.client.post(
            f"/api/langgraph/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": "research-copilot",
                "input": {
                    "messages": [
                        {
                            "type": "human",
                            "content": [{"type": "text", "text": "Use the upload"}],
                            "additional_kwargs": {"files": [uploaded]},
                        }
                    ]
                },
                "context": {"agent_name": "research-copilot", "model": "test-model", "mode": "pro"},
            },
        )
        self.assertEqual(stream_response.status_code, 200)
        self.assertIn("Content-Location", stream_response.headers)
        self.assertIn("event: metadata", stream_response.text)
        self.assertIn("event: events", stream_response.text)
        self.assertIn("event: values", stream_response.text)
        self.assertEqual(self.fake_agent.calls[0]["messages"][0].additional_kwargs["files"][0]["filename"], "note.txt")


def make_chunk(content):
    return SimpleNamespace(content=content, additional_kwargs={}, response_metadata={})


def parse_sse_events(payload: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in payload.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def run_async(awaitable):
    return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
