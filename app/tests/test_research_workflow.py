import pytest
from uuid import uuid4
from app.workflows.research_workflow import ResearchWorkflow
from app.models.task import TaskStatus
import logging

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_research_workflow_initialization(db_session):
    """Test research workflow initialization"""
    logger.info("Testing research workflow initialization")
    task_id = uuid4()
    
    try:
        workflow = ResearchWorkflow(task_id=task_id, db_session=db_session)
        assert workflow is not None
        assert workflow.task_id == task_id
        assert workflow.db_session == db_session
        assert workflow.planner is not None
        assert workflow.researcher is not None
        assert workflow.coordinator is not None
        assert workflow.memory is not None
        assert workflow.graph is not None
        logger.info("Research workflow initialization test passed")
        
    except Exception as e:
        logger.error(f"Error in research workflow initialization test: {str(e)}")
        raise

@pytest.mark.asyncio
async def test_research_workflow_execution(db_session):
    """Test research workflow execution"""
    logger.info("Testing research workflow execution")
    task_id = uuid4()
    
    try:
        workflow = ResearchWorkflow(task_id=task_id, db_session=db_session)
        
        # Prepare initial state
        initial_state = {
            "task_id": str(task_id),
            "task_type": "RESEARCH",
            "initial_request": "Research AAPL stock performance",
            "task_status": TaskStatus.PLANNING
        }
        logger.info(f"Starting workflow with initial state: {initial_state}")
        
        # Execute workflow
        final_state = await workflow.execute(initial_state)
        
        # Verify final state
        assert final_state is not None
        assert "error_info" not in final_state, f"Workflow failed with error: {final_state.get('error_info')}"
        assert "current_plan" in final_state
        logger.info("Research workflow execution test passed")
        
    except Exception as e:
        logger.error(f"Error in research workflow execution test: {str(e)}")
        raise

@pytest.mark.asyncio
async def test_research_workflow_resume(db_session):
    """Test research workflow resume functionality"""
    logger.info("Testing research workflow resume")
    task_id = uuid4()
    
    try:
        workflow = ResearchWorkflow(task_id=task_id, db_session=db_session)
        
        # Prepare and execute initial state
        initial_state = {
            "task_id": str(task_id),
            "task_type": "RESEARCH",
            "initial_request": "Research AAPL stock performance",
            "task_status": TaskStatus.PLANNING
        }
        logger.info("Starting initial workflow execution")
        await workflow.execute(initial_state)
        
        # Get saved state
        saved_state = await workflow.get_state()
        assert saved_state is not None
        logger.info("Retrieved saved state")
        
        # Resume workflow
        logger.info("Resuming workflow")
        final_state = await workflow.resume()
        
        # Verify resumed state
        assert final_state is not None
        assert final_state.get("plan_approved") is True
        assert "error_info" not in final_state, f"Resumed workflow failed with error: {final_state.get('error_info')}"
        logger.info("Research workflow resume test passed")
        
    except Exception as e:
        logger.error(f"Error in research workflow resume test: {str(e)}")
        raise

@pytest.mark.asyncio
async def test_research_workflow_error_handling(db_session):
    """Test research workflow error handling"""
    logger.info("Testing research workflow error handling")
    task_id = uuid4()
    
    try:
        workflow = ResearchWorkflow(task_id=task_id, db_session=db_session)
        
        # Prepare invalid initial state to trigger error
        invalid_state = {
            "task_id": str(task_id),
            "task_type": "INVALID_TYPE",  # Invalid task type
            "initial_request": None,  # Missing required field
            "task_status": TaskStatus.PLANNING
        }
        logger.info(f"Starting workflow with invalid state: {invalid_state}")
        
        # Execute workflow and expect error
        final_state = await workflow.execute(invalid_state)
        
        # Verify error handling
        assert final_state is not None
        assert "error_info" in final_state
        assert final_state["error_info"]["step"] is not None
        assert final_state["error_info"]["error"] is not None
        logger.info(f"Workflow correctly handled error: {final_state['error_info']}")
        logger.info("Research workflow error handling test passed")
        
    except Exception as e:
        logger.error(f"Error in research workflow error handling test: {str(e)}")
        raise
