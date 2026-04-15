"""FastAPI web application for VD-Flow."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
import shutil
import zipfile
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncGenerator
from urllib.parse import quote
from uuid import uuid4

import yaml
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from langgraph.errors import GraphRecursionError

from vdflow.config.paths import get_paths
from pydantic import BaseModel, Field

from vdflow.agent import create_agent
from vdflow.agent_profiles import AgentProfileStore, validate_agent_name
from vdflow.config import Config
from vdflow.memory import MemoryStorage
from vdflow.mcp.cache import load_mcp_tools
from vdflow.mcp.client import MCPClient, MCPServerConfig as RuntimeMCPServerConfig
from vdflow.skills import SkillsLoader
from vdflow.threads import ThreadManager
from vdflow.tools import get_available_tools
from vdflow.web.streaming import (
    build_model_runtime_options,
    build_phase_message,
    extract_chunk_parts,
    normalize_think_level,
    resolve_mode_and_effort,
    strip_leaked_memory_json,
)

logger = logging.getLogger(__name__)
CONFIG_PATH = Path("config.yaml")
DEFAULT_WORKSPACE_FRONTEND_PORT = 3000

# Global state
config: Config | None = None
agent = None
memory_storage: MemoryStorage | None = None
skills_loader: SkillsLoader | None = None
thread_manager: ThreadManager | None = None
thread_checkpointer = None
thread_store = None
agent_profile_store: AgentProfileStore | None = None
run_records: dict[str, dict[str, Any]] = {}
run_tasks: dict[str, asyncio.Task[Any]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize application on startup."""

    global config, agent, memory_storage, skills_loader, thread_manager, thread_checkpointer, thread_store, agent_profile_store

    from dotenv import load_dotenv

    load_dotenv()

    logger.info("Initializing VD-Flow...")

    config = Config.from_yaml(str(CONFIG_PATH))
    logger.info(
        "Loaded configuration with %s available models (out of %s configured)",
        len(config.available_models),
        len(config.models),
    )

    memory_storage = MemoryStorage(config.memory, sqlite_path=config.threads.sqlite_path)
    logger.info("Memory storage initialized")

    if config.threads.backend != "sqlite":
        raise RuntimeError(f"Thread backend '{config.threads.backend}' is not implemented yet")

    async with AsyncExitStack() as stack:
        from pathlib import Path

        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from langgraph.store.sqlite import AsyncSqliteStore

        sqlite_path = Path(config.threads.sqlite_path)
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        thread_checkpointer = await stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(str(sqlite_path))
        )
        thread_store = await stack.enter_async_context(
            AsyncSqliteStore.from_conn_string(str(sqlite_path))
        )
        await thread_checkpointer.setup()
        await thread_store.setup()

        thread_manager = ThreadManager(
            checkpointer=thread_checkpointer,
            store=thread_store,
            sqlite_path=str(sqlite_path),
            max_threads=config.threads.max_threads,
        )
        logger.info("Thread manager initialized with sqlite backend")

        agent_profile_store = AgentProfileStore("agents")
        logger.info("Agent profile store initialized")

        skills_loader = SkillsLoader(config.skills.path, config.skills.enabled_by_default)
        skills_loader.load_skills()
        logger.info("Skills loaded")

        tools = await _build_runtime_tools(config)
        agent = create_agent(
            config,
            tools=tools,
            checkpointer=thread_checkpointer,
            store=thread_store,
            skills=_get_enabled_skills(),
            memory_storage=memory_storage,
        )
        logger.info("Agent created successfully")

        yield

    logger.info("Shutting down VD-Flow...")


