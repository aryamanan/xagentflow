from typing import Dict, Any, List
from .base_agent import BaseAssistantAgent
import logging
import json

logger = logging.getLogger(__name__)

COORDINATOR_PROMPT = """You are a workflow coordinator responsible for managing the execution of complex tasks.
Your role is to:
1. Understand user requests and delegate to appropriate agents
2. Coordinate between planner and executor agents
3. Monitor progress and handle any issues
4. Ensure tasks are completed successfully
5. Provide clear status updates and results

Always maintain a clear overview of the workflow and ensure proper communication between agents."""

class CoordinatorAgent(BaseAssistantAgent):
    def __init__(self):
        super().__init__(
            name="coordinator",
            description="Workflow coordination and task management specialist"
        )
        self.system_prompt = COORDINATOR_PROMPT

    async def initiate_conversation(self, recipient: BaseAssistantAgent, message: str) -> Dict[str, Any]:
        """Initiate a conversation with another agent."""
        prompt = f"""{self.system_prompt}

Recipient: {recipient.name} ({recipient.description})
Message: {message}

Please coordinate this task by:
1. Understanding the request
2. Delegating appropriately
3. Monitoring execution
4. Ensuring completion
5. Providing clear results"""

        response = await self.generate_response(prompt)
        return {"content": response}

    async def aexecute_step(self, step: Dict[str, Any], researcher: BaseAssistantAgent, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single step in the workflow using the researcher agent. (Revised Logic v2)"""
        step_name = step.get('step_name', 'Unknown Step')
        task_id = state.get("task_id", "unknown")
        step_description = step.get('description', 'No description')
        step_tools = step.get('tools', [])
        step_success_criteria = step.get('success_criteria', 'No criteria')
        
        logger.info(f"[Task {task_id}] Coordinator executing step: {step_name}")
        
        # Construct a direct execution prompt for the researcher (removed as we call directly)
        # ... 

        try:
            # --- Call Researcher Directly --- 
            logger.info(f"[Task {task_id} / Step {step_name}] Calling researcher.execute_step_directly...") 
            step_execution_result = await researcher.execute_step_directly(step=step, state=state)
            logger.info(f"[Task {task_id} / Step {step_name}] Researcher execute_step_directly result received: {str(step_execution_result)[:150]}...")
            # --- End Direct Call --- 

            # (Optional) Validate the result (can be simplified or removed if adding too much overhead)
            logger.info(f"[Task {task_id} / Step {step_name}] Asking self (Coordinator) to validate results...")
            validation = await self.generate_response(f"""Please validate the research results below against the success criteria.

Step Name: {step_name}
Success Criteria: {step_success_criteria}

Research Results:
{json.dumps(step_execution_result, indent=2, default=str)} # Pass the actual result dictionary

Validation Request:
1. Does the result meet the success criteria?
2. Summarize the validation outcome (Pass/Fail with reason).""", expect_json=False)
            logger.info(f"[Task {task_id} / Step {step_name}] Validation complete.")

            # Return a combined result
            return {
                "step_name": step_name,
                "research_result": step_execution_result, # Contains status, results, etc.
                "validation": validation,
                # Use status from the researcher's direct execution
                "status": step_execution_result.get("status", "error") if isinstance(step_execution_result, dict) else "error",
                "error": step_execution_result.get("error") if isinstance(step_execution_result, dict) else None
            }

        except Exception as e:
            logger.error(f"[Task {task_id} / Step {step_name}] Error during direct step execution call: {str(e)}", exc_info=True)
            return {
                "step_name": step_name,
                "error": str(e),
                "status": "failed"
            }

def create_coordinator_agent() -> CoordinatorAgent:
    return CoordinatorAgent()