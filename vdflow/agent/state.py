"""Agent state definitions for VD-Flow."""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field


class ThreadDataState(BaseModel):
    """Per-thread working directories."""

    workspace_path: str = ""
    uploads_path: str = ""
    outputs_path: str = ""


class PendingClarificationState(BaseModel):
    """A clarification request waiting for user input."""

    question: str = ""
    clarification_type: str = "missing_info"
    context: str | None = None
    options: list[str] = Field(default_factory=list)
    asked_at: str = ""


class ThreadState(BaseModel):
    """State for a conversation thread."""

    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    thread_id: str = ""
    title: str = ""
    uploaded_files: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    memory_context: str = ""
    active_skills: list[str] = Field(default_factory=list)
    thread_data: ThreadDataState | None = None
    pending_clarification: PendingClarificationState | None = None
    token_usage: dict[str, Any] | None = None
    todos: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


class MemoryState(BaseModel):
    """State for memory system."""

    preferences: dict[str, Any] = Field(default_factory=dict)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
    facts: list[dict[str, Any]] = Field(default_factory=list)
    last_updated: str = ""
