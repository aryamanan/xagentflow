from typing import Dict, Any, Optional, List
from uuid import UUID
from langgraph.graph import StateGraph, END, START

from app.agents import (
    create_planner_agent,
    # create_research_agent,
    # create_coordinator_agent
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

# --- Import Tool Registry --- 
from app.tools.registry import workflow_tools
# --- End Import ---
from app.tools.financial_tools import (
    fetch_historical_data,
    calculate_technical_indicators
)
from app.tools.knowledge_tools import query_local_kb
from app.core.config import settings
# --- Remove OpenAI Import --- 
# from langchain_openai import ChatOpenAI
# --- End Removal ---
from langchain_core.messages import HumanMessage

# --- Add direct Gemini import ---
from langchain_google_genai import ChatGoogleGenerativeAI
# --- End Import --- 

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

# Custom JSON encoder to handle non-serializable types
def state_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, TaskStatus):
        return obj.value
    # Add other type handlers if necessary
    try:
        return str(obj) # Fallback for other complex types
    except Exception:
        return f"<unserializable:{type(obj).__name__}>"

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
                # --- Add logging ---
                logger.info(f"[Task {task_id}] generate_plan_node: Detected existing approved plan. Skipping generation. State status: {state['status']}")
                # --- End logging ---
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
                
                # --- Extract the inner plan --- 
                inner_plan = plan_result.get("plan")
                if not inner_plan:
                    raise ValueError("Planner result missing 'plan' key after validation")
                # --- End Extraction ---
                
                # --- Update task and state with the INNER plan --- 
                await crud_task.update_task_plan(db_session, task_id, inner_plan)
                state["current_plan"] = inner_plan 
                # --- End Update ---
                
                state["stop_for_approval"] = True
                state["status"] = TaskStatus.PENDING_APPROVAL
                
                # --- Save Checkpoint Data --- 
                try:
                    checkpoint_json = json.dumps(state, default=state_serializer)
                    logger.info(f"[Task {task_id}] Serialized state for checkpoint.")
                    await crud_task.update_task(
                        db_session,
                        task_id,
                        TaskUpdate(checkpoint_data=checkpoint_json)
                    )
                    logger.info(f"[Task {task_id}] Saved checkpoint data to DB.")
                except Exception as cp_err:
                    logger.error(f"[Task {task_id}] FAILED TO SAVE CHECKPOINT DATA: {str(cp_err)}", exc_info=True)
                    # Decide if this should fail the task or just log
                    state["error_info"] = {"step": "generate_plan", "error": f"Failed to save checkpoint: {str(cp_err)}"}
                    state["status"] = TaskStatus.FAILED
                    await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, f"Failed to save checkpoint: {str(cp_err)}")
                    return state
                # --- End Save Checkpoint Data ---

                # Update task status *after* saving checkpoint
                await crud_task.update_task_status(db_session, task_id, TaskStatus.PENDING_APPROVAL)
                
                logger.info(f"[Task {task_id}] Plan generated successfully, checkpoint saved.")
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

