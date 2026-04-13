"""Runtime context helpers shared between middleware and tools."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any


_THREAD_DATA: ContextVar[dict[str, str] | None] = ContextVar("vdflow_thread_data", default=None)


def set_thread_data(thread_data: dict[str, str] | None) -> None:
    """Store the current thread data for tool resolution."""

    _THREAD_DATA.set(thread_data)


def get_thread_data() -> dict[str, str] | None:
    """Return the current thread data if available."""

    return _THREAD_DATA.get()


def clear_thread_data() -> None:
    """Clear any active thread data."""

    _THREAD_DATA.set(None)
