import pytest
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from app.models.task import TaskStatus, TaskType, Task
from app.workflows.research_workflow import ResearchWorkflow
from app.workflows.strategy_workflow import StrategyWorkflow
from app.workflows.backtest_workflow import BacktestWorkflow
from app.core.logging import get_logger
from app.crud import crud_task
from app.schemas.task import TaskCreate

logger = get_logger(__name__)

@pytest.mark.asyncio
async def test_end_to_end_workflow(db_session):
    """Test complete workflow: Research -> Strategy -> Backtest"""
    
    # Generate unique task ID
    task_id = uuid4()
    logger.info("starting_end_to_end_test", task_id=str(task_id))
    
    try:
        # Create research task in database
        research_task_create = TaskCreate(
            title="Research AAPL Stock",
            description="Comprehensive research on Apple stock performance",
            task_type=TaskType.RESEARCH,
            input_data={
                "ticker_symbol": "AAPL",
                "time_horizon": "long_term",
                "research_depth": "comprehensive",
                "focus_areas": ["fundamentals", "technicals", "sentiment"],
                "additional_context": "Focus on AI/ML impact on business"
            }
        )
        research_task = await crud_task.create_task(db_session, research_task_create)
        
        # Step 1: Research Workflow
        research_request = {
            "task_id": str(research_task.id),
            "task_type": TaskType.RESEARCH.value,
            "initial_request": {
                "ticker_symbol": "AAPL",
                "time_horizon": "long_term",
                "research_depth": "comprehensive",
                "focus_areas": ["fundamentals", "technicals", "sentiment"],
                "additional_context": "Focus on AI/ML impact on business"
            },
            "input_data": {
                "ticker_symbol": "AAPL",
                "time_horizon": "long_term",
                "research_depth": "comprehensive"
            },
            "current_step_index": 0,
            "current_plan": None,
            "intermediate_results": {},
            "error_info": None,
            "status": TaskStatus.PLANNING
        }
        
        logger.info("starting_research_workflow", task_id=str(research_task.id), request=research_request)
        research_workflow = ResearchWorkflow(research_task.id, db_session)
        research_state = await research_workflow.execute(research_request)
        
        # Approve the research plan
        assert research_state["status"] == TaskStatus.PENDING_APPROVAL
        await crud_task.update_task_status(db_session, research_task.id, TaskStatus.IN_PROGRESS)
        research_state = await research_workflow.resume()
        
        assert research_state["status"] == TaskStatus.COMPLETED
        assert "research_results" in research_state
        logger.info("research_workflow_completed", 
                   task_id=str(research_task.id),
                   status=research_state["status"])
        
        # Create strategy task in database
        strategy_task_create = TaskCreate(
            title="Develop AAPL Trading Strategy",
            description="Develop trend following strategy for Apple stock",
            task_type=TaskType.STRATEGY_DEV,
            input_data={
                "ticker_symbol": "AAPL",
                "time_horizon": "long_term",
                "strategy_type": "trend_following",
                "risk_profile": "moderate",
                "include_indicators": ["rsi", "macd", "bollinger"]
            }
        )
        strategy_task = await crud_task.create_task(db_session, strategy_task_create)
        
        # Step 2: Strategy Workflow
        strategy_request = {
            "task_id": str(strategy_task.id),
            "task_type": TaskType.STRATEGY_DEV.value,
            "initial_request": {
                "ticker_symbol": "AAPL",
                "time_horizon": "long_term",
                "strategy_type": "trend_following",
                "risk_profile": "moderate",
                "include_indicators": ["rsi", "macd", "bollinger"]
            },
            "input_data": {
                "research_results": research_state["research_results"]
            },
            "current_step_index": 0,
            "current_plan": None,
            "intermediate_results": {},
            "error_info": None,
            "status": TaskStatus.PLANNING
        }
        
        logger.info("starting_strategy_workflow", task_id=str(strategy_task.id), request=strategy_request)
        strategy_workflow = StrategyWorkflow(strategy_task.id, db_session)
        strategy_state = await strategy_workflow.execute(strategy_request)
        
        # Approve the strategy plan
        assert strategy_state["status"] == TaskStatus.PENDING_APPROVAL
        await crud_task.update_task_status(db_session, strategy_task.id, TaskStatus.IN_PROGRESS)
        strategy_state = await strategy_workflow.resume()
        
        assert strategy_state["status"] == TaskStatus.COMPLETED
        assert "strategy" in strategy_state
        logger.info("strategy_workflow_completed", 
                   task_id=str(strategy_task.id),
                   status=strategy_state["status"])
        
        # Create backtest task in database
        backtest_task_create = TaskCreate(
            title="Backtest AAPL Strategy",
            description="Backtest trend following strategy on Apple stock",
            task_type=TaskType.BACKTEST,
            input_data={
                "strategy_id": strategy_state["strategy"]["id"],
                "ticker_symbol": "AAPL",
                "start_date": datetime.now() - timedelta(days=365),
                "end_date": datetime.now(),
                "initial_capital": 100000.0
            }
        )
        backtest_task = await crud_task.create_task(db_session, backtest_task_create)
        
        # Step 3: Backtest Workflow
        backtest_request = {
            "task_id": str(backtest_task.id),
            "task_type": TaskType.BACKTEST.value,
            "initial_request": {
                "strategy_id": strategy_state["strategy"]["id"],
                "ticker_symbol": "AAPL",
                "start_date": datetime.now() - timedelta(days=365),
                "end_date": datetime.now(),
                "initial_capital": 100000.0
            },
            "input_data": {
                "strategy": strategy_state["strategy"]
            },
            "current_step_index": 0,
            "current_plan": None,
            "intermediate_results": {},
            "error_info": None,
            "status": TaskStatus.PLANNING
        }
        
        logger.info("starting_backtest_workflow", task_id=str(backtest_task.id), request=backtest_request)
        backtest_workflow = BacktestWorkflow(backtest_task.id, db_session)
        backtest_state = await backtest_workflow.execute(backtest_request)
        
        # Approve the backtest plan
        assert backtest_state["status"] == TaskStatus.PENDING_APPROVAL
        await crud_task.update_task_status(db_session, backtest_task.id, TaskStatus.IN_PROGRESS)
        backtest_state = await backtest_workflow.resume()
        
        assert backtest_state["status"] == TaskStatus.COMPLETED
        assert "backtest_results" in backtest_state
        assert "performance_metrics" in backtest_state["backtest_results"]
        
        # Verify metrics
        metrics = backtest_state["backtest_results"]["performance_metrics"]
        assert "total_return" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics
        assert "win_rate" in metrics
        
        logger.info("backtest_workflow_completed", 
                   task_id=str(backtest_task.id),
                   status=backtest_state["status"],
                   metrics=metrics)
        
        return {
            "research_task_id": str(research_task.id),
            "research_results": research_state["research_results"],
            "strategy_task_id": str(strategy_task.id),
            "strategy": strategy_state["strategy"],
            "backtest_task_id": str(backtest_task.id),
            "backtest_results": backtest_state["backtest_results"]
        }
        
    except Exception as e:
        logger.error("end_to_end_test_failed",
                    task_id=str(task_id),
                    error=str(e),
                    error_type=type(e).__name__)
        raise

