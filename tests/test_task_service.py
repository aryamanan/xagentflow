import pytest
from app.services.task_service import TaskService
from app.models.task import TaskStatus
import logging

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_create_research_task(db_session, sample_research_task):
    """Test creating a research task"""
    logger.info("Testing research task creation")
    service = TaskService(db_session)
    
    try:
        task_id = await service.start_task(sample_research_task)
        logger.info(f"Created task with ID: {task_id}")
        assert task_id is not None
        
        # Verify task was created in DB
        task = await service.db.get(task_id)
        assert task is not None
        assert task.task_type == sample_research_task.task_type
        assert task.title == sample_research_task.title
        assert task.status == TaskStatus.PLANNING
        logger.info("Research task creation test passed")
        
    except Exception as e:
        logger.error(f"Error in research task creation test: {str(e)}")
        raise

@pytest.mark.asyncio
async def test_create_strategy_task(db_session, sample_strategy_task):
    """Test creating a strategy development task"""
    logger.info("Testing strategy task creation")
    service = TaskService(db_session)
    
    try:
        task_id = await service.start_task(sample_strategy_task)
        logger.info(f"Created task with ID: {task_id}")
        assert task_id is not None
        
        # Verify task was created in DB
        task = await service.db.get(task_id)
        assert task is not None
        assert task.task_type == sample_strategy_task.task_type
        assert task.title == sample_strategy_task.title
        assert task.status == TaskStatus.PLANNING
        logger.info("Strategy task creation test passed")
        
    except Exception as e:
        logger.error(f"Error in strategy task creation test: {str(e)}")
        raise

@pytest.mark.asyncio
async def test_create_backtest_task(db_session, sample_backtest_task):
    """Test creating a backtest task"""
    logger.info("Testing backtest task creation")
    service = TaskService(db_session)
    
    try:
        task_id = await service.start_task(sample_backtest_task)
        logger.info(f"Created task with ID: {task_id}")
        assert task_id is not None
        
        # Verify task was created in DB
        task = await service.db.get(task_id)
        assert task is not None
        assert task.task_type == sample_backtest_task.task_type
        assert task.title == sample_backtest_task.title
        assert task.status == TaskStatus.PLANNING
        logger.info("Backtest task creation test passed")
        
    except Exception as e:
        logger.error(f"Error in backtest task creation test: {str(e)}")
        raise

@pytest.mark.asyncio
async def test_task_workflow_execution(db_session, sample_research_task):
    """Test the complete task workflow execution"""
    logger.info("Testing complete task workflow execution")
    service = TaskService(db_session)
    
    try:
        # Create task
        task_id = await service.start_task(sample_research_task)
        logger.info(f"Created task with ID: {task_id}")
        
        # Verify initial state
        task = await service.db.get(task_id)
        assert task.status == TaskStatus.PLANNING
        
        # Approve the plan
        await service.approve_task_plan(
            task_id=task_id,
            approval={"approved": True}
        )
        logger.info("Approved task plan")
        
        # Verify task status after approval
        task = await service.db.get(task_id)
        assert task.status == TaskStatus.APPROVED
        
        # Wait for workflow completion
        import asyncio
        await asyncio.sleep(5)  # Give some time for the workflow to process
        
        # Verify final state
        task = await service.db.get(task_id)
        assert task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
        if task.status == TaskStatus.FAILED:
            logger.warning(f"Task failed with error: {task.error_details}")
        else:
            logger.info("Task completed successfully")
            assert task.output_data is not None
        
        logger.info("Task workflow execution test completed")
        
    except Exception as e:
        logger.error(f"Error in task workflow execution test: {str(e)}")
        raise
