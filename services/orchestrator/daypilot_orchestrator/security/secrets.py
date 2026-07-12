"""Secrets access abstraction (batch B11).

Credentials are read from an injected backend (environment by default; a managed
backend such as Vault/SOPS/keyring in production) and never written to the
database, logs, traces, prompts, or generated summaries. `redact` scrubs known
secret-shaped values from any text before it is logged or surfaced.
"""
from __future__ import annotations

import os
import re

# Env var names whose values must never appear in output.
SECRET_ENV_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")

_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.I)
_ASSIGN = re.compile(r"((?:api[_-]?key|token|secret|password)\s*[=:]\s*)([^\s,;]+)", re.I)


def get_secret(name: str, default: str | None = None) -> str | None:
    """Read a secret by name. Extend to call a managed backend in production."""
    return os.getenv(name, default)


def is_secret_name(name: str) -> bool:
    upper = name.upper()
    return any(hint in upper for hint in SECRET_ENV_HINTS)


def redact(text: str) -> str:
    """Scrub secret-shaped values so nothing sensitive lands in logs/traces."""
    text = _BEARER.sub(r"\1[REDACTED]", text)
    text = _ASSIGN.sub(r"\1[REDACTED]", text)
    # Redact any live secret env values that leak verbatim into the text.
    for name, value in os.environ.items():
        if value and len(value) >= 8 and is_secret_name(name) and value in text:
            text = text.replace(value, "[REDACTED]")
    return text
