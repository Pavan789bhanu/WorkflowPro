"""Structured logging for the automation engine.

Uses Python's standard :mod:`logging` module so that:
- Log levels can be filtered at runtime (DEBUG/INFO/WARNING/…).
- Container orchestrators (Docker, k8s) and log aggregators (Datadog,
  CloudWatch, …) capture structured output without extra config.
- Sensitive data is masked before any handler sees it.

Usage::

    from app.automation.utils.logger import log
    log("Agent started", level="info")   # or just log("message")
"""

from __future__ import annotations

import logging
import re
import sys


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("workflowpro.automation")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    # Don't propagate to the root logger to avoid duplicate output.
    logger.propagate = False
    return logger


_logger = _build_logger()

_SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"), "[EMAIL]"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "[API_KEY]"),
    (re.compile(r'api[_\-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{10,}', re.IGNORECASE), "[API_KEY]"),
    (re.compile(r'password["\']?\s*[:=]\s*["\']?[^\"\s,}]+', re.IGNORECASE), "[PASSWORD]"),
    (re.compile(r'pass["\']?\s*[:=]\s*["\']?[^\"\s,}]+', re.IGNORECASE), "[PASSWORD]"),
]


def _mask_sensitive(message: str) -> str:
    """Redact emails, API keys, and passwords from log messages."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


def log(message: str, level: str = "info") -> None:
    """Emit a masked, timestamped log message at *level*.

    Args:
        message: Human-readable log message. Sensitive data is masked
                 automatically before emission.
        level:   One of ``"debug"``, ``"info"``, ``"warning"``,
                 ``"error"``, ``"critical"``. Defaults to ``"info"``.
    """
    masked = _mask_sensitive(message)
    emit = getattr(_logger, level.lower(), _logger.info)
    emit(masked)
