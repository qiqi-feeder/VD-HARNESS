"""MCP tool cache — startup-time caching of discovered MCP tool schemas.

Wraps discovered MCP tools as LangChain-compatible tool objects
so they can be merged into get_available_tools().
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr, create_model

from vdflow.mcp.client import MCPClient, MCPServerConfig, MCPToolSchema

logger = logging.getLogger(__name__)

# Module-level cache
_tool_cache: list[Any] = []
_cache_loaded: bool = False


def _safe_tool_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return normalized or "mcp_tool"


def _type_from_json_schema(schema: dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        return list[Any]
    if schema_type == "object":
        return dict[str, Any]
    return Any


def _args_model_from_schema(tool_name: str, input_schema: dict[str, Any]) -> type[BaseModel]:
    properties = input_schema.get("properties") if isinstance(input_schema, dict) else None
    if not isinstance(properties, dict) or not properties:
        return create_model(f"{_safe_tool_name(tool_name)}Args")

    required = set(input_schema.get("required") or [])
    fields: dict[str, Any] = {}
    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            field_schema = {}
        field_type = _type_from_json_schema(field_schema)
        description = str(field_schema.get("description") or "")
        default = ... if field_name in required else None
        fields[str(field_name)] = (field_type, Field(default, description=description))
    return create_model(f"{_safe_tool_name(tool_name)}Args", **fields)


class MCPRuntimeTool(BaseTool):
    """LangChain tool wrapper that proxies execution to an MCP server."""

    _client: MCPClient = PrivateAttr()
    _schema: MCPToolSchema = PrivateAttr()

    def __init__(self, *, client: MCPClient, schema: MCPToolSchema):
        public_name = _safe_tool_name(f"mcp_{schema.server_name}_{schema.name}")
        super().__init__(
            name=public_name,
            description=f"[MCP:{schema.server_name}:{schema.name}] {schema.description}".strip(),
            args_schema=_args_model_from_schema(public_name, schema.input_schema),
        )
        self._client = client
        self._schema = schema

    def _run(self, **kwargs: Any) -> str:
        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, **kwargs: Any) -> str:
        return await self._client.call_tool(self._schema.server_name, self._schema.name, kwargs)


def _wrap_mcp_tool(client: MCPClient, schema: MCPToolSchema) -> BaseTool:
    """Wrap an MCP tool schema as a LangChain StructuredTool.

    The execution proxies each call to the configured MCP server.
    """

    return MCPRuntimeTool(client=client, schema=schema)


class MCPToolCache:
    """Cache for MCP-discovered tools."""

    def __init__(self, client: MCPClient):
        self.client = client
        self._tools: list[Any] = []
        self._loaded = False

    async def load(self) -> list[Any]:
        """Discover all MCP tools and cache them as LangChain tools."""
        if self._loaded:
            return self._tools

        schemas = await self.client.discover_all()
        self._tools = [_wrap_mcp_tool(self.client, s) for s in schemas]
        self._loaded = True
        logger.info("MCPToolCache: cached %d tools", len(self._tools))
        return self._tools

    def get_tools(self) -> list[Any]:
        """Get cached tools (empty if not yet loaded)."""
        return list(self._tools)

    @property
    def is_loaded(self) -> bool:
        return self._loaded


def get_cached_mcp_tools() -> list[Any]:
    """Get module-level cached MCP tools."""
    return list(_tool_cache)


async def load_mcp_tools(servers: list[MCPServerConfig]) -> list[Any]:
    """Load MCP tools from servers and cache them module-level."""
    global _tool_cache, _cache_loaded
    client = MCPClient(servers)
    cache = MCPToolCache(client)
    _tool_cache = await cache.load()
    _cache_loaded = True
    return _tool_cache
