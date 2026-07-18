from fastapi import APIRouter, Depends
from app.api.v1.endpoints import auth, workflows, executions, analytics, ai, playground, video_learning, automation
from app.api.v1.endpoints.auth import get_current_user

api_router = APIRouter()

# Auth dependency applied to every route in a router. Endpoints that also expose
# WebSockets (automation, playground) authenticate the socket handshake
# separately via a `?token=` query param, since browsers can't set headers.
_auth = [Depends(get_current_user)]

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(executions.router, prefix="/executions", tags=["executions"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"], dependencies=_auth)
api_router.include_router(playground.router, prefix="/playground", tags=["playground"])
api_router.include_router(playground.ws_router, prefix="/playground", tags=["playground"])
api_router.include_router(automation.router, prefix="/automation", tags=["automation"])
api_router.include_router(video_learning.router, prefix="/video-learning", tags=["video-learning"], dependencies=_auth)