app = FastAPI(
    title="VD-Flow",
    description="Lightweight AI Agent Framework with Memory and Skills",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """Chat request model."""

    message: str
    thread_id: str | None = None
    model: str | None = None
    think_level: str | None = None
    mode: str | None = None
    reasoning_effort: str | None = None


class ChatResponse(BaseModel):
    """Chat response model."""

    response: str
    thread_id: str
    model: str
    artifacts: list[str] = Field(default_factory=list)
    active_skills: list[str] = Field(default_factory=list)
    pending_clarification: dict[str, Any] | None = None


class ThreadCreateRequest(BaseModel):
    """Thread creation request."""

    title: str | None = None
    model: str | None = None


class ThreadUpdateRequest(BaseModel):
    """Thread update request."""

    title: str | None = None


class SkillUpdateRequest(BaseModel):
    """Skill update request."""

    enabled: bool


class MemoryImportRequest(BaseModel):
    """Memory import request."""

    memory: dict[str, Any]
    mode: str = "replace"


class ToolGroupUpdate(BaseModel):
    """Tool group state update."""

    name: str
    enabled: bool


class ToolsConfigUpdateRequest(BaseModel):
    """Tools config update request."""

    tool_groups: list[ToolGroupUpdate] | None = None
    allow_host_bash: bool | None = None


class MCPServerRequest(BaseModel):
    """MCP server create/update request."""

    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    timeout_seconds: float = 10.0


class MCPConfigUpdateRequest(BaseModel):
    """MCP top-level config update request."""

    enabled: bool | None = None


class AgentCreateRequest(BaseModel):
    """Custom agent creation request."""

    name: str
    description: str = ""
    model: str | None = None
    tool_groups: list[str] = Field(default_factory=list)
    soul: str = ""


class AgentUpdateRequest(BaseModel):
    """Custom agent update request."""

    description: str | None = None
    model: str | None = None
    tool_groups: list[str] | None = None
    soul: str | None = None


class ThreadSearchRequest(BaseModel):
    """LangGraph SDK thread search request."""

    metadata: dict[str, Any] | None = None
    ids: list[str] | None = None
    limit: int = 10
    offset: int = 0
    status: str | None = None
    sort_by: str | None = None
    sort_order: str | None = None
    select: list[str] | None = None
    values: dict[str, Any] | None = None
    extract: dict[str, str] | None = None


class LangGraphThreadCreateRequest(BaseModel):
    """LangGraph SDK-compatible thread creation request."""

    metadata: dict[str, Any] | None = None
    thread_id: str | None = None
    if_exists: str | None = None
    supersteps: list[dict[str, Any]] | None = None
    ttl: dict[str, Any] | None = None


class RunCreateRequest(BaseModel):
    """LangGraph SDK-compatible run request."""

    input: dict[str, Any] | None = None
    command: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    assistant_id: str = "lead_agent"
    stream_mode: str | list[str] | None = None
    stream_subgraphs: bool | None = None
    stream_resumable: bool | None = None
    multitask_strategy: str | None = None
    on_disconnect: str | None = None
    durability: str | None = None


class SkillInstallRequest(BaseModel):
    """Install a generated skill artifact into the custom skills folder."""

    thread_id: str
    path: str
    name: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _workspace_frontend_url(request: Request) -> str:
    configured = (
        os.getenv("VD_FLOW_WORKSPACE_URL")
        or os.getenv("WORKSPACE_FRONTEND_URL")
        or os.getenv("FRONTEND_URL")
    )
    if configured:
        return configured.rstrip("/")

    host = request.url.hostname or "127.0.0.1"
    if host == "0.0.0.0":
        host = "127.0.0.1"
    return f"{request.url.scheme}://{host}:{DEFAULT_WORKSPACE_FRONTEND_PORT}/workspace"


def _require_config() -> Config:
    if not config:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return config


def _load_raw_config_document() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Config file not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _save_raw_config_document(document: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        yaml.safe_dump(document, handle, allow_unicode=True, sort_keys=False)


def _reload_config_from_disk() -> Config:
    global config
    config = Config.from_yaml(str(CONFIG_PATH))
    return config


def _normalize_memory_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=400, detail="Memory payload must be a JSON object")

    preferences = snapshot.get("preferences") or {}
    conversation_history = snapshot.get("conversation_history") or []
    facts = snapshot.get("facts") or []

    if not isinstance(preferences, dict):
        raise HTTPException(status_code=400, detail="Memory preferences must be an object")
    if not isinstance(conversation_history, list):
        raise HTTPException(status_code=400, detail="Memory conversation_history must be an array")
    if not isinstance(facts, list):
        raise HTTPException(status_code=400, detail="Memory facts must be an array")

    normalized_history: list[dict[str, Any]] = []
    for item in conversation_history:
        if not isinstance(item, dict):
            continue
        normalized_history.append(
            {
                "summary": str(item.get("summary", "")),
                "thread_id": str(item.get("thread_id", "")),
                "timestamp": str(item.get("timestamp") or _utc_now_iso()),
            }
        )

    normalized_facts: list[dict[str, Any]] = []
    for index, item in enumerate(facts, start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        normalized_facts.append(
            {
                "id": str(item.get("id") or f"fact_{index}"),
                "content": content,
                "category": str(item.get("category") or "knowledge"),
                "confidence": float(item.get("confidence", 1.0)),
                "createdAt": str(item.get("createdAt") or _utc_now_iso()),
            }
        )

    return {
        "version": "1.0",
        "preferences": preferences,
        "conversation_history": normalized_history,
        "facts": normalized_facts,
    }


def _merge_memory_snapshots(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged_preferences = {**dict(current.get("preferences") or {}), **dict(incoming.get("preferences") or {})}
    merged_history = list(current.get("conversation_history") or []) + list(incoming.get("conversation_history") or [])
    merged_history = merged_history[-10:]

    fact_map: dict[str, dict[str, Any]] = {}
    for fact in list(current.get("facts") or []) + list(incoming.get("facts") or []):
        content = str(fact.get("content", "")).strip()
        if not content:
            continue
        fact_map[content] = {
            "id": str(fact.get("id") or f"fact_{len(fact_map) + 1}"),
            "content": content,
            "category": str(fact.get("category") or "knowledge"),
            "confidence": float(fact.get("confidence", 1.0)),
            "createdAt": str(fact.get("createdAt") or _utc_now_iso()),
        }

    return {
        "version": "1.0",
        "preferences": merged_preferences,
        "conversation_history": merged_history,
        "facts": list(fact_map.values()),
    }


def _serialize_tools_config(active_config: Config) -> dict[str, Any]:
    tool_groups = [
        {
            "name": group.name,
            "enabled": group.enabled,
            "tool_count": sum(1 for tool in active_config.tools if tool.group == group.name),
        }
        for group in active_config.tool_groups
    ]

    tools = []
    for tool in active_config.tools:
        group_enabled = active_config.is_tool_group_enabled(tool.group)
        host_blocked = tool.group == "bash" and not active_config.runtime.allow_host_bash
        tools.append(
            {
                "name": tool.name,
                "group": tool.group,
                "configured": tool.enabled,
                "enabled": bool(tool.enabled and group_enabled and not host_blocked),
                "group_enabled": group_enabled,
                "host_only": tool.group == "bash" or tool.host_only,
            }
        )

    enabled_mcp_servers = [server for server in active_config.mcp.servers if server.enabled]
    return {
        "tool_groups": tool_groups,
        "tools": tools,
        "runtime": {
            "allow_host_bash": active_config.runtime.allow_host_bash,
        },
        "mcp": {
            "supported": True,
            "enabled": active_config.mcp.enabled,
            "servers": [_serialize_mcp_server(server) for server in active_config.mcp.servers],
            "enabled_server_count": len(enabled_mcp_servers),
            "reason": "stdio MCP discovery/call is wired; remote transports are config-only for now.",
        },
    }


def _serialize_mcp_server(server: Any) -> dict[str, Any]:
    return {
        "name": server.name,
        "transport": server.transport,
        "command": server.command,
        "args": list(server.args or []),
        "url": server.url,
        "env": dict(server.env or {}),
        "enabled": server.enabled,
        "timeout_seconds": server.timeout_seconds,
    }


def _mcp_runtime_servers(active_config: Config) -> list[RuntimeMCPServerConfig]:
    if not active_config.mcp.enabled:
        return []
    return [
        RuntimeMCPServerConfig(
            name=server.name,
            transport=server.transport,
            command=server.command,
            args=list(server.args),
            url=server.url,
            env=dict(server.env),
            enabled=server.enabled,
            timeout_seconds=server.timeout_seconds,
        )
        for server in active_config.mcp.servers
        if server.enabled
    ]


async def _load_mcp_runtime_tools(active_config: Config) -> list[Any]:
    servers = _mcp_runtime_servers(active_config)
    if not servers:
        return []
    try:
        return await load_mcp_tools(servers)
    except Exception as exc:
        logger.warning("Failed to load MCP runtime tools: %s", exc)
        return []


async def _build_runtime_tools(
    active_config: Config,
    *,
    selected_model_name: str | None = None,
    subagent_enabled: bool = False,
) -> list[Any]:
    mcp_tools = await _load_mcp_runtime_tools(active_config)
    return get_available_tools(
        active_config,
        model_name=selected_model_name,
        subagent_enabled=subagent_enabled,
        extra_tools=mcp_tools,
    )


def _normalize_mcp_server_request(request: MCPServerRequest) -> dict[str, Any]:
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="MCP server name is required")
    if request.transport not in {"stdio", "sse", "streamable_http"}:
        raise HTTPException(status_code=400, detail="MCP transport must be stdio, sse, or streamable_http")
    if request.transport == "stdio" and not request.command.strip():
        raise HTTPException(status_code=400, detail="MCP stdio server command is required")
    if request.transport in {"sse", "streamable_http"} and not request.url.strip():
        raise HTTPException(status_code=400, detail="MCP remote server url is required")
    return {
        "name": name,
        "transport": request.transport,
        "command": request.command.strip(),
        "args": list(request.args or []),
        "url": request.url.strip(),
        "env": dict(request.env or {}),
        "enabled": request.enabled,
        "timeout_seconds": max(1.0, float(request.timeout_seconds)),
    }


def _require_thread_manager() -> ThreadManager:
    if not thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")
    return thread_manager


def _require_state_agent():
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent


def _require_checkpointer():
    if thread_checkpointer is None:
        raise HTTPException(status_code=503, detail="Thread checkpointer not initialized")
    return thread_checkpointer


def _require_agent_profile_store() -> AgentProfileStore:
    if agent_profile_store is None:
        raise HTTPException(status_code=503, detail="Agent profile store not initialized")
    return agent_profile_store


def _get_enabled_skills() -> list[Any]:
    if not skills_loader:
        return []
    return skills_loader.get_enabled_skills()


def _resolve_model(model_name: str | None) -> tuple[str, Any]:
    active_config = _require_config()
    available = active_config.available_models
    if not available:
        raise HTTPException(status_code=503, detail="No models with valid API keys configured.")

    selected_model_name = model_name or available[0].name
    model_config = next((item for item in available if item.name == selected_model_name), None)
    if not model_config:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{selected_model_name}' not found or has no valid API key",
        )
    return selected_model_name, model_config


def _serialize_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


def _build_agent_run_config(thread_id: str) -> dict[str, Any]:
    active_config = _require_config()
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": active_config.runtime.agent_recursion_limit,
    }


def _message_role(raw_message: Any) -> str:
    raw_type = str(getattr(raw_message, "type", "")).lower()
    if raw_type == "human":
        return "user"
    if raw_type == "ai":
        return "assistant"
    if raw_type == "system":
        return "system"
    if raw_type == "tool":
        return "tool"
    raw_role = str(getattr(raw_message, "role", "")).lower()
    if raw_role in {"user", "assistant", "system", "tool"}:
        return raw_role
    return ""


def _extract_ui_message(raw_message: Any) -> dict[str, Any] | None:
    role = _message_role(raw_message)
    if role not in {"user", "assistant"}:
        return None

    additional_kwargs = getattr(raw_message, "additional_kwargs", {}) or {}
    response_metadata = getattr(raw_message, "response_metadata", {}) or {}
    created_at = additional_kwargs.get("created_at") or response_metadata.get("created_at") or ""
    status = additional_kwargs.get("status") or response_metadata.get("status") or "completed"

    thinking = ""
    content = _serialize_message_content(getattr(raw_message, "content", ""))

    if role == "assistant":
        answer_text, thinking_text = extract_chunk_parts(
            SimpleNamespace(
                content=getattr(raw_message, "content", ""),
                additional_kwargs=additional_kwargs,
                response_metadata=response_metadata,
            )
        )
        content = answer_text or content
        # Strip leaked memory JSON from model output
        content = strip_leaked_memory_json(content)
        thinking = thinking_text
        if not content and getattr(raw_message, "tool_calls", None):
            return None

    if not content and not thinking:
        return None

    message = {
        "id": str(getattr(raw_message, "id", "") or ""),
        "role": role,
        "content": content,
        "created_at": created_at,
        "status": status,
    }
    if thinking:
        message["thinking"] = thinking
    return message


def _coerce_timestamp(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            normalized = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized).timestamp()
            except ValueError:
                return None
    return None


def _latest_visible_message(messages: list[dict[str, Any]], role: str | None = None) -> dict[str, Any] | None:
    for message in reversed(messages):
        if role and message.get("role") != role:
            continue
        if message.get("content") or message.get("thinking"):
            return message
    return None


