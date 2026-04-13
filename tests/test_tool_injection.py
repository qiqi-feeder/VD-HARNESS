"""Tests for harness tool injection into get_available_tools."""

from __future__ import annotations

from vdflow.config.models import Config, MiddlewareConfig
from vdflow.tools import get_available_tools


class TestHarnessToolInjection:
    def _tool_names(self, config: Config, **kwargs) -> set[str]:
        tools = get_available_tools(config, **kwargs)
        return {getattr(t, "name", getattr(t, "__name__", "")) for t in tools}

    def test_default_config_no_subagent(self):
        """By default (subagent_enabled=False), task tool is NOT injected."""
        names = self._tool_names(Config())
        assert "task" not in names

    def test_subagent_enabled_injects_task_tool(self):
        """When subagent_enabled=True, task tool IS injected."""
        names = self._tool_names(Config(), subagent_enabled=True)
        assert "task" in names

    def test_skill_manage_present_by_default(self):
        names = self._tool_names(Config())
        assert "skill_manage" in names

    def test_disable_skill_evolution_removes_skill_manage(self):
        config = Config(middleware=MiddlewareConfig(skill_evolution_enabled=False))
        names = self._tool_names(config)
        assert "skill_manage" not in names

    def test_search_always_available(self):
        # search_past_sessions has no feature gate — always available
        config = Config(middleware=MiddlewareConfig(
            skill_evolution_enabled=False,
        ))
        names = self._tool_names(config)
        assert "search_past_sessions" in names

    def test_builtin_tools_still_present(self):
        names = self._tool_names(Config())
        assert "web_search_tool" in names
        assert "bash_tool" in names
        assert "read_file_tool" in names
        assert "write_file_tool" in names
        assert "ask_clarification" in names

    def test_subagent_tools_exclude_task_when_disabled(self):
        """Subagent's own tool list (subagent_enabled=False) must not have task."""
        names = self._tool_names(Config(), subagent_enabled=False)
        assert "task" not in names
