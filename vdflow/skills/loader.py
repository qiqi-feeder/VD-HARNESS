"""Skills loader for VD-Flow"""

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class Skill:
    """Represents a skill"""

    def __init__(
        self,
        name: str,
        description: str,
        content: str,
        path: str = "",
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize a skill

        Args:
            name: Skill name
            description: Skill description
            content: Skill content/instructions
            path: Absolute or relative path to the skill file
            enabled: Whether skill is enabled
            metadata: Additional metadata
        """
        self.name = name
        self.description = description
        self.content = content
        self.path = path
        self.enabled = enabled
        self.metadata = metadata or {}


def parse_skill_file(file_path: Path) -> Skill | None:
    """Parse a skill file (Markdown with YAML frontmatter)

    Args:
        file_path: Path to skill file

    Returns:
        Parsed Skill object or None if invalid
    """
    try:
        with open(file_path) as f:
            content = f.read()

        # Parse frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1].strip()
                skill_content = parts[2].strip()

                # Parse YAML frontmatter
                metadata = yaml.safe_load(frontmatter_text) or {}

                return Skill(
                    name=metadata.get("name", file_path.parent.name),
                    description=metadata.get("description", ""),
                    content=skill_content,
                    path=str(file_path),
                    enabled=metadata.get("enabled", True),
                    metadata=metadata,
                )

        # No frontmatter, treat entire content as skill
        logger.warning(f"Skill file {file_path} has no frontmatter, using defaults")
        return Skill(
            name=file_path.parent.name,
            description="",
            content=content,
            path=str(file_path),
            enabled=True,
        )

    except Exception as e:
        logger.error(f"Failed to parse skill file {file_path}: {e}")
        return None


class SkillsLoader:
    """Loads and manages skills from directories"""

    def __init__(self, skills_path: str, enabled_by_default: bool = True):
        """Initialize skills loader

        Args:
            skills_path: Base path to skills directory
            enabled_by_default: Whether to enable skills by default
        """
        self.skills_path = Path(skills_path)
        self.enabled_by_default = enabled_by_default
        self._skills: dict[str, Skill] = {}
        self._loaded = False

    def load_skills(self) -> dict[str, Skill]:
        """Load all skills from skills directory

        Returns:
            Dictionary of skill name to Skill object
        """
        if self._loaded:
            return self._skills

        # Check if skills directory exists
        if not self.skills_path.exists():
            logger.info(f"Skills directory not found: {self.skills_path}")
            self._loaded = True
            return self._skills

        # Find all SKILL.md files
        skill_files = list(self.skills_path.rglob("SKILL.md"))
        logger.info(f"Found {len(skill_files)} skill files")

        for skill_file in skill_files:
            skill = parse_skill_file(skill_file)
            if skill:
                # Apply default enabled state
                if "enabled" not in skill.metadata:
                    skill.enabled = self.enabled_by_default

                self._skills[skill.name] = skill
                logger.info(f"Loaded skill: {skill.name} (enabled={skill.enabled})")

        self._loaded = True
        return self._skills

    def get_skill(self, name: str) -> Skill | None:
        """Get a specific skill by name

        Args:
            name: Skill name

        Returns:
            Skill object or None if not found
        """
        if not self._loaded:
            self.load_skills()

        return self._skills.get(name)

    def get_enabled_skills(self) -> list[Skill]:
        """Get all enabled skills

        Returns:
            List of enabled Skill objects
        """
        if not self._loaded:
            self.load_skills()

        return [s for s in self._skills.values() if s.enabled]

    def reload(self) -> dict[str, Skill]:
        """Reload skills from disk

        Returns:
            Dictionary of skill name to Skill object
        """
        self._skills.clear()
        self._loaded = False
        return self.load_skills()

    def set_skill_enabled(self, name: str, enabled: bool) -> Skill:
        """Persist skill enabled state to disk and reload cache."""

        skill = self.get_skill(name)
        if skill is None:
            raise FileNotFoundError(f"Skill '{name}' not found")

        skill_path = Path(skill.path)
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill file not found: {skill_path}")

        content = skill_path.read_text(encoding="utf-8")
        metadata = dict(skill.metadata or {})
        metadata["name"] = metadata.get("name", skill.name)
        metadata["description"] = metadata.get("description", skill.description)
        metadata["enabled"] = enabled

        if content.startswith("---"):
            parts = content.split("---", 2)
            skill_body = parts[2].lstrip() if len(parts) >= 3 else skill.content
        else:
            skill_body = skill.content or content

        frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
        next_content = f"---\n{frontmatter}\n---\n\n{skill_body.rstrip()}\n"

        skill_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(dir=str(skill_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(next_content)
            Path(temp_path).replace(skill_path)
        finally:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                logger.debug("Failed to cleanup temp skill file: %s", temp_path, exc_info=True)

        return self.reload()[name]


def format_skills_for_prompt(skills: list[Skill]) -> str:
    """Format skills for injection into agent prompt

    Args:
        skills: List of skills to format

    Returns:
        Formatted skills string
    """
    if not skills:
        return ""

    skill_items = []
    for skill in skills:
        skill_items.append(
            "    <skill>\n"
            f"        <name>{skill.name}</name>\n"
            f"        <description>{skill.description}</description>\n"
            f"        <location>{skill.path}</location>\n"
            "    </skill>"
        )
    return "<available_skills>\n" + "\n".join(skill_items) + "\n</available_skills>"
