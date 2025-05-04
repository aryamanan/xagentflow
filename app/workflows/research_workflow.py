from typing import Dict, Any, Optional, List
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
            state["status"] = TaskStatus.PLANNING
        
        # If we already have a plan and it's approved, validate and continue
        if task.plan and state.get("plan_approved"):
            try:
                # Validate existing plan structure
                plan = _load_plan(task.plan)
                steps = _extract_steps(plan)
                if not steps:
                    raise ValueError("Stored plan contains no steps")
                state["current_plan"] = plan
                state["status"] = TaskStatus.IN_PROGRESS
                return state
            except Exception as e:
                logger.error(f"[Task {task_id}] Error validating existing plan: {str(e)}")
                # Fall through to generate new plan
        
        # Generate new plan with retries
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                logger.info(f"[Task {task_id}] Generating plan attempt {attempt + 1}/{max_retries}")
                
                # Generate plan - plan_result should be {'plan': {'steps': [...]}}
                plan_result = await planner.generate_plan(
                    task_type=task.task_type.value,
                    initial_request=task.description
                )
                
                if not plan_result or not isinstance(plan_result, dict):
                    raise ValueError("Invalid plan result from planner")

                # Validate the structure returned by the planner immediately
                _validate_plan_structure(plan_result) 

                # Extract the inner plan for step extraction (optional, could pass plan_result)
                inner_plan_for_steps = plan_result.get("plan")
                if not inner_plan_for_steps:
                    raise ValueError("No 'plan' key found in planner result")

                steps = _extract_steps(inner_plan_for_steps) # _extract_steps handles inner structure
                if not steps:
                    raise ValueError("Generated plan contains no steps")
                
                # Update task with the full plan_result
                await crud_task.update_task_plan(db_session, task_id, plan_result)
                
                # Update state with the full plan_result
                state["current_plan"] = plan_result
                state["stop_for_approval"] = True
                state["status"] = TaskStatus.PENDING_APPROVAL
                
                # Update task status
                await crud_task.update_task_status(db_session, task_id, TaskStatus.PENDING_APPROVAL)
                
                logger.info(f"[Task {task_id}] Plan generated successfully")
                return state
                
            except Exception as e:
                last_error = e
                logger.warning(f"[Task {task_id}] Plan generation attempt {attempt + 1} failed: {str(e)}")
                await asyncio.sleep(1)  # Brief delay between retries
        
        # If we get here, all retries failed
        error_msg = f"Failed to generate valid plan after {max_retries} attempts: {str(last_error)}"
        logger.error(f"[Task {task_id}] {error_msg}")
        state["error_info"] = {"step": "generate_plan", "error": error_msg}
        state["status"] = TaskStatus.FAILED
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, error_msg)
        return state
        
    except Exception as e:
        error_msg = f"Unexpected error in plan generation: {str(e)}"
        logger.exception(f"[Task {task_id}] {error_msg}")
        state["error_info"] = {"step": "generate_plan", "error": error_msg}
        state["status"] = TaskStatus.FAILED
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, error_msg)
        return state

def _validate_plan_structure(plan: Dict[str, Any]) -> None:
    """Additional validation for plan structure."""
    if not isinstance(plan, dict):
        raise ValueError("Plan must be a dictionary")
    
    if "plan" not in plan:
        raise ValueError("Missing top-level 'plan' key")
    
    if not isinstance(plan["plan"], dict):
        raise ValueError("plan value must be a dictionary")
    
    if "steps" not in plan["plan"]:
        raise ValueError("Missing 'steps' in plan")
    
    steps = plan["plan"]["steps"]
    if not isinstance(steps, list):
        raise ValueError("Steps must be a list")
    
    if not steps:
        raise ValueError("Steps list cannot be empty")
    
    # Validate step numbers are sequential
    step_numbers = [step.get("step_number") for step in steps]
    if None in step_numbers:
        raise ValueError("All steps must have step_number")
    
    expected_numbers = list(range(1, len(steps) + 1))
    if sorted(step_numbers) != expected_numbers:
        raise ValueError("Step numbers must be sequential starting from 1")
    
    # Validate dependencies
    for step in steps:
        deps = step.get("dependencies", [])
        if not isinstance(deps, list):
            raise ValueError(f"Dependencies for step {step.get('step_number')} must be a list")
        
        for dep in deps:
            if not isinstance(dep, int):
                raise ValueError(f"Dependency {dep} in step {step.get('step_number')} must be an integer")
            if dep < 1 or dep >= step.get("step_number", 0):
                raise ValueError(f"Invalid dependency {dep} in step {step.get('step_number')}")

