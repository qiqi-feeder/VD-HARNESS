"""Session search tool — search past conversations via FTS5.

Allows the agent to search across all past sessions for relevant context.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Module-level search index reference (set during app init)
_search_index: Any = None


def set_search_index(index: Any) -> None:
    """Set the module-level search index reference."""
    global _search_index
    _search_index = index


@tool
def search_past_sessions(query: str, max_results: int = 10) -> str:
    """Search across all past conversation sessions for relevant information.

    Args:
        query: Search query. Supports FTS5 syntax (AND, OR, NOT, "exact phrases").
        max_results: Maximum number of results to return (default 10).
    """
    if _search_index is None:
        return "Session search is not available (index not initialized)."

    if not query.strip():
        return "Please provide a non-empty search query."

    results = _search_index.search(query, max_results=max_results)

    if not results:
        return f"No results found for: {query}"

    lines = [f"Found {len(results)} result(s) for '{query}':\n"]
    for i, result in enumerate(results, 1):
        thread_id = result["thread_id"][:8]
        role = result.get("role", "unknown")
        content = result["content"]
        # Truncate long content
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"[{i}] Thread {thread_id}… ({role}):")
        lines.append(f"    {content}")
        lines.append("")

    return "\n".join(lines)