# --- Refactored execute_step Node --- 
async def execute_step(state: WorkflowState, workflow_instance: 'ResearchWorkflow', db_session, task_id: UUID) -> WorkflowState:
    """Execute a single step by calling tools or LLM directly."""
    current_index = state.get("current_step_index", 0)
    logger.info(f"[Task {task_id} / execute_step] >>> ENTERING node for step index {current_index}")
    
    try:
        # --- Get Current Step --- 
        current_plan = state.get("current_plan")
        if not current_plan:
            raise ValueError("No plan found in state")
        
        steps = _extract_steps(current_plan)
        if not steps:
            raise ValueError("Plan contains no steps")
        
        if current_index >= len(steps):
            raise ValueError(f"Invalid step index {current_index} (total steps: {len(steps)})")
            
        current_step = steps[current_index]
        step_number = current_step["step_number"]
        step_name = current_step["step_name"]
        step_tools = current_step.get("tools", [])
        step_description = current_step.get("description", "")
        logger.info(f"[Task {task_id} / execute_step] Executing step {step_number}: {step_name} (Index: {current_index})")
        logger.debug(f"[Task {task_id} / execute_step] Step details: {json.dumps(current_step, indent=2, default=state_serializer)}")

        # --- Initialize state storage --- 
        if "agent_outputs" not in state: state["agent_outputs"] = {}
        if "intermediate_results" not in state: state["intermediate_results"] = {}

        # --- Check Dependencies --- 
        dependencies = current_step.get("dependencies", [])
        logger.info(f"[Task {task_id} / execute_step] Checking dependencies: {dependencies}")
        for dep in dependencies:
            dep_index = dep - 1
            dep_key = f"step_{dep_index}"
            if dep_key not in state["agent_outputs"]:
                raise ValueError(f"Missing dependency result for step {dep} (key: {dep_key})")
            
            dep_result = state["agent_outputs"][dep_key]
            dep_status = dep_result.get("status") if isinstance(dep_result, dict) else None
            if dep_status not in ["success", "completed_by_llm"]:
                raise ValueError(f"Dependency step {dep} (key: {dep_key}) did not succeed. Status: {dep_status}")
        logger.info(f"[Task {task_id} / execute_step] Dependencies satisfied.")

        # --- Update Task Status --- 
        task = await crud_task.get_task(db_session, task_id)
        if task and task.status != TaskStatus.IN_PROGRESS:
            await crud_task.update_task_status(db_session, task_id, TaskStatus.IN_PROGRESS)

        # --- Execute Step Action --- 
        step_result = None
        if step_tools: # If tools are specified, execute the first one
            tool_name = step_tools[0]
            logger.info(f"[Task {task_id} / execute_step] Step requires tool: '{tool_name}'")
            # --- Use imported registry --- 
            if tool_name not in workflow_tools:
                raise ValueError(f"Tool '{tool_name}' not available in workflow registry.")
            
            tool_func = workflow_tools[tool_name]
            # --- End registry use --- 
            tool_args = {} # Prepare arguments based on tool and context
            
            # Argument preparation logic (example)
            if tool_name == "fetch_historical_data":
                symbol = state.get("input_data", {}).get("symbol", "AAPL") # Default or from input
                tool_args = {"symbol": symbol, "period": "2y"} # Example fixed period
            elif tool_name == "calculate_technical_indicators":
                # --- Refined Logic: Find the output from the fetch_historical_data step --- 
                historical_data_output = None
                fetch_step_index = -1
                
                # Iterate through previous steps' outputs to find the data source
                for dep_index in range(current_index):
                    step_key = f"step_{dep_index}"
                    prev_step_definition = steps[dep_index] # Get the definition of the previous step
                    prev_step_tools = prev_step_definition.get("tools", [])
                    
                    if "fetch_historical_data" in prev_step_tools:
                        # This step should have the data we need
                        output = state["agent_outputs"].get(step_key)
                        if output and output.get("status") == "success" and "data" in output:
                            historical_data_output = output["data"]
                            fetch_step_index = dep_index
                            logger.info(f"[Task {task_id} / execute_step] Found historical data from step {dep_index + 1}")
                            break # Found the data, no need to check further back
                        else:
                            logger.warning(f"[Task {task_id} / execute_step] Step {dep_index + 1} used fetch_historical_data but output is invalid or missing data: {output}")

                if not historical_data_output:
                    # If loop completes without finding data, raise error
                    raise ValueError("Could not find valid historical data output from any previous fetch_historical_data step.")
                
                tool_args["data"] = historical_data_output
                # --- End Refined Logic ---

                # Extract indicators from description (simple example)
                desc_lower = step_description.lower()
                indicators_to_calc = []
                if "rsi" in desc_lower: indicators_to_calc.append("rsi")
                if "macd" in desc_lower: indicators_to_calc.append("macd")
                if "sma" in desc_lower: indicators_to_calc.append("sma") # Added SMA
                if "adx" in desc_lower: indicators_to_calc.append("adx") # Added ADX
                tool_args["indicators"] = indicators_to_calc if indicators_to_calc else ["rsi", "macd"] # Default if none found
            elif tool_name == "query_local_kb":
                 tool_args = {"query": step_description} # Use description as query
            
            logger.info(f"[Task {task_id} / execute_step] Calling tool '{tool_name}' with args: {tool_args}")
            try:
                step_result = await tool_func(**tool_args)
                # Ensure tool result has status
                if isinstance(step_result, dict) and "status" not in step_result:
                     logger.warning(f"Tool '{tool_name}' result missing 'status', assuming success.")
                     step_result["status"] = "success" 
                elif not isinstance(step_result, dict):
                    logger.warning(f"Tool '{tool_name}' returned non-dict, wrapping as success.")
                    step_result = {"status": "success", "result": step_result}
            except Exception as tool_err:
                 logger.error(f"[Task {task_id} / execute_step] Error calling tool '{tool_name}': {tool_err}", exc_info=True)
                 step_result = {"status": "error", "error": f"Tool call failed: {str(tool_err)}"}

        else: # No tools specified, use LLM for analysis/synthesis
            logger.info(f"[Task {task_id} / execute_step] Step requires LLM generation.")
            # Prepare prompt for LLM
            prompt = f"""Execute the following research step based on the provided context:

Step Number: {step_number}
Step Name: {step_name}
Description: {step_description}
Success Criteria: {current_step.get('success_criteria', 'N/A')}

Available Data from Previous Steps (agent_outputs):
{json.dumps(state.get('agent_outputs', {}), indent=2, default=state_serializer)}

Please perform the described task based *only* on the information provided. Provide a detailed report or summary as the result."""
            
            try:
                logger.info(f"[Task {task_id} / execute_step] Calling LLM...")
                # --- Add Delay ---
                logger.info(f"[Task {task_id} / execute_step] Waiting 15s before LLM call to avoid rate limits...")
                await asyncio.sleep(15)
                # --- End Delay ---
                llm_response = await workflow_instance.llm.ainvoke([HumanMessage(content=prompt)])
                step_result = {"status": "completed_by_llm", "content": llm_response.content}
                logger.info(f"[Task {task_id} / execute_step] LLM call successful.")
            except Exception as llm_err:
                logger.error(f"[Task {task_id} / execute_step] Error calling LLM: {llm_err}", exc_info=True)
                step_result = {"status": "error", "error": f"LLM call failed: {str(llm_err)}"}

        # --- Store Result --- 
        loggable_result = json.dumps(step_result, indent=2, default=state_serializer)
        logger.debug(f"[Task {task_id} / execute_step] Raw step result: {loggable_result}")
        state["agent_outputs"][f"step_{current_index}"] = step_result
        if isinstance(step_result, dict) and step_result.get("status") == "success" and "data" in step_result:
             state["intermediate_results"][f"step_{current_index}"] = step_result["data"]

        # --- Handle Outcome --- 
        step_status = step_result.get("status")
        step_error = step_result.get("error")
        logger.info(f"[Task {task_id} / execute_step] Outcome: Status='{step_status}', Error='{step_error}'")
        
        if step_status in ["success", "completed_by_llm"]:
            state["current_step_index"] = current_index + 1
            logger.info(f"[Task {task_id} / execute_step] Completed step {step_number} (Index: {current_index}). New index: {state['current_step_index']}")
            if state.get("error_info"):
                 state["error_info"] = None # Clear previous errors
        else:
            error_msg = step_error or f"Step failed with status: {step_status}"
            logger.error(f"[Task {task_id} / execute_step] Step {step_number} failed: {error_msg}")
            state["error_info"] = {"step": f"execute_step_{current_index}", "error": error_msg}
            await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, error_msg)

        # --- Update Progress --- 
        if task:
            progress = {
                "completed_steps": current_index + 1 if step_status in ["success", "completed_by_llm"] else current_index, # Only advance count on success
                "total_steps": len(steps),
                "current_step": {"number": step_number, "name": step_name, "status": step_status}
            }
            await crud_task.update_task(db=db_session, task_id=task_id, obj=TaskUpdate(progress_data=progress))
            logger.info(f"[Task {task_id} / execute_step] Progress updated.")

        logger.info(f"[Task {task_id} / execute_step] <<< EXITING node for step index {current_index}")
        return state

    except Exception as e:
        logger.exception(f"[Task {task_id} / execute_step] XXX UNEXPECTED EXCEPTION in node for step {current_index}: {str(e)}")
        state["error_info"] = {"step": f"execute_step_{current_index}", "error": str(e)}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, f"Unexpected error in step {current_index}: {str(e)}")
        return state
