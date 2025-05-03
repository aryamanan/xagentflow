from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime

from app.models.task import Task, TaskStatus
from app.schemas.task import TaskCreate, TaskUpdate

async def create_task(db: AsyncSession, task_create: TaskCreate) -> Task:
    """Create a new task."""
    task = Task(
        task_type=task_create.task_type,
        title=task_create.title,
        description=task_create.description,
        input_data=task_create.input_data,
        status=TaskStatus.PLANNING
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task

async def get_task(db: AsyncSession, task_id: UUID) -> Optional[Task]:
    """Get a task by ID."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()

async def update_task(db: AsyncSession, task_id: UUID, task_update: TaskUpdate) -> Optional[Task]:
    """Update a task."""
    await db.execute(
        update(Task)
        .where(Task.id == task_id)
        .values(**task_update.dict(exclude_unset=True))
    )
    await db.commit()
    return await get_task(db, task_id)

async def update_task_status(
    db: AsyncSession, 
    task_id: UUID, 
    status: TaskStatus,
    error_details: Optional[str] = None
) -> Optional[Task]:
    """Update task status."""
    update_data = {"status": status}
    if error_details:
        update_data["error_details"] = error_details
    await db.execute(
        update(Task)
        .where(Task.id == task_id)
        .values(**update_data)
    )
    await db.commit()
    return await get_task(db, task_id)

async def update_task_plan(
    db: AsyncSession,
    task_id: UUID,
    plan: Dict[str, Any]
) -> Optional[Task]:
    """Update task plan."""
    await db.execute(
        update(Task)
        .where(Task.id == task_id)
        .values(plan=plan)
    )
    await db.commit()
    return await get_task(db, task_id)