async def _create_runtime_agent(
    *,
    selected_model_name: str,
    model_runtime_options: dict[str, Any],
    mode: str = "pro",
    agent_name: str | None = None,
):
    active_config = _require_config()
    subagent_enabled = mode == "ultra"
    agent_profile = None
    if agent_name:
        try:
            agent_profile = _require_agent_profile_store().get(agent_name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # When Ultra mode, set task context so the task tool can create real subagents
    if subagent_enabled:
        from vdflow.tools.task import set_task_context
        set_task_context(active_config, parent_model_name=selected_model_name)

    return create_agent(
        active_config,
        model_name=selected_model_name,
        tools=await _build_runtime_tools(
            active_config,
            selected_model_name=selected_model_name,
            subagent_enabled=subagent_enabled,
        ),
        model_kwargs=model_runtime_options,
        checkpointer=thread_checkpointer,
        store=thread_store,
        skills=_get_enabled_skills(),
        memory_storage=memory_storage,
        subagent_enabled=subagent_enabled,
        agent_name=agent_profile.name if agent_profile else None,
        agent_soul=agent_profile.soul if agent_profile else None,
    )


async def _stream_agent_events(
    *,
    active_agent: Any,
    request_message: str,
    thread_id: str,
    queue: asyncio.Queue[tuple[str, Any]],
) -> None:
    from langchain_core.messages import HumanMessage

    try:
        async for mode, chunk in active_agent.astream(
            {
                "messages": [
                    HumanMessage(
                        content=request_message,
                        additional_kwargs={"created_at": _utc_now_iso()},
                    )
                ]
            },
            config=_build_agent_run_config(thread_id),
            stream_mode=["events", "custom"],
        ):
            if mode == "events":
                await queue.put(("event", chunk))
            elif mode == "custom":
                # Wrap custom data as an on_custom_event for uniform handling
                await queue.put(("event", {"event": "on_custom_event", "data": chunk}))
    except Exception as exc:
        await queue.put(("error", exc))
    finally:
        await queue.put(("done", None))


async def _load_thread_state(thread_id: str) -> dict[str, Any]:
    checkpoint = await _require_checkpointer().aget_tuple(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    )
    if checkpoint is None:
        return {"exists": False, "messages": []}

    snapshot = await _require_state_agent().aget_state({"configurable": {"thread_id": thread_id}})
    values = getattr(snapshot, "values", {}) or {}
    raw_messages = values.get("messages", []) or []

    messages: list[dict[str, Any]] = []
    for raw_message in raw_messages:
        ui_message = _extract_ui_message(raw_message)
        if ui_message is not None:
            messages.append(ui_message)

    latest_message = _latest_visible_message(messages)
    updated_at = _coerce_timestamp(latest_message.get("created_at")) if latest_message else None

    return {
        "exists": True,
        "messages": messages,
        "title": values.get("title") or None,
        "updated_at": updated_at,
        "metadata": {},
        "thread_data": (
            values.get("thread_data").model_dump()
            if hasattr(values.get("thread_data"), "model_dump")
            else values.get("thread_data")
        ),
        "artifacts": list(values.get("artifacts") or []),
        "active_skills": list(values.get("active_skills") or []),
        "pending_clarification": (
            values.get("pending_clarification").model_dump()
            if hasattr(values.get("pending_clarification"), "model_dump")
            else values.get("pending_clarification")
        ),
        "memory_context": values.get("memory_context") or "",
        "todos": list(values.get("todos") or []),
    }


async def _ensure_thread_summary(
    *,
    thread_id: str,
    selected_model_name: str,
    status: str,
    request_message: str | None = None,
) -> dict[str, Any]:
    manager = _require_thread_manager()
    thread_payload = await manager.get_thread(thread_id, _load_thread_state)
    summary = thread_payload["thread"]
    messages = thread_payload["messages"]

    fallback_title = request_message or ""
    latest_message = _latest_visible_message(messages)
    preview = latest_message.get("content", "") if latest_message else request_message or ""

    return await manager.touch_thread(
        thread_id,
        title=fallback_title,
        status=status,
        model=selected_model_name,
        preview=preview,
        message_count=len(messages),
    )


def _jsonable(value: Any) -> Any:
    """Best-effort JSON serializer for LangChain/LangGraph event payloads."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _jsonable(value.dict())
    if hasattr(value, "content"):
        payload = {
            "id": str(getattr(value, "id", "") or ""),
            "type": str(getattr(value, "type", "") or ""),
            "content": _jsonable(getattr(value, "content", "")),
        }
        tool_calls = getattr(value, "tool_calls", None)
        if tool_calls:
            payload["tool_calls"] = _jsonable(tool_calls)
        usage = getattr(value, "usage_metadata", None)
        if usage:
            payload["usage_metadata"] = _jsonable(usage)
        return payload
    return str(value)


def _sse_frame(event: str, data: Any, event_id: str | None = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(_jsonable(data), ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def _iso_from_timestamp(value: Any) -> str:
    timestamp = _coerce_timestamp(value)
    if timestamp is None:
        return _utc_now_iso()
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _to_langgraph_message(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message.get("id") or f"msg-{uuid4().hex}",
        "type": "human" if message.get("role") == "user" else "ai",
        "content": message.get("content") or "",
        "additional_kwargs": {
            "created_at": message.get("created_at") or "",
            "status": message.get("status") or "completed",
            **({"thinking": message.get("thinking")} if message.get("thinking") else {}),
        },
    }


async def _thread_state_values(thread_id: str) -> dict[str, Any]:
    state = await _load_thread_state(thread_id)
    return {
        "messages": [_to_langgraph_message(message) for message in state.get("messages", [])],
        "artifacts": list(state.get("artifacts") or []),
        "todos": list(state.get("todos") or []),
        "active_skills": list(state.get("active_skills") or []),
        "pending_clarification": state.get("pending_clarification"),
        "thread_data": state.get("thread_data"),
        "memory_context": state.get("memory_context") or "",
        "token_usage": state.get("token_usage") or {},
        "uploaded_files": state.get("uploaded_files") or [],
    }


def _langgraph_thread(summary: dict[str, Any], values: dict[str, Any] | None = None) -> dict[str, Any]:
    thread_id = summary.get("thread_id") or summary.get("id")
    metadata = dict(summary.get("metadata") or {})
    metadata.setdefault("title", summary.get("title") or "新对话")
    metadata.setdefault("model", summary.get("model") or "")
    return {
        "thread_id": thread_id,
        "created_at": _iso_from_timestamp(summary.get("created_at")),
        "updated_at": _iso_from_timestamp(summary.get("updated_at")),
        "metadata": metadata,
        "status": summary.get("status") or "idle",
        "config": {"configurable": {"thread_id": thread_id}},
        "values": values or {},
        "interrupts": {},
    }


async def _langgraph_thread_state(thread_id: str) -> dict[str, Any]:
    values = await _thread_state_values(thread_id)
    return {
        "values": values,
        "next": [],
        "tasks": [],
        "metadata": {},
        "created_at": _utc_now_iso(),
        "checkpoint": {"thread_id": thread_id, "checkpoint_id": thread_id, "checkpoint_ns": ""},
        "parent_checkpoint": None,
        "config": {"configurable": {"thread_id": thread_id}},
    }


def _agent_response(profile: Any) -> dict[str, Any]:
    return profile.to_dict()


def _assistant_response(assistant_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    name = assistant_id
    return {
        "assistant_id": assistant_id,
        "graph_id": "agent",
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "config": {},
        "context": {},
        "metadata": metadata or {},
        "name": name,
        "description": "VD-Flow lead agent runtime",
    }


def _run_response(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": record["run_id"],
        "thread_id": record["thread_id"],
        "assistant_id": record.get("assistant_id", "lead_agent"),
        "status": record.get("status", "pending"),
        "metadata": record.get("metadata") or {},
        "kwargs": record.get("kwargs") or {},
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


async def _publish_run_event(record: dict[str, Any], event: str, data: Any) -> None:
    event_id = str(len(record["events"]) + 1)
    item = {"id": event_id, "event": event, "data": _jsonable(data)}
    record["events"].append(item)
    for queue in list(record.get("queues", [])):
        await queue.put(item)


def _extract_input_text_and_files(payload: dict[str, Any] | None) -> tuple[str, list[dict[str, Any]]]:
    payload = payload or {}
    messages = payload.get("messages") or []
    if not messages:
        return "", list(payload.get("uploaded_files") or [])

    latest = messages[-1]
    content = latest.get("content", "") if isinstance(latest, dict) else str(latest)
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    text_parts.append(str(part.get("text") or ""))
                elif "text" in part:
                    text_parts.append(str(part.get("text") or ""))
            else:
                text_parts.append(str(part))
        text = "".join(text_parts).strip()
    else:
        text = str(content).strip()

    additional_kwargs = latest.get("additional_kwargs", {}) if isinstance(latest, dict) else {}
    files = list(additional_kwargs.get("files") or payload.get("uploaded_files") or [])
    return text, files


async def _run_agent_for_record(record: dict[str, Any]) -> None:
    from langchain_core.messages import HumanMessage

    thread_id = record["thread_id"]
    request = record["request"]
    context = dict(request.context or {})
    metadata = dict(request.metadata or {})
    input_text, uploaded_files = _extract_input_text_and_files(request.input)
    agent_name = context.get("agent_name") or metadata.get("agent_name")
    agent_profile = None
    if agent_name:
        agent_profile = _require_agent_profile_store().get(str(agent_name))

    selected_model_name, model_config = _resolve_model(
        context.get("model") or (agent_profile.model if agent_profile else None)
    )
    mode, reasoning_effort, think_level = resolve_mode_and_effort(
        context.get("mode") or metadata.get("mode"),
        context.get("reasoning_effort") or metadata.get("reasoning_effort"),
        context.get("think_level") or metadata.get("think_level"),
    )
    model_runtime_options = build_model_runtime_options(
        model_config, think_level, reasoning_effort=reasoning_effort, mode=mode,
    )

    try:
        record["status"] = "running"
        record["updated_at"] = _utc_now_iso()
        await _publish_run_event(
            record,
            "metadata",
            {"run_id": record["run_id"], "thread_id": thread_id},
        )
        await _require_thread_manager().touch_thread(
            thread_id,
            title=input_text,
            status="busy",
            model=selected_model_name,
            preview=input_text,
            metadata={"agent_name": agent_name} if agent_name else None,
        )
        active_agent = await _create_runtime_agent(
            selected_model_name=selected_model_name,
            model_runtime_options=model_runtime_options,
            mode=mode,
            agent_name=str(agent_name) if agent_name else None,
        )
        graph_input = {
            "messages": [
                HumanMessage(
                    content=input_text,
                    additional_kwargs={
                        "created_at": _utc_now_iso(),
                        "files": uploaded_files,
                    },
                )
            ],
        }
        if uploaded_files:
            graph_input["uploaded_files"] = uploaded_files

        async for stream_mode, chunk in active_agent.astream(
            graph_input,
            config=_build_agent_run_config(thread_id),
            stream_mode=["events", "custom"],
        ):
            if stream_mode == "custom":
                # Custom events from get_stream_writer() — publish directly
                if isinstance(chunk, dict):
                    await _publish_run_event(record, "custom", chunk)
                continue

            # stream_mode == "events" — same format as astream_events v2
            event = chunk
            kind = event.get("event", "")
            await _publish_run_event(record, "events", event)
            if kind == "on_tool_start":
                await _publish_run_event(
                    record,
                    "tools",
                    {
                        "event": "on_tool_start",
                        "name": event.get("name", "tool"),
                        "toolCallId": event.get("run_id"),
                        "input": event.get("data", {}).get("input"),
                    },
                )
            elif kind == "on_tool_end":
                await _publish_run_event(
                    record,
                    "tools",
                    {
                        "event": "on_tool_end",
                        "name": event.get("name", "tool"),
                        "toolCallId": event.get("run_id"),
                        "output": event.get("data", {}).get("output"),
                    },
                )

        values = await _thread_state_values(thread_id)
        await _publish_run_event(record, "values", values)
        await _ensure_thread_summary(
            thread_id=thread_id,
            selected_model_name=selected_model_name,
            status="idle",
            request_message=input_text,
        )
        record["status"] = "success"
    except asyncio.CancelledError:
        record["status"] = "interrupted"
        await _require_thread_manager().touch_thread(
            thread_id,
            status="interrupted",
            preview="[已中断]",
        )
        await _publish_run_event(record, "error", {"error": "cancelled", "message": "Run cancelled"})
        raise
    except GraphRecursionError as exc:
        record["status"] = "error"
        message = "调研过程超过当前步骤上限，执行被提前停止。"
        await _require_thread_manager().touch_thread(thread_id, status="error", preview=f"❌ {message}")
        await _publish_run_event(record, "error", {"error": exc.__class__.__name__, "message": message})
    except Exception as exc:
        record["status"] = "error"
        await _require_thread_manager().touch_thread(thread_id, status="error", preview=f"❌ {exc}")
        await _publish_run_event(record, "error", {"error": exc.__class__.__name__, "message": str(exc)})
    finally:
        record["updated_at"] = _utc_now_iso()
        for queue in list(record.get("queues", [])):
            await queue.put(None)


def _create_run_record(thread_id: str, request: RunCreateRequest) -> dict[str, Any]:
    run_id = uuid4().hex
    record = {
        "run_id": run_id,
        "thread_id": thread_id,
        "assistant_id": request.assistant_id,
        "status": "pending",
        "metadata": dict(request.metadata or {}),
        "kwargs": request.model_dump(),
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "request": request,
        "events": [],
        "queues": [],
    }
    run_records[run_id] = record
    return record


async def _stream_run_record(record: dict[str, Any], *, start: bool = False) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue[Any] = asyncio.Queue()
    record.setdefault("queues", []).append(queue)
    try:
        for item in record.get("events", []):
            yield _sse_frame(item["event"], item["data"], item["id"])

        if start and record["run_id"] not in run_tasks:
            run_tasks[record["run_id"]] = asyncio.create_task(_run_agent_for_record(record))

        while True:
            item = await queue.get()
            if item is None:
                break
            yield _sse_frame(item["event"], item["data"], item["id"])
    finally:
        with suppress(ValueError):
            record.get("queues", []).remove(queue)


_SAFE_FILENAME_RE = re.compile(r"^[^/\\\x00]+$")


def _safe_upload_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name or name != filename or not _SAFE_FILENAME_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid upload filename")
    return name


def _upload_info(thread_id: str, path: Path) -> dict[str, Any]:
    stat = path.stat()
    virtual_path = f"/mnt/user-data/uploads/{path.name}"
    return {
        "filename": path.name,
        "size": stat.st_size,
        "path": str(path),
        "virtual_path": virtual_path,
        "artifact_url": f"/api/threads/{thread_id}/artifacts/{virtual_path.lstrip('/')}",
        "extension": path.suffix.lstrip("."),
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
    }


async def _install_skill_from_file(source: Path, requested_name: str | None = None) -> dict[str, Any]:
    from vdflow.skills.manager import SkillManager, validate_skill_name

    if not skills_loader:
        raise HTTPException(status_code=503, detail="Skills loader not initialized")

    custom_dir = Path(config.skills.path) / "custom" if config else Path("skills/custom")
    manager = SkillManager(str(custom_dir))

    if source.suffix == ".skill":
        if not zipfile.is_zipfile(source):
            raise HTTPException(status_code=400, detail=".skill artifact must be a zip file")
        extract_root = custom_dir / (requested_name or source.stem)
        if validate_skill_name(extract_root.name):
            raise HTTPException(status_code=400, detail="Invalid skill name")
        if extract_root.exists():
            raise HTTPException(status_code=409, detail=f"Skill '{extract_root.name}' already exists")
        with zipfile.ZipFile(source) as archive:
            members = archive.namelist()
            if not any(member.endswith("SKILL.md") for member in members):
                raise HTTPException(status_code=400, detail=".skill archive must contain SKILL.md")
            extract_root.mkdir(parents=True, exist_ok=True)
            for member in members:
                target = (extract_root / member).resolve()
                try:
                    target.relative_to(extract_root.resolve())
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail="Skill archive contains unsafe paths") from exc
            archive.extractall(extract_root)
        skills_loader.reload()
        return {"success": True, "name": extract_root.name}

    if source.name != "SKILL.md":
        raise HTTPException(status_code=400, detail="Only .skill archives or SKILL.md artifacts can be installed")

    content = source.read_text(encoding="utf-8")
    name = requested_name or source.parent.name
    result = await manager.create(name, content)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    skills_loader.reload()
    return {"success": True, "name": result["name"]}


@app.get("/")
async def root(request: Request):
    """Redirect the product entry to the Next.js workspace."""

    return RedirectResponse(_workspace_frontend_url(request), status_code=307)


@app.get("/workspace")
@app.get("/workspace/{path:path}")
async def workspace_entry(request: Request, path: str = ""):
    """Redirect accidental FastAPI workspace visits to the Next.js app."""

    base_url = _workspace_frontend_url(request).rstrip("/")
    suffix = f"/{path}" if path else ""
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"{base_url}{suffix}{query}", status_code=307)


@app.get("/api/health")
async def health():
    """Health check endpoint."""

    return {"status": "healthy", "version": "0.1.0"}


@app.get("/api/threads")
async def list_threads(q: str | None = None):
    """List stored chat threads."""

    manager = _require_thread_manager()
    return {"threads": await manager.list_threads(query=q, state_loader=_load_thread_state)}


@app.post("/api/threads")
async def create_thread(request: ThreadCreateRequest | None = None):
    """Create a new empty thread."""

    manager = _require_thread_manager()
    payload = request or ThreadCreateRequest()
    thread = await manager.create_thread(title=payload.title, model=payload.model)
    return {"thread": thread}


@app.get("/api/threads/{thread_id}")
async def get_thread(thread_id: str):
    """Get a full thread with its messages."""

    manager = _require_thread_manager()
    try:
        payload = await manager.get_thread(thread_id, _load_thread_state)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    state = await _load_thread_state(thread_id)
    return {
        **payload,
        "thread_data": state.get("thread_data"),
        "artifacts": state.get("artifacts", []),
        "active_skills": state.get("active_skills", []),
        "pending_clarification": state.get("pending_clarification"),
        "todos": state.get("todos", []),
    }


@app.delete("/api/threads/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete a thread and its checkpoint history."""

    manager = _require_thread_manager()
    await manager.delete_thread(thread_id)
    # Clean up sandbox directories
    try:
        get_paths().delete_thread_dir(thread_id)
    except Exception:
        logger.warning("Failed to delete sandbox dir for thread %s", thread_id, exc_info=True)
    return {"success": True}


@app.patch("/api/threads/{thread_id}")
async def update_thread(thread_id: str, request: ThreadUpdateRequest):
    """Update thread metadata."""

    manager = _require_thread_manager()
    title = (request.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Thread title is required")

    try:
        thread = await manager.rename_thread(thread_id, title)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"thread": thread}


# ── LangGraph SDK compatibility gateway ────────────────────────────


@app.post("/api/langgraph/threads")
async def langgraph_create_thread(request: LangGraphThreadCreateRequest | None = None):
    """Create a thread in the shape expected by @langchain/langgraph-sdk."""

    payload = request or LangGraphThreadCreateRequest()
    manager = _require_thread_manager()
    title = None
    metadata = dict(payload.metadata or {})
    if isinstance(metadata.get("title"), str):
        title = metadata["title"]
    thread = await manager.create_thread(title=title, metadata=metadata, model=str(metadata.get("model") or ""))
    get_paths().ensure_thread_dirs(thread["thread_id"])
    return _langgraph_thread(thread, values={})


@app.get("/api/langgraph/threads/{thread_id}")
async def langgraph_get_thread(thread_id: str, include: list[str] | None = None):
    manager = _require_thread_manager()
    try:
        payload = await manager.get_thread(thread_id, _load_thread_state)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    values = await _thread_state_values(thread_id)
    return _langgraph_thread(payload["thread"], values=values if not include or "values" in include else {})


@app.patch("/api/langgraph/threads/{thread_id}")
async def langgraph_update_thread(thread_id: str, request: LangGraphThreadCreateRequest | None = None):
    manager = _require_thread_manager()
    metadata = dict((request.metadata if request else None) or {})
    try:
        thread = await manager.touch_thread(thread_id, metadata=metadata)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _langgraph_thread(thread, values=await _thread_state_values(thread_id))


@app.delete("/api/langgraph/threads/{thread_id}")
async def langgraph_delete_thread(thread_id: str):
    await delete_thread(thread_id)
    return None


@app.post("/api/langgraph/threads/search")
async def langgraph_search_threads(request: ThreadSearchRequest | None = None):
    payload = request or ThreadSearchRequest()
    manager = _require_thread_manager()
    summaries = await manager.list_threads(limit=max(payload.limit + payload.offset, payload.limit), state_loader=_load_thread_state)
    if payload.ids:
        allowed = set(payload.ids)
        summaries = [item for item in summaries if item.get("thread_id") in allowed or item.get("id") in allowed]
    if payload.status:
        summaries = [item for item in summaries if item.get("status") == payload.status]
    start = max(0, payload.offset)
    end = start + max(0, payload.limit)
    result = []
    for summary in summaries[start:end]:
        values = await _thread_state_values(summary["thread_id"]) if not payload.select or "values" in payload.select else {}
        result.append(_langgraph_thread(summary, values=values))
    return result


@app.post("/api/langgraph/threads/count")
async def langgraph_count_threads(request: ThreadSearchRequest | None = None):
    payload = request or ThreadSearchRequest()
    threads = await langgraph_search_threads(payload)
    return len(threads)


@app.get("/api/langgraph/threads/{thread_id}/state")
async def langgraph_get_thread_state(thread_id: str):
    return await _langgraph_thread_state(thread_id)


@app.post("/api/langgraph/threads/{thread_id}/history")
async def langgraph_get_thread_history(thread_id: str, request: dict[str, Any] | None = None):
    return [await _langgraph_thread_state(thread_id)]


@app.post("/api/langgraph/threads/{thread_id}/runs")
async def langgraph_create_run(thread_id: str, request: RunCreateRequest):
    record = _create_run_record(thread_id, request)
    run_tasks[record["run_id"]] = asyncio.create_task(_run_agent_for_record(record))
    return _run_response(record)


@app.post("/api/langgraph/threads/{thread_id}/runs/stream")
async def langgraph_stream_run(thread_id: str, request: RunCreateRequest):
    record = _create_run_record(thread_id, request)
    run_path = f"/api/langgraph/threads/{thread_id}/runs/{record['run_id']}"
    return StreamingResponse(
        _stream_run_record(record, start=True),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Content-Location": run_path,
            "Location": f"{run_path}/stream",
        },
    )


