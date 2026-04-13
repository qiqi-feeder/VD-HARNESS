"""Tests for lead prompt, skills, and built-in tools."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from vdflow.agent.prompt import build_system_prompt
from vdflow.config.models import Config
from vdflow.skills import SkillsLoader
from vdflow.tools import get_available_tools
from vdflow.tools.builtins import web_fetch_tool, write_file_tool


REPO_ROOT = Path(__file__).resolve().parents[1]


class ResearchAssistantTest(unittest.TestCase):
    def _patched_fetch_modules(self, *, document=None, tree=None):
        fake_readability = Mock()
        fake_readability.Document = Mock(return_value=document or Mock())

        fake_lxml_html = Mock()
        fake_lxml_html.fromstring = Mock(return_value=tree or Mock())
        fake_lxml = Mock()
        fake_lxml.html = fake_lxml_html

        return patch.dict(
            sys.modules,
            {
                "readability": fake_readability,
                "lxml": fake_lxml,
                "lxml.html": fake_lxml_html,
            },
        )

    def test_quick_research_skill_is_loaded(self) -> None:
        loader = SkillsLoader(str(REPO_ROOT / "skills"))
        skills = loader.load_skills()

        self.assertIn("quick_research", skills)
        self.assertIn("结构化综述报告", skills["quick_research"].description)

    def test_prompt_is_general_and_includes_skill_metadata(self) -> None:
        loader = SkillsLoader(str(REPO_ROOT / "skills"))
        skills = loader.get_enabled_skills()
        prompt = build_system_prompt(Config(), skills)
        today = datetime.now().astimezone().strftime("%Y-%m-%d")

        self.assertNotIn("你是一个科研助手", prompt)
        self.assertIn("通用助手", prompt)
        self.assertIn("<skill_system>", prompt)
        self.assertIn("quick_research", prompt)
        self.assertIn("<available_skills>", prompt)
        self.assertIn("<location>", prompt)
        self.assertIn("<current_time>", prompt)
        self.assertIn("<date>", prompt)
        self.assertIn(today, prompt)

    def test_get_available_tools_loads_config_tools_and_builtins(self) -> None:
        tool_names = [tool.name for tool in get_available_tools(Config())]
        self.assertIn("web_fetch_tool", tool_names)
        self.assertIn("ask_clarification", tool_names)

    def test_write_file_tool_writes_relative_paths_under_workspace(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tempdir:
            os.chdir(tempdir)
            try:
                result = write_file_tool.func("outputs/demo.md", "# report")
                target = Path(tempdir) / "workspace" / "outputs" / "demo.md"
                self.assertTrue(target.exists())
                self.assertEqual(target.read_text(encoding="utf-8"), "# report")
                self.assertIn(str(target), result)
            finally:
                os.chdir(original_cwd)

    def test_write_file_tool_blocks_paths_outside_workspace(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tempdir:
            os.chdir(tempdir)
            try:
                result = write_file_tool.func("../escape.md", "nope")
                self.assertIn("Error writing file", result)
                self.assertFalse((Path(tempdir) / "escape.md").exists())
            finally:
                os.chdir(original_cwd)

    def test_web_fetch_tool_extracts_main_text(self) -> None:
        fake_response = Mock()
        fake_response.content = b"<html><body>ignored</body></html>"
        fake_response.text = "<html><body>ignored</body></html>"
        fake_response.raise_for_status = Mock()

        fake_document = Mock()
        fake_document.summary.return_value = "<article><h1>Title</h1><p>Main content.</p></article>"

        fake_tree = Mock()
        fake_tree.text_content.return_value = "Title Main content."

        with self._patched_fetch_modules(document=fake_document, tree=fake_tree), patch(
            "requests.get", return_value=fake_response
        ):
            result = web_fetch_tool.func("https://example.com/paper")

        self.assertIn("Title Main content.", result)

    def test_web_fetch_tool_handles_timeout(self) -> None:
        import requests

        with self._patched_fetch_modules(), patch("requests.get", side_effect=requests.Timeout):
            result = web_fetch_tool.func("https://example.com/paper")

        self.assertIn("Timed out", result)

    def test_web_fetch_tool_handles_http_error(self) -> None:
        import requests

        response = Mock()
        response.status_code = 404
        error = requests.HTTPError(response=response)

        with self._patched_fetch_modules(), patch("requests.get", side_effect=error):
            result = web_fetch_tool.func("https://example.com/missing")

        self.assertIn("404", result)

    def test_web_fetch_tool_handles_empty_content(self) -> None:
        fake_response = Mock()
        fake_response.content = b""
        fake_response.text = ""
        fake_response.raise_for_status = Mock()

        fake_document = Mock()
        fake_document.summary.return_value = "<article></article>"

        fake_tree = Mock()
        fake_tree.text_content.return_value = "   "

        with self._patched_fetch_modules(document=fake_document, tree=fake_tree), patch(
            "requests.get", return_value=fake_response
        ):
            result = web_fetch_tool.func("https://example.com/empty")

        self.assertIn("No readable content", result)


if __name__ == "__main__":
    unittest.main()
