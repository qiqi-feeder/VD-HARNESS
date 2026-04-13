"""Project-level custom agent profiles.

Agents are product-level personas, not separate runtimes.  Each profile stores
durable authoring data and the FastAPI runtime injects it into the shared lead
agent at run time.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_AGENT_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class AgentProfile:
    """Serializable custom agent profile."""

    name: str
    description: str = ""
    model: str | None = None
    tool_groups: list[str] | None = None
    soul: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "tool_groups": list(self.tool_groups or []),
            "soul": self.soul,
        }


def validate_agent_name(name: str) -> str | None:
    """Return an error message when the agent name is invalid."""

    if not name:
        return "Agent name is required"
    if len(name) > 64:
        return "Agent name is too long; max 64 characters"
    if not _AGENT_NAME_RE.match(name):
        return "Agent name must be lowercase hyphen-case, e.g. research-copilot"
    return None


class AgentProfileStore:
    """File-backed store for custom agents."""

    def __init__(self, base_dir: str | Path = "agents") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _agent_dir(self, name: str) -> Path:
        error = validate_agent_name(name)
        if error:
            raise ValueError(error)
        target = (self.base_dir / name).resolve()
        try:
            target.relative_to(self.base_dir.resolve())
        except ValueError as exc:
            raise ValueError("Agent path traversal is not allowed") from exc
        return target

    def exists(self, name: str) -> bool:
        try:
            agent_dir = self._agent_dir(name)
        except ValueError:
            return False
        return (agent_dir / "config.yaml").exists()

    def list(self) -> list[AgentProfile]:
        profiles = []
        if not self.base_dir.exists():
            return profiles
        for child in sorted(self.base_dir.iterdir(), key=lambda item: item.name):
            if child.is_dir() and (child / "config.yaml").exists():
                try:
                    profiles.append(self.get(child.name))
                except (FileNotFoundError, ValueError):
                    continue
        return profiles

    def get(self, name: str) -> AgentProfile:
        agent_dir = self._agent_dir(name)
        config_path = agent_dir / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Agent '{name}' not found")
        document = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        soul_path = agent_dir / "SOUL.md"
        soul = soul_path.read_text(encoding="utf-8") if soul_path.exists() else ""
        return AgentProfile(
            name=str(document.get("name") or name),
            description=str(document.get("description") or ""),
            model=document.get("model") or None,
            tool_groups=list(document.get("tool_groups") or []),
            soul=soul,
        )

    def create(
        self,
        *,
        name: str,
        description: str = "",
        model: str | None = None,
        tool_groups: list[str] | None = None,
        soul: str = "",
    ) -> AgentProfile:
        agent_dir = self._agent_dir(name)
        if agent_dir.exists():
            raise FileExistsError(f"Agent '{name}' already exists")
        return self.update(
            name,
            description=description,
            model=model,
            tool_groups=tool_groups,
            soul=soul,
            create=True,
        )

    def update(
        self,
        name: str,
        *,
        description: str | None = None,
        model: str | None = None,
        tool_groups: list[str] | None = None,
        soul: str | None = None,
        create: bool = False,
    ) -> AgentProfile:
        agent_dir = self._agent_dir(name)
        if not create and not agent_dir.exists():
            raise FileNotFoundError(f"Agent '{name}' not found")

        current = None if create else self.get(name)
        next_profile = AgentProfile(
            name=name,
            description=description if description is not None else (current.description if current else ""),
            model=model if model is not None else (current.model if current else None),
            tool_groups=tool_groups if tool_groups is not None else (current.tool_groups if current else []),
            soul=soul if soul is not None else (current.soul if current else ""),
        )
        agent_dir.mkdir(parents=True, exist_ok=True)
        config_doc = {
            "name": next_profile.name,
            "description": next_profile.description,
            "model": next_profile.model,
            "tool_groups": list(next_profile.tool_groups or []),
        }
        (agent_dir / "config.yaml").write_text(
            yaml.safe_dump(config_doc, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        (agent_dir / "SOUL.md").write_text(next_profile.soul.rstrip() + "\n", encoding="utf-8")
        return next_profile

    def delete(self, name: str) -> None:
        agent_dir = self._agent_dir(name)
        if not agent_dir.exists():
            raise FileNotFoundError(f"Agent '{name}' not found")
        shutil.rmtree(agent_dir)