@app.post("/api/langgraph/threads/{thread_id}/runs/wait")
async def langgraph_wait_run(thread_id: str, request: RunCreateRequest):
    record = _create_run_record(thread_id, request)
    await _run_agent_for_record(record)
    if record.get("status") == "error":
        error_events = [event for event in record["events"] if event["event"] == "error"]
        if error_events:
            return {"__error__": error_events[-1]["data"]}
    return await _thread_state_values(thread_id)


@app.get("/api/langgraph/threads/{thread_id}/runs")
async def langgraph_list_runs(thread_id: str, limit: int = 10, offset: int = 0, status: str | None = None):
    records = [record for record in run_records.values() if record["thread_id"] == thread_id]
    if status:
        records = [record for record in records if record.get("status") == status]
    records.sort(key=lambda item: item["created_at"], reverse=True)
    return [_run_response(record) for record in records[offset: offset + limit]]


@app.get("/api/langgraph/threads/{thread_id}/runs/{run_id}")
async def langgraph_get_run(thread_id: str, run_id: str):
    record = run_records.get(run_id)
    if not record or record["thread_id"] != thread_id:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return _run_response(record)


@app.post("/api/langgraph/threads/{thread_id}/runs/{run_id}/cancel")
async def langgraph_cancel_run(thread_id: str, run_id: str, wait: bool = False, action: str = "interrupt"):
    record = run_records.get(run_id)
    if not record or record["thread_id"] != thread_id:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    task = run_tasks.get(run_id)
    if task and not task.done():
        task.cancel()
        if wait:
            with suppress(asyncio.CancelledError):
                await task
    record["status"] = "interrupted"
    record["updated_at"] = _utc_now_iso()
    return None


