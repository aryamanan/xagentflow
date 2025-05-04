from typing import List, Optional, Dict, Any
from uuid import UUID
from app.models.task import Task, TaskStatus, TaskType
from app.schemas.task import TaskCreate, TaskUpdate, TaskFilter, TaskResponse
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# In-memory storage
tasks: Dict[str, Task] = {}

async def create_task(db: Any, task_create: TaskCreate) -> Task:
    """Create a new task."""
    logger.debug(f"Creating task: {task_create}")
    task = Task(
        title=task_create.title,
        description=task_create.description,
        task_type=task_create.task_type,
        input_data=task_create.input_data,
        status=TaskStatus.PLANNING
    )
    tasks[task.id] = task
    logger.info(f"Created task with ID: {task.id}")
    return task

async def get_task(db: Any, task_id: UUID) -> Optional[Task]:
    """Get a task by ID."""
    logger.debug(f"Getting task with ID: {task_id}")
    try:
        task_id_str = str(task_id) if isinstance(task_id, UUID) else task_id
        task = tasks.get(task_id_str)
        if task:
            logger.debug(f"Found task: {task.id}")
        else:
            logger.debug(f"Task not found: {task_id}")
        return task
    except Exception as e:
        logger.error(f"Error getting task {task_id}: {str(e)}")
        return None

async def update_task(db: Any, task_id: UUID, obj: TaskUpdate) -> Optional[Task]:
    """Update a task."""
    logger.debug(f"Updating task {task_id} with data: {obj}")
    task = await get_task(db, task_id)
    if not task:
        logger.debug(f"Task not found for update: {task_id}")
        return None
        
    update_data = obj.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)
    
    task.updated_at = datetime.utcnow()
    logger.debug(f"Updated task: {task.id}")
    return task

async def update_task_status(
    db: Any,
    task_id: UUID,
    status: TaskStatus,
    error_details: Optional[str] = None
) -> Optional[Task]:
    """Update a task's status."""
    logger.debug(f"Updating task {task_id} status to {status}")
    task_id_str = str(task_id) if isinstance(task_id, UUID) else task_id
    task = tasks.get(task_id_str)
    if not task:
        logger.debug(f"Task not found for status update: {task_id}")
        return None
        
    task.status = status
    if error_details is not None:
        task.error_details = error_details
    
    task.updated_at = datetime.utcnow()
    if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
        task.completed_at = datetime.utcnow()
    
    logger.debug(f"Updated task status: {task.id} -> {status}")
    return task

async def update_task_plan(
    db: Any,
    task_id: UUID,
    plan: Dict[str, Any]
) -> Optional[Task]:
    """Update a task's plan."""
    logger.debug(f"Updating task {task_id} plan")
    task_id_str = str(task_id) if isinstance(task_id, UUID) else task_id
    task = tasks.get(task_id_str)
    if not task:
        logger.debug(f"Task not found for plan update: {task_id}")
        return None
        
    task.plan = plan
    task.updated_at = datetime.utcnow()
    
    logger.debug(f"Updated task plan: {task.id}")
    return task

async def list_tasks(db: Any) -> List[Task]:
    """List all tasks."""
    logger.debug("Listing all tasks")
    task_list = list(tasks.values())
    logger.debug(f"Found {len(task_list)} tasks")
    return task_list

async def list_tasks_filtered(
    db: Any,
    filter_params: TaskFilter,
    skip: int = 0,
    limit: int = 100
) -> List[Task]:
    """List tasks with filtering."""
    logger.debug(f"Listing tasks with filters: {filter_params}")
    filtered_tasks = []
    
    for task in tasks.values():
        if filter_params.task_types and task.task_type not in filter_params.task_types:
            continue
        if filter_params.statuses and task.status not in filter_params.statuses:
            continue
        if filter_params.start_date and task.created_at < filter_params.start_date:
            continue
        if filter_params.end_date and task.created_at > filter_params.end_date:
            continue
        filtered_tasks.append(task)
    
    filtered_tasks = filtered_tasks[skip:skip + limit]
    logger.debug(f"Found {len(filtered_tasks)} tasks matching filters")
    return filtered_tasks