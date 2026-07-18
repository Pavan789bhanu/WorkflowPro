"""Structured logging utilities.

Wraps Python's standard `logging` module with a formatter and a sensitive-data
mask, so log output is leveled, timestamped, and never leaks emails, API keys,
or passwords. `log()` is kept as a convenience wrapper for existing call sites.
"""

from __future__ import annotations

import logging
import os
import re

_SECRET_PATTERNS = [
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), '[EMAIL]'),
    (re.compile(r'sk-[a-zA-Z0-9_-]{20,}'), '[API_KEY]'),
    (re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{10,}', re.IGNORECASE), '[API_KEY]'),
    (re.compile(r'password["\']?\s*[:=]\s*["\']?[^\"\s,}]+', re.IGNORECASE), '[PASSWORD]'),
    (re.compile(r'pass["\']?\s*[:=]\s*["\']?[^\"\s,}]+', re.IGNORECASE), '[PASSWORD]'),
]


def _mask_sensitive_data(message: str) -> str:
    """Mask emails, API keys, and passwords from a log message."""
    for pattern, replacement in _SECRET_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


# Alias expected by tests / origin/dev call sites.
_mask_sensitive = _mask_sensitive_data


class _MaskingFilter(logging.Filter):
    """Logging filter that scrubs secrets from every record's message."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _mask_sensitive_data(record.msg)
        return True


_CONFIGURED = False


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger once, with a formatter and the masking filter.

    Idempotent — safe to call multiple times (e.g. on reload).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    log_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(_MaskingFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level, logging.INFO))
    _CONFIGURED = True


def get_logger(name: str = "workflowpro") -> logging.Logger:
    """Return a module logger (configures logging on first use)."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)


_default_logger = get_logger("workflowpro.agent")


def log(message: str, level: str = "info") -> None:
    """Emit a timestamped, secret-masked log message.

    Kept for backwards compatibility with existing call sites that call
    `log("...")`. New code can use `get_logger(__name__)` directly.
    """
    getattr(_default_logger, level.lower(), _default_logger.info)(message)