# --- End Refactored Node --- 

async def finalize_research_node(state: WorkflowState, workflow_instance: 'ResearchWorkflow', db_session, task_id) -> WorkflowState:
    """Finalize the research workflow and synthesize results."""
    logger.info(f"[Task {task_id} / finalize_research_node] >>> ENTERING Finalization Node") # Entry Log
    final_status = TaskStatus.FAILED # Default to failed unless successful
    error_info = None
    final_result = None
    
    try:
        # Check for errors accumulated during execution
        if state.get("error_info"):
            logger.error(f"[Task {task_id} / finalize_research_node] Finalizing with pre-existing error: {state['error_info']}")
            final_status = TaskStatus.FAILED
            error_info = state["error_info"]
        else:
            # --- Modify to use LLM directly for synthesis --- 
            logger.info(f"[Task {task_id} / finalize_research_node] No pre-existing errors found. Synthesizing results using LLM...")
            
            synthesis_prompt = f"""Synthesize the results from the following steps into a comprehensive final report.

Research Plan:
{json.dumps(state.get("current_plan",{}), indent=2, default=state_serializer)}

Step Outputs:
{json.dumps(state.get("agent_outputs", {}), indent=2, default=state_serializer)}

Please provide:
1. Executive Summary
2. Key Findings from each relevant step
3. Integrated Analysis
4. Supporting Evidence (if applicable)
5. Actionable Recommendations (if applicable)
6. Risk Considerations (if applicable)

Format the response as a well-structured report suitable for financial professionals."""

            try:
                 # --- Add Delay ---
                 logger.info(f"[Task {task_id} / finalize_research_node] Waiting 15s before LLM call...")
                 await asyncio.sleep(15)
                 # --- End Delay ---
                 llm_response = await workflow_instance.llm.ainvoke([HumanMessage(content=synthesis_prompt)])
                 final_result = {
                     "synthesis": llm_response.content,
                     "timestamp": datetime.utcnow().isoformat()
                 }
                 logger.info(f"[Task {task_id} / finalize_research_node] Final synthesis successful.")
                 final_status = TaskStatus.COMPLETED # Set status to completed on success
                 error_info = None # Clear error info on success

            except Exception as synth_err:
                logger.error(f"[Task {task_id} / finalize_research_node] Error during LLM synthesis: {synth_err}", exc_info=True)
                final_result = {"synthesis": f"Error synthesizing results: {str(synth_err)}"}
                final_status = TaskStatus.FAILED
                error_info = {"step": "finalize_synthesis", "error": str(synth_err)}
            # --- End Modification --- 
            
        # --- Database Update --- 
        logger.info(f"[Task {task_id} / finalize_research_node] Preparing final database update. Status: {final_status}")
        task_update = TaskUpdate(
            status=final_status,
            error_details=error_info["error"] if error_info else None,
            output_data=final_result if final_result else None,
            completed_at=datetime.utcnow() if final_status == TaskStatus.COMPLETED else None # Only set completed_at if truly completed
        )
        
        await crud_task.update_task(
            db=db_session,
            task_id=task_id,
            obj=task_update
        )
        logger.info(f"[Task {task_id} / finalize_research_node] Database task updated successfully.") # Log after DB update
        # --- End Database Update --- 
            
        # Update state
        state["final_result"] = final_result
        state["status"] = final_status
        state["error_info"] = error_info # Ensure error info is in final state if failed
        logger.info(f"[Task {task_id} / finalize_research_node] <<< EXITING Finalization Node. Final State Status: {state['status']}") # Exit Log
        return state
        
    except Exception as e:
        # Catch errors *within* the finalization node itself (e.g., DB update failure)
        logger.error(f"[Task {task_id} / finalize_research_node] XXX UNEXPECTED error during finalization: {str(e)}", exc_info=True)
        # Update state with the finalization error
        state["error_info"] = {"step": "finalize_node_internal", "error": str(e)}
        state["status"] = TaskStatus.FAILED
        # Attempt to update DB status one last time
        try:
            await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, f"Finalization node error: {str(e)}")
            logger.info(f"[Task {task_id} / finalize_research_node] Set final status to FAILED in DB due to finalization error.")
        except Exception as db_err:
            logger.error(f"[Task {task_id} / finalize_research_node] FAILED to update task status to FAILED after finalization error: {db_err}")
        logger.info(f"[Task {task_id} / finalize_research_node] <<< EXITING Finalization Node with UNEXPECTED ERROR.") # Exit Log
        return state

