"""Built-in guardrail provider with basic regex rules.

This is a starter implementation. For production, replace with a more
sophisticated provider (LLM-based, policy engine, etc.).
"""

from __future__ import annotations

import re
from typing_extensions import override

from vdflow.agent.guardrails.provider import (
    GuardrailDecision,
    GuardrailProvider,
    GuardrailReason,
    GuardrailRequest,
)

# File paths that should never be written/deleted by tools
_PROTECTED_PATHS = re.compile(
    r"(/etc/passwd|/etc/shadow|.ssh/|\.env$|\.git/config)",
    re.IGNORECASE,
)

# Tools that can mutate files — check their path arguments
_FILE_MUTATING_TOOLS = {"write_file", "delete_file", "str_replace"}


class DefaultGuardrailProvider:
    """Basic regex-based guardrail provider.

    Blocks tool calls that target protected file paths.
    """

    name: str = "default"

    @override
    def evaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        return self._check(request)

    @override
    async def aevaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        return self._check(request)

    def _check(self, request: GuardrailRequest) -> GuardrailDecision:
        # Only check file-mutating tools
        if request.tool_name not in _FILE_MUTATING_TOOLS:
            return GuardrailDecision(allow=True)

        # Check path arguments for protected paths
        path = request.tool_input.get("path", "") or request.tool_input.get("file_path", "")
        if isinstance(path, str) and _PROTECTED_PATHS.search(path):
            return GuardrailDecision(
                allow=False,
                reasons=[
                    GuardrailReason(
                        code="guardrail.protected_path",
                        message=f"Path '{path}' is protected and cannot be modified by agent tools.",
                    )
                ],
                policy_id="builtin.protected_paths",
            )

        return GuardrailDecision(allow=True)
