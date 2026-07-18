"""WebSocket connection manager for real-time updates.

Connections are tracked per authenticated user so that execution/workflow
progress is delivered ONLY to the owning user — never broadcast to every
connected client (which would leak one tenant's activity to another).
"""

from typing import List, Dict, Any, Optional
from fastapi import WebSocket
from datetime import datetime, timezone

from app.automation.utils.logger import get_logger

logger = get_logger("workflowpro.ws")


class ConnectionManager:
    """Manage WebSocket connections and route messages per user."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_connections: Dict[int, List[WebSocket]] = {}  # user_id -> connections

    async def connect(self, websocket: WebSocket, user_id: Optional[int] = None):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

        if user_id is not None:
            self.user_connections.setdefault(user_id, []).append(websocket)

        logger.info("WebSocket connected (total: %d)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket, user_id: Optional[int] = None):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # user_id may be unknown at disconnect time — scan if needed.
        if user_id is not None and user_id in self.user_connections:
            conns = self.user_connections[user_id]
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                del self.user_connections[user_id]
        else:
            for uid, conns in list(self.user_connections.items()):
                if websocket in conns:
                    conns.remove(websocket)
                if not conns:
                    del self.user_connections[uid]

        logger.info("WebSocket disconnected (total: %d)", len(self.active_connections))

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """Send a message to a specific connection."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning("Error sending personal message: %s", e)

    async def broadcast_to_user(self, user_id: int, message: Dict[str, Any]):
        """Send a message to all connections belonging to one user."""
        if user_id is None or user_id not in self.user_connections:
            return

        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()

        disconnected = []
        for connection in self.user_connections[user_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning("Error sending to user connection: %s", e)
                disconnected.append(connection)

        for conn in disconnected:
            if conn in self.user_connections.get(user_id, []):
                self.user_connections[user_id].remove(conn)

    async def send_workflow_update(
        self, workflow_id: int, event: str, data: Dict[str, Any], user_id: Optional[int] = None
    ):
        """Send a workflow-related update to the owning user only."""
        message = {
            "type": f"workflow_{event}",
            "workflow_id": workflow_id,
            "data": data,
        }
        if user_id is not None:
            await self.broadcast_to_user(user_id, message)

    async def send_execution_update(
        self, execution_id: int, event: str, data: Dict[str, Any], user_id: Optional[int] = None
    ):
        """Send an execution-related update to the owning user only."""
        message = {
            "type": f"execution_{event}",
            "execution_id": execution_id,
            "data": data,
        }
        if user_id is not None:
            await self.broadcast_to_user(user_id, message)


# Global instance
manager = ConnectionManager()