def check_continuation(state: WorkflowState) -> bool:
    """Check if the workflow should continue to the next step."""
    current_index = state.get("current_step_index", 0)
    task_id = state.get("task_id", "unknown")
    logger.info(f"[Task {task_id} / Edge check_continuation] Checking continuation from step index {current_index}")
    logger.debug(f"[Task {task_id} / Edge check_continuation] Full state: {json.dumps(state, indent=2, default=str)}")
    
    # Check for errors
    error_info = state.get("error_info")
    if error_info and error_info.get("error") is not None:
        logger.error(f"[Task {task_id} / Edge check_continuation] Stopping due to error: {error_info}")
        return False
    
    # Get and validate plan
    current_plan = state.get("current_plan")
    if not current_plan:
        logger.error(f"[Task {task_id} / Edge check_continuation] No plan found in state")
        return False
    
    try:
        # Extract steps using consistent logic
        workflow_plan = (
            current_plan.get("plan", {}).get("WorkflowPlan", {})
            or current_plan.get("plan", {})
            or current_plan
        )
        
        steps = (
            workflow_plan.get("Steps")
            or workflow_plan.get("steps")
            or []
        )
        
        if not steps:
            logger.error(f"[Task {task_id} / Edge check_continuation] No steps found in plan")
            return False
        
        # Map indices to steps
        step_map = {i: step for i, step in enumerate(steps)}
        total_steps = len(steps)
        
        # Check if we have more steps
        has_more_steps = current_index < total_steps
        
        if not has_more_steps:
            logger.info(f"[Task {task_id} / Edge check_continuation] No more steps to execute (current_index={current_index}, total_steps={total_steps})")
            return False
            
        # Log current step execution details
        current_outputs = state.get("agent_outputs", {})
        current_step_key = f"step_{current_index-1}"
        current_step_result = current_outputs.get(current_step_key) if current_index > 0 else None
        
        logger.info(f"[Task {task_id} / Edge check_continuation] Current step ({current_index-1}) result: {current_step_result}")
        
        if current_index > 0:
            if not current_step_result:
                logger.error(f"[Task {task_id} / Edge check_continuation] No result found for step {current_index-1}")
                return False
                
            step_status = current_step_result.get("status")
            step_error = current_step_result.get("error")
            logger.info(f"[Task {task_id} / Edge check_continuation] Step {current_index-1} status: {step_status}, error: {step_error}")
            
            if step_status not in ["success", "completed", "completed_by_llm"]:
                logger.error(f"[Task {task_id} / Edge check_continuation] Previous step {current_index-1} not properly completed (status: {step_status})")
                return False
        
        # Check if next step's dependencies are satisfied
        next_step = step_map.get(current_index)
        if next_step:
            dependencies = next_step.get("dependencies", [])
            logger.info(f"[Task {task_id} / Edge check_continuation] Checking dependencies for step {current_index}: {dependencies}")
            
            for dep in dependencies:
                dep_index = dep - 1  # Convert 1-based step number to 0-based index
                dep_result = current_outputs.get(f"step_{dep_index}")
                dep_status = dep_result.get("status") if dep_result else None
                
                logger.info(f"[Task {task_id} / Edge check_continuation] Dependency {dep} (index {dep_index}) status: {dep_status}")
                # --- Add detailed log before check ---
                check_result = dep_status not in ["success", "completed", "completed_by_llm"]
                logger.debug(f"[Task {task_id} / Edge check_continuation] Evaluating dependency: dep_result exists = {dep_result is not None}, dep_status = '{dep_status}', check_failed = {check_result}")
                loggable_dep_result = json.dumps(dep_result, indent=2, default=state_serializer)
                logger.debug(f"[Task {task_id} / Edge check_continuation] Full dependency result (step_{dep_index}): {loggable_dep_result}")
                # --- End detailed log ---
                
                if not dep_result or dep_status not in ["success", "completed", "completed_by_llm"]:
                    logger.error(f"[Task {task_id} / Edge check_continuation] Dependency step {dep} (index {dep_index}) not satisfied")
                    return False
        
        logger.info(f"[Task {task_id} / Edge check_continuation] All checks passed. Continuing to step index {current_index} ({current_index + 1}/{total_steps})")
        logger.info(f"[Task {task_id} / Edge check_continuation] <<< Returning TRUE") # Log result
        return True
        
    except Exception as e:
        logger.exception(f"[Task {task_id} / Edge check_continuation] Error checking continuation: {str(e)}")
        logger.info(f"[Task {task_id} / Edge check_continuation] <<< Returning FALSE (Exception)") # Log result
        return False

