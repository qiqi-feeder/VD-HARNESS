"""Configuration models for VD-Flow."""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field
from yaml import safe_load


class ModelConfig(BaseModel):
    """Configuration for an LLM model."""

    name: str
    display_name: str
    use: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    supports_vision: bool = False
    supports_thinking: bool = False
    when_thinking_enabled: dict[str, Any] | None = None
    when_thinking_disabled: dict[str, Any] | None = None

    model_config = {"extra": "allow"}

    def has_valid_api_key(self) -> bool:
        """Check whether the model has a usable API key."""

        if not self.api_key:
            return False
        key = self.api_key.strip()
        if not key:
            return False
        if key.startswith("$"):
            return False
        if key.startswith("your-") and key.endswith("-here"):
            return False
        if key in {"dummy", "sk-xxx", "test", "placeholder"}:
            return False
        return True


class MemoryConfig(BaseModel):
    """Configuration for memory system."""

    enabled: bool = True
    sqlite_path: str = "data/agent.db"
    max_facts: int = 100
    fact_confidence_threshold: float = 0.7
    injection_enabled: bool = True
    max_injection_tokens: int = 2000
    debounce_seconds: int = 30


class SkillsConfig(BaseModel):
    """Configuration for skills system."""

    path: str = "skills"
    public_path: str = "skills/public"
    custom_path: str = "skills/custom"
    container_path: str = "/mnt/skills"
    enabled_by_default: bool = True


class ToolGroupConfig(BaseModel):
    """Logical grouping for tools."""

    name: str
    enabled: bool = True


class ToolConfig(BaseModel):
    """Configuration for a tool."""

    name: str
    use: str
    group: str | None = None
    enabled: bool = True
    requires_vision: bool = False
    host_only: bool = False

    model_config = {"extra": "allow"}


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    name: str
    transport: Literal["stdio", "sse", "streamable_http"] = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    timeout_seconds: float = 10.0


class MCPConfig(BaseModel):
    """MCP runtime configuration."""

    enabled: bool = True
    servers: list[MCPServerConfig] = Field(default_factory=list)


class LeadPromptConfig(BaseModel):
    """Prompt behavior toggles for the lead agent."""

    enforce_clarification_first: bool = True
    encourage_skill_loading_for_complex_tasks: bool = True
    require_citations_for_web_results: bool = True


class ContextSizeSpec(BaseModel):
    """Context size specification for summarization trigger/keep."""

    type: Literal["fraction", "tokens", "messages"] = "tokens"
    value: Union[int, float] = 15564

    def to_tuple(self) -> tuple[str, Union[int, float]]:
        """Convert to tuple format expected by SummarizationMiddleware."""
        return (self.type, self.value)


class SummarizationConfig(BaseModel):
    """Configuration for automatic conversation summarization.

    Ported from DeerFlow's SummarizationConfig.
    """

    enabled: bool = True
    model_name: str | None = None
    trigger: ContextSizeSpec | list[ContextSizeSpec] | None = Field(
        default_factory=lambda: [
            ContextSizeSpec(type="tokens", value=15564),
        ]
    )
    keep: ContextSizeSpec = Field(
        default_factory=lambda: ContextSizeSpec(type="messages", value=10)
    )
    trim_tokens_to_summarize: int | None = 15564
    summary_prompt: str | None = None


class MiddlewareConfig(BaseModel):
    """Configurable middleware toggles."""

    thread_data_enabled: bool = True
    file_upload_enabled: bool = True
    context_compressor_enabled: bool = True
    dangling_tool_call_enabled: bool = True
    llm_error_handling_enabled: bool = True
    tool_error_enabled: bool = True
    sandbox_audit_enabled: bool = True
    guardrail_enabled: bool = True
    title_enabled: bool = True
    title_use_llm: bool = True
    memory_enabled: bool = True
    todo_enabled: bool = True
    skill_evolution_enabled: bool = True
    subagent_limit_enabled: bool = True
    subagent_max_concurrent: int = 3
    token_usage_enabled: bool = True
    loop_detection_enabled: bool = True
    loop_detection_warn_threshold: int = 3
    loop_detection_hard_limit: int = 5
    loop_detection_window_size: int = 20
    clarification_enabled: bool = True


class RuntimeConfig(BaseModel):
    """Execution environment toggles."""

    allow_host_bash: bool = True
    agent_recursion_limit: int = 500
    stream_heartbeat_seconds: int = 10


class ServerConfig(BaseModel):
    """Configuration for web server."""

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    reload: bool = True


class ThreadsConfig(BaseModel):
    """Configuration for thread storage."""

    backend: Literal["memory", "sqlite", "postgres"] = "sqlite"
    sqlite_path: str = "data/agent.db"
    storage_path: str = "data/threads"
    max_threads: int = 100


class Config(BaseModel):
    """Main configuration model."""

    models: list[ModelConfig] = Field(default_factory=list)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    tool_groups: list[ToolGroupConfig] = Field(default_factory=list)
    tools: list[ToolConfig] = Field(default_factory=list)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    lead_prompt: LeadPromptConfig = Field(default_factory=LeadPromptConfig)
    middleware: MiddlewareConfig = Field(default_factory=MiddlewareConfig)
    summarization: SummarizationConfig = Field(default_factory=SummarizationConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    threads: ThreadsConfig = Field(default_factory=ThreadsConfig)
    log_level: str = "info"

    @property
    def available_models(self) -> list[ModelConfig]:
        """Return only models with valid API keys configured."""

        return [model for model in self.models if model.has_valid_api_key()]

    def is_tool_group_enabled(self, group_name: str | None) -> bool:
        """Return whether a tool group is enabled."""

        if not group_name:
            return True
        if not self.tool_groups:
            return True
        matched = next((group for group in self.tool_groups if group.name == group_name), None)
        return matched.enabled if matched else True

    @classmethod
    def from_yaml(cls, path: str = "config.yaml") -> "Config":
        """Load configuration from YAML file."""

        import os

        path = os.path.expandvars(path)
        with open(path, encoding="utf-8") as handle:
            data = safe_load(handle) or {}
        data = cls._expand_env_vars(data)
        return cls(**data)

    @staticmethod
    def _expand_env_vars(data: Any) -> Any:
        """Recursively expand environment variables in config values."""

        import os
        import re

        if isinstance(data, dict):
            return {key: Config._expand_env_vars(value) for key, value in data.items()}
        if isinstance(data, list):
            return [Config._expand_env_vars(item) for item in data]
        if isinstance(data, str):
            pattern = r"\$\{?(\w+)\}?"

            def replace_var(match: re.Match[str]) -> str:
                var_name = match.group(1)
                return os.getenv(var_name, match.group(0))

            return re.sub(pattern, replace_var, data)
        return data
