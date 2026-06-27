"""
Automation endpoint — natural language → live agentic browser execution.

A single English query is all you need:
  POST  /api/automation/run           → run the agent, return full results + report
  WS    /api/automation/run-live      → run the agent, stream progress + screenshots

Both are powered by AutomationAgent: a vision-driven loop that looks at the
real page (screenshot + DOM digest) before every action, so it adapts to any
site without pre-scripted selectors, and finishes with a result report.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.automation.agent.automation_agent import AutomationAgent
from app.core.config import settings
from app.services.llm_client import LLMNotConfiguredError

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Plain English description of the automation task")
    url: Optional[str] = Field(None, description="Target URL (optional — the AI infers it from the query when omitted)")
    headless: bool = Field(default=True, description="Run the browser in headless (invisible) mode")
    max_steps: Optional[int] = Field(None, ge=1, le=60, description="Max agent steps (default from settings)")


def _credentials() -> dict:
    """Default automation credentials from .env (optional)."""
    if settings.LOGIN_EMAIL and settings.LOGIN_PASSWORD:
        return {"email": settings.LOGIN_EMAIL, "password": settings.LOGIN_PASSWORD}
    return {}


# ---------------------------------------------------------------------------
# REST endpoint — run agent and return everything at once
# ---------------------------------------------------------------------------

@router.post("/run")
async def run_automation(request: RunRequest):
    """
    Convert a plain English query into a live agentic browser automation.

    Example body:
    ```json
    {"query": "Go to Hacker News and summarize the top 5 stories"}
    ```
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query must not be empty")

    agent = AutomationAgent(
        headless=request.headless,
        credentials=_credentials(),
        max_steps=request.max_steps or settings.AGENT_MAX_STEPS,
    )
    try:
        result = await agent.run(query, request.url)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "query": request.query,
        "rewritten_task": result.rewritten_task,
        "success": result.success,
        "final_message": result.final_message,
        "report": result.report_markdown,
        "steps_executed": result.steps_executed,
        "final_url": result.final_url,
        "run_id": result.run_id,
        "extracted": result.extracted,
        "steps": [
            {
                "index": s.index,
                "action": s.action.get("action"),
                "title": s.action.get("step_title"),
                "status": s.status,
                "message": s.message,
                "url": s.url,
                "duration_ms": s.duration_ms,
            }
            for s in result.steps
        ],
        "error": result.error,
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint — stream progress and screenshots in real-time
# ---------------------------------------------------------------------------

@router.websocket("/run-live")
async def run_automation_live(websocket: WebSocket):
    """
    WebSocket endpoint for streaming agentic browser automation.

    Client → Server (JSON):
        {"query": "...", "url": "...", "headless": true, "max_steps": 25}

    Server → Client (JSON event stream):
        {"type": "planning_start",    "message": "..."}
        {"type": "planning_complete", "steps": [...], "plan": {...}, "mode": "agent", ...}
        {"type": "browser_starting",  "message": "..."}
        {"type": "browser_ready"}
        {"type": "step_start",        "step_index": 0, "step": {...}}
        {"type": "step_complete",     "step_index": 0, "step": {...}, "result": {...}}
        {"type": "report_generating", "message": "..."}
        {"type": "execution_complete","success": true, "report": "<markdown>", ...}
        {"type": "error",             "message": "..."}
    """
    await websocket.accept()
    send_lock = asyncio.Lock()
    closed = False

    async def send(payload: dict):
        nonlocal closed
        if closed:
            return
        async with send_lock:
            try:
                await websocket.send_json(payload)
            except Exception:
                closed = True

    agent: Optional[AutomationAgent] = None
    run_task: Optional[asyncio.Task] = None

    try:
        data = await websocket.receive_json()
        query: str = (data.get("query") or "").strip()
        url: Optional[str] = data.get("url") or None
        headless: bool = bool(data.get("headless", True))
        max_steps = data.get("max_steps")

        if not query:
            await send({"type": "error", "message": "query is required"})
            return

        agent = AutomationAgent(
            headless=headless,
            credentials=_credentials(),
            on_event=send,
            max_steps=int(max_steps) if max_steps else settings.AGENT_MAX_STEPS,
        )

        run_task = asyncio.create_task(agent.run(query, url))

        # While the agent runs, also listen for a client-side cancel message
        # or disconnect so we can stop the browser promptly.
        async def watch_client():
            try:
                while True:
                    msg = await websocket.receive_json()
                    if isinstance(msg, dict) and msg.get("type") == "cancel":
                        run_task.cancel()
                        return
            except Exception:
                # Disconnected — cancel the run.
                if not run_task.done():
                    run_task.cancel()

        watcher = asyncio.create_task(watch_client())
        try:
            await run_task
        except asyncio.CancelledError:
            await send({"type": "error", "message": "Run cancelled."})
        except LLMNotConfiguredError as exc:
            await send({"type": "error", "message": str(exc)})
        except Exception as exc:
            await send({"type": "error", "message": str(exc)})
        finally:
            watcher.cancel()

    except WebSocketDisconnect:
        if run_task and not run_task.done():
            run_task.cancel()
    except Exception as exc:
        await send({"type": "error", "message": str(exc)})
    finally:
        if agent:
            try:
                await agent.close()
            except Exception:
                pass
