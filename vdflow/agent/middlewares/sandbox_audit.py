"""SandboxAuditMiddleware — bash command security auditing.

Intercepts bash tool calls and classifies commands as high-risk (block),
medium-risk (warn), or safe (pass).

High-risk commands (rm -rf /, curl|sh, fork bombs) are blocked entirely.
Medium-risk commands (pip install, chmod 777) are warned but allowed.

Ported from DeerFlow's SandboxAuditMiddleware.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from typing_extensions import override

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from vdflow.agent.state import ThreadState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Command classification rules (compiled once at import time)
# ---------------------------------------------------------------------------

_HIGH_RISK_PATTERNS: list[re.Pattern[str]] = [
    # Recursive delete of critical directories
    re.compile(r"rm\s+-[^\s]*r[^\s]*\s+(/\*?|~/?\\*?|/home\b|/root\b)\s*$"),
    # Raw disk write
    re.compile(r"dd\s+if="),
    # Filesystem format
    re.compile(r"mkfs"),
    # Shadow file read
    re.compile(r"cat\s+/etc/shadow"),
    # Overwrite system config
    re.compile(r">+\s*/etc/"),
    # Pipe to shell (generalized)
    re.compile(r"\|\s*(ba)?sh\b"),
    # Command substitution with dangerous executables
    re.compile(r"[`$]\(?\s*(curl|wget|bash|sh|python|ruby|perl|base64)"),
    # Base64 decode piped to execution
    re.compile(r"base64\s+.*-d.*\|"),
    # Overwrite system binaries
    re.compile(r">+\s*(/usr/bin/|/bin/|/sbin/)"),
    # Overwrite shell startup files
    re.compile(r">+\s*~/?\\.(bashrc|profile|zshrc|bash_profile)"),
    # Process environment leakage
    re.compile(r"/proc/[^/]+/environ"),
    # Dynamic linker hijack
    re.compile(r"\b(LD_PRELOAD|LD_LIBRARY_PATH)\s*="),
    # Bash built-in networking (bypasses tool allowlists)
    re.compile(r"/dev/tcp/"),
    # Fork bomb patterns
    re.compile(r"\S+\(\)\s*\{[^}]*\|\s*\S+\s*&"),
    re.compile(r"while\s+true.*&\s*done"),
]

_MEDIUM_RISK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"chmod\s+777"),
    re.compile(r"pip3?\s+install"),
    re.compile(r"apt(-get)?\s+install"),
    re.compile(r"\b(sudo|su)\b"),
    re.compile(r"\bPATH\s*="),
]


# ---------------------------------------------------------------------------
# Command splitting (quote-aware)
# ---------------------------------------------------------------------------


def _split_compound_command(command: str) -> list[str]:
    """Split compound commands on unquoted shell operators (; && ||).

    Quote-aware: operators inside quotes are ignored.
    Unclosed quote or dangling escape → return whole command (fail-closed).
    """
    parts: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    escaping = False
    index = 0

    while index < len(command):
        char = command[index]

        if escaping:
            current.append(char)
            escaping = False
            index += 1
            continue

        if char == "\\" and not in_single_quote:
            current.append(char)
            escaping = True
            index += 1
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(char)
            index += 1
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(char)
            index += 1
            continue

        if not in_single_quote and not in_double_quote:
            if command.startswith("&&", index) or command.startswith("||", index):
                part = "".join(current).strip()
                if part:
                    parts.append(part)
                current = []
                index += 2
                continue
            if char == ";":
                part = "".join(current).strip()
                if part:
                    parts.append(part)
                current = []
                index += 1
                continue

        current.append(char)
        index += 1

    # Unclosed quote or dangling escape → fail-closed
    if in_single_quote or in_double_quote or escaping:
        return [command]

    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts if parts else [command]


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------


def _classify_single_command(command: str) -> str:
    """Classify a single (non-compound) command. Return 'block', 'warn', or 'pass'."""
    normalized = " ".join(command.split())

    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(normalized):
            return "block"

    # Also try shlex-parsed tokens for high-risk detection
    try:
        tokens = shlex.split(command)
        joined = " ".join(tokens)
        for pattern in _HIGH_RISK_PATTERNS:
            if pattern.search(joined):
                return "block"
    except ValueError:
        # shlex.split fails on unclosed quotes — treat as suspicious
        return "block"

    for pattern in _MEDIUM_RISK_PATTERNS:
        if pattern.search(normalized):
            return "warn"

    return "pass"


def _classify_command(command: str) -> str:
    """Return 'block', 'warn', or 'pass'.

    Strategy:
    1. First scan the *whole* raw command against high-risk patterns (catches
       structural attacks like fork bombs that span multiple statements).
    2. Then split compound commands and classify each sub-command independently.
       The most severe verdict wins.
    """
    # Pass 1: whole-command high-risk scan
    normalized = " ".join(command.split())
    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(normalized):
            return "block"

    # Pass 2: per-sub-command classification
    sub_commands = _split_compound_command(command)
    worst = "pass"
    for sub in sub_commands:
        verdict = _classify_single_command(sub)
        if verdict == "block":
            return "block"
        if verdict == "warn":
            worst = "warn"
    return worst


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

_MAX_COMMAND_LENGTH = 10_000
_AUDIT_COMMAND_LIMIT = 200


class SandboxAuditMiddleware(AgentMiddleware[ThreadState]):
    """Bash command security auditing middleware.

    For every ``bash`` tool call:
    1. **Input validation**: reject malformed input (empty, too long, null bytes).
    2. **Command classification**: regex + shlex analysis grades commands as
       high-risk (block), medium-risk (warn), or safe (pass).
    3. **Audit log**: every bash call is recorded as structured JSON.

    High-risk commands are blocked; medium-risk commands are warned.
    """

    state_schema = ThreadState

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def _validate_input(self, command: str) -> str | None:
        """Return None if acceptable, else a rejection reason."""
        if not command.strip():
            return "empty command"
        if len(command) > _MAX_COMMAND_LENGTH:
            return "command too long"
        if "\x00" in command:
            return "null byte detected"
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_thread_id(self, request: ToolCallRequest) -> str | None:
        runtime = request.runtime
        if runtime is None:
            return None
        ctx = getattr(runtime, "context", None) or {}
        thread_id = ctx.get("thread_id") if isinstance(ctx, dict) else None
        if thread_id is None:
            cfg = getattr(runtime, "config", None) or {}
            thread_id = cfg.get("configurable", {}).get("thread_id")
        return thread_id

    def _write_audit(
        self, thread_id: str | None, command: str, verdict: str, *, truncate: bool = False
    ) -> None:
        audited_command = command
        if truncate and len(command) > _AUDIT_COMMAND_LIMIT:
            audited_command = f"{command[:_AUDIT_COMMAND_LIMIT]}... ({len(command)} chars)"
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "thread_id": thread_id or "unknown",
            "command": audited_command,
            "verdict": verdict,
        }
        logger.info("[SandboxAudit] %s", json.dumps(record, ensure_ascii=False))

    def _build_block_message(self, request: ToolCallRequest, reason: str) -> ToolMessage:
        tool_call_id = str(request.tool_call.get("id") or "missing_id")
        return ToolMessage(
            content=f"Command blocked: {reason}. Please use a safer alternative approach.",
            tool_call_id=tool_call_id,
            name="bash",
            status="error",
        )

    def _append_warn_to_result(
        self, result: ToolMessage | Command[Any], command: str
    ) -> ToolMessage | Command[Any]:
        """Append a warning note to the tool result for medium-risk commands."""
        if not isinstance(result, ToolMessage):
            return result
        warning = f"\n\n⚠️ Warning: `{command}` is a medium-risk command that may modify the runtime environment."
        if isinstance(result.content, list):
            new_content = list(result.content) + [{"type": "text", "text": warning}]
        else:
            new_content = str(result.content) + warning
        return ToolMessage(
            content=new_content,
            tool_call_id=result.tool_call_id,
            name=result.name,
            status=result.status,
        )

    # ------------------------------------------------------------------
    # Core pre-processing
    # ------------------------------------------------------------------

    def _pre_process(
        self, request: ToolCallRequest
    ) -> tuple[str, str | None, str, str | None]:
        """Return (command, thread_id, verdict, reject_reason)."""
        args = request.tool_call.get("args", {})
        raw_command = args.get("command")
        command = raw_command if isinstance(raw_command, str) else ""
        thread_id = self._get_thread_id(request)

        # Input validation
        reject_reason = self._validate_input(command)
        if reject_reason:
            self._write_audit(thread_id, command, "block", truncate=True)
            logger.warning(
                "[SandboxAudit] INVALID INPUT thread=%s reason=%s",
                thread_id,
                reject_reason,
            )
            return command, thread_id, "block", reject_reason

        # Classify
        verdict = _classify_command(command)
        self._write_audit(thread_id, command, verdict)

        if verdict == "block":
            logger.warning("[SandboxAudit] BLOCKED thread=%s cmd=%r", thread_id, command)
        elif verdict == "warn":
            logger.warning(
                "[SandboxAudit] WARN (medium-risk) thread=%s cmd=%r",
                thread_id,
                command,
            )

        return command, thread_id, verdict, None

    # ------------------------------------------------------------------
    # wrap_tool_call hooks
    # ------------------------------------------------------------------

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call.get("name") != "bash":
            return handler(request)

        command, _, verdict, reject_reason = self._pre_process(request)
        if verdict == "block":
            reason = reject_reason or "security violation detected"
            return self._build_block_message(request, reason)
        result = handler(request)
        if verdict == "warn":
            result = self._append_warn_to_result(result, command)
        return result

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call.get("name") != "bash":
            return await handler(request)

        command, _, verdict, reject_reason = self._pre_process(request)
        if verdict == "block":
            reason = reject_reason or "security violation detected"
            return self._build_block_message(request, reason)
        result = await handler(request)
        if verdict == "warn":
            result = self._append_warn_to_result(result, command)
        return result
