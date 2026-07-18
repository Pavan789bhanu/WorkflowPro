"""Cross-cutting HTTP middleware: request IDs, access logging, security headers.

These give the API production hygiene:
- every request gets a correlation ID (returned as `X-Request-ID`),
- each request/response is logged with method, path, status, and duration,
- responses carry a baseline set of security headers.
"""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.automation.utils.logger import get_logger

logger = get_logger("workflowpro.http")

# Conservative security headers safe for an API + SPA behind nginx.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "0",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID, log the request, and set security headers."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        start = time.perf_counter()

        response: Response = await call_next(request)

        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "%s %s -> %s (%dms) [rid=%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )

        response.headers["X-Request-ID"] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response
