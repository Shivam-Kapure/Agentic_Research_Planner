"""Scrub API-key-shaped strings from text before it reaches logs, traces or HTTP responses."""

import re

_KEY_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9]{8,}"),  # Groq
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google / Gemini
    re.compile(r"(?i)(api[_-]?key|authorization|bearer)([\"'=:\s]+)[A-Za-z0-9_\-\.]{12,}"),
]

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    for pattern in _KEY_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
        else:
            text = pattern.sub(REDACTED, text)
    return text
