from typing import Dict, Any
from .base_agent import BaseAssistantAgent
import json
import re

PLANNER_PROMPT = """You are a financial research planner. Your role is to break down research requests into clear, executable steps.

For each research request, create a detailed step-by-step plan that includes:
1. A sequence of research steps
2. Clear description of each step
3. Required tools for each step (specify "None" if no tool is needed)
4. Dependencies between steps
5. Success criteria for each step

Available Tools (use these EXACT tool names when a tool is needed):
1. Financial Data Tools:
   - fetch_historical_data
   - calculate_technical_indicators
2. Knowledge Base Tools:
   - query_local_kb

IMPORTANT TOOL USAGE RULES:
1. For steps that need tools, list them using EXACT names from above
2. For steps that don't need tools, write "None"
3. NEVER make up new tool names or variations
4. NEVER combine tool names or add explanations
5. NEVER leave the tools field empty

Format each step EXACTLY like this:

Step 1: [Step Name]
Description: [What needs to be done]
Tools: fetch_historical_data
Dependencies: None
Success Criteria: [How to know the step is complete]

Step 2: [Step Name]
Description: [What needs to be done]
Tools: None
Dependencies: 1
Success Criteria: [How to know the step is complete]

Step 3: [Step Name]
Description: [What needs to be done]
Tools: calculate_technical_indicators, query_local_kb
Dependencies: 1, 2
Success Criteria: [How to know the step is complete]

IMPORTANT FORMATTING RULES:
1. When a step requires tools, use the EXACT tool names as shown (no variations or additions)
2. When a step doesn't require any tools, write "None"
3. Step numbers must start at 1 and be sequential
4. Dependencies must only reference earlier step numbers
5. Be specific and actionable in descriptions
6. Include clear success criteria"""