def check_approval(state: WorkflowState) -> bool:
    """Check if the plan has been approved."""
    task_id = state.get("task_id", "unknown")
    logger.info(f"[Task {task_id} / Edge check_approval] >>> ENTERING check_approval edge") # New log
    logger.info(f"[Task {task_id} / Edge check_approval] Checking plan approval status.")
    logger.debug(f"[Task {task_id} / Edge check_approval] Full state entering edge: {json.dumps(state, indent=2, default=str)}")
    
    # --- Add detailed logging ---
    plan_approved_in_state = state.get("plan_approved", False)
    stop_for_approval_in_state = state.get("stop_for_approval", False)
    error_info_in_state = state.get("error_info")
    logger.info(f"[Task {task_id} / Edge check_approval] State details - plan_approved: {plan_approved_in_state}, stop_for_approval: {stop_for_approval_in_state}, error_info: {error_info_in_state}")
    # --- End logging ---
    
    # If we have an error, don't continue
    if state.get("error_info"):
        logger.error(f"[Task {task_id} / Edge check_approval] Cannot proceed due to error_info: {state['error_info']}")
        logger.info(f"[Task {task_id} / Edge check_approval] <<< EXITING check_approval edge with result: False (due to error)") # New log
        return False
        
    # Check if we're waiting for approval (stop_for_approval should be True initially)
    # current_status = state.get("status") # Status might not be updated yet
    plan_approved = state.get("plan_approved", False)
    stop_for_approval = state.get("stop_for_approval", False)
    
    logger.info(f"[Task {task_id} / Edge check_approval] Checking: stop_for_approval={stop_for_approval}, plan_approved={plan_approved}") # New log
    
    if stop_for_approval and not plan_approved:
         logger.info(f"[Task {task_id} / Edge check_approval] Result: False (stop_for_approval=True, plan_approved=False)")
         logger.info(f"[Task {task_id} / Edge check_approval] <<< EXITING check_approval edge with result: False (waiting)") # New log
         return False # Waiting for approval

    if not plan_approved:
        logger.info(f"[Task {task_id} / Edge check_approval] Result: False (plan_approved=False)")
        logger.info(f"[Task {task_id} / Edge check_approval] <<< EXITING check_approval edge with result: False (not approved)") # New log
        return False # Plan not approved yet
        
    logger.info(f"[Task {task_id} / Edge check_approval] Result: True (plan_approved=True)")
    logger.info(f"[Task {task_id} / Edge check_approval] <<< EXITING check_approval edge with result: True (approved)") # New log
    return True

