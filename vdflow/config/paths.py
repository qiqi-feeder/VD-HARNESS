"""Centralized path configuration for VD-Flow thread isolation.

Directory layout:
    {base_dir}/
    └── threads/
        └── {thread_id}/
            └── user-data/
                ├── workspace/   ← /mnt/user-data/workspace/
                ├── uploads/     ← /mnt/user-data/uploads/
                └── outputs/     ← /mnt/user-data/outputs/

Models see virtual paths under /mnt/user-data/ which this module maps
to real host paths under {base_dir}/threads/{thread_id}/user-data/.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

# Virtual prefix seen by the model / tools
VIRTUAL_PATH_PREFIX = "/mnt/user-data"

_SAFE_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _validate_thread_id(thread_id: str) -> str:
    if not _SAFE_THREAD_ID_RE.match(thread_id):
        raise ValueError(
            f"Invalid thread_id {thread_id!r}: "
            "only alphanumeric characters, hyphens, and underscores are allowed."
        )
    return thread_id


class Paths:
    """Map virtual sandbox paths to real host filesystem paths."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is not None:
            self._base_dir = Path(base_dir).resolve()
        else:
            self._base_dir = None

    @property
    def base_dir(self) -> Path:
        if self._base_dir is not None:
            return self._base_dir
        # Default: project-root-level .vd-flow/
        return Path(__file__).resolve().parents[2] / ".vd-flow"

    # ── Thread-scoped paths ──────────────────────────────────────────

    def thread_dir(self, thread_id: str) -> Path:
        return self.base_dir / "threads" / _validate_thread_id(thread_id)

    def sandbox_user_data_dir(self, thread_id: str) -> Path:
        return self.thread_dir(thread_id) / "user-data"

    def sandbox_work_dir(self, thread_id: str) -> Path:
        """Host path for workspace. Virtual: /mnt/user-data/workspace/"""
        return self.sandbox_user_data_dir(thread_id) / "workspace"

    def sandbox_uploads_dir(self, thread_id: str) -> Path:
        """Host path for uploads. Virtual: /mnt/user-data/uploads/"""
        return self.sandbox_user_data_dir(thread_id) / "uploads"

    def sandbox_outputs_dir(self, thread_id: str) -> Path:
        """Host path for outputs. Virtual: /mnt/user-data/outputs/"""
        return self.sandbox_user_data_dir(thread_id) / "outputs"

    # ── Directory lifecycle ──────────────────────────────────────────

    def ensure_thread_dirs(self, thread_id: str) -> None:
        """Create all standard sandbox directories for a thread."""
        for d in [
            self.sandbox_work_dir(thread_id),
            self.sandbox_uploads_dir(thread_id),
            self.sandbox_outputs_dir(thread_id),
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def delete_thread_dir(self, thread_id: str) -> None:
        """Delete all persisted data for a thread (idempotent)."""
        td = self.thread_dir(thread_id)
        if td.exists():
            shutil.rmtree(td)

    # ── Virtual → real path resolution ───────────────────────────────

    def resolve_virtual_path(self, thread_id: str, virtual_path: str) -> Path:
        """Resolve a virtual sandbox path to the actual host path.

        Args:
            thread_id: The thread ID.
            virtual_path: Path as seen inside the sandbox, e.g.
                          "/mnt/user-data/outputs/report.pptx"
                          or "mnt/user-data/outputs/report.pptx"

        Returns:
            Resolved absolute host path.

        Raises:
            ValueError: If path doesn't start with the expected prefix
                        or a path-traversal attempt is detected.
        """
        stripped = virtual_path.lstrip("/")
        prefix = VIRTUAL_PATH_PREFIX.lstrip("/")

        if stripped != prefix and not stripped.startswith(prefix + "/"):
            raise ValueError(f"Path must start with /{prefix}")

        relative = stripped[len(prefix):].lstrip("/")
        base = self.sandbox_user_data_dir(thread_id).resolve()
        actual = (base / relative).resolve()

        # Path traversal guard
        try:
            actual.relative_to(base)
        except ValueError:
            raise ValueError("Access denied: path traversal detected")

        return actual

    def to_virtual_path(self, thread_id: str, host_path: str | Path) -> str:
        """Convert a host path back to its virtual sandbox path.

        Returns the virtual path string or the original path if it's not
        within this thread's sandbox.
        """
        host_path = Path(host_path).resolve()
        base = self.sandbox_user_data_dir(thread_id).resolve()
        try:
            relative = host_path.relative_to(base)
            return f"{VIRTUAL_PATH_PREFIX}/{relative}"
        except ValueError:
            return str(host_path)


# ── Singleton ────────────────────────────────────────────────────────

_paths: Paths | None = None


def get_paths() -> Paths:
    """Return the global Paths singleton."""
    global _paths
    if _paths is None:
        _paths = Paths()
    return _paths


def reset_paths(base_dir: str | Path | None = None) -> Paths:
    """Reset singleton (for testing)."""
    global _paths
    _paths = Paths(base_dir)
    return _paths
