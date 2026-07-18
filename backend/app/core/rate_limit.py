"""Shared rate limiter.

Defined in its own module so both the app factory (`main.py`) and individual
endpoint modules (e.g. auth for stricter login limits) can import the same
`Limiter` instance without creating circular imports.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    # Disable in the test environment so suites that fire many requests from a
    # single client IP aren't throttled.
    enabled=(settings.ENVIRONMENT != "test"),
)
