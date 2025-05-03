import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.models.task import TaskStatus
from app.workflows.strategy_workflow import StrategyWorkflow
from app.workflows.state import WorkflowState

@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    
    # Mock get_task
    session.execute.return_value.scalar_one_or_none = MagicMock(return_value=MagicMock(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        task_type="STRATEGY_DEV",
        title="Test Strategy",
        input_data={"prompt": "Test prompt"},
        status=TaskStatus.APPROVED,
        plan={"steps": ["step1", "step2"]},
        error_details=None
    ))
    
    # Mock update_task_status and update_task_plan
    session.execute.return_value.scalar_one = AsyncMock(return_value=True)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = AsyncMock()
    return session

@pytest.fixture
def mock_planner():
    planner = AsyncMock()
    planner.generate_plan = AsyncMock(return_value={
        "plan": {
            "strategy_name": "Test Strategy",
            "workflow_plan": {
                "main_objectives": ["Test objective"],
                "required_steps": [{"step_id": 1, "description": "Test step"}]
            }
        }
    })
    return planner

@pytest.fixture
def mock_coordinator():
    coordinator = AsyncMock()
    coordinator.execute_tool = AsyncMock(return_value={"data": "test_data"})
    return coordinator

@pytest.fixture
def mock_strategist():
    strategist = AsyncMock()
    strategist.generate_strategy = AsyncMock(return_value={
        "logic": "test_logic",
        "params": {"param1": "value1"}
    })
    return strategist

@pytest.fixture
def mock_memory_saver():
    memory = AsyncMock()
    memory.get_state = AsyncMock(return_value=None)
    memory.save_state = AsyncMock()
    return memory

@pytest.fixture
def mock_graph():
    graph = AsyncMock()
    graph.ainvoke = AsyncMock(return_value={"status": "completed", "result": {"strategy": {"logic": "test_logic", "params": {"param1": "value1"}}}})
    graph.get_state = AsyncMock(return_value=MagicMock(values={"task_id": UUID("12345678-1234-5678-1234-567812345678")}))
    graph.update_state = AsyncMock()
    return graph

@pytest.fixture
def mock_state_info():
    state_info = MagicMock()
    state_info.values = {
        "task_id": UUID("12345678-1234-5678-1234-567812345678"),
        "task_type": "STRATEGY_DEV",
        "initial_request": {
            "task_type": "STRATEGY_DEV",
            "title": "Test Strategy",
            "input_data": {"prompt": "Test prompt"},
            "market_data_params": {
                "symbol": "TSLA",
                "start_date": "2020-01-01",
                "end_date": "2025-05-03"
            }
        },
        "plan_approved": True,
        "task_status": TaskStatus.APPROVED,
        "agent_inputs": {},
        "agent_outputs": {},
        "intermediate_results": {
            "market_data": {"data": "test_data"},
            "strategy": {"logic": "test_logic", "params": {"param1": "value1"}}
        },
        "final_result": None,
        "error_info": None,
        "metadata": {}
    }
    return state_info

@pytest.fixture
def test_task_id():
    return UUID("12345678-1234-5678-1234-567812345678")

@pytest.fixture
def test_initial_state(test_task_id):
    return {
        "task_id": test_task_id,
        "task_type": "STRATEGY_DEV",
        "initial_request": {
            "task_type": "STRATEGY_DEV",
            "title": "Test Strategy",
            "input_data": {
                "prompt": "Test prompt",
                "indicator_config": {},
                "strategy_requirements": {}
            },
            "market_data_params": {
                "symbol": "TSLA",
                "start_date": "2020-01-01",
                "end_date": "2025-05-03"
            }
        },
        "plan_approved": False,
        "task_status": TaskStatus.PLANNING,
        "agent_inputs": {},
        "agent_outputs": {},
        "intermediate_results": {},
        "final_result": None,
        "error_info": None,
        "metadata": {}
    }

@pytest.mark.asyncio
async def test_workflow_initialization(
    test_task_id,
    mock_db_session,
    mock_planner,
    mock_coordinator,
    mock_strategist,
    mock_memory_saver,
    mock_graph
):
    with patch("app.workflows.strategy_workflow.create_planner_agent", return_value=mock_planner), \
         patch("app.workflows.strategy_workflow.create_strategy_agent", return_value=mock_strategist), \
         patch("app.workflows.strategy_workflow.create_coordinator_agent", return_value=mock_coordinator), \
         patch("app.workflows.strategy_workflow.MemorySaver", return_value=mock_memory_saver), \
         patch.object(StateGraph, "compile", return_value=mock_graph):
        
        workflow = StrategyWorkflow(test_task_id, mock_db_session)
        assert workflow.task_id == test_task_id
        assert workflow.db_session == mock_db_session
        assert workflow.planner == mock_planner
        assert workflow.strategist == mock_strategist
        assert workflow.coordinator == mock_coordinator

@pytest.mark.asyncio
async def test_workflow_execute(
    test_task_id,
    test_initial_state,
    mock_db_session,
    mock_planner,
    mock_coordinator,
    mock_strategist,
    mock_memory_saver,
    mock_graph,
    mock_state_info
):
    with patch("app.workflows.strategy_workflow.create_planner_agent", return_value=mock_planner), \
         patch("app.workflows.strategy_workflow.create_strategy_agent", return_value=mock_strategist), \
         patch("app.workflows.strategy_workflow.create_coordinator_agent", return_value=mock_coordinator), \
         patch("app.workflows.strategy_workflow.MemorySaver", return_value=mock_memory_saver), \
         patch.object(StateGraph, "compile", return_value=mock_graph):
        
        workflow = StrategyWorkflow(test_task_id, mock_db_session)
        
        # Execute workflow
        result = await workflow.execute(test_initial_state)
        
        # Verify graph was invoked
        mock_graph.ainvoke.assert_called_once()

@pytest.mark.asyncio
async def test_workflow_resume(
    test_task_id,
    test_initial_state,
    mock_db_session,
    mock_planner,
    mock_coordinator,
    mock_strategist,
    mock_memory_saver,
    mock_graph,
    mock_state_info
):
    with patch("app.workflows.strategy_workflow.create_planner_agent", return_value=mock_planner), \
         patch("app.workflows.strategy_workflow.create_strategy_agent", return_value=mock_strategist), \
         patch("app.workflows.strategy_workflow.create_coordinator_agent", return_value=mock_coordinator), \
         patch("app.workflows.strategy_workflow.MemorySaver", return_value=mock_memory_saver), \
         patch.object(StateGraph, "compile", return_value=mock_graph), \
         patch.object(StrategyWorkflow, "get_state", new=AsyncMock(return_value=mock_state_info)):
        
        workflow = StrategyWorkflow(test_task_id, mock_db_session)
        
        # Resume workflow
        result = await workflow.resume()
        
        # Verify graph was invoked
        mock_graph.ainvoke.assert_called_once()