def _load_plan(plan_raw: Any) -> Dict[str, Any]:
    """Return a dict no matter if we got a dict or a JSON string."""
    if isinstance(plan_raw, str):
        try:
            plan_raw = json.loads(plan_raw)
        except json.JSONDecodeError:
            raise ValueError("Stored plan is not valid JSON")
    if not isinstance(plan_raw, dict):
        raise ValueError("Plan must be a dictionary")
    return plan_raw

def _extract_steps(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract steps from a plan using flexible path."""
    # Try different possible plan structures
    workflow_plan = (
        plan.get("plan", {}).get("WorkflowPlan", {})  # Original expected structure
        or plan.get("plan", {})                       # Current structure
        or plan                                       # Direct structure
    )
    
    # Try different possible step locations
    steps = (
        workflow_plan.get("Steps")
        or workflow_plan.get("steps")                 # Try lowercase
        or workflow_plan.get("steps", [])             # Try direct steps
        or []                                         # Default to empty
    )
    
    if not isinstance(steps, list):
        raise ValueError("Steps must be a list")
    
    # Normalize step structure (convert camelCase to snake_case)
    normalized_steps = []
    for step in steps:
        normalized_step = {
            "step_number": step.get("stepNumber") or step.get("step_number"),
            "step_name": step.get("stepName") or step.get("step_name"),
            "description": step.get("description"),
            "tools": step.get("tools", []),  # Added tools field
            "dependencies": step.get("dependencies", []),
            "success_criteria": step.get("successCriteria") or step.get("success_criteria"),
            "resources": step.get("resources", []),
            "risks": step.get("risks", []),
            "mitigation_strategies": step.get("mitigationStrategies") or step.get("mitigation_strategies", [])
        }
        
        # Validate required fields
        required_fields = ["step_number", "step_name", "description", "tools"]
        missing_fields = [field for field in required_fields if field not in normalized_step or normalized_step[field] is None]
        if missing_fields:
            raise ValueError(f"Step missing required fields: {', '.join(missing_fields)}")
        
        normalized_steps.append(normalized_step)
    
    return normalized_steps

async def execute_step_node(state: WorkflowState, coordinator, researcher, db_session, task_id) -> WorkflowState:
    """Execute a single step in the workflow."""
    current_index = state.get("current_step_index", 0)
    logger.info(f"[Task {task_id}] Executing step {current_index}")
    
    # --- Plan Structure Validation ---
    current_plan = state.get("current_plan")
    if not current_plan:
        logger.error(f"[Task {task_id}] No plan found in state")
        state["error_info"] = {"step": "execute_step", "error": "No plan found in state"}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, "No plan found in state")
        return state
    
    # Handle string plans
    if isinstance(current_plan, str):
        try:
            current_plan = json.loads(current_plan)
            state["current_plan"] = current_plan
        except json.JSONDecodeError:
            logger.error(f"[Task {task_id}] Invalid JSON string in plan")
            state["error_info"] = {"step": "execute_step", "error": "Invalid JSON string in plan"}
            await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, "Invalid JSON string in plan")
            return state
    
    if not isinstance(current_plan, dict):
        logger.error(f"[Task {task_id}] Plan must be a dictionary")
        state["error_info"] = {"step": "execute_step", "error": "Plan must be a dictionary"}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, "Plan must be a dictionary")
        return state
    
    # Try multiple possible plan structures
    plan_root = current_plan
    workflow_plan = (
        plan_root.get("plan", {}).get("WorkflowPlan", {})  # Original expected structure
        or plan_root.get("plan", {})                       # Current structure
        or plan_root                                       # Direct structure
    )
    
    steps = (
        workflow_plan.get("Steps")
        or workflow_plan.get("steps")                      # Try lowercase
        or []                                              # Default to empty
    )
    
    # Log the plan structure for debugging
    logger.debug(f"[Task {task_id}] Plan structure: {json.dumps(current_plan, indent=2)}")
    logger.debug(f"[Task {task_id}] Found steps: {json.dumps(steps, indent=2)}")
    
    if not steps:
        logger.error(f"[Task {task_id}] No steps found in plan")
        state["error_info"] = {"step": "execute_step", "error": "Plan contains no steps"}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, "Plan contains no steps")
        return state
    
    if not isinstance(steps, list):
        logger.error(f"[Task {task_id}] Steps must be a list")
        state["error_info"] = {"step": "execute_step", "error": "Steps must be a list"}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, "Steps must be a list")
        return state
    
    if current_index >= len(steps):
        logger.error(f"[Task {task_id}] Step index {current_index} out of range (total steps: {len(steps)})")
        state["error_info"] = {"step": "execute_step", "error": f"Step index {current_index} out of range"}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, f"Step index {current_index} out of range")
        return state
    
    try:
        # Update task status to IN_PROGRESS if not already
        task = await crud_task.get_task(db_session, task_id)
        if task and task.status != TaskStatus.IN_PROGRESS:
            await crud_task.update_task_status(db_session, task_id, TaskStatus.IN_PROGRESS)
        
        # Get current step
        current_step = steps[current_index]
        logger.info(f"[Task {task_id}] Executing {current_step.get('step_name', 'Unknown Step')} with inputs: {current_step}")
        
        # Execute step using coordinator and researcher
        step_result = await coordinator.aexecute_step(
            step=current_step,
            researcher=researcher,
            state=state
        )
        
        logger.info(f"[Task {task_id}] Step {current_index} execution result:\n{json.dumps(step_result, indent=2)}")

        # Update state with results
        if "agent_outputs" not in state:
            state["agent_outputs"] = {}
        state["agent_outputs"][f"step_{current_index}"] = step_result
        
        step_status = step_result.get("status") if isinstance(step_result, dict) else "error"
        step_error = step_result.get("error") if isinstance(step_result, dict) else "Unknown execution result structure"

        # Handle step outcome
        if step_status == "completed":
            state["current_step_index"] = current_index + 1
            logger.info(f"[Task {task_id}] Successfully executed step {current_index}")
            # Clear error info if the step was previously failed but now succeeded (e.g., on retry)
            if state.get("error_info"):
                 logger.info(f"[Task {task_id}] Clearing previous error_info after successful step {current_index}")
                 state["error_info"] = None 
        else:
            # Log failure only if status indicates failure
            logger.error(f"[Task {task_id}] Step {current_index} failed. Status: {step_status}, Error: {step_error}")
            # Set error_info state - use the actual error message
            state["error_info"] = {"step": f"execute_step_{current_index}", "error": step_error}
            await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, step_error) # Update DB task status
        
        # Update progress in task
        if task:
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
        
        return state
        
    except Exception as e:
        logger.exception(f"[Task {task_id}] Error executing step {current_index}: {str(e)}")
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
            logger.info(f"[Task {task_id}] Finalizing: Calling researcher.asynthesize_results...")
            final_result = await researcher.asynthesize_results(
                plan=state["current_plan"],
                step_outputs=state["agent_outputs"]
            )
            # --- Added Detailed Logging --- 
            logger.info(f"[Task {task_id}] Final synthesis result:\n{json.dumps(final_result, indent=2)}")
            # --- End Added Logging ---
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
    logger.info(f"[Task {task_id} / Edge check_continuation] Checking: current_step_index={current_step}")
    logger.debug(f"[Task {task_id} / Edge check_continuation] Full state entering edge: {json.dumps(state, indent=2, default=str)}")
    
    # --- Modified Error Check --- 
    error_info = state.get("error_info")
    if error_info and error_info.get("error") is not None:
        logger.error(f"[Task {task_id} / Edge check_continuation] Stopping due to error_info: {error_info}")
        return False
    # --- End Modified Error Check --- 
    
    # Check if we're stopping for approval (Should not happen post-resume, but good check)
    # if state.get("stop_for_approval", False) and not state.get("plan_approved", False):
    #     logger.info(f"[Task {task_id} / Edge check_continuation] Stopping for plan approval (unexpected here)")
    #     return False
    
    # Get current plan
    current_plan = state.get("current_plan")
    if not current_plan:
        logger.error(f"[Task {task_id} / Edge check_continuation] No current_plan found in state.")
        # Setting error here might prevent finalize node from running
        # state["error_info"] = {"step": "check_continuation", "error": "No plan in state"}
        return False # Stop execution if no plan
    
    # Handle string plans (Should be dict by now, but check defensively)
    if isinstance(current_plan, str):
        try:
            current_plan = json.loads(current_plan)
        except json.JSONDecodeError:
            logger.error(f"[Task {task_id} / Edge check_continuation] Invalid JSON string in plan.")
            return False
    
    if not isinstance(current_plan, dict):
        logger.error(f"[Task {task_id} / Edge check_continuation] current_plan is not a dictionary.")
        return False
    
    # Extract steps (using same logic as execute_step_node for consistency)
    try:
        steps = _extract_steps(current_plan) # Use the helper function
        logger.info(f"[Task {task_id} / Edge check_continuation] Extracted {len(steps)} steps from plan.")
    except Exception as e:
        logger.error(f"[Task {task_id} / Edge check_continuation] Failed to extract steps from plan: {e}")
        return False # Stop if steps can't be extracted
    
    if not steps:
        logger.error(f"[Task {task_id} / Edge check_continuation] No steps extracted from plan.")
        return False
        
    # Check if we have more steps to execute
    has_more_steps = current_step < len(steps)
    logger.info(f"[Task {task_id} / Edge check_continuation] Result: Has more steps? {has_more_steps} (current={current_step}, total={len(steps)})")
    
    # Return True only if we have more steps and no *actual* error
    return has_more_steps

def check_approval(state: WorkflowState) -> bool:
    """Check if the plan has been approved."""
    task_id = state.get("task_id", "unknown")
    logger.info(f"[Task {task_id} / Edge check_approval] Checking plan approval status.")
    logger.debug(f"[Task {task_id} / Edge check_approval] Full state entering edge: {json.dumps(state, indent=2, default=str)}")
    
    # If we have an error, don't continue
    if state.get("error_info"):
        logger.error(f"[Task {task_id} / Edge check_approval] Cannot proceed due to error_info: {state['error_info']}")
        return False
        
    # Check if we're waiting for approval (stop_for_approval should be True initially)
    # current_status = state.get("status") # Status might not be updated yet
    plan_approved = state.get("plan_approved", False)
    stop_for_approval = state.get("stop_for_approval", False)
    
    if stop_for_approval and not plan_approved:
         logger.info(f"[Task {task_id} / Edge check_approval] Result: False (stop_for_approval=True, plan_approved=False)")
         return False # Waiting for approval

    if not plan_approved:
        logger.info(f"[Task {task_id} / Edge check_approval] Result: False (plan_approved=False)")
        return False # Plan not approved yet
        
    logger.info(f"[Task {task_id} / Edge check_approval] Result: True (plan_approved=True)")
    return True

class ResearchWorkflow:
    def __init__(self, task_id: UUID, db_session):
        logger.info(f"[Task {task_id}] Initializing ResearchWorkflow")
        self.task_id = task_id
        self.db_session = db_session
        
        # Initialize agents
        self.planner = create_planner_agent()
        self.researcher = create_research_agent()
        self.coordinator = create_coordinator_agent()
        
        # Initialize memory saver for checkpointing
        self.memory_saver = MemorySaver()
        
        # Build workflow graph
        self.graph = self._build_graph()
        logger.info(f"[Task {task_id}] Built workflow graph")

    def _build_graph(self):
        """Build the workflow graph."""
        logger.info(f"[Task {self.task_id}] Building workflow graph")
        
        # Create the graph
        workflow = StateGraph(WorkflowState)
        
        # Add nodes
        workflow.add_node("generate_plan", self._generate_plan_wrapper)
        workflow.add_node("execute_step", self._execute_step_wrapper)
        workflow.add_node("finalize", self._finalize_research_wrapper)
        
        # Add conditional edges for plan generation and approval
        workflow.add_conditional_edges(
            "generate_plan",
            check_approval,  # Use check_approval function to determine next step
            {
                True: "execute_step",  # If approved, move to execution
                False: END  # If not approved or error, end workflow
            }
        )
        
        # Add conditional edges for step execution
        workflow.add_conditional_edges(
            "execute_step",
            check_continuation,  # Use check_continuation function to determine next step
            {
                True: "execute_step",  # Continue executing steps if there are more
                False: "finalize"  # Move to finalization if done or error
            }
        )
        
        # Add edge from finalize to end
        workflow.add_edge("finalize", END)
        
        # Set entry point
        workflow.set_entry_point("generate_plan")
        
        # Compile graph with checkpointing
        return workflow.compile(checkpointer=self.memory_saver)

    async def _generate_plan_wrapper(self, state: WorkflowState) -> WorkflowState:
        """Wrapper for generate_plan_node."""
        logger.info(f"[Task {self.task_id}] Entered _generate_plan_wrapper") # Added log
        logger.debug(f"[Task {self.task_id}] State entering _generate_plan_wrapper: {json.dumps(state, indent=2, default=str)}")
        try:
            # Generate plan
            state = await generate_plan_node(state, self.planner, self.db_session, self.task_id)
            logger.info(f"[Task {self.task_id}] Exiting _generate_plan_wrapper. Status: {state.get('status')}. Error: {state.get('error_info')}")
            logger.debug(f"[Task {self.task_id}] State exiting _generate_plan_wrapper: {json.dumps(state, indent=2, default=str)}")
            
            # NOTE: Plan saving moved to generate_plan_node itself before setting status
            # if state.get("status") == TaskStatus.PENDING_APPROVAL:
            #     await crud_task.update_task_plan(...
            
            return state
            
        except Exception as e:
            logger.error(f"[Task {self.task_id}] Error in generate_plan_wrapper: {str(e)}")
            state["error_info"] = {"step": "generate_plan", "error": str(e)}
            state["status"] = TaskStatus.FAILED
            await crud_task.update_task_status(self.db_session, self.task_id, TaskStatus.FAILED, str(e))
            return state

    async def _execute_step_wrapper(self, state: WorkflowState) -> WorkflowState:
        """Wrapper for execute_step_node."""
        logger.info(f"[Task {self.task_id}] Entered _execute_step_wrapper") 
        logger.debug(f"[Task {self.task_id}] State entering _execute_step_wrapper: {json.dumps(state, indent=2, default=str)}")
        try:
            # Ensure we have a plan and it's approved
            logger.info(f"[Task {self.task_id}] Checking plan existence and approval status in _execute_step_wrapper...") 
            if not state.get("current_plan"):
                logger.error(f"[Task {self.task_id}] _execute_step_wrapper: No plan found in state") 
                raise ValueError("No plan found in state")
            if not state.get("plan_approved"):
                logger.error(f"[Task {self.task_id}] _execute_step_wrapper: Plan not approved") 
                raise ValueError("Plan not approved")
            
            logger.info(f"[Task {self.task_id}] Plan found and approved. Calling execute_step_node...") 
            state = await execute_step_node(state, self.coordinator, self.researcher, self.db_session, self.task_id)
            logger.info(f"[Task {self.task_id}] Exiting _execute_step_wrapper. Current index: {state.get('current_step_index')}. Error: {state.get('error_info')}")
            logger.debug(f"[Task {self.task_id}] State exiting _execute_step_wrapper: {json.dumps(state, indent=2, default=str)}")
            return state
            
        except Exception as e:
            logger.error(f"[Task {self.task_id}] Error in _execute_step_wrapper: {str(e)}", exc_info=True)
            state["error_info"] = {"step": "execute_step", "error": str(e)}
            state["status"] = TaskStatus.FAILED
            await crud_task.update_task_status(self.db_session, self.task_id, TaskStatus.FAILED, str(e))
            return state

    async def _finalize_research_wrapper(self, state: WorkflowState) -> WorkflowState:
        """Wrapper for finalize_research_node."""
        logger.info(f"[Task {self.task_id}] Entered _finalize_research_wrapper") # Added log
        logger.debug(f"[Task {self.task_id}] State entering _finalize_research_wrapper: {json.dumps(state, indent=2, default=str)}")
        state = await finalize_research_node(state, self.researcher, self.db_session, self.task_id)
        logger.info(f"[Task {self.task_id}] Exiting _finalize_research_wrapper. Final status: {state.get('status')}")
        logger.debug(f"[Task {self.task_id}] State exiting _finalize_research_wrapper: {json.dumps(state, indent=2, default=str)}")
        return state

    async def execute(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the workflow with initial state."""
        logger.info(f"[Task {self.task_id}] Entered ResearchWorkflow.execute()") # Added log
        logger.info(f"[Task {self.task_id}] ResearchWorkflow.execute(): Initializing state...") # Added log
        state = WorkflowState(
            task_id=initial_state["task_id"],
            task_type=initial_state["task_type"],
            initial_request=initial_state["initial_request"],
            input_data=initial_state["input_data"],
            current_step_index=0,
            current_plan=initial_state.get("current_plan"),
            plan_approved=False,
            agent_inputs={},
            agent_outputs={},
            intermediate_results={},
            final_result=None,
            error_info=None,
            metadata={},
            status=TaskStatus.PLANNING
        )
        logger.info(f"[Task {self.task_id}] ResearchWorkflow.execute(): State initialized. Calling self.graph.ainvoke...") # Added log
        logger.debug(f"[Task {self.task_id}] Initial State for execute graph: {json.dumps(state, indent=2, default=str)}")
        # Execute graph
        config = {"configurable": {"thread_id": str(self.task_id)}}
        final_state = await self.graph.ainvoke(state, config=config)
        logger.info(f"[Task {self.task_id}] ResearchWorkflow.execute(): self.graph.ainvoke completed") # Added log
        return final_state

    async def resume(self) -> Dict[str, Any]:
        """Resume workflow execution after plan approval."""
        logger.info(f"[Task {self.task_id}] Entered ResearchWorkflow.resume()") 
        try:
            # Get current state from database
            logger.info(f"[Task {self.task_id}] ResearchWorkflow.resume(): Getting task from DB...") 
            task = await crud_task.get_task(self.db_session, self.task_id)
            if not task:
                logger.error(f"[Task {self.task_id}] ResearchWorkflow.resume(): Task not found in DB") 
                raise ValueError("Task not found")
            logger.info(f"[Task {self.task_id}] ResearchWorkflow.resume(): Task found. Status: {task.status}") 
                
            # Initialize state with current task data
            logger.info(f"[Task {self.task_id}] ResearchWorkflow.resume(): Initializing state for resume...") 
            state = WorkflowState(
                task_id=str(self.task_id),
                task_type=task.task_type.value,
                initial_request=task.description,
                input_data=task.input_data or {},
                # --- Start execution from step 0 after resume --- 
                current_step_index=0, 
                # --- Load the plan from the task --- 
                current_plan=task.plan,
                plan_approved=True, # Set approved flag
                agent_inputs={},
                agent_outputs={},
                intermediate_results={},
                final_result=None,
                error_info=None,
                metadata={},
                # --- Status should reflect it's now running --- 
                status=TaskStatus.IN_PROGRESS,
                stop_for_approval=False  # Don't stop for approval when resuming
            )
            logger.info(f"[Task {self.task_id}] ResearchWorkflow.resume(): State initialized. Plan loaded: {task.plan is not None}. Approved: {state.get('plan_approved')}") 
            
            # Execute graph
            config = {"configurable": {"thread_id": str(self.task_id)}}
            logger.info(f"[Task {self.task_id}] ResearchWorkflow.resume(): Calling self.graph.ainvoke...") 
            logger.debug(f"[Task {self.task_id}] State for resume graph: {json.dumps(state, indent=2, default=str)}")
            final_state = await self.graph.ainvoke(state, config=config)
            logger.info(f"[Task {self.task_id}] ResearchWorkflow.resume(): self.graph.ainvoke completed") 
            logger.debug(f"[Task {self.task_id}] Final state from resume graph: {json.dumps(final_state, indent=2, default=str)}")
            return final_state
            
        except Exception as e:
            logger.error(f"[Task {self.task_id}] Error resuming workflow: {str(e)}", exc_info=True)
            error_state = {"error_info": {"step": "resume", "error": str(e)}}
            await crud_task.update_task_status(self.db_session, self.task_id, TaskStatus.FAILED, str(e))
            return error_state

    async def get_state(self) -> Optional[Dict[str, Any]]:
        """Get current workflow state."""
        try:
            task = await crud_task.get_task(self.db_session, self.task_id)
            if not task:
                return None
                
            return {
                "task_id": str(self.task_id),
                "task_type": task.task_type.value,
                "initial_request": task.description,
                "input_data": task.input_data or {},
                "current_step_index": task.progress_data.get("completed_steps", 0) if task.progress_data else 0,
                "current_plan": task.plan,
                "agent_outputs": {},
                "error_info": {"error": task.error_details} if task.error_details else None,
                "status": task.status,
                "plan_approved": task.status == TaskStatus.IN_PROGRESS,
                "stop_for_approval": task.status == TaskStatus.PENDING_APPROVAL
            }
        except Exception as e:
            logger.error(f"[Task {self.task_id}] Error getting state: {str(e)}")
            return None