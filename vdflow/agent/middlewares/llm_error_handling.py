"""LLM error handling middleware with error classification, retry/backoff, and user-facing fallbacks.

Classifies LLM errors into categories (quota, auth, transient, busy, overflow, generic)
and applies appropriate recovery strategies:
- Transient/busy: exponential backoff with retry, Retry-After header parsing
- Quota/auth: immediate user-facing message, no retry
- Overflow: signal context compression needed
- SSE retry events pushed to frontend via stream_writer

Ported from DeerFlow's LLMErrorHandlingMiddleware with Hermes overflow classification.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from email.utils import parsedate_to_datetime
from typing import Any
from typing_extensions import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error pattern catalogs (Chinese + English)
# ---------------------------------------------------------------------------

_RETRIABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

_BUSY_PATTERNS = (
    "server busy",
    "temporarily unavailable",
    "try again later",
    "please retry",
    "please try again",
    "overloaded",
    "high demand",
    "rate limit",
    "负载较高",
    "服务繁忙",
    "稍后重试",
    "请稍后重试",
)

_NETWORK_PATTERNS = (
    "network error",
    "connection error",
    "connection reset",
    "connection refused",
    "connection aborted",
    "connection closed",
    "connect timeout",
    "read timeout",
    "timed out",
    "eof occurred",
    "broken pipe",
    "ssl error",
    "remote disconnected",
    "网络错误",
    "连接超时",
    "连接失败",
    "网络异常",
)

_QUOTA_PATTERNS = (
    "insufficient_quota",
    "quota",
    "billing",
    "credit",
    "payment",
    "余额不足",
    "超出限额",
    "额度不足",
    "欠费",
)

_AUTH_PATTERNS = (
    "authentication",
    "unauthorized",
    "invalid api key",
    "invalid_api_key",
    "permission",
    "forbidden",
    "access denied",
    "无权",
    "未授权",
)

_OVERFLOW_PATTERNS = (
    "context length",
    "context_length_exceeded",
    "maximum context length",
    "token limit",
    "too many tokens",
    "reduce the length",
    "max_tokens",
    "context window",
    "上下文长度",
    "超出最大长度",
    "tokens exceeded",
)

_RUNTIME_PATTERNS = (
    "event loop is closed",
    "event loop is already running",
    "cannot schedule new futures",
    "cannot run nested event loops",
    "interpreter shutdown",
    "no current event loop",
)


class LLMErrorHandlingMiddleware(AgentMiddleware[AgentState]):
    """Classify LLM errors, retry transient ones, and surface graceful messages.

    Without this middleware any LLM error kills the entire agent run.
    """

    retry_max_attempts: int = 5
    retry_base_delay_ms: int = 1000
    retry_cap_delay_ms: int = 15000

    # ------------------------------------------------------------------
    # Error classification
    # ------------------------------------------------------------------

    def _classify_error(self, exc: BaseException) -> tuple[bool, str]:
        """Classify an exception into (retriable, reason).

        Returns:
            (retriable, reason) where reason is one of:
            'quota', 'auth', 'overflow', 'runtime', 'transient', 'busy', 'generic'
        """
        detail = _extract_error_detail(exc)
        lowered = detail.lower()
        error_code = _extract_error_code(exc)
        status_code = _extract_status_code(exc)

        # Non-retriable categories first
        if _matches_any(lowered, _QUOTA_PATTERNS) or _matches_any(
            str(error_code).lower(), _QUOTA_PATTERNS
        ):
            return False, "quota"
        if _matches_any(lowered, _AUTH_PATTERNS):
            return False, "auth"
        if _matches_any(lowered, _OVERFLOW_PATTERNS):
            return False, "overflow"
        if _matches_any(lowered, _RUNTIME_PATTERNS):
            return False, "runtime"

        # Retriable by exception class name
        exc_name = exc.__class__.__name__
        if exc_name in {
            "APITimeoutError",
            "APIConnectionError",
            "InternalServerError",
            "ConnectError",
            "ReadTimeout",
            "ConnectTimeout",
            "RemoteProtocolError",
            "ReadError",
        }:
            return True, "transient"

        # Retriable by base exception type
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True, "transient"

        # Retriable by HTTP status code
        if status_code in _RETRIABLE_STATUS_CODES:
            return True, "transient"

        # Retriable by message pattern — network errors
        if _matches_any(lowered, _NETWORK_PATTERNS):
            return True, "transient"

        # Retriable by message pattern — busy/overloaded
        if _matches_any(lowered, _BUSY_PATTERNS):
            return True, "busy"

        return False, "generic"

    # ------------------------------------------------------------------
    # Retry delay calculation
    # ------------------------------------------------------------------

    def _build_retry_delay_ms(self, attempt: int, exc: BaseException) -> int:
        """Calculate retry delay, preferring Retry-After header."""
        retry_after = _extract_retry_after_ms(exc)
        if retry_after is not None:
            return retry_after
        backoff = self.retry_base_delay_ms * (2 ** max(0, attempt - 1))
        return min(backoff, self.retry_cap_delay_ms)

    # ------------------------------------------------------------------
    # User-facing messages
    # ------------------------------------------------------------------

    def _build_retry_message(self, attempt: int, wait_ms: int, reason: str) -> str:
        seconds = max(1, round(wait_ms / 1000))
        reason_text = {
            "busy": "模型服务繁忙",
            "transient": "网络或服务暂时不可用",
        }.get(reason, "模型请求暂时失败")
        return f"正在重试 {attempt}/{self.retry_max_attempts}：{reason_text}，{seconds}s 后重试..."

    def _build_user_message(self, exc: BaseException, reason: str) -> str:
        detail = _extract_error_detail(exc)
        if reason == "quota":
            return (
                "模型服务因余额不足或使用受限拒绝了请求。"
                "请检查 API 账户额度后重试。"
            )
        if reason == "auth":
            return (
                "模型服务因鉴权失败拒绝了请求。"
                "请检查 API Key 配置后重试。"
            )
        if reason == "overflow":
            return (
                "对话上下文超出模型最大长度。"
                "系统将自动压缩上下文，请重新发送消息。"
            )
        if reason in {"busy", "transient"}:
            return (
                "模型服务在多次重试后仍不可用。"
                "请稍等片刻后继续对话。"
            )
        if reason == "runtime":
            return "系统内部运行异常，请重试。"
        return f"模型请求失败：{detail}"

    # ------------------------------------------------------------------
    # SSE retry event
    # ------------------------------------------------------------------

    def _emit_retry_event(self, attempt: int, wait_ms: int, reason: str) -> None:
        """Push a retry status event to the frontend via stream writer."""
        try:
            from langgraph.config import get_stream_writer

            writer = get_stream_writer()
            writer(
                {
                    "type": "llm_retry",
                    "attempt": attempt,
                    "max_attempts": self.retry_max_attempts,
                    "wait_ms": wait_ms,
                    "reason": reason,
                    "message": self._build_retry_message(attempt, wait_ms, reason),
                }
            )
        except Exception:
            logger.debug("Failed to emit llm_retry event", exc_info=True)

    # ------------------------------------------------------------------
    # wrap_model_call (sync)
    # ------------------------------------------------------------------

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        attempt = 1
        while True:
            try:
                return handler(request)
            except Exception as exc:
                # Preserve LangGraph control-flow signals
                if _is_graph_bubble_up(exc):
                    raise
                retriable, reason = self._classify_error(exc)
                if retriable and attempt < self.retry_max_attempts:
                    wait_ms = self._build_retry_delay_ms(attempt, exc)
                    logger.warning(
                        "Transient LLM error on attempt %d/%d; retrying in %dms: %s",
                        attempt,
                        self.retry_max_attempts,
                        wait_ms,
                        _extract_error_detail(exc),
                    )
                    self._emit_retry_event(attempt, wait_ms, reason)
                    time.sleep(wait_ms / 1000)
                    attempt += 1
                    continue
                logger.warning(
                    "LLM call failed after %d attempt(s) [%s]: %s",
                    attempt,
                    reason,
                    _extract_error_detail(exc),
                    exc_info=exc,
                )
                return AIMessage(content=self._build_user_message(exc, reason))

    # ------------------------------------------------------------------
    # awrap_model_call (async)
    # ------------------------------------------------------------------

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        attempt = 1
        while True:
            try:
                return await handler(request)
            except Exception as exc:
                if _is_graph_bubble_up(exc):
                    raise
                retriable, reason = self._classify_error(exc)
                if retriable and attempt < self.retry_max_attempts:
                    wait_ms = self._build_retry_delay_ms(attempt, exc)
                    logger.warning(
                        "Transient LLM error on attempt %d/%d; retrying in %dms: %s",
                        attempt,
                        self.retry_max_attempts,
                        wait_ms,
                        _extract_error_detail(exc),
                    )
                    self._emit_retry_event(attempt, wait_ms, reason)
                    await asyncio.sleep(wait_ms / 1000)
                    attempt += 1
                    continue
                logger.warning(
                    "LLM call failed after %d attempt(s) [%s]: %s",
                    attempt,
                    reason,
                    _extract_error_detail(exc),
                    exc_info=exc,
                )
                return AIMessage(content=self._build_user_message(exc, reason))


# ---------------------------------------------------------------------------
# Helper functions (module-level, testable)
# ---------------------------------------------------------------------------


def _is_graph_bubble_up(exc: BaseException) -> bool:
    """Check if exception is a LangGraph control-flow signal."""
    try:
        from langgraph.errors import GraphBubbleUp

        return isinstance(exc, GraphBubbleUp)
    except ImportError:
        return False


def _matches_any(detail: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in detail for pattern in patterns)


def _extract_error_code(exc: BaseException) -> Any:
    """Extract error code from various exception formats."""
    for attr in ("code", "error_code"):
        value = getattr(exc, attr, None)
        if value not in (None, ""):
            return value

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            for key in ("code", "type"):
                value = error.get(key)
                if value not in (None, ""):
                    return value
    return None


def _extract_status_code(exc: BaseException) -> int | None:
    """Extract HTTP status code from exception or its response."""
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _extract_retry_after_ms(exc: BaseException) -> int | None:
    """Parse Retry-After / Retry-After-Ms header from exception's response."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None

    raw = None
    header_name = ""
    for key in ("retry-after-ms", "Retry-After-Ms", "retry-after", "Retry-After"):
        header_name = key
        if hasattr(headers, "get"):
            raw = headers.get(key)
        if raw:
            break
    if not raw:
        return None

    try:
        multiplier = 1 if "ms" in header_name.lower() else 1000
        return max(0, int(float(raw) * multiplier))
    except (TypeError, ValueError):
        try:
            target = parsedate_to_datetime(str(raw))
            delta = target.timestamp() - time.time()
            return max(0, int(delta * 1000))
        except (TypeError, ValueError, OverflowError):
            return None


def _extract_error_detail(exc: BaseException) -> str:
    """Get a human-readable error detail from an exception."""
    detail = str(exc).strip()
    if detail:
        return detail
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message.strip():
        return message.strip()
    return exc.__class__.__name__
