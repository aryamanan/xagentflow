from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime
from app.models.task import TaskType, TaskStatus

class TaskBase(BaseModel):
    """Base Task Schema"""
    title: str
    description: str
    task_type: TaskType
    input_data: Optional[Dict[str, Any]] = None

class TaskCreate(TaskBase):
    """Task Creation Schema"""
    pass

class TaskUpdate(BaseModel):
    """Task Update Schema"""
    title: Optional[str] = None
    description: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    plan: Optional[Dict[str, Any]] = None
    error_details: Optional[str] = None

class TaskResponse(TaskBase):
    """Task Response Schema"""
    id: str
    status: TaskStatus
    plan: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_details: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class PlanApproval(BaseModel):
    """Plan Approval Schema"""
    approved: bool
    feedback: Optional[str] = None
    modified_plan: Optional[Dict[str, Any]] = None

class TaskFilter(BaseModel):
    """Task Filter Schema"""
    task_types: Optional[List[TaskType]] = None
    statuses: Optional[List[TaskStatus]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class TaskList(BaseModel):
    """Task List Schema"""
    items: List[TaskResponse]
    total: int