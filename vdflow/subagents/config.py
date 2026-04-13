"""Subagent configuration and data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SubagentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class SubagentConfig:
    """Configuration for a subagent."""

    name: str
    description: str = ""
    system_prompt: str = ""
    tools: list[str] | None = None  # None = inherit from parent
    disallowed_tools: list[str] = field(default_factory=lambda: ["task"])
    model: str | None = None  # None = inherit from parent
    max_turns: int = 25
    timeout_seconds: int = 120
    share_sandbox: bool = True


@dataclass
class SubagentResult:
    """Result of a subagent execution."""

    status: SubagentStatus
    output: str = ""
    error: str = ""
    turns_used: int = 0
    elapsed_seconds: float = 0.0
    trace_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    ai_messages: list[str] = field(default_factory=list)