class PlannerAgent(BaseAssistantAgent):
    def __init__(self):
        super().__init__(
            name="PlannerAgent",
            description="Financial research planning specialist"
        )
        self.system_prompt = PLANNER_PROMPT
    
    def _parse_plan_from_text(self, text: str) -> Dict[str, Any]:
        """Parse a natural language plan into structured format."""
        steps = []
        current_step = None
        
        # Split text into lines and process
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Look for step number pattern (e.g., "Step 1:", "1.", etc.)
            step_match = re.match(r'^(?:Step\s*)?(\d+)[:.]\s*(.+)', line)
            if step_match:
                # If we have a previous step, add it to steps
                if current_step:
                    steps.append(current_step)
                
                # Start new step
                step_num = int(step_match.group(1))
                step_name = step_match.group(2).strip()
                current_step = {
                    "step_number": step_num,
                    "step_name": step_name,
                    "description": "",
                    "tools": [],
                    "dependencies": [],
                    "success_criteria": ""
                }
                continue
            
            if not current_step:
                continue
                
            # Look for section markers
            lower_line = line.lower()
            if "description:" in lower_line:
                current_step["description"] = line.split(":", 1)[1].strip()
            elif "tools:" in lower_line or "using:" in lower_line:
                tools_text = line.split(":", 1)[1].strip().lower()
                # Check if tools are explicitly marked as None
                if tools_text in ["none", "no tools", "n/a"]:
                    current_step["tools"] = []
                else:
                    # Split by comma and clean each tool name
                    tools = []
                    for tool in tools_text.split(","):
                        tool = tool.strip()
                        # Remove any text in parentheses
                        tool = re.sub(r'\s*\([^)]*\)', '', tool).strip()
                        # Only add if it's a valid tool name
                        valid_tools = ["fetch_historical_data", "calculate_technical_indicators", "query_local_kb"]
                        if tool in valid_tools:
                            tools.append(tool)
                    current_step["tools"] = tools
            elif "dependencies:" in lower_line or "depends on:" in lower_line:
                deps_text = line.split(":", 1)[1].strip()
                if deps_text.lower() not in ["none", "no dependencies", "n/a", "-"]:
                    current_step["dependencies"] = [
                        int(d.strip()) for d in deps_text.split(",")
                        if d.strip().isdigit()
                    ]
            elif "success criteria:" in lower_line or "completion criteria:" in lower_line:
                current_step["success_criteria"] = line.split(":", 1)[1].strip()
            elif current_step["description"] == "":  # Use as description if no other match
                current_step["description"] = line
        
        # Add the last step if exists
        if current_step:
            steps.append(current_step)
        
        return {"plan": {"steps": steps}}
    
    def _validate_step(self, step: Dict[str, Any]) -> None:
        """Validate a single step in the plan."""
        required_fields = ["step_number", "step_name", "description", "tools", "dependencies", "success_criteria"]
        
        # Check required fields
        missing_fields = [field for field in required_fields if field not in step]
        if missing_fields:
            raise ValueError(f"Step missing required fields: {', '.join(missing_fields)}")
            
        # Validate field types
        if not isinstance(step["step_number"], int):
            raise ValueError("step_number must be an integer")
        if not isinstance(step["step_name"], str):
            raise ValueError("step_name must be a string")
        if not isinstance(step["description"], str):
            raise ValueError("description must be a string")
        if not isinstance(step["tools"], list):
            raise ValueError("tools must be a list")
        if not isinstance(step["dependencies"], list):
            raise ValueError("dependencies must be a list")
        if not isinstance(step["success_criteria"], str):
            raise ValueError("success_criteria must be a string")
            
        # Validate step number is positive
        if step["step_number"] < 1:
            raise ValueError("step_number must be positive")
            
        # Validate tools contains only valid tools if any are specified
        valid_tools = ["fetch_historical_data", "calculate_technical_indicators", "query_local_kb"]
        invalid_tools = [t for t in step["tools"] if t not in valid_tools]
        if invalid_tools:
            raise ValueError(f"Invalid tools specified: {', '.join(invalid_tools)}")
    
    async def generate_plan(self, task_type: str, initial_request: str) -> Dict[str, Any]:
        """Generate a research plan."""
        prompt = f"""{self.system_prompt}

Task Type: {task_type}
Research Request: {initial_request}

Please create a detailed step-by-step plan. For each step, specify:
1. Step number and name
2. Description of what needs to be done
3. Tools required (use exact names from the list above)
4. Dependencies on previous steps (if any)
5. Success criteria

Format each step clearly with headers, for example:

Step 1: Initial Data Collection
Description: Fetch historical market data for analysis
Tools: fetch_historical_data
Dependencies: None
Success Criteria: Successfully retrieved market data

Step 2: Technical Analysis
Description: Calculate key technical indicators
Tools: calculate_technical_indicators
Dependencies: 1
Success Criteria: All technical indicators computed successfully"""

        try:
            # Get natural language plan from LLM
            print("Generating LLM response...")  # Debug logging
            response = await self.generate_response(prompt, expect_json=False)  # Explicitly set expect_json=False
            print(f"Raw LLM Response:\n{response}")  # Debug logging
            
            # Parse the natural language plan into structured format
            try:
                print("Attempting to parse plan from text...")  # Debug logging
                plan = self._parse_plan_from_text(response)
                print(f"Successfully parsed plan. Structure:\n{json.dumps(plan, indent=2)}")  # Debug logging
                
                # Additional validation logging
                print("Validating plan structure...")  # Debug logging
                if not isinstance(plan, dict):
                    print("Error: Plan is not a dictionary")  # Debug logging
                    raise ValueError("Plan must be a dictionary")
                if "plan" not in plan:
                    print("Error: Missing 'plan' key")  # Debug logging
                    raise ValueError("Missing top-level 'plan' key")
                if not isinstance(plan["plan"], dict):
                    print("Error: Plan value is not a dictionary")  # Debug logging
                    raise ValueError("plan value must be a dictionary")
                if "steps" not in plan["plan"]:
                    print("Error: Missing 'steps' key")  # Debug logging
                    raise ValueError("Missing 'steps' in plan")
                
                steps = plan["plan"]["steps"]
                print(f"Found {len(steps)} steps in plan")  # Debug logging
                
                if not isinstance(steps, list):
                    print("Error: Steps is not a list")  # Debug logging
                    raise ValueError("Steps must be a list")
                if not steps:
                    print("Error: Steps list is empty")  # Debug logging
                    raise ValueError("Steps list cannot be empty")
                
                # Validate each step
                print("Validating individual steps...")  # Debug logging
                for i, step in enumerate(steps, 1):
                    print(f"Validating step {i}...")  # Debug logging
                    self._validate_step(step)
                print("All steps validated successfully")  # Debug logging
                
                # Validate step numbers are sequential
                step_numbers = [step["step_number"] for step in steps]
                expected_numbers = list(range(1, len(steps) + 1))
                print(f"Step numbers: {step_numbers}")  # Debug logging
                print(f"Expected numbers: {expected_numbers}")  # Debug logging
                if step_numbers != expected_numbers:
                    print("Error: Step numbers are not sequential")  # Debug logging
                    raise ValueError("Step numbers must be sequential starting from 1")
                
                # Validate dependencies refer to valid step numbers
                print("Validating step dependencies...")  # Debug logging
                for step in steps:
                    for dep in step["dependencies"]:
                        if not isinstance(dep, int) or dep < 1 or dep >= step["step_number"]:
                            print(f"Error: Invalid dependency {dep} in step {step['step_number']}")  # Debug logging
                            raise ValueError(f"Invalid dependency {dep} in step {step['step_number']}")
                print("All dependencies validated successfully")  # Debug logging
                
                # Convert plan to proper format for workflow
                workflow_plan = {
                    "plan": {
                        "steps": [
                            {
                                "step_number": step["step_number"],
                                "step_name": step["step_name"],
                                "description": step["description"],
                                "tools": step["tools"],
                                "dependencies": step["dependencies"],
                                "success_criteria": step["success_criteria"]
                            }
                            for step in steps
                        ]
                    }
                }
                
                print(f"Final workflow plan:\n{json.dumps(workflow_plan, indent=2)}")  # Debug logging
                return workflow_plan
                
            except Exception as parse_error:
                print(f"Error parsing plan: {str(parse_error)}")  # Debug logging
                raise ValueError(f"Failed to parse plan from LLM response: {str(parse_error)}")
            
        except Exception as e:
            print(f"Error in generate_plan: {str(e)}")  # Debug logging
            raise ValueError(f"Error generating plan: {str(e)}")

def create_planner_agent() -> PlannerAgent:
    return PlannerAgent()