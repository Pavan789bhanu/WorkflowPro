"""WebSocket endpoint for real-time updates."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.websocket_manager import manager
from app.api.v1.endpoints.auth import authenticate_token
from app.core.database import SessionLocal
from app.automation.utils.logger import get_logger
import json

router = APIRouter()
logger = get_logger("workflowpro.websocket")

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Authenticated WebSocket for real-time updates (scoped to the current user).

    Connect with `?token=<JWT>`. The client then receives only its own:
    - Workflow execution progress / status changes
    - Task completion notifications
    """
    await websocket.accept()

    # Authenticate the socket via ?token= (browsers can't set WS headers).
    db = SessionLocal()
    try:
        user = authenticate_token(websocket.query_params.get("token"), db)
    finally:
        db.close()
    if user is None:
        await websocket.send_json({"type": "error", "message": "Authentication required."})
        await websocket.close(code=1008)
        return

    user_id = user.id
    # Register under the user (connection already accepted above).
    manager.active_connections.append(websocket)
    manager.user_connections.setdefault(user_id, []).append(websocket)
    logger.info("WebSocket connected (total: %d)", len(manager.active_connections))

    try:
        while True:
            # Keep connection alive and handle incoming messages if needed
            data = await websocket.receive_text()

            # Echo back for testing/heartbeat
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await manager.send_personal_message(
                        {"type": "pong", "timestamp": message.get("timestamp")},
                        websocket
                    )
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.warning("WebSocket error: %s", e)
        manager.disconnect(websocket, user_id)
