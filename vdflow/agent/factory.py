"""Lead-agent factory for VD-Flow."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from langchain.agents import create_agent as create_langchain_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from vdflow.agent.middlewares import build_middlewares
from vdflow.agent.prompt import load_lead_prompt
from vdflow.agent.state import ThreadState
from vdflow.config.models import Config, ModelConfig
from vdflow.memory import MemoryStorage, MemoryUpdater
from vdflow.skills import Skill

logger = logging.getLogger(__name__)


def create_chat_model(config: ModelConfig, **kwargs: Any) -> BaseChatModel:
    """Create a chat model from configuration."""

    module_path, class_name = config.use.rsplit(":", 1)
    module = importlib.import_module(module_path)
    model_class = getattr(module, class_name)

    model_kwargs = {
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        **kwargs,
    }
    if config.api_key:
        model_kwargs["api_key"] = config.api_key
    if config.base_url:
        model_kwargs["base_url"] = config.base_url

    extra_fields = config.model_dump(exclude_unset=True)
    for field in (
        "name",
        "display_name",
        "use",
        "model",
        "api_key",
        "base_url",
        "temperature",
        "max_tokens",
        "supports_vision",
        "supports_thinking",
        "when_thinking_enabled",
        "when_thinking_disabled",
    ):
        extra_fields.pop(field, None)
    model_kwargs.update(extra_fields)
    return model_class(**model_kwargs)


def resolve_model_config(config: Config, model_name: str | None = None) -> ModelConfig:
    """Resolve an available model config."""

    available = config.available_models
    if model_name:
        model_config = next((model for model in available if model.name == model_name), None)
        if model_config is not None:
            return model_config
        exists = any(model.name == model_name for model in config.models)
        if exists:
            raise ValueError(
                f"Model '{model_name}' exists but does not have a valid API key. Please check your .env file."
            )
        raise ValueError(f"Model '{model_name}' not found in configuration")

    if not available:
        raise ValueError("No models with valid API keys configured. Please set API keys in your .env file.")
    return available[0]


def create_agent(
    config: Config,
    model_name: str | None = None,
    tools: list[BaseTool] | None = None,
    system_prompt: str | None = None,
    model_kwargs: dict[str, Any] | None = None,
    checkpointer: Any | None = None,
    store: Any | None = None,
    skills: list[Skill] | None = None,
    memory_storage: MemoryStorage | None = None,
    subagent_enabled: bool = False,
    agent_name: str | None = None,
    agent_soul: str | None = None,
    is_subagent: bool = False,
    **kwargs: Any,
) -> CompiledStateGraph:
    """Create an agent runtime.

    When ``is_subagent=True``, builds a slim middleware chain (safety only)
    suitable for ephemeral subagent execution.
    """

    model_config = resolve_model_config(config, model_name)
    model = create_chat_model(model_config, **(model_kwargs or {}))

    if system_prompt is None:
        system_prompt = load_lead_prompt(
            config,
            skills,
            subagent_enabled=subagent_enabled,
            agent_name=agent_name,
            agent_soul=agent_soul,
        )

    if is_subagent:
        from vdflow.agent.middlewares import build_subagent_middlewares
        middlewares = build_subagent_middlewares(config)
    else:
        memory_updater = None
        if config.memory.enabled and memory_storage is not None:
            memory_updater = MemoryUpdater(memory_storage, model)
        middlewares = build_middlewares(
            config,
            model=model,
            memory_storage=memory_storage,
            memory_updater=memory_updater,
            skills=skills,
        )

    agent = create_langchain_agent(
        model=model,
        tools=tools or [],
        middleware=middlewares,
        state_schema=ThreadState,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        store=store,
        **kwargs,
    )
    logger.info(
        "%s created successfully with model: %s",
        "Subagent" if is_subagent else "Lead agent",
        model_config.name,
    )
    return agent
