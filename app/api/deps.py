from typing import Generator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.task_service import TaskService

async def get_task_service(db: AsyncSession = Depends(get_db)) -> TaskService:
    """Dependency to get a TaskService instance."""
    return TaskService(db) 