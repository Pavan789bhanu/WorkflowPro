from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timezone
import json

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.models import Execution as ExecutionModel, Workflow as WorkflowModel, User as UserModel, ExecutionStatus
from app.schemas.schemas import Execution, ExecutionCreate, ExecutionResponse
from app.api.v1.endpoints.auth import get_current_user
from app.services.workflow_executor import execute_workflow
from app.services.task_queue import task_queue

router = APIRouter()


def get_current_user_flexible(
    request: Request,
    token: Optional[str] = Query(None, description="JWT (for iframe/image loads that can't send headers)"),
    db: Session = Depends(get_db),
) -> UserModel:
    """Authenticate via Authorization header OR ?token= query param.

    Reports and screenshots are loaded in <iframe>/<img> tags, which cannot
    attach Authorization headers — those callers pass the JWT as a query param.
    """
    auth_header = request.headers.get("Authorization", "")
    raw_token = token or (auth_header.split(" ", 1)[1] if auth_header.startswith("Bearer ") else None)
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    if not raw_token:
        raise credentials_exception
    payload = decode_access_token(raw_token)
    if not payload or not payload.get("sub"):
        raise credentials_exception
    user = db.query(UserModel).filter(UserModel.username == payload["sub"]).first()
    if not user:
        raise credentials_exception
    return user

@router.get("/", response_model=List[ExecutionResponse])
def get_executions(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page (max 100)"),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    # Calculate offset from page number
    skip = (page - 1) * page_size
    
    # Query executions with workflow names (filtered by current user)
    results = db.query(
        ExecutionModel,
        WorkflowModel.name.label('workflow_name')
    ).join(
        WorkflowModel, ExecutionModel.workflow_id == WorkflowModel.id
    ).filter(
        WorkflowModel.owner_id == current_user.id
    ).order_by(
        ExecutionModel.created_at.desc()
    ).offset(skip).limit(page_size).all()
    
    # Build response with workflow names
    executions = []
    for execution, workflow_name in results:
        # Calculate duration
        duration = None
        if execution.started_at:
            if execution.completed_at:
                duration = int((execution.completed_at - execution.started_at).total_seconds())
            elif execution.status.value == 'running':
                from datetime import datetime
                duration = int((datetime.now(timezone.utc).replace(tzinfo=None) - execution.started_at).total_seconds())
        
        executions.append({
            'id': execution.id,
            'workflow_id': execution.workflow_id,
            'workflow_name': workflow_name,
            'status': execution.status.value if hasattr(execution.status, 'value') else str(execution.status),
            'started_at': execution.started_at,
            'completed_at': execution.completed_at,
            'duration': duration,
            'error_message': execution.error_message,
            'result': execution.result,
            'created_at': execution.created_at
        })
    
    return executions

@router.post("/", response_model=Execution)
async def create_execution(
    execution: ExecutionCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    workflow = db.query(WorkflowModel).filter(
        WorkflowModel.id == execution.workflow_id,
        WorkflowModel.owner_id == current_user.id
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Create execution record with pending status
    db_execution = ExecutionModel(
        workflow_id=execution.workflow_id,
        status=ExecutionStatus.PENDING
    )
    db.add(db_execution)
    db.commit()
    db.refresh(db_execution)
    
    # Add to concurrent task queue
    task_id = f"execution_{db_execution.id}"
    await task_queue.add_task(
        task_id=task_id,
        task_func=execute_workflow,
        execution_id=db_execution.id,
        db=None  # Will create new session in executor
    )
    
    return db_execution

def _get_owned_execution(execution_id: int, user: UserModel, db: Session) -> ExecutionModel:
    execution = db.query(ExecutionModel).join(
        WorkflowModel, ExecutionModel.workflow_id == WorkflowModel.id
    ).filter(
        ExecutionModel.id == execution_id,
        WorkflowModel.owner_id == user.id,
    ).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("/{execution_id}/report", response_class=HTMLResponse)
def get_execution_report(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user_flexible),
):
    """
    Get the HTML report for a specific execution (success OR failure —
    failed runs also produce a report explaining what happened).
    """
    execution = _get_owned_execution(execution_id, current_user, db)

    if not execution.result:
        raise HTTPException(
            status_code=404,
            detail="No execution result available yet. The workflow may still be running.",
        )

    try:
        result_data = json.loads(execution.result)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid execution result data")

    html_report_path = result_data.get("html_report")
    if html_report_path and Path(html_report_path).exists():
        return HTMLResponse(content=Path(html_report_path).read_text(encoding="utf-8"), status_code=200)

    # Fallback: render the markdown report / message inline so users always see something.
    report_md = result_data.get("report_markdown") or result_data.get("message") or result_data.get("error")
    if report_md:
        import html as _html
        body = "".join(f"<p>{_html.escape(line)}</p>" for line in str(report_md).splitlines() if line.strip())
        return HTMLResponse(
            content=f"<html><body style='font-family:sans-serif;max-width:800px;margin:40px auto;'>{body}</body></html>",
            status_code=200,
        )
    raise HTTPException(status_code=404, detail="No report was generated for this execution.")


@router.get("/{execution_id}/files/{filename}")
def get_execution_file(
    execution_id: int,
    filename: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user_flexible),
):
    """Serve static files (screenshots, etc.) from the execution's report directory."""
    execution = _get_owned_execution(execution_id, current_user, db)

    if not execution.result:
        raise HTTPException(status_code=404, detail="No execution result available")

    try:
        result_data = json.loads(execution.result)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid execution result data")

    html_report_path = result_data.get("html_report")
    if not html_report_path:
        raise HTTPException(status_code=404, detail="No HTML report available")

    report_dir = Path(html_report_path).parent.resolve()
    # Prevent directory traversal
    file_path = (report_dir / filename).resolve()
    if not str(file_path).startswith(str(report_dir)) or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return FileResponse(file_path)


@router.get("/{execution_id}", response_model=Execution)
def get_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    return _get_owned_execution(execution_id, current_user, db)

@router.delete("/{execution_id}")
def delete_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    execution = db.query(ExecutionModel).join(
        WorkflowModel, ExecutionModel.workflow_id == WorkflowModel.id
    ).filter(
        ExecutionModel.id == execution_id,
        WorkflowModel.owner_id == current_user.id
    ).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    db.delete(execution)
    db.commit()

    return {"message": "Execution deleted successfully", "id": execution_id}


class ExecutionFeedback(BaseModel):
    """User feedback on an execution — feeds the learning system."""
    rating: str = Field(..., pattern="^(positive|negative)$", description="Thumbs up/down")
    notes: Optional[str] = Field(None, max_length=2000, description="What worked / what should change")


@router.post("/{execution_id}/feedback")
def submit_execution_feedback(
    execution_id: int,
    feedback: ExecutionFeedback,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Record user feedback on a workflow execution.

    The feedback is stored on the execution AND fed into the workflow
    learning system, so future runs on the same site benefit from it.
    """
    execution = _get_owned_execution(execution_id, current_user, db)

    # Parse result payload for task/domain context
    result_data = {}
    try:
        result_data = json.loads(execution.result) if execution.result else {}
    except json.JSONDecodeError:
        pass

    task = result_data.get("task") or "unknown task"
    url = result_data.get("final_url") or result_data.get("url") or ""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc or "unknown"

    # Feed the learning system (file-backed knowledge base)
    try:
        from app.services.workflow_learner import WorkflowLearner
        learner = WorkflowLearner()
        learner.record_user_correction(
            task=task,
            domain=domain,
            generated_steps=[],
            corrected_steps=[],
            feedback_type="success" if feedback.rating == "positive" else "failure",
            notes=feedback.notes,
        )
    except Exception as learn_err:
        # Feedback storage on the execution still proceeds
        print(f"[FEEDBACK] learner error: {learn_err}")

    # Persist feedback on the execution row (inside the result JSON)
    result_data["user_feedback"] = {
        "rating": feedback.rating,
        "notes": feedback.notes,
        "by": current_user.username,
        "at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }
    execution.result = json.dumps(result_data)
    db.commit()

    return {
        "message": "Feedback recorded — the model will learn from it.",
        "execution_id": execution_id,
        "rating": feedback.rating,
    }


@router.get("/queue/status")
async def get_queue_status(
    current_user: UserModel = Depends(get_current_user)  # noqa: ARG001
):
    """Get the status of the concurrent task queue."""
    return {
        "queue_stats": task_queue.get_stats(),
        "all_tasks": task_queue.get_all_tasks()
    }


@router.post("/{execution_id}/cancel")
async def cancel_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Cancel a running or queued execution.
    """
    execution = db.query(ExecutionModel).join(
        WorkflowModel, ExecutionModel.workflow_id == WorkflowModel.id
    ).filter(
        ExecutionModel.id == execution_id,
        WorkflowModel.owner_id == current_user.id
    ).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    task_id = f"execution_{execution_id}"
    cancelled = await task_queue.cancel_task(task_id)
    
    if cancelled:
        # Update execution status
        execution.status = ExecutionStatus.FAILED
        execution.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        execution.error_message = "Execution cancelled by user"
        db.commit()
        
        return {
            "message": "Execution cancelled successfully",
            "execution_id": execution_id,
            "cancelled": True
        }
    else:
        return {
            "message": "Execution could not be cancelled (already completed or not found in queue)",
            "execution_id": execution_id,
            "cancelled": False
        }
