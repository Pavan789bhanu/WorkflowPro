from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import List

from app.core.database import get_db
from app.models.models import Workflow as WorkflowModel, User as UserModel, Execution as ExecutionModel, ExecutionStatus
from app.schemas.schemas import Workflow, WorkflowCreate, WorkflowUpdate, WorkflowResponse
from app.api.v1.endpoints.auth import get_current_user
from app.services.workflow_executor import execute_workflow
from app.services.task_queue import task_queue
from app.core.config import APP_URL_MAPPINGS
from app.utils.ssrf_protector import SSRFProtector
from app.core.encryption import encrypt_password
from app.automation.utils.logger import get_logger

router = APIRouter()
logger = get_logger("workflowpro.workflows")

# Module-level singleton — avoids rebuilding blocked-IP-range objects on every request.
_ssrf = SSRFProtector()


def _workflow_to_response(
    workflow: WorkflowModel,
    *,
    execution_count: int = 0,
    success_count: int = 0,
    last_executed=None,
) -> dict:
    """Serialize a workflow for API responses without exposing stored credentials."""
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "app_name": workflow.app_name,
        "start_url": workflow.start_url,
        "login_email": workflow.login_email,
        "login_password": None,
        "status": workflow.status.value,
        "owner_id": workflow.owner_id,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
        "execution_count": execution_count,
        "success_count": success_count,
        "last_executed": last_executed,
    }


@router.get("/", response_model=List[WorkflowResponse])
def get_workflows(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page (max 100)"),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    # Calculate offset from page number
    skip = (page - 1) * page_size
    
    # Query workflows with execution statistics (filtered by current user)
    workflows = db.query(
        WorkflowModel,
        func.count(ExecutionModel.id).label('execution_count'),
        func.sum(
            case(
                (ExecutionModel.status == ExecutionStatus.SUCCESS, 1),
                else_=0
            )
        ).label('success_count'),
        func.max(ExecutionModel.started_at).label('last_executed')
    ).filter(
        WorkflowModel.owner_id == current_user.id
    ).outerjoin(
        ExecutionModel, WorkflowModel.id == ExecutionModel.workflow_id
    ).group_by(
        WorkflowModel.id
    ).offset(skip).limit(page_size).all()
    
    # Build response with stats
    result = []
    for workflow, exec_count, success_count, last_exec in workflows:
        result.append(
            _workflow_to_response(
                workflow,
                execution_count=exec_count or 0,
                success_count=success_count or 0,
                last_executed=last_exec,
            )
        )
    
    return result

@router.post("/", response_model=WorkflowResponse)
def create_workflow(
    workflow: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    
    # Auto-populate start_url from app_name if not provided
    workflow_data = workflow.model_dump()
    if not workflow_data.get('start_url') and workflow_data.get('app_name'):
        app_name_lower = workflow_data['app_name'].lower()
        if app_name_lower in APP_URL_MAPPINGS:
            workflow_data['start_url'] = APP_URL_MAPPINGS[app_name_lower]
            logger.info("Auto-populated URL for %s: %s", workflow_data['app_name'], workflow_data['start_url'])
    
    # Validate start_url for SSRF (if provided)
    if workflow_data.get('start_url'):
        is_valid, error_msg = _ssrf.validate_url(workflow_data['start_url'])
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid start_url: {error_msg}")

    # Login credentials are per-workflow and user-supplied only. We deliberately
    # do NOT fall back to server-side .env credentials here — that would attach
    # the operator's personal login to workflows owned by any user.
    if workflow_data.get('login_password'):
        workflow_data['login_password'] = encrypt_password(workflow_data['login_password'])

    db_workflow = WorkflowModel(
        **workflow_data,
        owner_id=current_user.id
    )
    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)
    
    return _workflow_to_response(db_workflow)

@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    result = db.query(
        WorkflowModel,
        func.count(ExecutionModel.id).label('execution_count'),
        func.sum(
            case(
                (ExecutionModel.status == ExecutionStatus.SUCCESS, 1),
                else_=0
            )
        ).label('success_count'),
        func.max(ExecutionModel.started_at).label('last_executed')
    ).outerjoin(
        ExecutionModel, WorkflowModel.id == ExecutionModel.workflow_id
    ).filter(
        WorkflowModel.id == workflow_id,
        WorkflowModel.owner_id == current_user.id
    ).group_by(
        WorkflowModel.id
    ).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    workflow, exec_count, success_count, last_exec = result

    return _workflow_to_response(
        workflow,
        execution_count=exec_count or 0,
        success_count=success_count or 0,
        last_executed=last_exec,
    )

@router.put("/{workflow_id}", response_model=Workflow)
def update_workflow(
    workflow_id: int,
    workflow: WorkflowUpdate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    db_workflow = db.query(WorkflowModel).filter(
        WorkflowModel.id == workflow_id,
        WorkflowModel.owner_id == current_user.id
    ).first()
    if not db_workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    update_data = workflow.model_dump(exclude_unset=True)

    if 'start_url' in update_data and update_data['start_url']:
        is_valid, error_msg = _ssrf.validate_url(update_data['start_url'])
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid start_url: {error_msg}")

    # Encrypt password if being updated
    if 'login_password' in update_data and update_data['login_password']:
        update_data['login_password'] = encrypt_password(update_data['login_password'])

    for key, value in update_data.items():
        setattr(db_workflow, key, value)
    
    db.commit()
    db.refresh(db_workflow)
    return Workflow.model_validate(db_workflow, from_attributes=True).model_copy(
        update={"login_password": None}
    )

@router.delete("/{workflow_id}")
def delete_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    workflow = db.query(WorkflowModel).filter(
        WorkflowModel.id == workflow_id,
        WorkflowModel.owner_id == current_user.id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    db.delete(workflow)
    db.commit()
    return {"message": "Workflow deleted successfully"}

@router.post("/{workflow_id}/execute")
async def execute_workflow_endpoint(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """Execute a workflow with the automation engine (concurrent execution)."""
    # Verify workflow exists and user owns it
    workflow = db.query(WorkflowModel).filter(
        WorkflowModel.id == workflow_id,
        WorkflowModel.owner_id == current_user.id
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Create execution record
    execution = ExecutionModel(
        workflow_id=workflow_id,
        status=ExecutionStatus.PENDING
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    
    # Add to concurrent task queue
    task_id = f"execution_{execution.id}"
    await task_queue.add_task(
        task_id=task_id,
        task_func=execute_workflow,
        execution_id=execution.id,
        db=None  # Will create new session in executor
    )
    
    return {
        "message": "Workflow execution started (concurrent)",
        "execution_id": execution.id,
        "task_id": task_id,
        "status": "PENDING",
        "queue_stats": task_queue.get_stats()
    }

