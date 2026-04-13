"""Middleware to interrupt execution when the model asks for clarification."""

from __future__ import annotations

from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from vdflow.agent.middlewares._utils import _state_get, _utc_now_iso
from vdflow.agent.state import PendingClarificationState, ThreadState


class ClarificationMiddleware(AgentMiddleware[ThreadState]):
    """Interrupt execution when the model asks for clarification."""

    state_schema = ThreadState

    def before_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        pending_clarification = _state_get(state, "pending_clarification")
        messages = _state_get(state, "messages", [])
        if pending_clarification is None:
            return None
        if not messages:
            return None
        latest = messages[-1]
        if getattr(latest, "type", "") != "human":
            return None
        return {"pending_clarification": None}

    @staticmethod
    def _format_message(args: dict[str, Any]) -> str:
        question = str(args.get("question", "")).strip()
        context = str(args.get("context") or "").strip()
        options = args.get("options") or []
        lines: list[str] = []
        if context:
            lines.append(context)
        if question:
            lines.append(question)
        if options:
            lines.append("")
            for index, option in enumerate(options, start=1):
                lines.append(f"{index}. {option}")
        return "\n".join(lines).strip()

    def _build_command(self, request: ToolCallRequest) -> Command[Any]:
        args = request.tool_call.get("args", {})
        formatted_message = self._format_message(args)
        pending = PendingClarificationState(
            question=str(args.get("question", "")).strip(),
            clarification_type=str(args.get("clarification_type", "missing_info")),
            context=args.get("context"),
            options=list(args.get("options") or []),
            asked_at=_utc_now_iso(),
        )
        ai_message = AIMessage(
            content=formatted_message,
            additional_kwargs={
                "status": "clarification_needed",
                "created_at": pending.asked_at,
                "clarification_type": pending.clarification_type,
            },
        )
        return Command(
            update={
                "pending_clarification": pending,
                "messages": [ai_message],
            },
            goto=END,
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call.get("name") != "ask_clarification":
            return handler(request)
        return self._build_command(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call.get("name") != "ask_clarification":
            return await handler(request)
        return self._build_command(request)
