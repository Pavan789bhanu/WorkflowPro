"""
Playground API endpoints for testing and running workflows
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json
import base64

from app.api.v1.endpoints.auth import authenticate_token, get_current_user
from app.core.database import SessionLocal
from app.services.playground_executor import playground_executor
from app.services.workflow_learner import WorkflowLearner

# Every HTTP route here drives a real browser / LLM, so require auth on all of
# them. The WebSocket lives on a separate router (no header dependency) and
# authenticates its handshake via a `?token=` query param instead.
router = APIRouter(dependencies=[Depends(get_current_user)])
ws_router = APIRouter()
workflow_learner = WorkflowLearner()


class ExecuteStepRequest(BaseModel):
    """Request to execute a single step"""
    step: Dict[str, Any] = Field(..., description="Step to execute")
    continue_from_current: bool = Field(default=True, description="Continue from current page state")


class ExecuteWorkflowRequest(BaseModel):
    """Request to execute entire workflow"""
    steps: List[Dict[str, Any]] = Field(..., description="Workflow steps")
    headless: bool = Field(default=True, description="Run in headless mode")


class ValidateSelectorRequest(BaseModel):
    """Request to validate selector"""
    selector: str = Field(..., description="CSS selector or XPath")


class WorkflowFeedbackRequest(BaseModel):
    """Request to submit workflow feedback"""
    original_task: str = Field(..., description="Original task description")
    generated_steps: List[Dict[str, Any]] = Field(..., description="AI-generated steps")
    corrected_steps: List[Dict[str, Any]] = Field(..., description="User-corrected steps")
    feedback_type: str = Field(..., description="Type of feedback: 'correction', 'success', 'failure'")
    url: str = Field(..., description="URL where workflow was tested")
    notes: Optional[str] = Field(None, description="Additional notes from user")


class GetSuggestionsRequest(BaseModel):
    """Request to get workflow suggestions based on learning"""
    task_description: str = Field(..., description="Task description")
    url: Optional[str] = Field(None, description="Target URL if known")


@router.post("/execute-step")
async def execute_step(request: ExecuteStepRequest):
    """
    Execute a single workflow step in playground
    
    Returns execution result with screenshot and metadata
    """
    try:
        result = await playground_executor.execute_step(request.step)
        
        # Convert screenshot bytes to base64 if present
        if result.get('screenshot'):
            result['screenshot'] = base64.b64encode(result['screenshot']).decode('utf-8')
        
        return {
            'success': result['status'] == 'success',
            'result': result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute step: {str(e)}")


@router.post("/execute-workflow")
async def execute_workflow(request: ExecuteWorkflowRequest):
    """
    Execute complete workflow in playground
    
    Returns execution results for all steps
    """
    try:
        # Initialize browser
        await playground_executor.initialize(headless=request.headless)
        
        results = []
        
        for i, step in enumerate(request.steps):
            # Execute step
            result = await playground_executor.execute_step(step)
            
            # Convert screenshot to base64
            if result.get('screenshot'):
                result['screenshot'] = base64.b64encode(result['screenshot']).decode('utf-8')
            
            results.append({
                'step_index': i,
                'step': step,
                'result': result
            })
            
            # Stop on error unless specified otherwise
            if result['status'] == 'error':
                break
        
        # Cleanup
        await playground_executor.cleanup()
        
        return {
            'success': all(r['result']['status'] == 'success' for r in results),
            'total_steps': len(request.steps),
            'executed_steps': len(results),
            'results': results
        }
        
    except Exception as e:
        await playground_executor.cleanup()
        raise HTTPException(status_code=500, detail=f"Failed to execute workflow: {str(e)}")


@router.post("/validate-selector")
async def validate_selector(request: ValidateSelectorRequest):
    """
    Validate if selector exists on current page
    
    Returns count and preview of matching elements
    """
    try:
        validation = await playground_executor.validate_selector(request.selector)
        
        return validation
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate selector: {str(e)}")


@router.get("/page-state")
async def get_page_state():
    """
    Get current page state (URL, title, etc.)
    
    Useful for debugging and context
    """
    try:
        state = await playground_executor.get_page_state()
        
        return state
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get page state: {str(e)}")


@router.post("/initialize")
async def initialize_browser(headless: bool = False):
    """
    Initialize browser for playground session
    """
    try:
        await playground_executor.initialize(headless=headless)
        
        return {
            'success': True,
            'message': 'Browser initialized successfully'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize browser: {str(e)}")


@router.post("/cleanup")
async def cleanup_browser():
    """
    Cleanup and close browser
    """
    try:
        await playground_executor.cleanup()
        
        return {
            'success': True,
            'message': 'Browser cleaned up successfully'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup browser: {str(e)}")


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time workflow execution
    
    Clients can send steps and receive real-time updates
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

    try:
        # Initialize browser for this session
        await playground_executor.initialize(headless=False)
        
        while True:
            # Receive step from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            action = message.get('action')
            
            if action == 'execute_step':
                step = message.get('step')
                
                # Send starting status
                await websocket.send_json({
                    'type': 'step_started',
                    'step': step
                })
                
                # Execute step
                result = await playground_executor.execute_step(step)
                
                # Convert screenshot to base64
                if result.get('screenshot'):
                    result['screenshot'] = base64.b64encode(result['screenshot']).decode('utf-8')
                
                # Send result
                await websocket.send_json({
                    'type': 'step_completed',
                    'result': result
                })
                
            elif action == 'validate_selector':
                selector = message.get('selector')
                validation = await playground_executor.validate_selector(selector)
                
                await websocket.send_json({
                    'type': 'validation_result',
                    'validation': validation
                })
                
            elif action == 'get_state':
                state = await playground_executor.get_page_state()
                
                await websocket.send_json({
                    'type': 'page_state',
                    'state': state
                })
                
            elif action == 'cleanup':
                await playground_executor.cleanup()
                await websocket.send_json({
                    'type': 'cleanup_complete'
                })
                break
                
    except WebSocketDisconnect:
        await playground_executor.cleanup()
    except Exception as e:
        await websocket.send_json({
            'type': 'error',
            'message': str(e)
        })
        await playground_executor.cleanup()
        await websocket.close()


@router.post("/feedback")
async def submit_workflow_feedback(request: WorkflowFeedbackRequest):
    """
    Submit feedback on AI-generated workflow for learning
    
    This endpoint allows users to provide corrections and feedback on workflows
    generated by the AI, enabling the system to learn and improve over time.
    """
    try:
        # Extract domain from URL
        from urllib.parse import urlparse
        domain = urlparse(request.url).netloc
        
        # Record the feedback in the learning system
        workflow_learner.record_user_correction(
            task=request.original_task,
            domain=domain,
            generated_steps=request.generated_steps,
            corrected_steps=request.corrected_steps,
            feedback_type=request.feedback_type,
            notes=request.notes
        )
        
        return {
            'success': True,
            'message': 'Feedback recorded successfully. The AI will learn from your corrections!',
            'learned_improvements': workflow_learner.get_improvement_summary(domain)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {str(e)}")


@router.post("/suggestions")
async def get_workflow_suggestions(request: GetSuggestionsRequest):
    """
    Get workflow suggestions based on learning from past feedback
    
    Returns learned patterns and corrections that may apply to the given task
    """
    try:
        domain = None
        if request.url:
            from urllib.parse import urlparse
            domain = urlparse(request.url).netloc
        
        # Get learned suggestions
        suggestions = workflow_learner.get_suggestions_for_task(
            task=request.task_description,
            domain=domain
        )
        
        return {
            'success': True,
            'suggestions': suggestions,
            'has_learned_patterns': len(suggestions) > 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {str(e)}")


@router.get("/learning-stats")
async def get_learning_stats():
    """
    Get statistics about the learning system
    
    Returns information about how much the system has learned from user feedback
    """
    try:
        stats = workflow_learner.get_statistics()
        
        return {
            'success': True,
            'stats': stats
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")
