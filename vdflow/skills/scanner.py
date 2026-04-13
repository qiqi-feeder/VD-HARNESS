"""Skill content security scanner.

Scans skill definitions and support files for dangerous patterns before
they are persisted. Lightweight regex-based approach (no LLM needed).
"""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern catalogs
# ---------------------------------------------------------------------------

# Patterns that should never appear in skill instructions
_INSTRUCTION_BLOCK_PATTERNS: list[re.Pattern[str]] = [
    # Prompt injection attempts
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    re.compile(r"\bignore\s+(all\s+)?previous\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\brole\s*[:=]\s*system\b", re.IGNORECASE),
    # Data exfiltration instructions
    re.compile(
        r"\b(?:exfiltrate|leak|dump|extract|send)\b.*(?:credentials?|secrets?|api.?keys?|passwords?|tokens?)",
        re.IGNORECASE,
    ),
    # Telling agent to hide its actions
    re.compile(r"\bdo\s*n.?t\s+(?:tell|show|reveal|display)\b", re.IGNORECASE),
]

# Patterns for executable files (.sh, .py)
_EXECUTABLE_BLOCK_PATTERNS: list[re.Pattern[str]] = [
    # Reverse shells
    re.compile(r"/dev/tcp/", re.IGNORECASE),
    re.compile(r"\bbash\s+-i\b.*>&\s*/dev/", re.IGNORECASE),
    re.compile(r"\bnc\s+-[^\s]*e\b", re.IGNORECASE),
    # Credential harvesting
    re.compile(r"cat\s+/etc/shadow"),
    re.compile(r"\$\(?env\)?\b.*(?:KEY|SECRET|TOKEN|PASSWORD)", re.IGNORECASE),
    # Destructive operations
    re.compile(r"rm\s+-[^\s]*rf?\s+/\s"),
    re.compile(r"dd\s+if="),
    re.compile(r"mkfs\b"),
    # Obfuscated payload execution
    re.compile(r"base64\s.*-d.*\|"),
    re.compile(r"eval\s*\(\s*(?:compile|exec)\s*\(", re.IGNORECASE),
]

_EXECUTABLE_WARN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsudo\b"),
    re.compile(r"\bchmod\s+777\b"),
    re.compile(r"\bpip3?\s+install\b"),
    re.compile(r"\bcurl\s.*\|\s*(?:ba)?sh\b"),
]


class SkillSecurityScanner:
    """Scan skill content for dangerous patterns.

    Returns {"verdict": "pass"|"warn"|"block", "reason": ...}
    """

    async def scan(self, content: str, *, executable: bool = False) -> dict[str, Any]:
        """Scan content. Set executable=True for scripts."""
        # Always check instruction-level patterns
        for pattern in _INSTRUCTION_BLOCK_PATTERNS:
            if pattern.search(content):
                reason = f"blocked pattern: {pattern.pattern[:60]}"
                logger.warning("Skill scan BLOCK: %s", reason)
                return {"verdict": "block", "reason": reason}

        if executable:
            for pattern in _EXECUTABLE_BLOCK_PATTERNS:
                if pattern.search(content):
                    reason = f"blocked executable pattern: {pattern.pattern[:60]}"
                    logger.warning("Skill scan BLOCK: %s", reason)
                    return {"verdict": "block", "reason": reason}

            for pattern in _EXECUTABLE_WARN_PATTERNS:
                if pattern.search(content):
                    reason = f"warning: {pattern.pattern[:60]}"
                    logger.info("Skill scan WARN: %s", reason)
                    return {"verdict": "warn", "reason": reason}

        return {"verdict": "pass", "reason": ""}
