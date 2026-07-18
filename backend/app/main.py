from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv
from pathlib import Path

from app.automation.utils.logger import setup_logging, get_logger

setup_logging()
logger = get_logger("workflowpro.startup")

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    logger.info("Loaded environment variables from: %s", env_path)
else:
    logger.warning("No .env file found at: %s", env_path)

from app.core.config import settings
from app.core.rate_limit import limiter
from app.api.v1.router import api_router
from app.services.task_queue import task_queue

_cleanup_task: asyncio.Task = None


async def _periodic_queue_cleanup() -> None:
    """Runs every 10 minutes to evict completed tasks older than 1 hour."""
    while True:
        await asyncio.sleep(600)
        try:
            await task_queue.cleanup_completed(max_age_seconds=3600)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task
    _cleanup_task = asyncio.create_task(_periodic_queue_cleanup())
    yield
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="UI Capture System API",
    description="Production-ready API for browser automation and workflow management",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter to app state and enforce it globally via middleware.
# (Previously the limiter was constructed but never attached, so the default
# per-minute limit was a no-op — login brute-force and cost abuse were open.)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS - Environment-aware configuration.
# We never combine a wildcard origin with credentials (the browser rejects it
# and it's insecure). In development we allow the known local dev origins with
# credentials; in production only the configured ALLOWED_ORIGINS are permitted.
DEV_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
]
origins = DEV_ORIGINS if settings.ENVIRONMENT == "development" else settings.ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Request IDs, access logging, and security headers.
from app.core.middleware import RequestContextMiddleware
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all handler so unexpected errors never leak stack traces.

    The full error is logged server-side (with the request ID for correlation);
    the client gets a generic 500 with that ID for support.
    """
    request_id = getattr(request.state, "request_id", None)
    logger.exception("Unhandled error on %s %s [rid=%s]", request.method, request.url.path, request_id)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


# Include API routes
app.include_router(api_router, prefix="/api")

# Include WebSocket at root level (not under /api prefix)
from app.api.v1.endpoints.websocket import router as ws_router
app.include_router(ws_router)

@app.get("/")
async def root():
    return {
        "message": "UI Capture System API",
        "version": settings.VERSION,
        "status": "RUNNING",
    }


@app.get("/health")
async def liveness():
    """Liveness probe — process is up. Does not touch dependencies."""
    return {"status": "healthy", "version": settings.VERSION}


def _readiness_payload():
    """Shared readiness check: DB reachable + an LLM provider configured."""
    from app.core.database import engine
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unavailable"

    llm_provider = settings.active_llm_provider
    ready = db_status == "healthy" and llm_provider != "none"
    return ready, {
        "status": "ready" if ready else "degraded",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "llm_provider": llm_provider,
    }


@app.get("/health/ready")
async def readiness():
    """Readiness probe — returns 503 if a hard dependency is unavailable."""
    ready, payload = _readiness_payload()
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@app.get("/api/health")
async def api_health_check():
    """Health check under the /api prefix (matches the frontend expectation)."""
    _, payload = _readiness_payload()
    return payload
