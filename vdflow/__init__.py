"""VD-Flow: Lightweight AI Agent Framework with Memory and Skills."""

__version__ = "0.1.0"
__author__ = "VD-Flow Team"

__all__ = ["create_agent", "Config", "__version__"]


def __getattr__(name: str):
    if name == "create_agent":
        from vdflow.agent.factory import create_agent

        return create_agent
    if name == "Config":
        from vdflow.config.models import Config

        return Config
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
