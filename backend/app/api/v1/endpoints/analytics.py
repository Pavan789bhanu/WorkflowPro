from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.core.database import get_db
from app.models.models import Workflow, Execution, ExecutionStatus, User
from app.api.v1.endpoints.auth import get_current_user
from app.automation.utils.logger import get_logger

router = APIRouter()
logger = get_logger("workflowpro.analytics")

@router.get("/overview")
def get_analytics_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get analytics overview for current user's workflows."""
    # Total workflows (for current user)
    total_workflows = db.query(func.count(Workflow.id)).filter(
        Workflow.owner_id == current_user.id
    ).scalar() or 0
    
    # Active workflows (for current user)
    active_workflows = db.query(func.count(Workflow.id)).filter(
        Workflow.status == "active",
        Workflow.owner_id == current_user.id
    ).scalar() or 0
    
    # Get current user's workflow IDs
    user_workflow_ids = db.query(Workflow.id).filter(
        Workflow.owner_id == current_user.id
    ).subquery()
    
    # Total executions
    total_executions = db.query(func.count(Execution.id)).filter(
        Execution.workflow_id.in_(user_workflow_ids)
    ).scalar() or 0
    
    # Executions by status
    execution_stats = db.query(
        Execution.status,
        func.count(Execution.id).label('count')
    ).filter(
        Execution.workflow_id.in_(user_workflow_ids)
    ).group_by(Execution.status).all()
    
    status_counts = {status: 0 for status in ExecutionStatus}
    for status, count in execution_stats:
        status_counts[status] = count
    
    success_executions = status_counts.get(ExecutionStatus.SUCCESS, 0)
    failed_executions = status_counts.get(ExecutionStatus.FAILED, 0)
    running_executions = status_counts.get(ExecutionStatus.RUNNING, 0)
    
    # Calculate success rate
    completed_executions = success_executions + failed_executions
    success_rate = (success_executions / completed_executions * 100) if completed_executions > 0 else 0
    
    # Average duration (in minutes) - Calculate manually for SQLite
    # Get executions with both timestamps
    executions_with_times = db.query(
        Execution.started_at,
        Execution.completed_at
    ).filter(
        Execution.workflow_id.in_(user_workflow_ids),
        Execution.status == ExecutionStatus.SUCCESS,
        Execution.started_at.isnot(None),
        Execution.completed_at.isnot(None)
    ).all()
    
    # Calculate average duration manually
    total_duration_seconds = 0
    valid_count = 0
    
    for execution in executions_with_times:
        if execution.started_at and execution.completed_at:
            # Parse timestamps and calculate duration
            from datetime import datetime
            try:
                if isinstance(execution.started_at, str):
                    started = datetime.fromisoformat(execution.started_at.replace('Z', '+00:00'))
                else:
                    started = execution.started_at
                    
                if isinstance(execution.completed_at, str):
                    completed = datetime.fromisoformat(execution.completed_at.replace('Z', '+00:00'))
                else:
                    completed = execution.completed_at
                
                duration_seconds = (completed - started).total_seconds()
                if duration_seconds > 0:  # Only count positive durations
                    total_duration_seconds += duration_seconds
                    valid_count += 1
            except Exception as e:
                logger.debug("Error parsing execution timestamps: %s", e)
                continue
    
    average_duration_seconds = total_duration_seconds / valid_count if valid_count > 0 else 0
    average_duration_minutes = average_duration_seconds / 60
    
    return {
        "total_workflows": total_workflows,
        "active_workflows": active_workflows,
        "total_executions": total_executions,
        "success_executions": success_executions,
        "failed_executions": failed_executions,
        "running_executions": running_executions,
        "success_rate": round(success_rate, 2),
        "average_duration": round(average_duration_minutes, 2)
    }

@router.get("/top-workflows")
def get_top_workflows(
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get top workflows by execution count (for current user)."""
    
    # Get workflow execution stats (filtered by current user)
    results = db.query(
        Workflow.id,
        Workflow.name,
        func.count(Execution.id).label('execution_count'),
        func.sum(
            case(
                (Execution.status == ExecutionStatus.SUCCESS, 1),
                else_=0
            )
        ).label('success_count')
    ).filter(
        Workflow.owner_id == current_user.id
    ).outerjoin(
        Execution, Workflow.id == Execution.workflow_id
    ).group_by(
        Workflow.id, Workflow.name
    ).order_by(
        func.count(Execution.id).desc()
    ).limit(limit).all()
    
    workflows = []
    for row in results:
        execution_count = row.execution_count or 0
        success_count = row.success_count or 0
        success_rate = (success_count / execution_count * 100) if execution_count > 0 else 0
        
        workflows.append({
            "id": str(row.id),
            "name": row.name,
            "execution_count": execution_count,
            "success_count": success_count,
            "success_rate": round(success_rate, 2)
        })
    
    return {"workflows": workflows}
