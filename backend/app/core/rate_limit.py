"""Shared rate limiter.

Defined in its own module so both the app factory (`main.py`) and individual
endpoint modules (e.g. auth for stricter login limits) can import the same
`Limiter` instance without creating circular imports.
"""
import os
import sys

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Disable rate limiting under test so suites that fire many requests from a
# single client IP aren't throttled. Detect tests robustly (a committed .env can
# otherwise leak ENVIRONMENT=development into the pytest process).
_TESTING = (
    settings.ENVIRONMENT == "test"
    or "pytest" in sys.modules
    or "PYTEST_CURRENT_TEST" in os.environ
)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
    enabled=not _TESTING,
)