@app.get("/api/langgraph/threads/{thread_id}/runs/{run_id}/join")
async def langgraph_join_run(thread_id: str, run_id: str):
    record = run_records.get(run_id)
    if not record or record["thread_id"] != thread_id:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    task = run_tasks.get(run_id)
    if task:
        with suppress(asyncio.CancelledError):
            await task
    return await _thread_state_values(thread_id)


@app.get("/api/langgraph/threads/{thread_id}/runs/{run_id}/stream")
async def langgraph_join_run_stream(thread_id: str, run_id: str):
    record = run_records.get(run_id)
    if not record or record["thread_id"] != thread_id:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return StreamingResponse(
        _stream_run_record(record, start=False),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/langgraph/assistants")
async def langgraph_list_assistants():
    return [_assistant_response("lead_agent"), *[
        _assistant_response(profile.name, {"agent_name": profile.name})
        for profile in _require_agent_profile_store().list()
    ]]


@app.post("/api/langgraph/assistants/search")
async def langgraph_search_assistants(request: dict[str, Any] | None = None):
    return await langgraph_list_assistants()


@app.get("/api/langgraph/assistants/{assistant_id}")
async def langgraph_get_assistant(assistant_id: str):
    if assistant_id == "lead_agent":
        return _assistant_response("lead_agent")
    try:
        profile = _require_agent_profile_store().get(assistant_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _assistant_response(profile.name, {"agent_name": profile.name})


@app.get("/api/assistants")
async def list_assistants():
    return await langgraph_list_assistants()


@app.get("/api/assistants/{assistant_id}")
async def get_assistant(assistant_id: str):
    return await langgraph_get_assistant(assistant_id)


# ── Custom agents ───────────────────────────────────────────────────


@app.get("/api/agents")
async def list_agents():
    return {"agents": [_agent_response(profile) for profile in _require_agent_profile_store().list()]}


@app.get("/api/agents/check")
async def check_agent_name(name: str):
    normalized = name.strip().lower()
    error = validate_agent_name(normalized)
    exists = _require_agent_profile_store().exists(normalized) if not error else False
    return {"name": normalized, "valid": error is None, "available": error is None and not exists, "reason": error}


@app.post("/api/agents")
async def create_agent_profile(request: AgentCreateRequest):
    name = request.name.strip().lower()
    error = validate_agent_name(name)
    if error:
        raise HTTPException(status_code=400, detail=error)
    try:
        profile = _require_agent_profile_store().create(
            name=name,
            description=request.description,
            model=request.model,
            tool_groups=request.tool_groups,
            soul=request.soul,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"agent": _agent_response(profile)}


@app.get("/api/agents/{name}")
async def get_agent_profile(name: str):
    try:
        profile = _require_agent_profile_store().get(name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"agent": _agent_response(profile)}


@app.put("/api/agents/{name}")
async def update_agent_profile(name: str, request: AgentUpdateRequest):
    try:
        profile = _require_agent_profile_store().update(
            name,
            description=request.description,
            model=request.model,
            tool_groups=request.tool_groups,
            soul=request.soul,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"agent": _agent_response(profile)}


@app.delete("/api/agents/{name}")
async def delete_agent_profile(name: str):
    try:
        _require_agent_profile_store().delete(name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True}


# ── Uploads ─────────────────────────────────────────────────────────


@app.post("/api/threads/{thread_id}/uploads")
async def upload_thread_files(thread_id: str, files: list[UploadFile] = File(...)):
    paths = get_paths()
    paths.ensure_thread_dirs(thread_id)
    upload_dir = paths.sandbox_uploads_dir(thread_id)
    saved = []
    for upload in files:
        filename = _safe_upload_filename(upload.filename or "")
        target = upload_dir / filename
        content = await upload.read()
        target.write_bytes(content)
        saved.append(_upload_info(thread_id, target))
    return {"files": saved}


@app.get("/api/threads/{thread_id}/uploads/list")
async def list_thread_uploads(thread_id: str):
    upload_dir = get_paths().sandbox_uploads_dir(thread_id)
    if not upload_dir.exists():
        return {"files": []}
    return {
        "files": [
            _upload_info(thread_id, path)
            for path in sorted(upload_dir.iterdir(), key=lambda item: item.name)
            if path.is_file()
        ]
    }


@app.delete("/api/threads/{thread_id}/uploads/{filename}")
async def delete_thread_upload(thread_id: str, filename: str):
    safe_name = _safe_upload_filename(filename)
    target = (get_paths().sandbox_uploads_dir(thread_id) / safe_name).resolve()
    try:
        target.relative_to(get_paths().sandbox_uploads_dir(thread_id).resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Upload path traversal is not allowed") from exc
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Upload '{filename}' not found")
    target.unlink()
    return {"success": True}


# ── Artifacts download ──────────────────────────────────────────────

_ACTIVE_MIME_TYPES = {"text/html", "application/xhtml+xml", "image/svg+xml"}


@app.get("/api/threads/{thread_id}/artifacts/{path:path}")
async def get_artifact(thread_id: str, path: str, download: bool = False):
    """Download or view a file generated by the agent."""
    paths = get_paths()
    try:
        actual_path = paths.resolve_virtual_path(thread_id, path)
    except ValueError as e:
        status = 403 if "traversal" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))

    if not actual_path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {path}")
    if not actual_path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {path}")

    mime_type, _ = mimetypes.guess_type(str(actual_path))
    filename = actual_path.name
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"

    # Force download for active content (XSS prevention)
    if mime_type in _ACTIVE_MIME_TYPES or download:
        return FileResponse(
            path=actual_path, filename=filename, media_type=mime_type,
            headers={"Content-Disposition": disposition},
        )

    # Text files inline
    if mime_type and mime_type.startswith("text/"):
        return PlainTextResponse(
            content=actual_path.read_text(encoding="utf-8"),
            media_type=mime_type,
        )

    # Binary files inline with download option
    return FileResponse(path=actual_path, filename=filename, media_type=mime_type)


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Send a message and get a streaming response via SSE."""

    _require_config()
    selected_model_name, model_config = _resolve_model(request.model)
    mode, reasoning_effort, think_level = resolve_mode_and_effort(
        request.mode, request.reasoning_effort, request.think_level,
    )
    model_runtime_options = build_model_runtime_options(
        model_config, think_level, reasoning_effort=reasoning_effort, mode=mode,
    )
    manager = _require_thread_manager()

    if request.thread_id:
        thread_id = request.thread_id
        try:
            await manager.touch_thread(
                thread_id,
                title=request.message,
                status="busy",
                model=selected_model_name,
                preview=request.message,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        thread = await manager.create_thread(title=request.message, model=selected_model_name)
        thread_id = thread["id"]
        # Ensure sandbox directories exist for this thread
        try:
            get_paths().ensure_thread_dirs(thread_id)
        except Exception:
            logger.warning("Failed to create sandbox dirs for thread %s", thread_id, exc_info=True)
        await manager.touch_thread(
            thread_id,
            status="busy",
            model=selected_model_name,
            preview=request.message,
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        active_config = _require_config()
        active_agent = await _create_runtime_agent(
            selected_model_name=selected_model_name,
            model_runtime_options=model_runtime_options,
            mode=mode,
        )
        heartbeat_seconds = max(1, int(active_config.runtime.stream_heartbeat_seconds))
        event_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        producer = asyncio.create_task(
            _stream_agent_events(
                active_agent=active_agent,
                request_message=request.message,
                thread_id=thread_id,
                queue=event_queue,
            )
        )

        answer_parts: list[str] = []
        thinking_parts: list[str] = []
        thinking_open = False
        answer_started = False
        assistant_status = "completed"
        failure_text = ""

        yield (
            "data: "
            f"{json.dumps({'type': 'meta', 'thread_id': thread_id, 'model': selected_model_name, 'mode': mode, 'reasoning_effort': reasoning_effort})}\n\n"
        )

        start_phase = build_phase_message("start", think_level)
        if start_phase:
            yield f"data: {json.dumps({'type': 'phase', 'text': start_phase, 'stage': 'start'})}\n\n"

        try:
            while True:
                try:
                    item_type, payload = await asyncio.wait_for(event_queue.get(), timeout=heartbeat_seconds)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue

                if item_type == "done":
                    break
                if item_type == "error":
                    raise payload

                event = payload
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    answer_text, thinking_text = extract_chunk_parts(chunk)

                    if thinking_text:
                        thinking_parts.append(thinking_text)
                        if not thinking_open:
                            thinking_open = True
                            yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"
                        yield f"data: {json.dumps({'type': 'thinking_delta', 'text': thinking_text})}\n\n"

                    if answer_text:
                        answer_parts.append(answer_text)
                        if thinking_open:
                            thinking_open = False
                            yield f"data: {json.dumps({'type': 'thinking_end'})}\n\n"
                        if not answer_started:
                            answer_started = True
                            answer_phase = build_phase_message("before_answer", think_level)
                            if answer_phase:
                                yield f"data: {json.dumps({'type': 'phase', 'text': answer_phase, 'stage': 'before_answer'})}\n\n"
                        yield f"data: {json.dumps({'type': 'content', 'text': answer_text})}\n\n"

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "tool")
                    tool_event: dict[str, Any] = {"type": "tool_start", "tool": tool_name}
                    # Enrich task tool events with subagent metadata for branch visualization
                    if tool_name == "task":
                        tool_input = event.get("data", {}).get("input", {})
                        if isinstance(tool_input, dict):
                            tool_event["task_id"] = event.get("run_id", "")
                            tool_event["description"] = tool_input.get("description", "子任务")
                            tool_event["subagent_type"] = tool_input.get("subagent_type", "general")
                    yield f"data: {json.dumps(tool_event)}\n\n"
                    phase_text = build_phase_message("tool_start", think_level, tool_name)
                    if phase_text:
                        yield (
                            "data: "
                            f"{json.dumps({'type': 'phase', 'text': phase_text, 'stage': 'tool_start', 'tool': tool_name})}\n\n"
                        )

                elif kind == "on_tool_end":
                    tool_name = event.get("name", "tool")
                    tool_event = {"type": "tool_end", "tool": tool_name}
                    if tool_name == "task":
                        tool_event["task_id"] = event.get("run_id", "")
                        tool_output = event.get("data", {}).get("output", "")
                        if isinstance(tool_output, str):
                            tool_event["output"] = tool_output[:500]  # cap for SSE
                        tool_event["status"] = "completed"
                    yield f"data: {json.dumps(tool_event)}\n\n"
                    phase_text = build_phase_message("tool_end", think_level, tool_name)
                    if phase_text:
                        yield (
                            "data: "
                            f"{json.dumps({'type': 'phase', 'text': phase_text, 'stage': 'tool_end', 'tool': tool_name})}\n\n"
                        )

                elif kind == "on_chat_model_end":
                    # Extract token usage from the final AIMessage
                    output = event.get("data", {}).get("output")
                    if output is not None:
                        usage = getattr(output, "usage_metadata", None)
                        if usage:
                            input_detail = usage.get("input_token_details", {}) or {}
                            output_detail = usage.get("output_token_details", {}) or {}
                            token_event = {
                                "type": "token_usage",
                                "input_tokens": usage.get("input_tokens", 0),
                                "output_tokens": usage.get("output_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                                "reasoning_tokens": (output_detail.get("reasoning", 0) or 0),
                                "cache_read_tokens": (input_detail.get("cache_read", 0) or 0),
                            }
                            yield f"data: {json.dumps(token_event)}\n\n"

                elif kind == "on_custom_event":
                    # Forward custom events from get_stream_writer()
                    custom_data = event.get("data", {})
                    if isinstance(custom_data, dict) and "type" in custom_data:
                        event_type = custom_data["type"]

                        # Task lifecycle events
                        if event_type in (
                            "task_started", "task_running", "task_completed",
                            "task_failed", "task_timed_out", "task_cancelled",
                        ):
                            safe_data = dict(custom_data)
                            if "message" in safe_data:
                                msg = safe_data["message"]
                                if isinstance(msg, str):
                                    safe_data["message"] = msg[:500]
                                else:
                                    safe_data["message"] = str(msg)[:500]
                            yield f"data: {json.dumps(safe_data)}\n\n"

                        # LLM retry events
                        elif event_type == "llm_retry":
                            safe_data = dict(custom_data)
                            yield f"data: {json.dumps(safe_data)}\n\n"

        except asyncio.CancelledError:
            assistant_status = "interrupted"
            if not "".join(answer_parts).strip():
                answer_parts.append("[已中断]")
            logger.info("Chat stream cancelled for thread %s", thread_id)
            producer.cancel()
            with suppress(asyncio.CancelledError):
                await producer
        except GraphRecursionError:
            assistant_status = "error"
            failure_text = (
                "调研过程超过当前步骤上限，执行被提前停止。"
                "这通常发生在多轮搜索和抓取过多时。"
            )
            logger.warning("Graph recursion limit reached for thread %s", thread_id)
            if not "".join(answer_parts).strip():
                answer_parts.append(f"❌ {failure_text}")
            yield f"data: {json.dumps({'type': 'error', 'text': failure_text})}\n\n"
        except Exception as exc:
            assistant_status = "error"
            failure_text = str(exc)
            logger.error("Stream error: %s", exc)
            if not "".join(answer_parts).strip():
                answer_parts.append(f"❌ {failure_text}")
            yield f"data: {json.dumps({'type': 'error', 'text': failure_text})}\n\n"
        finally:
            if not producer.done():
                producer.cancel()
                with suppress(asyncio.CancelledError):
                    await producer

            if thinking_open:
                yield f"data: {json.dumps({'type': 'thinking_end'})}\n\n"

            # Strip leaked memory JSON from final answer
            final_answer = strip_leaked_memory_json("".join(answer_parts))
            if final_answer != "".join(answer_parts):
                answer_parts.clear()
                answer_parts.append(final_answer)

            if not final_answer.strip() and assistant_status == "completed":
                thread_state = await _load_thread_state(thread_id)
                assistant_message = _latest_visible_message(thread_state.get("messages", []), role="assistant")
                if assistant_message and assistant_message.get("content"):
                    cleaned_content = strip_leaked_memory_json(assistant_message["content"])
                    answer_parts.append(cleaned_content)
                    yield f"data: {json.dumps({'type': 'content', 'text': cleaned_content})}\n\n"

            if assistant_status in {"interrupted", "error"}:
                await manager.touch_thread(
                    thread_id,
                    status=assistant_status,
                    model=selected_model_name,
                    preview="".join(answer_parts) or request.message,
                )

            await _ensure_thread_summary(
                thread_id=thread_id,
                selected_model_name=selected_model_name,
                status="idle" if assistant_status == "completed" else assistant_status,
                request_message=request.message,
            )
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message and get a response (non-streaming)."""

    from langchain_core.messages import HumanMessage

    _require_config()
    selected_model_name, model_config = _resolve_model(request.model)
    mode, reasoning_effort, think_level = resolve_mode_and_effort(
        request.mode, request.reasoning_effort, request.think_level,
    )
    model_runtime_options = build_model_runtime_options(
        model_config, think_level, reasoning_effort=reasoning_effort, mode=mode,
    )
    manager = _require_thread_manager()

    if request.thread_id:
        thread_id = request.thread_id
        try:
            await manager.touch_thread(
                thread_id,
                title=request.message,
                status="busy",
                model=selected_model_name,
                preview=request.message,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        thread = await manager.create_thread(title=request.message, model=selected_model_name)
        thread_id = thread["id"]
        await manager.touch_thread(
            thread_id,
            status="busy",
            model=selected_model_name,
            preview=request.message,
        )

    try:
        active_agent = await _create_runtime_agent(
            selected_model_name=selected_model_name,
            model_runtime_options=model_runtime_options,
            mode=mode,
        )
        await active_agent.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content=request.message,
                        additional_kwargs={"created_at": _utc_now_iso()},
                    )
                ]
            },
            config=_build_agent_run_config(thread_id),
        )

        thread_payload = await manager.get_thread(thread_id, _load_thread_state)
        state = await _load_thread_state(thread_id)
        assistant_message = _latest_visible_message(thread_payload["messages"], role="assistant")
        response_text = assistant_message.get("content", "") if assistant_message else ""

        await manager.touch_thread(
            thread_id,
            title=request.message,
            status="idle",
            model=selected_model_name,
            preview=response_text or request.message,
            message_count=len(thread_payload["messages"]),
        )

        return ChatResponse(
            response=response_text,
            thread_id=thread_id,
            model=selected_model_name,
            artifacts=list(state.get("artifacts") or []),
            active_skills=list(state.get("active_skills") or []),
            pending_clarification=state.get("pending_clarification"),
        )

    except HTTPException:
        raise
    except GraphRecursionError as exc:
        message = (
            "调研过程超过当前步骤上限，执行被提前停止。"
            "建议缩小问题范围，或提高 `runtime.agent_recursion_limit`。"
        )
        logger.warning("Chat recursion limit reached for thread %s", thread_id)
        await manager.touch_thread(
            thread_id,
            status="error",
            model=selected_model_name,
            preview=f"❌ {message}",
        )
        raise HTTPException(status_code=500, detail=message) from exc
    except Exception as exc:
        logger.error("Chat error: %s", exc)
        await manager.touch_thread(
            thread_id,
            status="error",
            model=selected_model_name,
            preview=f"❌ {exc}",
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/models")
async def list_models():
    """List available models."""

    active_config = _require_config()
    return {
        "models": [
            {
                "name": item.name,
                "display_name": item.display_name,
                "supports_vision": item.supports_vision,
                "supports_thinking": item.supports_thinking,
                "supports_reasoning_effort": item.supports_thinking,
            }
            for item in active_config.available_models
        ]
    }


@app.get("/api/skills")
async def list_skills():
    """List available skills."""

    if not skills_loader:
        raise HTTPException(status_code=503, detail="Service not initialized")

    skills = skills_loader.load_skills().values()
    return {
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "enabled": skill.enabled,
                "path": skill.path,
            }
            for skill in skills
        ]
    }


