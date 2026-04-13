"""Middleware to expose uploaded files to the model as structured context."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from vdflow.agent.middlewares._utils import _state_get
from vdflow.agent.state import ThreadState

THREAD_DATA_MARKER = "<thread_data>"


class FileUploadMiddleware(AgentMiddleware[ThreadState]):
    """Expose uploaded files to the model as structured context."""

    state_schema = ThreadState

    def before_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        uploaded_files = _state_get(state, "uploaded_files", [])
        messages = _state_get(state, "messages", [])
        if not uploaded_files:
            return None
        if any(
            getattr(msg, "type", "") == "system"
            and THREAD_DATA_MARKER not in str(getattr(msg, "content", ""))
            and "<uploaded_files>" in str(getattr(msg, "content", ""))
            for msg in messages
        ):
            return None
        file_lines = []
        for file_info in uploaded_files:
            filename = file_info.get("filename", "unknown")
            file_path = file_info.get("path") or filename
            file_lines.append(f"- {filename}: {file_path}")
        return {
            "messages": [
                SystemMessage(
                    content="<uploaded_files>\n" + "\n".join(file_lines) + "\n</uploaded_files>"
                )
            ]
        }
