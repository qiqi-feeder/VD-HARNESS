"""Shared utilities for middleware modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.config import get_config
from langgraph.runtime import Runtime


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_thread_id(runtime: Runtime | None) -> str:
    context = getattr(runtime, "context", None) or {}
    thread_id = context.get("thread_id")
    if thread_id:
        return str(thread_id)
    config = get_config()
    return str(config.get("configurable", {}).get("thread_id", ""))


def _state_get(state: Any, key: str, default: Any = None) -> Any:
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)