@app.patch("/api/skills/{skill_name}")
async def update_skill(skill_name: str, request: SkillUpdateRequest):
    """Enable or disable a skill."""

    if not skills_loader:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        skill = skills_loader.set_skill_enabled(skill_name, request.enabled)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to update skill %s: %s", skill_name, exc)
        raise HTTPException(status_code=500, detail="Failed to update skill") from exc

    return {
        "skill": {
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
            "path": skill.path,
        }
    }


@app.post("/api/skills/install")
async def install_skill_from_artifact(request: SkillInstallRequest):
    """Install a generated .skill archive or SKILL.md artifact into custom skills."""

    try:
        source = get_paths().resolve_virtual_path(request.thread_id, request.path)
    except ValueError as exc:
        status = 403 if "traversal" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail=f"Skill artifact not found: {request.path}")
    return await _install_skill_from_file(source, request.name)


@app.get("/api/memory")
async def get_memory():
    """Get current memory data."""

    if not memory_storage:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return memory_storage.load()


@app.get("/api/memory/export")
async def export_memory():
    """Export current memory snapshot."""

    if not memory_storage:
        raise HTTPException(status_code=503, detail="Service not initialized")

    return JSONResponse(
        content=memory_storage.load(),
        headers={"Content-Disposition": 'attachment; filename="vdflow-memory-export.json"'},
    )