class ResearchWorkflow:
    def __init__(self, task_id: UUID, db_session):
        logger.info(f"[Task {task_id}] Initializing ResearchWorkflow")
        self.task_id = task_id
        self.db_session = db_session
        
        # Initialize planner agent
        self.planner = create_planner_agent()
        
        # --- Initialize LLM directly --- 
        if not settings.GEMINI_API_KEY:
             raise ValueError("GEMINI_API_KEY must be set in settings")
        # --- Set specific model name --- 
        self.llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=settings.GEMINI_API_KEY)
        logger.info(f"Initialized Gemini LLM: {self.llm.model}")
        # --- End LLM Initialization / Model Change --- 

        # Build workflow graph (stateless compile)
        self.graph = self._build_graph()
        logger.info(f"[Task {task_id}] Built workflow graph")

    def _build_graph(self):
        """Build the workflow graph."""
        logger.info(f"[Task {self.task_id}] Building workflow graph")
        
        workflow = StateGraph(WorkflowState)
        
        # Add nodes
        workflow.add_node("generate_plan", self._generate_plan_wrapper)
        # --- Rename execute_step node --- 
        workflow.add_node("execute_step", self._execute_step_wrapper)
        # --- End rename ---
        workflow.add_node("finalize", self._finalize_research_wrapper)
        
        # Add conditional edges 
        workflow.add_conditional_edges(
            "generate_plan",
            check_approval,
            { True: "execute_step", False: END }
        )
        workflow.add_conditional_edges(
            "execute_step",
            check_continuation,
            { True: "execute_step", False: "finalize" }
        )
        workflow.add_edge("finalize", END)
        workflow.set_entry_point("generate_plan")
        
        # Compile graph WITHOUT checkpointer
        logger.info(f"[Task {self.task_id}] Compiling graph without checkpointer.")
        return workflow.compile()

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
        """Wrapper for execute_step node."""
        logger.info(f"[Task {self.task_id}] >>> ENTERING _execute_step_wrapper node logic") 
        logger.debug(f"[Task {self.task_id}] State entering _execute_step_wrapper: {json.dumps(state, indent=2, default=state_serializer)}")
        logger.info(f"[Task {self.task_id}] _execute_step_wrapper: STARTING execution. plan_approved: {state.get('plan_approved')}, current_plan exists: {state.get('current_plan') is not None}")
        try:
            # Ensure we have a plan and it's approved
            logger.info(f"[Task {self.task_id}] Checking plan existence and approval status in _execute_step_wrapper...") 
            if not state.get("current_plan"):
                logger.error(f"[Task {self.task_id}] _execute_step_wrapper: No plan found in state") 
                raise ValueError("No plan found in state")
            if not state.get("plan_approved"):
                logger.error(f"[Task {self.task_id}] _execute_step_wrapper: Plan not approved") 
                raise ValueError("Plan not approved")
            
            logger.info(f"[Task {self.task_id}] Plan found and approved. Calling execute_step...") 
            # --- Modify call to pass self for tool/llm access --- 
            state = await execute_step(state, self, self.db_session, self.task_id)
            # --- End modification ---
            logger.info(f"[Task {self.task_id}] Exiting _execute_step_wrapper. Current index: {state.get('current_step_index')}. Error: {state.get('error_info')}")
            logger.debug(f"[Task {self.task_id}] State exiting _execute_step_wrapper: {json.dumps(state, indent=2, default=state_serializer)}")
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
        state = await finalize_research_node(state, self, self.db_session, self.task_id)
        logger.info(f"[Task {self.task_id}] Exiting _finalize_research_wrapper. Final status: {state.get('status')}")
        logger.debug(f"[Task {self.task_id}] State exiting _finalize_research_wrapper: {json.dumps(state, indent=2, default=str)}")
        return state

    async def execute(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the workflow with initial state."""
        logger.info(f"[Task {self.task_id}] Entered ResearchWorkflow.execute()") 
        # Simplified initial state using WorkflowState defaults
        state = WorkflowState(
            task_id=initial_state["task_id"],
            task_type=initial_state["task_type"],
            initial_request=initial_state["initial_request"],
            input_data=initial_state["input_data"]
        )
        logger.info(f"[Task {self.task_id}] ResearchWorkflow.execute(): State initialized. Calling self.graph.ainvoke...")
        # Execute graph - no config needed as graph is stateless now
        final_state = await self.graph.ainvoke(state)
        logger.info(f"[Task {self.task_id}] ResearchWorkflow.execute(): self.graph.ainvoke completed")
        return final_state

    async def resume(self) -> Dict[str, Any]:
        """Resume workflow execution after plan approval."""
        logger.info(f"[Task {self.task_id} / ResearchWorkflow.resume] >>> ENTERING resume method") # Entry Log
        try:
            logger.info(f"[Task {self.task_id} / ResearchWorkflow.resume] Getting task from DB...") 
            task = await crud_task.get_task(self.db_session, self.task_id)
            if not task:
                logger.error(f"[Task {self.task_id} / ResearchWorkflow.resume] Task not found in DB") 
                raise ValueError("Task not found")
            logger.info(f"[Task {self.task_id} / ResearchWorkflow.resume] Task found. Status: {task.status}") 
            
            # --- Load State from DB Checkpoint --- 
            logger.info(f"[Task {self.task_id} / ResearchWorkflow.resume] Loading state from checkpoint_data...")
            if not task.checkpoint_data:
                logger.error(f"[Task {self.task_id} / ResearchWorkflow.resume] Checkpoint data missing in task!")
                raise ValueError("Checkpoint data missing")
            
            try:
                loaded_state_dict = json.loads(task.checkpoint_data)
                logger.info(f"[Task {self.task_id} / ResearchWorkflow.resume] Checkpoint JSON loaded.")
                # Rehydrate state using WorkflowState class to ensure methods/defaults
                state = WorkflowState(**loaded_state_dict) # Use **kwargs for Pydantic init
                # Update status and flags for resume
                state["plan_approved"] = True
                state["stop_for_approval"] = False
                state["status"] = TaskStatus.IN_PROGRESS # Ensure status reflects running
                logger.info(f"[Task {self.task_id} / ResearchWorkflow.resume] State rehydrated. Plan approved flag set.")
            except Exception as load_err:
                logger.error(f"[Task {self.task_id} / ResearchWorkflow.resume] FAILED TO LOAD/REHYDRATE STATE: {str(load_err)}", exc_info=True)
                raise ValueError(f"Failed to load checkpoint state: {str(load_err)}")
            # --- End Load State --- 

            # Execute graph - no config needed
            logger.info(f"[Task {self.task_id} / ResearchWorkflow.resume] Calling self.graph.ainvoke...") 
            logger.debug(f"[Task {self.task_id} / ResearchWorkflow.resume] State for resume graph: {json.dumps(state, default=state_serializer)}")
            final_state = await self.graph.ainvoke(state) # No config needed
            logger.info(f"[Task {self.task_id} / ResearchWorkflow.resume] self.graph.ainvoke completed") 
            logger.debug(f"[Task {self.task_id} / ResearchWorkflow.resume] Final state from resume graph: {json.dumps(final_state, default=state_serializer)}")
            logger.info(f"[Task {self.task_id} / ResearchWorkflow.resume] <<< EXITING resume method successfully.") # Exit Log
            return final_state
            
        except Exception as e:
            logger.error(f"[Task {self.task_id} / ResearchWorkflow.resume] XXX UNEXPECTED error during resume: {str(e)}", exc_info=True)
            logger.info(f"[Task {self.task_id} / ResearchWorkflow.resume] <<< EXITING resume method with ERROR.") # Exit Log
            # Optionally re-raise or return error state
            raise # Re-raise the exception for now

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