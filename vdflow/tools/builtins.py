"""Built-in tools for VD-Flow."""

from __future__ import annotations

import html
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Literal

from langchain.tools import tool

from vdflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from vdflow.runtime_context import get_thread_data

logger = logging.getLogger(__name__)


def _current_thread_id() -> str | None:
    """Get the current thread ID from runtime context."""
    thread_data = get_thread_data() or {}
    # Thread ID is stored in workspace_path as: .../threads/{tid}/user-data/workspace
    workspace = thread_data.get("workspace_path", "")
    if not workspace:
        return None
    parts = Path(workspace).parts
    # Find "threads" in path and return the next segment
    for i, part in enumerate(parts):
        if part == "threads" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _resolve_virtual_path(file_path: str) -> Path | None:
    """If file_path starts with /mnt/user-data/, resolve via Paths system."""
    if not file_path.startswith(VIRTUAL_PATH_PREFIX):
        return None
    thread_id = _current_thread_id()
    if not thread_id:
        return None
    try:
        return get_paths().resolve_virtual_path(thread_id, file_path)
    except ValueError:
        return None


def _workspace_root() -> Path:
    return (Path.cwd() / "workspace").resolve()


def _thread_dir(kind: str) -> Path | None:
    thread_data = get_thread_data() or {}
    raw = thread_data.get(f"{kind}_path")
    return Path(raw).resolve() if raw else None


def _resolve_default_read_candidates(raw_path: Path) -> list[Path]:
    candidates: list[Path] = []
    workspace_dir = _thread_dir("workspace")
    outputs_dir = _thread_dir("outputs")
    uploads_dir = _thread_dir("uploads")

    if raw_path.is_absolute():
        return [raw_path.resolve()]

    parts = raw_path.parts
    if len(parts) >= 2 and parts[0] == "workspace" and parts[1] == "outputs" and outputs_dir is not None:
        return [(outputs_dir / Path(*parts[2:])).resolve()]
    if parts and parts[0] in {"workspace", "outputs", "uploads"}:
        base_dir = _thread_dir(parts[0])
        if base_dir is not None:
            return [(base_dir / Path(*parts[1:])).resolve()]

    for base_dir in (workspace_dir, outputs_dir, uploads_dir):
        if base_dir is not None:
            candidates.append((base_dir / raw_path).resolve())
    candidates.append((Path.cwd() / raw_path).resolve())
    return candidates


def _resolve_read_path(file_path: str) -> Path:
    # Virtual path takes priority
    resolved = _resolve_virtual_path(file_path)
    if resolved is not None:
        return resolved
    raw_path = Path(file_path)
    for candidate in _resolve_default_read_candidates(raw_path):
        if candidate.exists():
            return candidate
    return _resolve_default_read_candidates(raw_path)[0]


def _resolve_write_path(file_path: str) -> Path:
    # Virtual path takes priority
    resolved = _resolve_virtual_path(file_path)
    if resolved is not None:
        return resolved
    raw_path = Path(file_path)
    workspace_dir = _thread_dir("workspace")
    outputs_dir = _thread_dir("outputs")
    uploads_dir = _thread_dir("uploads")

    if raw_path.is_absolute():
        resolved = raw_path.resolve()
        allowed_roots = [path for path in (workspace_dir, outputs_dir, uploads_dir) if path is not None]
        if allowed_roots:
            for root in allowed_roots:
                try:
                    resolved.relative_to(root)
                    return resolved
                except ValueError:
                    continue
            raise ValueError(f"Write path must stay inside current thread directories: {file_path}")
            raise ValueError(f"Write path must stay inside current thread directories: {file_path}")
        workspace_root = _workspace_root()
        try:
            resolved.relative_to(workspace_root)
        except ValueError as exc:
            raise ValueError(f"Write path must stay inside workspace/: {file_path}") from exc
        return resolved

    parts = raw_path.parts
    if len(parts) >= 2 and parts[0] == "workspace" and parts[1] == "outputs":
        base_dir = outputs_dir or (_workspace_root() / "outputs")
        resolved = (base_dir / Path(*parts[2:])).resolve()
        try:
            resolved.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Write path must stay inside outputs/: {file_path}") from exc
        return resolved
    if parts and parts[0] == "outputs":
        base_dir = outputs_dir or (_workspace_root() / "outputs")
        resolved = (base_dir / Path(*parts[1:])).resolve()
        try:
            resolved.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Write path must stay inside outputs/: {file_path}") from exc
        return resolved
    if parts and parts[0] == "uploads":
        base_dir = uploads_dir or _workspace_root()
        resolved = (base_dir / Path(*parts[1:])).resolve()
        try:
            resolved.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Write path must stay inside uploads/: {file_path}") from exc
        return resolved
    if parts and parts[0] == "workspace":
        base_dir = workspace_dir or _workspace_root()
        resolved = (base_dir / Path(*parts[1:])).resolve()
        try:
            resolved.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"Write path must stay inside workspace/: {file_path}") from exc
        return resolved

    base_dir = workspace_dir or _workspace_root()
    resolved = (base_dir / raw_path).resolve()
    try:
        resolved.relative_to(base_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Write path must stay inside workspace/: {file_path}") from exc
    return resolved


@tool
def web_search_tool(query: str, max_results: int = 5) -> str:
    """Search the web for up-to-date information."""

    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if tavily_key and not tavily_key.startswith("your-"):
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=tavily_key)
            response = client.search(query, max_results=max_results)
            results = []
            for result in response.get("results", []):
                results.append(
                    f"- **{result.get('title', 'No title')}**\n"
                    f"  URL: {result.get('url', '')}\n"
                    f"  {result.get('content', '')}\n"
                )
            return "\n".join(results) if results else "No results found."
        except ImportError:
            logger.warning("tavily-python not installed, falling back to DuckDuckGo")
        except Exception as exc:  # pragma: no cover - network behavior
            logger.error("Tavily search failed: %s", exc)

    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            search_results = list(ddgs.text(query, max_results=max_results))
        for result in search_results:
            results.append(
                f"- **{result['title']}**\n"
                f"  URL: {result['href']}\n"
                f"  {result['body']}\n"
            )
        return "\n".join(results) if results else "No results found."
    except ImportError:
        return (
            "搜索不可用：未安装搜索依赖。\n"
            "推荐方案：pip install tavily-python 并在 .env 配置 TAVILY_API_KEY\n"
            "备用方案：pip install duckduckgo-search"
        )
    except Exception as exc:  # pragma: no cover - network behavior
        logger.error("DuckDuckGo search failed: %s", exc)
        return f"搜索失败: {exc}"