@app.post("/api/memory/import")
async def import_memory(request: MemoryImportRequest):
    """Import memory snapshot."""

    if not memory_storage:
        raise HTTPException(status_code=503, detail="Service not initialized")

    incoming = _normalize_memory_snapshot(request.memory)
    mode = request.mode.strip().lower()
    if mode not in {"replace", "merge"}:
        raise HTTPException(status_code=400, detail="Memory import mode must be 'replace' or 'merge'")

    current = memory_storage.load()
    snapshot = incoming if mode == "replace" else _merge_memory_snapshots(current, incoming)
    if not memory_storage.save(snapshot):
        raise HTTPException(status_code=500, detail="Failed to import memory")

    saved = memory_storage.load()
    return {
        "success": True,
        "mode": mode,
        "memory": saved,
        "counts": {
            "preferences": len(saved.get("preferences", {})),
            "conversation_history": len(saved.get("conversation_history", [])),
            "facts": len(saved.get("facts", [])),
        },
    }


@app.post("/api/memory/clear")
async def clear_memory():
    """Clear all memory data."""

    if not memory_storage:
        raise HTTPException(status_code=503, detail="Service not initialized")

    memory_storage.save(memory_storage._create_empty_memory())
    return {"success": True, "message": "Memory cleared"}


@app.get("/api/tools/config")
async def get_tools_config():
    """Get runtime tools configuration."""

    active_config = _require_config()
    return _serialize_tools_config(active_config)


