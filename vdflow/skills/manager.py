"""Skill manager — CRUD operations on custom skills with atomic writes and history.

Ported from DeerFlow's skills/manager.py with adaptations for VD-Flow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MAX_SKILL_NAME_LENGTH = 64
_MAX_CONTENT_SIZE = 50_000  # bytes


def validate_skill_name(name: str) -> str | None:
    """Return None if valid, else an error message."""
    if not name:
        return "skill name is empty"
    if len(name) > _MAX_SKILL_NAME_LENGTH:
        return f"skill name too long (max {_MAX_SKILL_NAME_LENGTH})"
    if not _SKILL_NAME_RE.match(name):
        return "skill name must be hyphen-case (e.g. 'my-skill')"
    return None


def validate_skill_content(content: str) -> str | None:
    """Return None if valid, else an error message."""
    if not content.strip():
        return "skill content is empty"
    if len(content.encode()) > _MAX_CONTENT_SIZE:
        return f"skill content too large (max {_MAX_CONTENT_SIZE} bytes)"
    # Must have YAML frontmatter
    if not content.startswith("---"):
        return "skill content must start with YAML frontmatter (---)"
    parts = content.split("---", 2)
    if len(parts) < 3:
        return "invalid YAML frontmatter (missing closing ---)"
    try:
        meta = yaml.safe_load(parts[1])
        if not isinstance(meta, dict):
            return "YAML frontmatter must be a mapping"
        if "name" not in meta and "description" not in meta:
            return "YAML frontmatter must contain 'name' or 'description'"
    except yaml.YAMLError as e:
        return f"invalid YAML frontmatter: {e}"
    return None


def ensure_safe_path(base_dir: Path, filename: str) -> Path | None:
    """Return resolved path if safe, None if path traversal detected."""
    target = (base_dir / filename).resolve()
    if not str(target).startswith(str(base_dir.resolve())):
        return None
    return target


# ---------------------------------------------------------------------------
# Per-skill locks
# ---------------------------------------------------------------------------

_skill_locks: dict[str, asyncio.Lock] = {}


def _get_lock(name: str) -> asyncio.Lock:
    if name not in _skill_locks:
        _skill_locks[name] = asyncio.Lock()
    return _skill_locks[name]


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via tempfile + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# History tracking
# ---------------------------------------------------------------------------


def append_history(history_dir: Path, record: dict[str, Any]) -> None:
    """Append a change record to the skill's history file."""
    history_dir.mkdir(parents=True, exist_ok=True)
    history_file = history_dir / "history.jsonl"
    record["timestamp"] = datetime.now(UTC).isoformat()
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# SkillManager
# ---------------------------------------------------------------------------


class SkillManager:
    """Manages custom skill CRUD with validation, atomic writes, and history."""

    def __init__(self, custom_skills_path: str = "skills/custom"):
        self.custom_dir = Path(custom_skills_path)
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        self._on_change_callbacks: list[Any] = []

    def on_change(self, callback: Any) -> None:
        """Register a callback to be called when skills change."""
        self._on_change_callbacks.append(callback)

    def _notify_change(self) -> None:
        for cb in self._on_change_callbacks:
            try:
                cb()
            except Exception:
                logger.debug("Skill change callback failed", exc_info=True)

    def skill_exists(self, name: str) -> bool:
        return (self.custom_dir / name / "SKILL.md").exists()

    def get_skill_dir(self, name: str) -> Path:
        return self.custom_dir / name

    def get_skill_file(self, name: str) -> Path:
        return self.custom_dir / name / "SKILL.md"

    def list_skills(self) -> list[str]:
        """List all custom skill names."""
        if not self.custom_dir.exists():
            return []
        return [
            d.name for d in sorted(self.custom_dir.iterdir())
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

    async def create(self, name: str, content: str, *, scanner: Any = None) -> dict[str, Any]:
        """Create a new custom skill. Returns {"ok": True} or {"error": "..."}."""
        err = validate_skill_name(name)
        if err:
            return {"error": err}
        err = validate_skill_content(content)
        if err:
            return {"error": err}
        if self.skill_exists(name):
            return {"error": f"skill '{name}' already exists — use 'edit' to modify"}

        # Security scan
        if scanner is not None:
            scan = await scanner.scan(content, executable=False)
            if scan.get("verdict") == "block":
                return {"error": f"security scan blocked: {scan.get('reason', 'unknown')}"}

        async with _get_lock(name):
            skill_file = self.get_skill_file(name)
            atomic_write(skill_file, content)
            append_history(
                self.get_skill_dir(name),
                {"action": "create", "content_length": len(content)},
            )

        self._notify_change()
        return {"ok": True, "name": name}

    async def edit(self, name: str, content: str, *, scanner: Any = None) -> dict[str, Any]:
        """Replace entire skill content."""
        err = validate_skill_name(name)
        if err:
            return {"error": err}
        err = validate_skill_content(content)
        if err:
            return {"error": err}
        if not self.skill_exists(name):
            return {"error": f"skill '{name}' does not exist"}

        if scanner is not None:
            scan = await scanner.scan(content, executable=False)
            if scan.get("verdict") == "block":
                return {"error": f"security scan blocked: {scan.get('reason', 'unknown')}"}

        async with _get_lock(name):
            prev = self.get_skill_file(name).read_text(encoding="utf-8")
            atomic_write(self.get_skill_file(name), content)
            append_history(
                self.get_skill_dir(name),
                {"action": "edit", "prev_length": len(prev), "new_length": len(content)},
            )

        self._notify_change()
        return {"ok": True, "name": name}

    async def delete(self, name: str) -> dict[str, Any]:
        """Delete a custom skill directory."""
        err = validate_skill_name(name)
        if err:
            return {"error": err}
        if not self.skill_exists(name):
            return {"error": f"skill '{name}' does not exist"}

        async with _get_lock(name):
            import shutil
            skill_dir = self.get_skill_dir(name)
            shutil.rmtree(skill_dir, ignore_errors=True)

        self._notify_change()
        return {"ok": True, "name": name}

    async def write_support_file(
        self, name: str, filename: str, content: str, *, scanner: Any = None
    ) -> dict[str, Any]:
        """Write a support file (script, config, etc.) inside a skill directory."""
        err = validate_skill_name(name)
        if err:
            return {"error": err}
        if not self.skill_exists(name):
            return {"error": f"skill '{name}' does not exist"}

        skill_dir = self.get_skill_dir(name)
        target = ensure_safe_path(skill_dir, filename)
        if target is None:
            return {"error": "path traversal detected"}

        executable = filename.endswith((".sh", ".py", ".bash"))
        if scanner is not None:
            scan = await scanner.scan(content, executable=executable)
            if scan.get("verdict") == "block":
                return {"error": f"security scan blocked: {scan.get('reason', 'unknown')}"}

        async with _get_lock(name):
            atomic_write(target, content)
            append_history(
                skill_dir,
                {"action": "write_file", "filename": filename, "size": len(content)},
            )

        return {"ok": True, "name": name, "filename": filename}
