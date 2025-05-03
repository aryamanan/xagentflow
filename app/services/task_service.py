from typing import Optional, List, Any
from uuid import UUID
from fastapi import HTTPException
from app.crud import crud_task
from app.models.task import TaskStatus, TaskType
from app.schemas.task import TaskCreate, TaskUpdate, PlanApproval, TaskResponse, TaskFilter, TaskList
from app.workflows.research_workflow import ResearchWorkflow
from app.workflows.strategy_workflow import StrategyWorkflow
from app.workflows.backtest_workflow import BacktestWorkflow
from app.workflows.state import WorkflowState
import asyncio
import logging

logger = logging.getLogger(__name__)

class TaskService:
    def __init__(self, db: Any = None):
        logger.info("Initializing TaskService")
        self.db = db

    async def start_task(self, task_create: TaskCreate) -> UUID:
        logger.info(f"Starting task with type: {task_create.task_type}")
        
        # Create task in memory
        task = await crud_task.create_task(None, task_create)
        logger.info(f"Created task with ID: {task.id}")
        
        # Prepare initial state for workflow
        initial_state = {
            "task_id": str(task.id),
            "task_type": task_create.task_type.value,
            "initial_request": task_create.description,
            "input_data": task_create.input_data or {},
            "current_step_index": 0,
            "current_plan": None,
            "intermediate_results": {},
            "error_info": None
        }
        logger.info(f"Prepared initial state: {initial_state}")

        # Start workflow based on task type
        try:
            logger.info(f"Creating workflow for task type: {task_create.task_type}")
            if task_create.task_type == TaskType.RESEARCH:
                workflow = ResearchWorkflow(task.id, None)
                logger.info("Created ResearchWorkflow")
            elif task_create.task_type == TaskType.STRATEGY_DEV:
                workflow = StrategyWorkflow(task.id, None)
                logger.info("Created StrategyWorkflow")
            elif task_create.task_type == TaskType.BACKTEST:
                workflow = BacktestWorkflow(task.id, None)
                logger.info("Created BacktestWorkflow")
            else:
                logger.error(f"Unsupported task type: {task_create.task_type}")
                raise ValueError(f"Unsupported task type: {task_create.task_type}")
            
            # Execute workflow ASYNCHRONOUSLY in the background
            logger.info(f"Starting workflow asynchronously for task {task.id}...")
            asyncio.create_task(self._run_workflow_background(workflow, initial_state, task.id))

        except ValueError as e:
            error_msg = f"Configuration error: {str(e)}"
            logger.error(error_msg)
            await crud_task.update_task_status(
                None,
                task.id,
                TaskStatus.FAILED,
                error_details=error_msg
            )
            raise HTTPException(500, error_msg)
        except Exception as e:
            error_msg = f"Workflow instantiation failed: {str(e)}"
            logger.error(error_msg)
            await crud_task.update_task_status(
                None,
                task.id,
                TaskStatus.FAILED,
                error_details=error_msg
            )
            raise HTTPException(500, error_msg)
        
        return task.id

    async def approve_task_plan(self, task_id: UUID, approval: PlanApproval) -> None:
        """Approve or reject a task's plan."""
        logger.info(f"Processing plan approval for task {task_id}")
        
        # Get current task state
        task = await crud_task.get_task(None, task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            raise HTTPException(404, "Task not found")
            
        if task.status != TaskStatus.PENDING_APPROVAL:
            logger.error(f"Task {task_id} is not in PENDING_APPROVAL state")
            raise HTTPException(400, "Task is not in pending approval state")
            
        if not approval.approved:
            logger.info(f"Plan rejected for task {task_id}")
            await crud_task.update_task_status(
                None,
                task_id,
                TaskStatus.REJECTED,
                error_details="Plan rejected by user"
            )
            return
            
        logger.info(f"Plan approved for task {task_id}. Resuming workflow...")
        await crud_task.update_task_status(None, task_id, TaskStatus.IN_PROGRESS)
        
        # Resume workflow execution in the background
        asyncio.create_task(self._resume_workflow_background(task_id, task.task_type))

    async def _resume_workflow_background(self, task_id: str, task_type: TaskType):
        """Helper to resume workflow in the background after approval."""
        logger.info(f"Resuming workflow for task {task_id}")
        try:
            # Re-instantiate the workflow
            if task_type == TaskType.RESEARCH:
                workflow = ResearchWorkflow(task_id, None)
                logger.info("Created ResearchWorkflow for resume")
            elif task_type == TaskType.STRATEGY_DEV:
                workflow = StrategyWorkflow(task_id, None)
                logger.info("Created StrategyWorkflow for resume")
            elif task_type == TaskType.BACKTEST:
                workflow = BacktestWorkflow(task_id, None)
                logger.info("Created BacktestWorkflow for resume")
            else:
                logger.error(f"Unsupported task type for resume: {task_type}")
                raise ValueError(f"Unsupported task type for resume: {task_type}")

            logger.info(f"Resuming workflow for task {task_id}...")
            final_state = await workflow.resume()
            logger.info(f"Workflow for task {task_id} finished resuming. Final state keys: {final_state.keys() if final_state else 'None'}")

        except Exception as e:
            logger.error(f"Error resuming workflow for task {task_id}: {e}")
            await crud_task.update_task_status(None, task_id, TaskStatus.FAILED, f"Workflow resume failed: {e}")

    async def _run_workflow_background(self, workflow, initial_state, task_id):
        """Helper to run the initial workflow execution in the background."""
        logger.info(f"Running workflow background task for {task_id}")
        try:
            logger.info(f"Running workflow background task for {task_id}")
            try:
                # Execute the workflow
                final_state = await workflow.execute(initial_state)
                logger.info(f"Initial workflow execution finished for {task_id}")
                
                # Check for errors in the final state
                if final_state and final_state.get("error_info"):
                    error_msg = str(final_state["error_info"].get("error", "Unknown error"))
                    logger.error(f"Workflow execution failed for task {task_id}: {error_msg}")
                    await crud_task.update_task_status(None, task_id, TaskStatus.FAILED, error_msg)
                else:
                    # Check if we're stopping for approval
                    if final_state and final_state.get("stop_for_approval"):
                        logger.info(f"Workflow paused for approval for task {task_id}")
                        # Status should already be PENDING_APPROVAL from the workflow
                    elif final_state and final_state.get("status") == TaskStatus.PENDING_APPROVAL:
                        logger.info(f"Workflow paused for approval for task {task_id}")
                        # Status should already be PENDING_APPROVAL from the workflow
                    else:
                        # Only mark as completed if we're not waiting for approval
                        task = await crud_task.get_task(None, task_id)
                        if task and task.status != TaskStatus.PENDING_APPROVAL:
                            logger.info(f"Workflow execution successful for task {task_id}")
                            await crud_task.update_task_status(None, task_id, TaskStatus.COMPLETED)
                    
            except Exception as workflow_err:
                error_msg = str(workflow_err)
                logger.error(f"Workflow background task failed for task {task_id}: {error_msg}")
                await crud_task.update_task_status(None, task_id, TaskStatus.FAILED, error_msg)

        except Exception as e:
            logger.error(f"Error in workflow background task for {task_id}: {str(e)}")
            await crud_task.update_task_status(None, task_id, TaskStatus.FAILED, str(e))

    async def get_task(self, task_id: UUID) -> TaskResponse:
        """Get a task by ID."""
        logger.debug(f"Getting task with ID: {task_id}")
        try:
            task = await crud_task.get_task(None, task_id)
            if not task:
                logger.error(f"Task not found: {task_id}")
                raise HTTPException(404, "Task not found")
            return task
        except Exception as e:
            logger.error(f"Error getting task {task_id}: {str(e)}")
            raise HTTPException(500, "Internal server error")

    async def list_tasks_filtered(
        self,
        filter_params: TaskFilter,
        skip: int = 0,
        limit: int = 100
    ) -> TaskList:
        """List tasks with filtering."""
        tasks = await crud_task.list_tasks_filtered(None, filter_params, skip, limit)
        total = len(tasks)
        return TaskList(items=tasks, total=total)

    async def list_tasks(self) -> List[TaskResponse]:
        """List all tasks without filtering."""
        tasks = await crud_task.list_tasks(None)
        return tasks