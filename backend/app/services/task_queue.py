"""
Concurrent Task Queue for running multiple workflows simultaneously.

This module provides a task queue that allows multiple workflows to run
concurrently without blocking each other.
"""

import asyncio
from typing import Dict, Optional, Callable, Any
from datetime import datetime, timezone
from enum import Enum

from app.automation.utils.logger import log


class TaskStatus(Enum):
    """Status of a task in the queue."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskInfo:
    """Information about a queued task."""
    
    def __init__(self, task_id: str, task_func: Callable, args: tuple, kwargs: dict):
        self.task_id = task_id
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs
        self.status = TaskStatus.QUEUED
        self.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None
        self.result: Any = None
        self.task: Optional[asyncio.Task] = None


class ConcurrentTaskQueue:
    """
    Manages concurrent execution of multiple workflows.
    
    Features:
    - Run multiple workflows simultaneously
    - Configurable max concurrent tasks
    - Track task status and results
    - Automatic cleanup of completed tasks
    """
    
    def __init__(self, max_concurrent: int = 5):
        """
        Initialize task queue.
        
        Args:
            max_concurrent: Maximum number of tasks to run simultaneously
        """
        self.max_concurrent = max_concurrent
        self.tasks: Dict[str, TaskInfo] = {}
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._cleanup_lock = asyncio.Lock()
        
    async def add_task(
        self,
        task_id: str,
        task_func: Callable,
        *args,
        **kwargs
    ) -> str:
        """
        Add a task to the queue and start execution.
        
        Args:
            task_id: Unique identifier for the task
            task_func: Async function to execute
            *args: Positional arguments for task_func
            **kwargs: Keyword arguments for task_func
            
        Returns:
            Task ID
        """
        # Create task info
        task_info = TaskInfo(task_id, task_func, args, kwargs)
        self.tasks[task_id] = task_info
        
        # Start task execution
        task_info.task = asyncio.create_task(
            self._execute_task(task_info)
        )
        
        log(f"[TASK QUEUE] Added task {task_id} to queue")
        log(f"[TASK QUEUE] Current tasks: {len(self.tasks)}, Running: {self.get_running_count()}")
        
        return task_id
    
    async def _execute_task(self, task_info: TaskInfo):
        """
        Execute a task with concurrency control.
        
        Args:
            task_info: Information about the task to execute
        """
        task_id = task_info.task_id
        
        try:
            # Wait for available slot
            async with self.semaphore:
                # Update status to running
                task_info.status = TaskStatus.RUNNING
                task_info.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
                log(f"[TASK QUEUE] Starting task {task_id}")
                
                # Execute the task
                try:
                    result = await task_info.task_func(*task_info.args, **task_info.kwargs)
                    task_info.result = result
                    task_info.status = TaskStatus.COMPLETED
                    log(f"[TASK QUEUE] Task {task_id} completed successfully")
                    
                except asyncio.CancelledError:
                    task_info.status = TaskStatus.CANCELLED
                    log(f"[TASK QUEUE] Task {task_id} was cancelled")
                    raise
                    
                except Exception as e:
                    task_info.status = TaskStatus.FAILED
                    task_info.error = str(e)
                    log(f"[TASK QUEUE] Task {task_id} failed: {e}")
                    
                finally:
                    task_info.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    
        except Exception as e:
            log(f"[TASK QUEUE] Error executing task {task_id}: {e}")
            task_info.status = TaskStatus.FAILED
            task_info.error = str(e)
            task_info.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """
        Get the status of a task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task status or None if not found
        """
        task_info = self.tasks.get(task_id)
        return task_info.status if task_info else None
    
    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task information dict or None if not found
        """
        task_info = self.tasks.get(task_id)
        if not task_info:
            return None
        
        duration = None
        if task_info.started_at and task_info.completed_at:
            duration = (task_info.completed_at - task_info.started_at).total_seconds()
        
        return {
            "task_id": task_info.task_id,
            "status": task_info.status.value,
            "created_at": task_info.created_at.isoformat(),
            "started_at": task_info.started_at.isoformat() if task_info.started_at else None,
            "completed_at": task_info.completed_at.isoformat() if task_info.completed_at else None,
            "duration": duration,
            "error": task_info.error
        }
    
    def get_running_count(self) -> int:
        """Get the number of currently running tasks."""
        return sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
    
    def get_queued_count(self) -> int:
        """Get the number of queued tasks."""
        return sum(1 for t in self.tasks.values() if t.status == TaskStatus.QUEUED)
    
    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all tasks."""
        return {
            task_id: self.get_task_info(task_id)
            for task_id in self.tasks.keys()
        }
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running or queued task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if task was cancelled, False otherwise
        """
        task_info = self.tasks.get(task_id)
        if not task_info:
            return False
        
        if task_info.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return False
        
        if task_info.task:
            task_info.task.cancel()
            task_info.status = TaskStatus.CANCELLED
            task_info.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            log(f"[TASK QUEUE] Cancelled task {task_id}")
            return True
        
        return False
    
    async def cleanup_completed(self, max_age_seconds: int = 3600):
        """
        Remove completed tasks older than max_age_seconds.
        
        Args:
            max_age_seconds: Maximum age in seconds before cleanup
        """
        async with self._cleanup_lock:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            to_remove = []
            
            for task_id, task_info in self.tasks.items():
                if task_info.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    if task_info.completed_at:
                        age = (now - task_info.completed_at).total_seconds()
                        if age > max_age_seconds:
                            to_remove.append(task_id)
            
            for task_id in to_remove:
                del self.tasks[task_id]
            
            if to_remove:
                log(f"[TASK QUEUE] Cleaned up {len(to_remove)} old tasks")
    
    async def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Optional[Any]:
        """
        Wait for a task to complete and return its result.
        
        Args:
            task_id: Task identifier
            timeout: Maximum time to wait in seconds
            
        Returns:
            Task result or None if task not found
        """
        task_info = self.tasks.get(task_id)
        if not task_info or not task_info.task:
            return None
        
        try:
            if timeout:
                await asyncio.wait_for(task_info.task, timeout=timeout)
            else:
                await task_info.task
            
            return task_info.result
            
        except asyncio.TimeoutError:
            log(f"[TASK QUEUE] Timeout waiting for task {task_id}")
            return None
        except asyncio.CancelledError:
            log(f"[TASK QUEUE] Task {task_id} was cancelled while waiting")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            "total_tasks": len(self.tasks),
            "queued": self.get_queued_count(),
            "running": self.get_running_count(),
            "completed": sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED),
            "cancelled": sum(1 for t in self.tasks.values() if t.status == TaskStatus.CANCELLED),
            "max_concurrent": self.max_concurrent,
            "available_slots": self.max_concurrent - self.get_running_count()
        }


# Global task queue instance
task_queue = ConcurrentTaskQueue(max_concurrent=5)
