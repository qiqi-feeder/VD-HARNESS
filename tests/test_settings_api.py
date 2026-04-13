"""API tests for memory import/export, skills toggles, and tools config updates."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml


FASTAPI_READY = (
    importlib.util.find_spec("fastapi") is not None
    and importlib.util.find_spec("langchain") is not None
    and importlib.util.find_spec("langchain_core") is not None
    and importlib.util.find_spec("langgraph") is not None
)


class DummyAgent:
    async def aget_state(self, config):
        return type("Snapshot", (), {"values": {"messages": []}})()


@unittest.skipUnless(FASTAPI_READY, "fastapi/langchain/langchain_core/langgraph not installed")
class SettingsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        import vdflow.web.app as web_app_module
        from vdflow.config import Config
        from vdflow.memory import MemoryStorage
        from vdflow.skills import SkillsLoader

        self.web_app_module = web_app_module
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.config_path = self.base / "config.yaml"
        self.skills_dir = self.base / "skills"
        self.skill_path = self.skills_dir / "demo-skill" / "SKILL.md"
        self.skill_path.parent.mkdir(parents=True, exist_ok=True)
        self.skill_path.write_text(
            "---\n"
            "name: demo-skill\n"
            "description: demo\n"
            "enabled: true\n"
            "---\n\n"
            "# Demo Skill\n",
            encoding="utf-8",
        )
        self.mcp_server_script = self.base / "fake_mcp_server.py"
        self.mcp_server_script.write_text(
            "import json, sys\n"
            "for line in sys.stdin:\n"
            "    payload = json.loads(line)\n"
            "    method = payload.get('method')\n"
            "    if method == 'initialize':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': payload['id'], 'result': {'protocolVersion': '2025-06-18', 'capabilities': {}}}), flush=True)\n"
            "    elif method == 'notifications/initialized':\n"
            "        continue\n"
            "    elif method == 'tools/list':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': payload['id'], 'result': {'tools': [{'name': 'echo', 'description': 'Echo text', 'inputSchema': {'type': 'object', 'properties': {'message': {'type': 'string'}}}}]}}), flush=True)\n"
            "    elif method == 'tools/call':\n"
            "        args = payload.get('params', {}).get('arguments', {})\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': payload['id'], 'result': {'content': [{'type': 'text', 'text': json.dumps(args)}]}}), flush=True)\n",
            encoding="utf-8",
        )

        self.config_doc = {
            "models": [
                {
                    "name": "test-model",
                    "display_name": "Test Model",
                    "use": "langchain_openai:ChatOpenAI",
                    "model": "dummy-model",
                    "api_key": "sk-test",
                }
            ],
            "memory": {
                "enabled": True,
                "sqlite_path": str(self.base / "agent.db"),
            },
            "skills": {
                "path": str(self.skills_dir),
                "enabled_by_default": True,
            },
            "tool_groups": [
                {"name": "web", "enabled": True},
                {"name": "file", "enabled": True},
                {"name": "bash", "enabled": True},
            ],
            "tools": [
                {"name": "web_search", "group": "web", "use": "vdflow.tools.builtins:web_search_tool"},
                {"name": "bash", "group": "bash", "use": "vdflow.tools.builtins:bash_tool"},
            ],
            "runtime": {
                "allow_host_bash": True,
            },
            "mcp": {
                "enabled": True,
                "servers": [],
            },
            "threads": {
                "backend": "sqlite",
                "sqlite_path": str(self.base / "agent.db"),
                "max_threads": 20,
            },
        }
        self.config_path.write_text(yaml.safe_dump(self.config_doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

        self.original_config = web_app_module.config
        self.original_memory_storage = web_app_module.memory_storage
        self.original_skills_loader = web_app_module.skills_loader
        self.original_agent = web_app_module.agent
        self.original_config_path = web_app_module.CONFIG_PATH

        web_app_module.CONFIG_PATH = self.config_path
        web_app_module.config = Config.from_yaml(str(self.config_path))
        web_app_module.memory_storage = MemoryStorage(
            web_app_module.config.memory,
            sqlite_path=web_app_module.config.threads.sqlite_path,
        )
        web_app_module.skills_loader = SkillsLoader(web_app_module.config.skills.path, True)
        web_app_module.skills_loader.load_skills()
        web_app_module.agent = DummyAgent()

        self.client = TestClient(web_app_module.app)

    def tearDown(self) -> None:
        self.web_app_module.config = self.original_config
        self.web_app_module.memory_storage = self.original_memory_storage
        self.web_app_module.skills_loader = self.original_skills_loader
        self.web_app_module.agent = self.original_agent
        self.web_app_module.CONFIG_PATH = self.original_config_path
        self.tempdir.cleanup()

    def test_memory_import_and_export_roundtrip(self) -> None:
        payload = {
            "memory": {
                "preferences": {"language": "Chinese"},
                "conversation_history": [{"summary": "summary", "thread_id": "thread-1"}],
                "facts": [{"content": "User prefers Chinese", "category": "preference", "confidence": 0.9}],
            },
            "mode": "replace",
        }

        response = self.client.post("/api/memory/import", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["counts"]["facts"], 1)

        export_response = self.client.get("/api/memory/export")
        self.assertEqual(export_response.status_code, 200)
        exported = export_response.json()
        self.assertEqual(exported["preferences"]["language"], "Chinese")
        self.assertEqual(exported["facts"][0]["content"], "User prefers Chinese")

    def test_patch_skill_updates_frontmatter_and_api_state(self) -> None:
        response = self.client.patch("/api/skills/demo-skill", json={"enabled": False})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["skill"]["enabled"])

        skill_file = self.skill_path.read_text(encoding="utf-8")
        self.assertIn("enabled: false", skill_file)

        list_response = self.client.get("/api/skills")
        self.assertEqual(list_response.status_code, 200)
        skill = next(item for item in list_response.json()["skills"] if item["name"] == "demo-skill")
        self.assertFalse(skill["enabled"])

    def test_patch_tools_config_persists_to_yaml_and_runtime(self) -> None:
        response = self.client.patch(
            "/api/tools/config",
            json={
                "tool_groups": [{"name": "web", "enabled": False}],
                "allow_host_bash": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        web_group = next(item for item in payload["tool_groups"] if item["name"] == "web")
        self.assertFalse(web_group["enabled"])
        self.assertFalse(payload["runtime"]["allow_host_bash"])

        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        self.assertFalse(raw["runtime"]["allow_host_bash"])
        persisted_web = next(item for item in raw["tool_groups"] if item["name"] == "web")
        self.assertFalse(persisted_web["enabled"])

    def test_mcp_server_crud_discover_and_runtime_merge(self) -> None:
        response = self.client.post(
            "/api/mcp/servers",
            json={
                "name": "local-echo",
                "transport": "stdio",
                "command": "python",
                "args": [str(self.mcp_server_script)],
                "enabled": True,
            },
        )
        self.assertEqual(response.status_code, 200)

        discover_response = self.client.post("/api/mcp/servers/local-echo/discover")
        self.assertEqual(discover_response.status_code, 200)
        self.assertEqual(discover_response.json()["tools"][0]["name"], "echo")

        tools = self.web_app_module.asyncio.run(
            self.web_app_module._build_runtime_tools(  # type: ignore[attr-defined]
                self.web_app_module.config,
                selected_model_name="test-model",
                subagent_enabled=False,
            )
        )
        mcp_tool = next(tool for tool in tools if tool.name == "mcp_local-echo_echo")
        tool_result = self.web_app_module.asyncio.run(mcp_tool.ainvoke({"message": "hello"}))
        self.assertIn("hello", tool_result)

        patch_response = self.client.patch(
            "/api/mcp/servers/local-echo",
            json={
                "name": "local-echo",
                "transport": "stdio",
                "command": "python",
                "args": [str(self.mcp_server_script)],
                "enabled": False,
            },
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertFalse(patch_response.json()["server"]["enabled"])

        delete_response = self.client.delete("/api/mcp/servers/local-echo")
        self.assertEqual(delete_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
