from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from app.schemas.task import TaskCreate, TaskResponse, PlanApproval, TaskFilter, TaskList
from app.models.task import TaskStatus, TaskType
from app.services.task_service import TaskService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

def get_task_service():
    return TaskService()

@router.post("/", response_model=TaskResponse)
async def create_task(
    task: TaskCreate,
    task_service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    """Create a new task."""
    task_id = await task_service.start_task(task)
    return await task_service.get_task(task_id)

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    task_service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    """Get a specific task by ID."""
    return await task_service.get_task(task_id)

@router.get("/", response_model=TaskList)
async def list_tasks(
    task_types: List[TaskType] = Query(None),
    statuses: List[TaskStatus] = Query(None),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 100,
    task_service: TaskService = Depends(get_task_service)
) -> TaskList:
    """List all tasks with optional filtering."""
    filter_params = TaskFilter(
        task_types=task_types,
        statuses=statuses,
        start_date=start_date,
        end_date=end_date
    )
    return await task_service.list_tasks_filtered(filter_params, skip, limit)

@router.post("/{task_id}/approve", response_model=TaskResponse)
async def approve_task_plan(
    task_id: UUID,
    approval: PlanApproval,
    task_service: TaskService = Depends(get_task_service)
) -> TaskResponse:
    """Approve or reject a task's plan."""
    logger.info(f"Received plan approval request for task {task_id}")
    await task_service.approve_task_plan(task_id, approval)
    return await task_service.get_task(task_id)