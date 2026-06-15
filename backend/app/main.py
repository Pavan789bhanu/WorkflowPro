from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✓ Loaded environment variables from: {env_path}")
else:
    print(f"⚠️  No .env file found at: {env_path}")

from app.core.config import settings
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


# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])

app = FastAPI(
    title="UI Capture System API",
    description="Production-ready API for browser automation and workflow management",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - Environment-aware configuration
origins = ["*"] if settings.ENVIRONMENT == "development" else settings.ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=(settings.ENVIRONMENT != "development"),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
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
        "version": "1.0.0",
        "status": "RUNNING",
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

@app.get("/api/health")
async def api_health_check():
    """Health check accessible under the /api prefix (matches frontend expectation)."""
    from app.core.database import engine
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unavailable"
    return {
        "status": "healthy",
        "version": "2.0.0",
        "database": db_status,
        "llm_provider": settings.active_llm_provider,
    }
