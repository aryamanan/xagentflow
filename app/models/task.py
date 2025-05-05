from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID, uuid4
import enum

class TaskType(str, enum.Enum):
    RESEARCH = "RESEARCH"
    STRATEGY_DEV = "STRATEGY_DEV"
    BACKTEST = "BACKTEST"

class TaskStatus(str, enum.Enum):
    PLANNING = "planning"
    PENDING_APPROVAL = "pending_approval"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"

class Task:
    def __init__(
        self,
        title: str,
        description: str,
        task_type: TaskType,
        input_data: Optional[Dict[str, Any]] = None,
        status: TaskStatus = TaskStatus.PLANNING
    ):
        self.id = str(uuid4())
        self.title = title
        self.description = description
        self.task_type = task_type
        self.status = status
        self.input_data = input_data or {}
        self.output_data = None
        self.plan = None
        self.error_details = None
        self.checkpoint_data: Optional[str] = None
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.completed_at = None