@app.patch("/api/tools/config")
async def update_tools_config(request: ToolsConfigUpdateRequest):
    """Persist tools configuration to config.yaml and refresh runtime config."""

    document = _load_raw_config_document()
    if request.tool_groups is not None:
        existing_groups = {
            str(item.get("name")): dict(item)
            for item in list(document.get("tool_groups") or [])
            if isinstance(item, dict) and item.get("name")
        }
        for group in request.tool_groups:
            existing_groups[group.name] = {"name": group.name, "enabled": group.enabled}
        document["tool_groups"] = list(existing_groups.values())

    if request.allow_host_bash is not None:
        runtime = dict(document.get("runtime") or {})
        runtime["allow_host_bash"] = request.allow_host_bash
        document["runtime"] = runtime

    _save_raw_config_document(document)
    active_config = _reload_config_from_disk()
    return _serialize_tools_config(active_config)


@app.get("/api/mcp/config")
async def get_mcp_config():
    """Get MCP server configuration."""

    active_config = _require_config()
    return {
        "enabled": active_config.mcp.enabled,
        "servers": [_serialize_mcp_server(server) for server in active_config.mcp.servers],
    }


@app.patch("/api/mcp/config")
async def update_mcp_config(request: MCPConfigUpdateRequest):
    """Update top-level MCP configuration."""

    document = _load_raw_config_document()
    mcp_doc = dict(document.get("mcp") or {})
    if request.enabled is not None:
        mcp_doc["enabled"] = request.enabled
    mcp_doc.setdefault("servers", [])
    document["mcp"] = mcp_doc
    _save_raw_config_document(document)
    active_config = _reload_config_from_disk()
    return {
        "enabled": active_config.mcp.enabled,
        "servers": [_serialize_mcp_server(server) for server in active_config.mcp.servers],
    }


@app.post("/api/mcp/servers")
async def create_mcp_server(request: MCPServerRequest):
    """Create a new MCP server configuration."""

    server_doc = _normalize_mcp_server_request(request)
    document = _load_raw_config_document()
    mcp_doc = dict(document.get("mcp") or {})
    servers = list(mcp_doc.get("servers") or [])
    if any(isinstance(item, dict) and item.get("name") == server_doc["name"] for item in servers):
        raise HTTPException(status_code=409, detail=f"MCP server '{server_doc['name']}' already exists")
    servers.append(server_doc)
    mcp_doc["servers"] = servers
    mcp_doc.setdefault("enabled", True)
    document["mcp"] = mcp_doc
    _save_raw_config_document(document)
    active_config = _reload_config_from_disk()
    server = next(item for item in active_config.mcp.servers if item.name == server_doc["name"])
    return {"server": _serialize_mcp_server(server)}


@app.patch("/api/mcp/servers/{server_name}")
async def update_mcp_server(server_name: str, request: MCPServerRequest):
    """Update an MCP server configuration."""

    server_doc = _normalize_mcp_server_request(request)
    server_doc["name"] = server_name
    document = _load_raw_config_document()
    mcp_doc = dict(document.get("mcp") or {})
    servers = list(mcp_doc.get("servers") or [])
    updated = False
    next_servers: list[dict[str, Any]] = []
    for item in servers:
        if isinstance(item, dict) and item.get("name") == server_name:
            next_servers.append(server_doc)
            updated = True
        elif isinstance(item, dict):
            next_servers.append(item)
    if not updated:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")
    mcp_doc["servers"] = next_servers
    mcp_doc.setdefault("enabled", True)
    document["mcp"] = mcp_doc
    _save_raw_config_document(document)
    active_config = _reload_config_from_disk()
    server = next(item for item in active_config.mcp.servers if item.name == server_name)
    return {"server": _serialize_mcp_server(server)}


@app.delete("/api/mcp/servers/{server_name}")
async def delete_mcp_server(server_name: str):
    """Delete an MCP server configuration."""

    document = _load_raw_config_document()
    mcp_doc = dict(document.get("mcp") or {})
    servers = list(mcp_doc.get("servers") or [])
    next_servers = [
        item
        for item in servers
        if not (isinstance(item, dict) and item.get("name") == server_name)
    ]
    if len(next_servers) == len(servers):
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")
    mcp_doc["servers"] = next_servers
    document["mcp"] = mcp_doc
    _save_raw_config_document(document)
    _reload_config_from_disk()
    return {"success": True}


@app.post("/api/mcp/servers/{server_name}/discover")
async def discover_mcp_server(server_name: str):
    """Discover tools from one configured MCP server."""

    active_config = _require_config()
    server = next((item for item in active_config.mcp.servers if item.name == server_name), None)
    if server is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")
    runtime_server = RuntimeMCPServerConfig(
        name=server.name,
        transport=server.transport,
        command=server.command,
        args=list(server.args),
        url=server.url,
        env=dict(server.env),
        enabled=server.enabled,
        timeout_seconds=server.timeout_seconds,
    )
    client = MCPClient([runtime_server])
    tools = await client.discover_tools(runtime_server)
    return {
        "server": _serialize_mcp_server(server),
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "server_name": tool.server_name,
            }
            for tool in tools
        ],
        "connected": server_name in client.connected_servers,
    }


if __name__ == "__main__":
    import uvicorn

    try:
        server_config = Config.from_yaml(str(CONFIG_PATH)).server
    except Exception:
        server_config = None

    uvicorn.run(
        "vdflow.web.app:app",
        host=server_config.host if server_config else "0.0.0.0",
        port=server_config.port if server_config else 8000,
        reload=server_config.reload if server_config else True,
    )