@pytest.mark.asyncio
async def test_error_handling(db_session):
    """Test error handling with invalid inputs"""
    
    task_id = uuid4()
    logger.info("starting_error_handling_test", task_id=str(task_id))
    
    try:
        # Create task in database with invalid ticker
        task_create = TaskCreate(
            title="Research Invalid Stock",
            description="Research on invalid ticker",
            task_type=TaskType.RESEARCH,
            input_data={
                "ticker_symbol": "INVALID_TICKER",
                "time_horizon": "long_term",
                "research_depth": "comprehensive"
            }
        )
        task = await crud_task.create_task(db_session, task_create)
        
        # Test with invalid ticker
        research_request = {
            "task_id": str(task.id),
            "task_type": TaskType.RESEARCH.value,
            "initial_request": {
                "ticker_symbol": "INVALID_TICKER",
                "time_horizon": "long_term",
                "research_depth": "comprehensive"
            },
            "input_data": {
                "ticker_symbol": "INVALID_TICKER",
                "time_horizon": "long_term",
                "research_depth": "comprehensive"
            },
            "current_step_index": 0,
            "current_plan": None,
            "intermediate_results": {},
            "error_info": None,
            "status": TaskStatus.PLANNING
        }
        
        logger.info("testing_invalid_ticker", task_id=str(task.id), request=research_request)
        research_workflow = ResearchWorkflow(task.id, db_session)
        research_state = await research_workflow.execute(research_request)
        
        # Approve the plan to trigger the error
        assert research_state["status"] == TaskStatus.PENDING_APPROVAL
        await crud_task.update_task_status(db_session, task.id, TaskStatus.IN_PROGRESS)
        research_state = await research_workflow.resume()
        
        assert research_state["status"] == TaskStatus.FAILED
        assert "error_info" in research_state
        assert research_state["error_info"]["step"] is not None
        assert research_state["error_info"]["error"] is not None
        
        logger.info("error_handling_test_completed", 
                   task_id=str(task.id),
                   error=research_state["error_info"])
        
    except Exception as e:
        logger.error("error_handling_test_failed",
                    task_id=str(task_id),
                    error=str(e),
                    error_type=type(e).__name__)
        raise

if __name__ == "__main__":
    # For manual testing
    import asyncio
    from app.db.session import SessionLocal
    
    async def run_tests():
        async with SessionLocal() as session:
            results = await test_end_to_end_workflow(session)
            print("Test Results:", results)
    
    asyncio.run(run_tests()) 