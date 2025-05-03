from typing import TypedDict, Optional, List, Dict, Any, Union
from uuid import UUID

class WorkflowState(TypedDict):
    """Type definition for workflow state."""
    task_id: Union[UUID, str]
    task_type: str
    initial_request: Dict[str, Any]
    input_data: Dict[str, Any]
    current_step_index: int
    current_plan: Optional[Dict[str, Any]]
    plan_approved: bool
    agent_inputs: Dict[str, Any]
    agent_outputs: Dict[str, Any]
    intermediate_results: Dict[str, Any]
    final_result: Optional[Dict[str, Any]]
    error_info: Optional[Dict[str, Any]]
    metadata: Dict[str, Any]
    status: str