from typing import Dict, Any
import json
import re
from app.agents.base_agent import BaseAssistantAgent

PLANNER_PROMPT = """You are a workflow planning agent responsible for creating detailed execution plans.
Your task is to break down complex workflows into clear, actionable steps.
Consider dependencies, resources, and potential bottlenecks in your planning.
Always ensure your plans are practical and executable."""

class PlannerAgent(BaseAssistantAgent):
    def __init__(self):
        super().__init__(
            name="planner",
            description="Workflow planning and task breakdown specialist"
        )
        self.system_prompt = PLANNER_PROMPT

    async def generate_plan(self, task_type: str, initial_request: str) -> Dict[str, Any]:
        """Generate a workflow plan based on the task type and initial request.
        
        Args:
            task_type: Type of task to plan (e.g., RESEARCH, STRATEGY_DEV, BACKTEST)
            initial_request: Initial user request or task description
            
        Returns:
            Dict containing the plan and status
        """
        prompt = f"""{self.system_prompt}

Task Type: {task_type}
Initial Request: {initial_request}

Please create a detailed workflow plan that includes:
1. Main objectives
2. Required steps with clear dependencies
3. Success criteria for each step
4. Required resources and tools
5. Potential risks and mitigation strategies
6. Expected outcomes and deliverables

Format the response as a structured JSON with these sections."""

        try:
            response_text = await self.generate_response(prompt)
            
            # Extract JSON from markdown code block if present
            match = re.search(r"```(json)?\s*({.*?})\s*```", response_text, re.DOTALL | re.IGNORECASE)
            if match:
                json_string = match.group(2)
            else:
                # Assume the response is plain JSON
                json_string = response_text
            
            try:
                parsed_plan = json.loads(json_string)
                return {
                    "plan": parsed_plan,
                    "status": "success"
                }
            except json.JSONDecodeError as e:
                return {
                    "plan": response_text,
                    "status": "parse_error",
                    "error": f"Failed to parse plan JSON: {str(e)}"
                }
                
        except Exception as e:
            return {
                "plan": None,
                "status": "error",
                "error": f"Failed to generate plan: {str(e)}"
            }

def create_planner_agent() -> PlannerAgent:
    return PlannerAgent()