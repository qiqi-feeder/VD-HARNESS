"""Lead-agent middleware chain for VD-Flow.

Middleware ordering follows DeerFlow's validated pipeline:

     1. ThreadDataMiddleware       (before_agent)      — workspace dirs
     2. FileUploadMiddleware       (before_model)      — inject uploaded files
     3. SummarizationMiddleware    (before_model)      — long-conversation summarization
     4. DanglingToolCallMiddleware (wrap_model_call)    — fix broken message history
     5. LLMErrorHandlingMiddleware (wrap_model_call)    — error classification + retry
     6. ToolErrorMiddleware        (wrap_tool_call)     — tool exception fallback
     7. SandboxAuditMiddleware     (wrap_tool_call)     — bash command security audit
     8. GuardrailMiddleware        (wrap_tool_call)     — pre-tool-call authorization
     9. TokenUsageMiddleware       (after_model)        — log token consumption
    10. TitleMiddleware            (after_agent)        — derive title
    11. MemoryMiddleware           (before_model + after_agent) — inject + update
    12. LoopDetectionMiddleware    (after_model)        — detect repetitive loops
    13. ClarificationMiddleware    (wrap_tool_call + before_model) — MUST BE LAST

IMPORTANT:
  - SummarizationMiddleware EARLY (reduce context before other processing)
  - DanglingToolCall BEFORE LLMErrorHandling (fix messages first, then call)
  - SandboxAudit + Guardrail AFTER ToolError (security check before execution)
  - Clarification MUST be last (it can halt the run via goto=END)
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel

from vdflow.agent.guardrails.builtin import DefaultGuardrailProvider
from vdflow.agent.guardrails.middleware import GuardrailMiddleware
from vdflow.agent.middlewares.clarification import ClarificationMiddleware
from vdflow.agent.middlewares.context_compressor import ContextCompressorMiddleware
from vdflow.agent.middlewares.dangling_tool_call import DanglingToolCallMiddleware
from vdflow.agent.middlewares.file_upload import FileUploadMiddleware
from vdflow.agent.middlewares.llm_error_handling import LLMErrorHandlingMiddleware
from vdflow.agent.middlewares.loop_detection import LoopDetectionMiddleware
from vdflow.agent.middlewares.memory import MemoryMiddleware
from vdflow.agent.middlewares.sandbox_audit import SandboxAuditMiddleware
from vdflow.agent.middlewares.skill_evolution import SkillEvolutionMiddleware
from vdflow.agent.middlewares.subagent_limit import SubagentLimitMiddleware
from vdflow.agent.middlewares.todo import TodoMiddleware
from vdflow.agent.middlewares.thread_data import ThreadDataMiddleware
from vdflow.agent.middlewares.title import TitleMiddleware
from vdflow.agent.middlewares.token_usage import TokenUsageMiddleware
from vdflow.agent.middlewares.tool_error import ToolErrorMiddleware
from vdflow.config.models import Config, SummarizationConfig
from vdflow.memory import MemoryStorage, MemoryUpdater
from vdflow.skills import Skill

logger = logging.getLogger(__name__)

__all__ = [
    "ClarificationMiddleware",
    "ContextCompressorMiddleware",
    "DanglingToolCallMiddleware",
    "FileUploadMiddleware",
    "GuardrailMiddleware",
    "LLMErrorHandlingMiddleware",
    "LoopDetectionMiddleware",
    "MemoryMiddleware",
    "SandboxAuditMiddleware",
    "SkillEvolutionMiddleware",
    "SubagentLimitMiddleware",
    "ThreadDataMiddleware",
    "TitleMiddleware",
    "TodoMiddleware",
    "TokenUsageMiddleware",
    "ToolErrorMiddleware",
    "build_middlewares",
    "build_subagent_middlewares",
]


def _create_summarization_middleware(
    config: SummarizationConfig,
    model: BaseChatModel,
) -> Any | None:
    """Create a SummarizationMiddleware from config.

    Returns None if summarization is disabled or misconfigured.
    """
    if not config.enabled:
        return None

    try:
        from langchain.agents.middleware import SummarizationMiddleware
    except ImportError:
        logger.warning("SummarizationMiddleware not available in this langchain version")
        return None

    # Prepare trigger parameter
    trigger = None
    if config.trigger is not None:
        if isinstance(config.trigger, list):
            trigger = [t.to_tuple() for t in config.trigger]
        else:
            trigger = config.trigger.to_tuple()

    # Prepare keep parameter
    keep = config.keep.to_tuple()

    kwargs: dict[str, Any] = {
        "model": model,
        "trigger": trigger,
        "keep": keep,
    }

    if config.trim_tokens_to_summarize is not None:
        kwargs["trim_tokens_to_summarize"] = config.trim_tokens_to_summarize

    if config.summary_prompt is not None:
        kwargs["summary_prompt"] = config.summary_prompt

    logger.info(
        "SummarizationMiddleware enabled — trigger=%s, keep=%s",
        trigger,
        keep,
    )
    return SummarizationMiddleware(**kwargs)


def build_subagent_middlewares(config: Config) -> list[AgentMiddleware]:
    """Build a slim middleware chain for subagent execution.

    Keeps safety and error-handling middlewares (DanglingToolCall, LLMError,
    ToolError, SandboxAudit, Guardrail).  Drops lead-agent-only middlewares
    (context compression, summarization, memory, title, todo, skill evolution,
    subagent limit, loop detection, clarification, file upload, thread data).

    This mirrors DeerFlow's ``build_subagent_runtime_middlewares()``.
    """
    mw = config.middleware
    middlewares: list[AgentMiddleware] = []

    # --- Model call protection ---
    if mw.dangling_tool_call_enabled:
        middlewares.append(DanglingToolCallMiddleware())
    if mw.llm_error_handling_enabled:
        middlewares.append(LLMErrorHandlingMiddleware())

    # --- Tool call protection ---
    if mw.tool_error_enabled:
        middlewares.append(ToolErrorMiddleware())
    if mw.sandbox_audit_enabled:
        middlewares.append(SandboxAuditMiddleware())
    if mw.guardrail_enabled:
        middlewares.append(GuardrailMiddleware(DefaultGuardrailProvider()))

    return middlewares


def build_middlewares(
    config: Config,
    *,
    model: BaseChatModel | None = None,
    memory_storage: MemoryStorage | None = None,
    memory_updater: MemoryUpdater | None = None,
    skills: list[Skill] | None = None,
) -> list[AgentMiddleware]:
    """Build the middleware chain in DeerFlow-validated order.

    Args:
        config: Application configuration.
        model: The LLM model instance (needed for SummarizationMiddleware).
        memory_storage: Memory storage backend.
        memory_updater: Memory updater for async persistence.
        skills: Available skills.
    """

    mw = config.middleware
    middlewares: list[AgentMiddleware] = []

    # --- Layer 1: Runtime infra (before_agent / before_model) ---
    if mw.thread_data_enabled:
        middlewares.append(ThreadDataMiddleware(skills=skills))
    if mw.file_upload_enabled:
        middlewares.append(FileUploadMiddleware())

    # --- Layer 2: Context management (before_model) ---
    # ContextCompressor BEFORE Summarization (zero-cost pre-trim, then LLM summarize)
    if mw.context_compressor_enabled:
        middlewares.append(ContextCompressorMiddleware())
    if model is not None:
        summarization_mw = _create_summarization_middleware(config.summarization, model)
        if summarization_mw is not None:
            middlewares.append(summarization_mw)

    # --- Layer 3: Model call protection (wrap_model_call) ---
    if mw.dangling_tool_call_enabled:
        middlewares.append(DanglingToolCallMiddleware())
    if mw.llm_error_handling_enabled:
        middlewares.append(LLMErrorHandlingMiddleware())

    # --- Layer 4: Tool call protection (wrap_tool_call) ---
    if mw.tool_error_enabled:
        middlewares.append(ToolErrorMiddleware())
    if mw.sandbox_audit_enabled:
        middlewares.append(SandboxAuditMiddleware())
    if mw.guardrail_enabled:
        middlewares.append(GuardrailMiddleware(DefaultGuardrailProvider()))

    # --- Layer 5: Post-model processing (after_model / after_agent) ---
    if mw.token_usage_enabled:
        middlewares.append(TokenUsageMiddleware())
    if mw.title_enabled:
        middlewares.append(TitleMiddleware(model=model, use_llm=mw.title_use_llm))
    if mw.memory_enabled and memory_storage is not None:
        middlewares.append(
            MemoryMiddleware(
                memory_storage,
                memory_updater,
                debounce_seconds=config.memory.debounce_seconds,
            )
        )
    if mw.todo_enabled:
        middlewares.append(TodoMiddleware())
    if mw.skill_evolution_enabled:
        middlewares.append(SkillEvolutionMiddleware())
    if mw.subagent_limit_enabled:
        middlewares.append(SubagentLimitMiddleware(max_concurrent=mw.subagent_max_concurrent))
    if mw.loop_detection_enabled:
        middlewares.append(
            LoopDetectionMiddleware(
                warn_threshold=mw.loop_detection_warn_threshold,
                hard_limit=mw.loop_detection_hard_limit,
                window_size=mw.loop_detection_window_size,
            )
        )

    # --- Layer 6: Execution flow control (MUST BE LAST) ---
    if mw.clarification_enabled:
        middlewares.append(ClarificationMiddleware())

    return middlewares