@tool
def read_file_tool(file_path: str) -> str:
    """Read the contents of a file."""

    try:
        path = _resolve_read_path(file_path)
        if not path.exists():
            return f"Error: File not found: {file_path}"
        if not path.is_file():
            return f"Error: Not a file: {file_path}"

        content = path.read_text(encoding="utf-8")
        max_chars = 10000
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n... (truncated, file has {len(content)} characters)"
        return content
    except Exception as exc:
        logger.error("Failed to read file %s: %s", file_path, exc)
        return f"Error reading file: {exc}"


@tool
def web_fetch_tool(url: str) -> str:
    """Fetch and extract the main readable content of a web page."""

    try:
        import requests
        from lxml import html as lxml_html
        from readability import Document
    except ImportError:
        return "抓取不可用：缺少网页抓取依赖。\n请安装：pip install requests readability-lxml"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout:
        return f"Error: Timed out while fetching URL: {url}"
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        return f"Error: Failed to fetch URL ({status_code}): {url}"
    except Exception as exc:  # pragma: no cover - network behavior
        logger.error("Failed to fetch URL %s: %s", url, exc)
        return f"Error fetching URL: {exc}"

    try:
        document = Document(response.content)
        summary_html = document.summary()
        tree = lxml_html.fromstring(summary_html)
        text_content = tree.text_content()
    except Exception as exc:  # pragma: no cover - depends on upstream html
        logger.warning("Readability extraction failed for %s: %s", url, exc)
        text_content = response.text

    cleaned = html.unescape(text_content)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return f"Error: No readable content extracted from URL: {url}"

    max_chars = 12000
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + f"\n\n... (truncated, {len(text_content)} characters total)"
    return cleaned


@tool
def write_file_tool(file_path: str, content: str, mode: str = "write") -> str:
    """Write content to a file inside the active thread workspace."""

    try:
        path = _resolve_write_path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_mode = "a" if mode == "append" else "w"
        with open(path, write_mode, encoding="utf-8") as handle:
            handle.write(content)
        action = "appended to" if mode == "append" else "written to"
        return f"Successfully {action} {path} ({len(content)} characters)"
    except Exception as exc:
        logger.error("Failed to write file %s: %s", file_path, exc)
        return f"Error writing file: {exc}"


@tool
def bash_tool(command: str, timeout: int = 30) -> str:
    """Execute a bash command with basic safety restrictions."""

    dangerous_commands = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "dd if=/dev/zero",
        ":(){:|:&};:",
        "chmod -R 777 /",
        "chown -R",
        "> /dev/sda",
    ]
    for dangerous in dangerous_commands:
        if dangerous in command:
            return f"Error: Dangerous command blocked for safety: {dangerous}"

    thread_data = get_thread_data() or {}
    cwd = thread_data.get("workspace_path") or os.getcwd()
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output = []
        if result.stdout:
            output.append(result.stdout)
        if result.stderr:
            output.append(f"STDERR:\n{result.stderr}")
        output_str = "\n".join(output) if output else "Command executed successfully (no output)"
        max_chars = 5000
        if len(output_str) > max_chars:
            output_str = output_str[:max_chars] + f"\n\n... (truncated, {len(output_str)} characters total)"
        return output_str
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds"
    except Exception as exc:
        logger.error("Bash command failed: %s", exc)
        return f"Error executing command: {exc}"


@tool("ask_clarification", parse_docstring=True, return_direct=True)
def ask_clarification_tool(
    question: str,
    clarification_type: Literal[
        "missing_info",
        "ambiguous_requirement",
        "approach_choice",
        "risk_confirmation",
        "suggestion",
    ],
    context: str | None = None,
    options: list[str] | None = None,
) -> str:
    """Ask the user for clarification when more information is required.

    Args:
        question: The specific clarification question to ask.
        clarification_type: Why the clarification is needed.
        context: Optional background context for the question.
        options: Optional explicit choices to present to the user.
    """

    return "Clarification request processed by middleware"


BUILTIN_TOOLS = [
    web_search_tool,
    web_fetch_tool,
    read_file_tool,
    write_file_tool,
    bash_tool,
    ask_clarification_tool,
]


def get_builtin_tools() -> list:
    """Return built-in tool definitions."""

    return BUILTIN_TOOLS
