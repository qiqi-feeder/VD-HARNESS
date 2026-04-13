"""Per-thread workspace/uploads/outputs directory middleware.

Uses the centralized Paths system for thread-isolated sandbox directories.
The model sees virtual paths like /mnt/user-data/workspace/, and this
middleware maps them to real host paths.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from vdflow.agent.middlewares._utils import _resolve_thread_id, _state_get
from vdflow.agent.state import ThreadDataState, ThreadState
from vdflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from vdflow.runtime_context import clear_thread_data, set_thread_data
from vdflow.skills import Skill

logger = logging.getLogger(__name__)


def _latest_human_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "human" and getattr(message, "content", ""):
            return str(message.content)
    return ""


def _match_skills(skills: list[Skill], user_text: str) -> list[str]:
    if not user_text:
        return []
    text = user_text.lower()
    matched: list[str] = []
    for skill in skills:
        haystacks = [
            skill.name.lower(),
            skill.description.lower(),
            str(skill.metadata.get("name", "")).lower(),
            str(skill.metadata.get("description", "")).lower(),
        ]
        if any(fragment and fragment in text for fragment in haystacks):
            matched.append(skill.name)
            continue

        if "research" in skill.name.lower() and any(token in text for token in ("调研", "综述", "研究", "资料")):
            matched.append(skill.name)
        elif "code" in skill.name.lower() and any(token in text for token in ("代码", "bug", "重构", "review", "debug")):
            matched.append(skill.name)
    return list(dict.fromkeys(matched))


def _virtual_artifacts(thread_id: str, thread_data: ThreadDataState | None) -> list[str]:
    """List artifacts as virtual paths for the model to reference."""
    if isinstance(thread_data, dict):
        outputs_path = thread_data.get("outputs_path", "")
    else:
        outputs_path = getattr(thread_data, "outputs_path", "")
    if not outputs_path:
        return []
    from pathlib import Path

    outputs_dir = Path(outputs_path)
    if not outputs_dir.exists():
        return []

    paths_obj = get_paths()
    return sorted(
        paths_obj.to_virtual_path(thread_id, p)
        for p in outputs_dir.rglob("*")
        if p.is_file()
    )


class ThreadDataMiddleware(AgentMiddleware[ThreadState]):
    """Provide per-thread workspace/uploads/outputs directories using Paths system."""

    state_schema = ThreadState

    def __init__(self, base_dir: str | None = None, skills: list[Skill] | None = None):
        # base_dir is kept for backward compat but we use get_paths()
        self.skills = skills or []

    def _thread_dirs(self, thread_id: str) -> ThreadDataState:
        paths = get_paths()
        paths.ensure_thread_dirs(thread_id)
        return ThreadDataState(
            workspace_path=str(paths.sandbox_work_dir(thread_id).resolve()),
            uploads_path=str(paths.sandbox_uploads_dir(thread_id).resolve()),
            outputs_path=str(paths.sandbox_outputs_dir(thread_id).resolve()),
        )

    def before_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        thread_id = _resolve_thread_id(runtime)
        thread_data = self._thread_dirs(thread_id)
        set_thread_data(thread_data.model_dump())
        active_skills = _match_skills(self.skills, _latest_human_text(_state_get(state, "messages", [])))
        return {
            "thread_id": thread_id,
            "thread_data": thread_data,
            "active_skills": active_skills,
            "artifacts": _virtual_artifacts(thread_id, thread_data),
        }

    def after_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        try:
            thread_id = _resolve_thread_id(runtime)
            thread_data = _state_get(state, "thread_data")
            return {"artifacts": _virtual_artifacts(thread_id, thread_data)}
        finally:
            clear_thread_data()
