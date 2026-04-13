"""MCP client — connect to MCP servers and discover tools.

Supports stdio transport with a small JSON-RPC client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    transport: str = "stdio"  # "stdio" | "sse"
    command: str = ""         # for stdio transport
    args: list[str] = field(default_factory=list)
    url: str = ""             # for sse transport
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    timeout_seconds: float = 10.0


@dataclass
class MCPToolSchema:
    """Schema for a tool discovered from an MCP server."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


class MCPClient:
    """Client for connecting to MCP servers and discovering tools.

    Manages lifecycle of MCP server connections and tool schema discovery.
    """

    def __init__(self, servers: list[MCPServerConfig] | None = None):
        self.servers = servers or []
        self._discovered_tools: dict[str, MCPToolSchema] = {}
        self._connected: set[str] = set()
        self._server_by_name = {server.name: server for server in self.servers}

    async def discover_tools(self, server: MCPServerConfig) -> list[MCPToolSchema]:
        """Discover tools from a single MCP server.

        In a full implementation, this would:
        1. Spawn the MCP server process (stdio) or connect via SSE
        2. Send initialize request
        3. Call tools/list to get available tools
        4. Return parsed schemas

        Returns:
            List of discovered tool schemas.
        """
        if not server.enabled:
            return []

        try:
            if server.transport == "stdio":
                return await self._discover_stdio(server)
            elif server.transport in {"sse", "streamable_http"}:
                logger.warning("MCP transport %s is not implemented yet", server.transport)
                return []
            else:
                logger.warning("Unknown MCP transport: %s", server.transport)
                return []
        except Exception as exc:
            logger.error("Failed to discover tools from MCP server %s: %s", server.name, exc)
            return []

    async def _discover_stdio(self, server: MCPServerConfig) -> list[MCPToolSchema]:
        """Discover tools via stdio transport."""
        logger.info("Discovering tools from MCP server %s (stdio: %s)", server.name, server.command)
        if not server.command:
            logger.warning("MCP stdio server %s has no command configured", server.name)
            return []

        result = await self._stdio_request(server, "tools/list")
        raw_tools = result.get("tools", []) if isinstance(result, dict) else []
        tools: list[MCPToolSchema] = []
        for raw_tool in raw_tools:
            if not isinstance(raw_tool, dict):
                continue
            tool_name = str(raw_tool.get("name") or "").strip()
            if not tool_name:
                continue
            input_schema = raw_tool.get("inputSchema") or raw_tool.get("input_schema") or {}
            tools.append(
                MCPToolSchema(
                    name=tool_name,
                    description=str(raw_tool.get("description") or ""),
                    input_schema=input_schema if isinstance(input_schema, dict) else {},
                    server_name=server.name,
                )
            )
        self._connected.add(server.name)
        return tools

    async def _discover_sse(self, server: MCPServerConfig) -> list[MCPToolSchema]:
        """Discover tools via SSE transport."""
        logger.info("Discovering tools from MCP server %s (sse: %s)", server.name, server.url)
        logger.warning("MCP SSE transport is not implemented yet")
        return []

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on an MCP server."""

        server = self._server_by_name.get(server_name)
        if server is None:
            raise ValueError(f"MCP server '{server_name}' is not configured")
        if not server.enabled:
            raise ValueError(f"MCP server '{server_name}' is disabled")
        if server.transport != "stdio":
            raise NotImplementedError(f"MCP transport '{server.transport}' is not implemented yet")

        result = await self._stdio_request(
            server,
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
        return self._format_tool_result(result)

    async def _stdio_request(
        self,
        server: MCPServerConfig,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        env = {**os.environ, **server.env}
        process = await asyncio.create_subprocess_exec(
            server.command,
            *server.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        next_id = 1

        try:
            await self._write_message(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": next_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "vd-flow", "version": "0.1.0"},
                    },
                },
            )
            await self._read_response(process, next_id, timeout=server.timeout_seconds)

            await self._write_message(
                process,
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                },
            )

            next_id += 1
            await self._write_message(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": next_id,
                    "method": method,
                    "params": params or {},
                },
            )
            return await self._read_response(process, next_id, timeout=server.timeout_seconds)
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

    async def _write_message(self, process: asyncio.subprocess.Process, message: dict[str, Any]) -> None:
        if process.stdin is None:
            raise RuntimeError("MCP server stdin is not available")
        process.stdin.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        await process.stdin.drain()

    async def _read_response(
        self,
        process: asyncio.subprocess.Process,
        expected_id: int,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        async def _read() -> dict[str, Any]:
            if process.stdout is None:
                raise RuntimeError("MCP server stdout is not available")
            while True:
                line = await process.stdout.readline()
                if not line:
                    stderr = ""
                    if process.stderr is not None:
                        stderr_bytes = await process.stderr.read()
                        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
                    raise RuntimeError(f"MCP server exited before response. {stderr}".strip())
                payload = json.loads(line.decode("utf-8"))
                if payload.get("id") != expected_id:
                    continue
                if payload.get("error"):
                    raise RuntimeError(f"MCP error: {payload['error']}")
                result = payload.get("result") or {}
                return result if isinstance(result, dict) else {"value": result}

        return await asyncio.wait_for(_read(), timeout=timeout)

    def _format_tool_result(self, result: dict[str, Any]) -> str:
        content = result.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    parts.append(str(item))
                    continue
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            return "\n".join(part for part in parts if part)
        if "structuredContent" in result:
            return json.dumps(result["structuredContent"], ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)

    async def discover_all(self) -> list[MCPToolSchema]:
        """Discover tools from all configured servers."""
        all_tools: list[MCPToolSchema] = []
        for server in self.servers:
            if server.enabled:
                tools = await self.discover_tools(server)
                all_tools.extend(tools)
                for tool in tools:
                    self._discovered_tools[tool.name] = tool
        logger.info("Discovered %d MCP tools from %d servers", len(all_tools), len(self.servers))
        return all_tools

    def get_discovered_tools(self) -> dict[str, MCPToolSchema]:
        """Get all discovered tool schemas."""
        return dict(self._discovered_tools)

    @property
    def connected_servers(self) -> set[str]:
        return set(self._connected)
