import asyncio
import logging
import json
from uuid import uuid4

from app.agents.coordinator_agent import create_coordinator_agent
from app.agents.research_agent import create_research_agent
from app.workflows.state import WorkflowState
from app.models.task import TaskStatus, TaskType

# --- Configuration ---
# Configure logging to see output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
# --- End Configuration ---

# --- Synthetic Data ---
SYNTHETIC_TASK_ID = str(uuid4())
SYNTHETIC_PLAN = {
    "plan": {
        "steps": [
            {
                "step_number": 1,
                "step_name": "Fetch AAPL Data",
                "description": "Fetch historical market data for Apple (AAPL) stock for the past 1 year.",
                "tools": ["fetch_historical_data"],
                "dependencies": [],
                "success_criteria": "Successfully retrieved AAPL historical data for 1 year."
            },
            {
                "step_number": 2,
                "step_name": "Calculate AAPL Indicators",
                "description": "Calculate RSI and MACD for the fetched AAPL data.",
                "tools": ["calculate_technical_indicators"],
                "dependencies": [1],
                "success_criteria": "RSI and MACD calculated for AAPL data."
            },
            {
                "step_number": 3,
                "step_name": "Query KB for AAPL Info",
                "description": "Query knowledge base for recent news or analysis on AAPL.",
                "tools": ["query_local_kb"],
                "dependencies": [1],
                "success_criteria": "Relevant information about AAPL retrieved from KB."
            },
             {
                "step_number": 4,
                "step_name": "Synthesize Findings",
                "description": "Synthesize the data and analysis into a brief summary.",
                "tools": [],
                "dependencies": [1, 2, 3],
                "success_criteria": "Summary report created."
            }
        ]
    }
}

INITIAL_STATE = WorkflowState(
    task_id=SYNTHETIC_TASK_ID,
    task_type=TaskType.RESEARCH.value,
    initial_request="Synthetic Test: Analyze AAPL stock performance",
    input_data={"symbol": "AAPL"},
    current_step_index=0, # Start at the first step
    current_plan=SYNTHETIC_PLAN,
    plan_approved=True, # Mark plan as approved
    agent_inputs={},
    agent_outputs={},
    intermediate_results={},
    final_result=None,
    error_info=None,
    metadata={},
    status=TaskStatus.IN_PROGRESS, # Start in progress
    stop_for_approval=False
)
# --- End Synthetic Data ---


async def main():
    logger.info(f"--- Starting Synthetic Execution Test for Task {SYNTHETIC_TASK_ID} ---")

    # Instantiate agents
    coordinator = create_coordinator_agent()
    researcher = create_research_agent()
    
    # --- Execute Step 1: Fetch Data ---
    step_to_execute_index = 0 # Index 0 corresponds to Step 1
    step_info = SYNTHETIC_PLAN["plan"]["steps"][step_to_execute_index]
    logger.info(f"--- Attempting to execute Step {step_info['step_number']}: {step_info['step_name']} ---")
    
    current_state = INITIAL_STATE.copy()
    current_state["current_step_index"] = step_to_execute_index

    try:
        step_result = await coordinator.aexecute_step(
            step=step_info,
            researcher=researcher,
            state=current_state
        )
        logger.info(f"--- Step {step_info['step_number']} Result ---")
        logger.info(json.dumps(step_result, indent=2))
        
        # Update state for potential next steps (optional for this test)
        current_state["agent_outputs"][f"step_{step_to_execute_index}"] = step_result
        if step_result.get("status") == "completed":
             current_state["current_step_index"] += 1
        else:
             current_state["error_info"] = step_result.get("error")
             logger.error(f"Step failed: {step_result.get('error')}")
             return # Stop if a step fails

    except Exception as e:
        logger.error(f"--- Error during Step {step_info['step_number']} execution ---", exc_info=True)

    logger.info("--- Synthetic Execution Test Finished ---")


if __name__ == "__main__":
    # Ensure necessary environment variables are set (e.g., GEMINI_API_KEY)
    # You might need to load them using python-dotenv or set them manually
    # import os
    # from dotenv import load_dotenv
    # load_dotenv()
    # print(f"Gemini Key Loaded: {os.getenv('GEMINI_API_KEY') is not None}")

    asyncio.run(main()) 