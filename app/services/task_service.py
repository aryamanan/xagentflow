from typing import Optional, List, Any, Dict
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
        
        # Create task in database
        task = await crud_task.create_task(self.db, task_create)
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
                # Don't pass checkpointer anymore
                workflow = ResearchWorkflow(task.id, self.db)
                logger.info("Created ResearchWorkflow")
            elif task_create.task_type == TaskType.STRATEGY_DEV:
                raise ValueError(f"STRATEGY_DEV workflow needs checkpointer modification review")
            elif task_create.task_type == TaskType.BACKTEST:
                raise ValueError(f"BACKTEST workflow needs checkpointer modification review")
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
                self.db,
                task.id,
                TaskStatus.FAILED,
                error_details=error_msg
            )
            raise HTTPException(500, error_msg)
        except Exception as e:
            error_msg = f"Workflow instantiation failed: {str(e)}"
            logger.error(error_msg)
            await crud_task.update_task_status(
                self.db,
                task.id,
                TaskStatus.FAILED,
                error_details=error_msg
            )
            raise HTTPException(500, error_msg)
        
        return task.id

    async def approve_task_plan(self, task_id: UUID, approval: PlanApproval) -> None:
        """Approve or reject a task's plan. Runs workflow SYNCHRONOUSLY for debugging."""
        logger.info(f"[Task {task_id}] Entered approve_task_plan. Approval value: {approval.approved}")
        
        # Get current task state
        logger.info(f"[Task {task_id}] approve_task_plan: Getting task...")
        task = await crud_task.get_task(self.db, task_id)
        if not task:
            logger.error(f"[Task {task_id}] approve_task_plan: Task not found")
            raise HTTPException(404, "Task not found")
        logger.info(f"[Task {task_id}] approve_task_plan: Task found. Current status: {task.status}")
            
        if task.status != TaskStatus.PENDING_APPROVAL:
            logger.error(f"[Task {task_id}] approve_task_plan: Task not in PENDING_APPROVAL state")
            raise HTTPException(400, "Task is not in pending approval state")
        logger.info(f"[Task {task_id}] approve_task_plan: Task status is PENDING_APPROVAL.")
            
        if not approval.approved:
            logger.info(f"[Task {task_id}] approve_task_plan: Plan rejected by user.")
            await crud_task.update_task_status(
                self.db,
                task_id,
                TaskStatus.REJECTED,
                error_details="Plan rejected by user"
            )
            logger.info(f"[Task {task_id}] approve_task_plan: Updated DB status to REJECTED.")
            return
            
        logger.info(f"[Task {task_id}] approve_task_plan: Plan approved. Updating status...")
        await crud_task.update_task_status(self.db, task_id, TaskStatus.IN_PROGRESS)
        logger.info(f"[Task {task_id}] Status updated to IN_PROGRESS in DB.")
        
        # --- Run Workflow (No Checkpointer Retrieval Needed) --- 
        try:
            logger.info(f"[Task {task_id}] Attempting to run workflow SYNCHRONOUSLY...") 
            
            # Re-instantiate the workflow directly (doesn't need checkpointer passed)
            logger.info(f"[Task {task_id}] Re-instantiating workflow for synchronous run...")
            if task.task_type == TaskType.RESEARCH:
                workflow = ResearchWorkflow(task_id, self.db)
                logger.info(f"[Task {task_id}] Created ResearchWorkflow for synchronous run")
            # Add other workflow types here if needed
            # elif task.task_type == TaskType.STRATEGY_DEV:
            #     workflow = StrategyWorkflow(task_id, self.db)
            # elif task.task_type == TaskType.BACKTEST:
            #     workflow = BacktestWorkflow(task_id, self.db)
            else:
                logger.error(f"[Task {task_id}] Unsupported task type for synchronous run: {task.task_type}")
                raise ValueError(f"Unsupported task type for synchronous run: {task.task_type}")

            logger.info(f"[Task {task_id}] Calling workflow.resume() synchronously...")
            final_state = await workflow.resume() # Execute directly
            logger.info(f"[Task {task_id}] workflow.resume() finished synchronously. Final state keys: {final_state.keys() if final_state else 'None'}")

        except Exception as e:
            logger.error(f"[Task {task_id}] FAILED during synchronous workflow run: {str(e)}", exc_info=True) 
            await crud_task.update_task_status(self.db, task_id, TaskStatus.FAILED, f"Workflow resume failed: {e}")
        # --- End Synchronous Execution --- 

        logger.info(f"[Task {task_id}] Exiting approve_task_plan function after synchronous run.") 

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
                    await crud_task.update_task_status(self.db, task_id, TaskStatus.FAILED, error_msg)
                else:
                    # Check if we have a plan that needs approval
                    if final_state and final_state.get("current_plan"):
                        logger.info(f"Plan generated for task {task_id}, waiting for approval")
                        # Save the plan to the task
                        await crud_task.update_task_plan(
                            self.db,
                            task_id,
                            final_state["current_plan"]
                        )
                        # Update status to pending approval
                        await crud_task.update_task_status(
                            self.db,
                            task_id,
                            TaskStatus.PENDING_APPROVAL
                        )
                    else:
                        # No plan was generated
                        error_msg = "No plan was generated by the workflow"
                        logger.error(f"Workflow failed for task {task_id}: {error_msg}")
                        await crud_task.update_task_status(self.db, task_id, TaskStatus.FAILED, error_msg)
                
            except Exception as workflow_err:
                error_msg = str(workflow_err)
                logger.error(f"Workflow background task failed for task {task_id}: {error_msg}")
                await crud_task.update_task_status(self.db, task_id, TaskStatus.FAILED, error_msg)

        except Exception as e:
            logger.error(f"Error in workflow background task for {task_id}: {str(e)}")
            await crud_task.update_task_status(self.db, task_id, TaskStatus.FAILED, str(e))

    async def get_task(self, task_id: UUID) -> TaskResponse:
        """Get a task by ID."""
        logger.debug(f"Getting task with ID: {task_id}")
        try:
            task = await crud_task.get_task(self.db, task_id)
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
        tasks = await crud_task.list_tasks_filtered(self.db, filter_params, skip, limit)
        total = len(tasks)
        return TaskList(items=tasks, total=total)

    async def list_tasks(self) -> List[TaskResponse]:
        """List all tasks without filtering."""
        tasks = await crud_task.list_tasks(self.db)
        return tasks