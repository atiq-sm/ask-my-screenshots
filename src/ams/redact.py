from __future__ import annotations

import re

SECRET_PATTERNS = [
  re.compile(r"AKIA[0-9A-Z]{16}"),
  re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*", re.IGNORECASE),
  re.compile(r"sk-[a-zA-Z0-9]{20,}"),
  re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+"),
  re.compile(r"(?i)api[_-]?key\s*[=:]\s*\S+"),
  re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
]


def redact_secrets(text: str) -> str:
    if not text:
        return text
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted
