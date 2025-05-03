from typing import Dict, Any, Optional
from uuid import UUID
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from app.agents import (
    create_planner_agent,
    create_research_agent,
    create_coordinator_agent
)
from app.crud import crud_task
from app.models.task import TaskStatus
from app.schemas.task import TaskUpdate
from app.workflows.state import WorkflowState
from datetime import datetime
import logging
import json
import asyncio
import concurrent.futures
import functools

logger = logging.getLogger(__name__)

def run_async_in_thread(coro):
    """Helper function to run async code in a thread."""
    logger.debug(f"Running async code in thread. Current event loop: {id(asyncio.get_event_loop()) if asyncio.get_event_loop_policy()._local._loop else 'None'}")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.debug(f"Created new event loop: {id(loop)}")
        result = loop.run_until_complete(coro)
        logger.debug(f"Async operation completed successfully in thread")
        return result
    except Exception as e:
        logger.error(f"Error in thread execution: {str(e)}")
        raise
    finally:
        loop.close()
        asyncio.set_event_loop(None)
        logger.debug("Thread event loop closed and removed")

# Define node functions without decorators
async def generate_plan_node(state: WorkflowState, planner, db_session, task_id) -> WorkflowState:
    """Generate a research plan."""
    logger.info(f"[Task {task_id}] Generating research plan")
    try:
        # Get task details
        task = await crud_task.get_task(db_session, task_id)
        if not task:
            raise ValueError("Task not found")
            
        # Update task status to PLANNING if just starting
        if task.status == TaskStatus.PLANNING:
            await crud_task.update_task_status(db_session, task_id, TaskStatus.PLANNING)
            
        # If we already have a plan and it's approved, continue
        if task.plan and state.get("plan_approved"):
            state["current_plan"] = task.plan
            state["status"] = TaskStatus.IN_PROGRESS
            await crud_task.update_task_status(db_session, task_id, TaskStatus.IN_PROGRESS)
            logger.info(f"[Task {task_id}] Using approved plan")
            return state
            
        # If we don't have a plan, generate one
        if not task.plan:
            # Generate plan using planner agent
            plan = await planner.generate_plan(
                task_type=task.task_type,
                initial_request=task.description
            )
            
            # Update task with plan and status
            await crud_task.update_task_plan(db_session, task_id, plan)
            await crud_task.update_task_status(db_session, task_id, TaskStatus.PENDING_APPROVAL)
            
            # Update state and force stop
            state["current_plan"] = plan
            state["status"] = TaskStatus.PENDING_APPROVAL
            state["plan_approved"] = False
            state["stop_for_approval"] = True
            logger.info(f"[Task {task_id}] Plan generated successfully, stopping for approval")
            return state
            
        # If we have a plan but it's not approved, wait
        if not state.get("plan_approved"):
            state["current_plan"] = task.plan
            state["status"] = TaskStatus.PENDING_APPROVAL
            state["plan_approved"] = False
            state["stop_for_approval"] = True
            logger.info(f"[Task {task_id}] Waiting for plan approval")
            return state
            
    except Exception as e:
        logger.error(f"[Task {task_id}] Error generating plan: {str(e)}")
        state["error_info"] = {"step": "generate_plan", "error": str(e)}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, str(e))
        return state

async def execute_step_node(state: WorkflowState, coordinator, researcher, db_session, task_id) -> WorkflowState:
    """Execute a single step in the workflow."""
    current_index = state.get("current_step_index", 0)
    task_id = state.get("task_id", "unknown")
    logger.info(f"[Task {task_id}] Executing step {current_index}")
    
    # Check if plan exists and has steps
    if not state.get("current_plan") or not isinstance(state["current_plan"], dict):
        logger.error(f"[Task {task_id}] Invalid plan format in state")
        state["error_info"] = {"step": "execute_step", "error": "Invalid plan format"}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, "Invalid plan format")
        return state
        
    steps = state["current_plan"].get("steps", [])
    if not steps or current_index >= len(steps):
        logger.error(f"[Task {task_id}] Step index {current_index} out of range")
        state["error_info"] = {"step": "execute_step", "error": "Step index out of range"}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, "Step index out of range")
        return state
    
    try:
        # Update task status to IN_PROGRESS if not already
        task = await crud_task.get_task(db_session, task_id)
        if task.status != TaskStatus.IN_PROGRESS:
            await crud_task.update_task_status(db_session, task_id, TaskStatus.IN_PROGRESS)
        
        # Get current step
        current_step = steps[current_index]
        
        # Execute step using coordinator and researcher
        step_result = await coordinator.aexecute_step(
            step=current_step,
            researcher=researcher,
            state=state
        )
        
        # Update state with results
        state["agent_outputs"][f"step_{current_index}"] = step_result
        state["current_step_index"] = current_index + 1
        state["status"] = TaskStatus.IN_PROGRESS
        
        # Update progress in task
        progress = {
            "completed_steps": current_index + 1,
            "total_steps": len(steps),
            "current_step": current_step
        }
        await crud_task.update_task(
            db=db_session,
            task_id=task_id,
            obj=TaskUpdate(progress_data=progress)
        )
        
        logger.info(f"[Task {task_id}] Step {current_index} executed successfully")
        return state
        
    except Exception as e:
        logger.error(f"[Task {task_id}] Error executing step {current_index}: {str(e)}")
        state["error_info"] = {"step": "execute_step", "error": str(e)}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, str(e))
        return state

async def finalize_research_node(state: WorkflowState, researcher, db_session, task_id) -> WorkflowState:
    """Finalize the research workflow and synthesize results."""
    logger.info(f"[Task {task_id}] Finalizing research")
    
    try:
        # Check for errors
        if state.get("error_info"):
            logger.error(f"[Task {task_id}] Finalizing with error: {state['error_info']}")
            final_status = TaskStatus.FAILED
            error_info = state["error_info"]
            final_result = None
        else:
            # Synthesize results using researcher agent
            final_result = await researcher.asynthesize_results(
                plan=state["current_plan"],
                step_outputs=state["agent_outputs"]
            )
            final_status = TaskStatus.COMPLETED
            error_info = None
            logger.info(f"[Task {task_id}] Research finalized successfully")
            
        # Update task status and results
        task_update = TaskUpdate(
            status=final_status,
            error_details=error_info.get("error") if error_info else None,
            output_data=final_result if final_result else None,
            completed_at=datetime.utcnow()
        )
        
        await crud_task.update_task(
            db=db_session,
            task_id=task_id,
            obj=task_update
        )
            
        # Update state
        state["final_result"] = final_result
        state["status"] = final_status
        return state
        
    except Exception as e:
        logger.error(f"[Task {task_id}] Error finalizing research: {str(e)}")
        state["error_info"] = {"step": "finalize", "error": str(e)}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, str(e))
        return state

def check_continuation(state: WorkflowState) -> bool:
    """Check if the workflow should continue to the next step."""
    current_step = state.get("current_step_index", 0)
    task_id = state.get("task_id", "unknown")
    
    # Check if we have a plan
    if not state.get("current_plan") or not isinstance(state["current_plan"], dict):
        logger.error(f"[Task {task_id}] No valid plan in state")
        return False
        
    steps = state["current_plan"].get("steps", [])
    has_more_steps = current_step < len(steps)
    
    logger.info(f"[Task {task_id}] Checking continuation: current_step={current_step}, has_more_steps={has_more_steps}")
    
    # Check for errors
    if state.get("error_info"):
        logger.error(f"[Task {task_id}] Stopping workflow due to error: {state['error_info']}")
        return False
        
    return has_more_steps and not state.get("error_info")

def check_approval(state: WorkflowState) -> bool:
    """Check if the plan has been approved."""
    task_id = state.get("task_id", "unknown")
    logger.info(f"[Task {task_id}] Checking plan approval status")
    
    # If we have an error, don't continue
    if state.get("error_info"):
        logger.error(f"[Task {task_id}] Cannot proceed due to error")
        return False
        
    # Check if we're waiting for approval
    current_status = state.get("status")
    if current_status == TaskStatus.PENDING_APPROVAL and not state.get("plan_approved"):
        logger.info(f"[Task {task_id}] Waiting for plan approval")
        return False
        
    # If we're in planning or failed state, don't proceed
    if current_status in [TaskStatus.PLANNING, TaskStatus.FAILED]:
        logger.info(f"[Task {task_id}] Cannot proceed in {current_status} state")
        return False
        
    # Only proceed if we have an approved plan
    if not state.get("plan_approved"):
        logger.info(f"[Task {task_id}] Plan not yet approved")
        return False
        
    logger.info(f"[Task {task_id}] Plan is approved, proceeding with execution")
    return True

class ResearchWorkflow:
    def __init__(self, task_id: UUID, db_session):
        logger.info(f"[Task {task_id}] Initializing ResearchWorkflow")
        self.task_id = task_id
        self.db_session = db_session
        self.planner = create_planner_agent()
        self.researcher = create_research_agent()
        self.coordinator = create_coordinator_agent()
        self.memory = MemorySaver()
        
        # Get current event loop info
        try:
            current_loop = asyncio.get_event_loop()
            logger.debug(f"[Task {task_id}] Current event loop: {id(current_loop)}, Running: {current_loop.is_running()}")
        except Exception as e:
            logger.debug(f"[Task {task_id}] No event loop in current thread: {str(e)}")
        
        self.graph = self._build_graph()
        logger.info(f"[Task {task_id}] Built workflow graph")

    def _build_graph(self):
        """Build the workflow graph."""
        logger.info(f"[Task {self.task_id}] Building workflow graph")
        workflow = StateGraph(WorkflowState)
        
        # Define node wrappers
        def _generate_plan_wrapper(state):
            logger.debug(f"[Task {self.task_id}] Entering generate_plan_wrapper")
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(run_async_in_thread, generate_plan_node(state, self.planner, self.db_session, self.task_id))
                    result_state = future.result()
                    
                    # Force stop after plan generation if requested
                    if result_state.get("stop_for_approval"):
                        logger.info(f"[Task {self.task_id}] Stopping workflow for plan approval")
                        return result_state
                    return result_state
            except Exception as e:
                logger.error(f"[Task {self.task_id}] Error in generate_plan_wrapper: {str(e)}")
                state["error_info"] = {"step": "generate_plan", "error": str(e)}
                return state

        def _check_approval_wrapper(state):
            """Wrapper to check approval status and update state accordingly."""
            logger.debug(f"[Task {self.task_id}] Checking approval status")
            try:
                # Get latest task status from database
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(run_async_in_thread, crud_task.get_task(self.db_session, self.task_id))
                    task = future.result()
                
                if task.status == TaskStatus.PENDING_APPROVAL:
                    state["status"] = TaskStatus.PENDING_APPROVAL
                    state["plan_approved"] = False
                    state["stop_for_approval"] = True
                    logger.info(f"[Task {self.task_id}] Task is pending approval")
                elif task.status == TaskStatus.IN_PROGRESS:
                    state["status"] = TaskStatus.IN_PROGRESS
                    state["plan_approved"] = True
                    state["stop_for_approval"] = False
                    logger.info(f"[Task {self.task_id}] Task plan is approved")
                
                return state
            except Exception as e:
                logger.error(f"[Task {self.task_id}] Error checking approval status: {str(e)}")
                state["error_info"] = {"step": "check_approval", "error": str(e)}
                return state

        def _execute_step_wrapper(state):
            logger.debug(f"[Task {self.task_id}] Entering execute_step_wrapper")
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(run_async_in_thread, execute_step_node(state, self.coordinator, self.researcher, self.db_session, self.task_id))
                    return future.result()
            except Exception as e:
                logger.error(f"[Task {self.task_id}] Error in execute_step_wrapper: {str(e)}")
                state["error_info"] = {"step": "execute_step", "error": str(e)}
                return state

        def _finalize_research_wrapper(state):
            logger.debug(f"[Task {self.task_id}] Entering finalize_research_wrapper")
            try:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(run_async_in_thread, finalize_research_node(state, self.researcher, self.db_session, self.task_id))
                    return future.result()
            except Exception as e:
                logger.error(f"[Task {self.task_id}] Error in finalize_research_wrapper: {str(e)}")
                state["error_info"] = {"step": "finalize_research", "error": str(e)}
                return state

        # Add nodes
        workflow.add_node("generate_plan", _generate_plan_wrapper)
        workflow.add_node("check_approval", _check_approval_wrapper)
        workflow.add_node("execute_step", _execute_step_wrapper)
        workflow.add_node("finalize_research", _finalize_research_wrapper)
        
        # Add edges for initial plan generation
        workflow.add_edge(START, "generate_plan")
        
        # Add conditional edges based on approval status
        workflow.add_conditional_edges(
            "generate_plan",
            lambda x: not x.get("stop_for_approval", False),
            {
                True: "check_approval",  # Continue if not stopping for approval
                False: END  # Stop if waiting for approval
            }
        )
        
        # Add conditional edges based on approval status
        workflow.add_conditional_edges(
            "check_approval",
            lambda x: not x.get("stop_for_approval", False) and x.get("plan_approved", False),
            {
                True: "execute_step",  # If approved and not stopping, move to execution
                False: END  # If not approved or stopping, end the workflow
            }
        )
        
        # Add execution flow edges
        workflow.add_conditional_edges(
            "execute_step",
            check_continuation,
            {
                True: "execute_step",  # Loop back if there are more steps
                False: "finalize_research"  # Move to finalization if done
            }
        )
        workflow.add_edge("finalize_research", END)
        
        logger.info(f"[Task {self.task_id}] Workflow graph built successfully")
        return workflow.compile()

    async def execute(self, initial_state: Dict[str, Any]):
        """Execute the workflow."""
        logger.info(f"[Task {self.task_id}] Starting workflow execution")
        try:
            # Initialize workflow state
            workflow_state = {
                "task_id": str(self.task_id),
                "task_type": initial_state["task_type"],
                "initial_request": initial_state["initial_request"],
                "input_data": initial_state.get("input_data", {}),
                "current_step_index": 0,
                "current_plan": None,
                "plan_approved": False,
                "agent_inputs": {},
                "agent_outputs": {},
                "intermediate_results": {},
                "final_result": None,
                "error_info": None,
                "metadata": {},
                "status": TaskStatus.PLANNING
            }
            
            # Execute workflow using ainvoke
            try:
                config = {"configurable": {"thread_id": str(self.task_id)}}
                result = await self.graph.ainvoke(workflow_state, config=config)
                return result
            except Exception as e:
                logger.error(f"[Task {self.task_id}] Error in graph execution: {str(e)}")
                await crud_task.update_task_status(
                    self.db_session,
                    self.task_id,
                    TaskStatus.FAILED,
                    str(e)
                )
                raise
            
        except Exception as e:
            logger.error(f"[Task {self.task_id}] Error in workflow execution: {str(e)}")
            raise

    async def resume(self):
        """Resume workflow execution after plan approval."""
        logger.info(f"[Task {self.task_id}] Resuming workflow")
        try:
            # Get task from database to ensure we have latest status
            task = await crud_task.get_task(self.db_session, self.task_id)
            if not task:
                raise ValueError("Task not found")
            
            # Build execution graph
            workflow = StateGraph(WorkflowState)
            workflow.add_node("execute_step", self._execute_step_wrapper)
            workflow.add_node("finalize_research", self._finalize_research_wrapper)
            
            # Add edges for execution phase
            workflow.add_edge(START, "execute_step")
            workflow.add_conditional_edges(
                "execute_step",
                check_continuation,
                {
                    True: "execute_step",  # Loop back if there are more steps
                    False: "finalize_research"  # Move to finalization if done
                }
            )
            workflow.add_edge("finalize_research", END)
            
            # Compile execution graph
            execution_graph = workflow.compile()
            
            # Initialize state for execution phase
            execution_state = {
                "task_id": str(self.task_id),
                "task_type": task.task_type,
                "initial_request": task.description,
                "input_data": task.input_data,
                "current_step_index": 0,
                "current_plan": task.plan,
                "plan_approved": True,
                "agent_inputs": {},
                "agent_outputs": {},
                "intermediate_results": {},
                "final_result": None,
                "error_info": None,
                "metadata": {},
                "status": TaskStatus.IN_PROGRESS
            }
            
            # Execute workflow
            try:
                config = {"configurable": {"thread_id": str(self.task_id)}}
                result = await execution_graph.ainvoke(execution_state, config=config)
                return result
            except Exception as e:
                logger.error(f"[Task {self.task_id}] Error in graph resume: {str(e)}")
                await crud_task.update_task_status(
                    self.db_session,
                    self.task_id,
                    TaskStatus.FAILED,
                    str(e)
                )
                raise
            
        except Exception as e:
            logger.error(f"[Task {self.task_id}] Error in workflow resume: {str(e)}")
            raise

    async def get_state(self):
        """Get the current workflow state."""
        try:
            config = {"configurable": {"thread_id": str(self.task_id)}}
            state_info = await self.graph.get_state(config)
            if state_info and state_info.values:
                logger.info(f"[Task {self.task_id}] Retrieved state from memory")
                return dict(state_info.values)
            return None
        except Exception as e:
            logger.error(f"[Task {self.task_id}] Error retrieving state: {str(e)}")
            return None