import asyncio
import logging
import sys
from uuid import uuid4
from app.workflows.research_workflow import ResearchWorkflow
from app.models.task import TaskType

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('event_loop_debug.log')
    ]
)

logger = logging.getLogger(__name__)

async def test_workflow_execution():
    """Test the research workflow execution with detailed event loop logging."""
    task_id = uuid4()
    logger.info(f"Starting test with task ID: {task_id}")
    
    try:
        # Log initial event loop state
        current_loop = asyncio.get_event_loop()
        logger.debug(f"Main test event loop: {id(current_loop)}, Running: {current_loop.is_running()}")
        
        # Initialize workflow
        workflow = ResearchWorkflow(task_id, None)
        logger.info("Workflow initialized")
        
        # Prepare test state
        initial_state = {
            "task_id": str(task_id),
            "task_type": TaskType.RESEARCH.value,
            "initial_request": "Analyze tech sector performance",
            "input_data": {},
            "current_step_index": 0,
            "current_plan": None,
            "intermediate_results": {},
            "error_info": None
        }
        
        # Execute workflow
        logger.info("Starting workflow execution")
        final_state = await workflow.execute(initial_state)
        
        # Log results
        if final_state.get("error_info"):
            logger.error(f"Workflow failed: {final_state['error_info']}")
        else:
            logger.info("Workflow completed successfully")
            logger.debug(f"Final state: {final_state}")
            
    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(test_workflow_execution())
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise 