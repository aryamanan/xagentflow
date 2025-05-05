from typing import TypedDict, Optional, List, Dict, Any, Union
from uuid import UUID
from app.models.task import TaskStatus
import logging
import json

logger = logging.getLogger(__name__)

class ToolUsage(TypedDict):
    """Track tool usage in workflow."""
    tool_name: str
    timestamp: str
    status: str
    input_params: Dict[str, Any]
    output: Optional[Dict[str, Any]]
    error: Optional[str]

class WorkflowState(TypedDict):
    """Represents the state of the research workflow."""
    task_id: str
    initial_request: Dict[str, Any] # Original request that started the task
    current_plan: Optional[List[Dict[str, Any]]] # The approved plan
    current_step_index: int # 0-based index of the step being executed or about to be
    plan_approved: bool # Flag indicating if the plan is approved for execution
    step_outputs: Dict[int, Any] # Stores outputs for each step index
    final_result: Optional[Dict[str, Any]] # Final output data for the task
    error_info: Optional[Dict[str, Any]] # Details if an error occurred

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setdefault("status", TaskStatus.PLANNING)
        self.setdefault("current_step_index", 0)
        self.setdefault("intermediate_results", {})
        self.setdefault("error_info", None)
        self.setdefault("current_plan", None)
        self.setdefault("plan_approved", False)
        self.setdefault("stop_for_approval", False)
        self.setdefault("tool_usage", [])
        self.setdefault("validation_errors", [])
        self.setdefault("retry_count", 0)
    
    @property
    def is_failed(self) -> bool:
        return self["status"] == TaskStatus.FAILED
    
    @property
    def is_complete(self) -> bool:
        return self["status"] == TaskStatus.COMPLETED
    
    @property
    def needs_approval(self) -> bool:
        return self["status"] == TaskStatus.PENDING_APPROVAL
    
    def _validate_plan_structure(self, plan: Dict[str, Any]) -> None:
        """Validate the structure of a plan."""
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
        
        # Validate each step
        for step in steps:
            required_fields = ["step_number", "step_name", "description", "tools", "dependencies", "success_criteria"]
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
            
            # Validate tools is not empty
            if not step["tools"]:
                raise ValueError("tools list cannot be empty")
        
        # Validate step numbers are sequential
        step_numbers = [step["step_number"] for step in steps]
        expected_numbers = list(range(1, len(steps) + 1))
        if step_numbers != expected_numbers:
            raise ValueError("Step numbers must be sequential starting from 1")
        
        # Validate dependencies
        for step in steps:
            for dep in step["dependencies"]:
                if not isinstance(dep, int) or dep < 1 or dep >= step["step_number"]:
                    raise ValueError(f"Invalid dependency {dep} in step {step['step_number']}")
    
    def set_plan(self, plan: Dict[str, Any]) -> None:
        """Set the current plan with validation."""
        try:
            # Handle string plans
            if isinstance(plan, str):
                try:
                    plan = json.loads(plan)
                except json.JSONDecodeError:
                    raise ValueError("Plan is not valid JSON")
            
            # Validate plan structure
            self._validate_plan_structure(plan)
            
            # Update state
            self["current_plan"] = plan
            self["status"] = TaskStatus.PENDING_APPROVAL
            self["stop_for_approval"] = True
            self["validation_errors"] = []  # Clear any previous validation errors
            logger.info("Plan set successfully")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error setting plan: {error_msg}")
            self.add_validation_error(error_msg)
            self.set_error("planning", error_msg)
    
    def approve_plan(self) -> None:
        """Approve the current plan."""
        if not self["current_plan"]:
            error_msg = "No plan to approve"
            logger.error(error_msg)
            self.set_error("approval", error_msg)
            return
        
        try:
            # Re-validate plan before approval
            self._validate_plan_structure(self["current_plan"])
            
            self["plan_approved"] = True
            self["status"] = TaskStatus.IN_PROGRESS
            self["stop_for_approval"] = False
            self["validation_errors"] = []  # Clear any validation errors
            logger.info("Plan approved")
            
        except Exception as e:
            error_msg = f"Plan validation failed during approval: {str(e)}"
            logger.error(error_msg)
            self.set_error("approval", error_msg)
    
    def track_tool_usage(self, tool_name: str, input_params: Dict[str, Any]) -> None:
        """Track tool usage with input parameters."""
        from datetime import datetime
        
        usage = {
            "tool_name": tool_name,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "pending",
            "input_params": input_params,
            "output": None,
            "error": None
        }
        self["tool_usage"].append(usage)
        logger.info(f"Tool usage tracked: {tool_name}")
    
    def update_tool_result(self, tool_name: str, result: Dict[str, Any], error: Optional[str] = None) -> None:
        """Update the result of a tool usage."""
        if not self["tool_usage"]:
            logger.warning(f"No tool usage found for {tool_name}")
            return
        
        latest_usage = self["tool_usage"][-1]
        if latest_usage["tool_name"] != tool_name:
            logger.error(f"Tool mismatch: expected {tool_name}, found {latest_usage['tool_name']}")
            return
        
        latest_usage["output"] = result
        latest_usage["error"] = error
        latest_usage["status"] = "error" if error else "success"
        
        if error:
            logger.error(f"Tool {tool_name} failed: {error}")
            self.add_validation_error(f"Tool execution failed: {tool_name} - {error}")
    
    def add_validation_error(self, error: str) -> None:
        """Add a validation error."""
        self["validation_errors"].append(error)
        logger.error(f"Validation error: {error}")
    
    def set_error(self, step: str, error: str) -> None:
        """Set error information."""
        self["error_info"] = {"step": step, "error": error}
        self["status"] = TaskStatus.FAILED
        logger.error(f"Workflow error in step {step}: {error}")
    
    def add_result(self, step: int, result: Dict[str, Any]) -> None:
        """Add intermediate result for a step."""
        self["intermediate_results"][step] = result
        logger.info(f"Added result for step {step}")
    
    def get_current_step(self) -> Optional[Dict[str, Any]]:
        """Get the current step from the plan."""
        if not self["current_plan"] or "steps" not in self["current_plan"].get("plan", {}):
            logger.warning("No current plan or steps found")
            return None
        
        steps = self["current_plan"]["plan"]["steps"]
        if not steps or self["current_step_index"] >= len(steps):
            logger.warning("Current step index out of range")
            return None
        
        return steps[self["current_step_index"]]
    
    def advance_step(self) -> bool:
        """Advance to the next step. Returns True if there are more steps."""
        if not self["current_plan"] or "steps" not in self["current_plan"].get("plan", {}):
            logger.warning("Cannot advance step: no plan or steps found")
            return False
        
        steps = self["current_plan"]["plan"]["steps"]
        self["current_step_index"] += 1
        
        if self["current_step_index"] >= len(steps):
            self["status"] = TaskStatus.COMPLETED
            logger.info("Workflow completed")
            return False
        
        logger.info(f"Advanced to step {self['current_step_index']}")
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "status": self["status"].value if isinstance(self["status"], TaskStatus) else self["status"],
            "current_step": self["current_step_index"],
            "plan": self["current_plan"],
            "results": self["intermediate_results"],
            "error": self["error_info"],
            "needs_approval": self.needs_approval,
            "tool_usage": self["tool_usage"],
            "validation_errors": self["validation_errors"],
            "retry_count": self["retry_count"]
        }