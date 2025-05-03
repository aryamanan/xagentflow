from typing import Dict, Any, Optional
from uuid import UUID
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.agents import (
    create_planner_agent,
    create_backtest_agent,
    create_coordinator_agent
)
from app.crud import crud_task
from app.models.task import TaskStatus
from app.schemas.task import TaskUpdate
from app.workflows.state import WorkflowState
from datetime import datetime

# --- Node Functions --- 

async def generate_backtest_plan_node(state: WorkflowState, planner, db_session, task_id) -> WorkflowState:
    plan_result = await planner.generate_plan(
        task_type="BACKTEST",
        initial_request=state["initial_request"]
    )
    state["current_plan"] = plan_result["plan"]
    
    await crud_task.update_task_plan(
        db=db_session,
        task_id=task_id,
        plan=plan_result["plan"]
    )
    await crud_task.update_task_status(db_session, task_id, TaskStatus.PENDING_APPROVAL)
    return state

async def execute_fetch_backtest_data_node(state: WorkflowState, coordinator, db_session, task_id) -> WorkflowState:
    if "intermediate_results" not in state:
        state["intermediate_results"] = {}
    try:
        data_params = state.get("initial_request", {}).get("backtest_data_params", {})
        if not data_params:
            raise ValueError("Backtest data parameters missing")
            
        result = await coordinator.execute_tool("get_market_data", data_params)
        state["intermediate_results"]["market_data"] = result
    except Exception as e:
        state["error_info"] = {"step": "fetch_backtest_data", "error": str(e)}
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, error_details=str(state["error_info"]))
    return state

async def execute_run_backtest_node(state: WorkflowState, coordinator) -> WorkflowState:
    if "intermediate_results" not in state:
        state["intermediate_results"] = {}
    try:
        market_data = state["intermediate_results"].get("market_data")
        initial_request = state.get("initial_request", {})
        strategy_params = initial_request.get("strategy_params", {})
        logic_identifier = initial_request.get("strategy_logic")

        if not market_data or not logic_identifier:
             raise ValueError("Missing market data or strategy logic for backtest")

        result = await coordinator.execute_tool(
            "run_vectorbt_backtest",
            {
                "data_dict": market_data,
                "strategy_params": strategy_params,
                "logic_identifier": logic_identifier
            }
        )
        state["intermediate_results"]["backtest_results"] = result
    except Exception as e:
        state["error_info"] = {"step": "run_backtest", "error": str(e)}
    return state

async def finalize_backtest_node(state: WorkflowState, backtester, db_session, task_id) -> WorkflowState:
    final_status = TaskStatus.COMPLETED
    final_result = None
    error_info = state.get("error_info")

    if error_info:
        final_status = TaskStatus.FAILED
    else:
        backtest_results = state.get("intermediate_results", {}).get("backtest_results")
        if not backtest_results:
            final_status = TaskStatus.FAILED
            error_info = {"step": "finalize", "error": "Backtest results missing or failed."}
            state["error_info"] = error_info
        else:
            try:
                summary = await backtester.analyze_results(backtest_results)
                final_result = {
                    "backtest_summary": summary,
                    "detailed_metrics": backtest_results.get("metrics", {}),
                    "trades": backtest_results.get("trades", [])
                }
                state["final_result"] = final_result
            except Exception as e:
                 final_result = {
                     "backtest_summary": f"Error during analysis: {str(e)}",
                     "detailed_metrics": backtest_results.get("metrics", {}),
                     "trades": backtest_results.get("trades", [])
                 }
                 state["final_result"] = final_result
                 final_status = TaskStatus.FAILED
                 error_info = {"step": "finalize_analysis", "error": str(e)}
                 state["error_info"] = error_info
             
    await crud_task.update_task_status(
        db=db_session,
        task_id=task_id,
        status=final_status,
        error_details=str(error_info) if error_info else None
    )
            
    if final_status == TaskStatus.COMPLETED and final_result:
         task_update_payload = TaskUpdate(output_data=final_result, completed_at=datetime.utcnow())
         await crud_task.update_task(
              db=db_session,
              task_id=task_id,
              task_update=task_update_payload
         )
            
    return state

# --- Conditional Edge Logic --- 

def should_continue_backtest_edge(state: WorkflowState) -> str:
    if state.get("error_info"):
        return "finalize_backtest"

    # If plan is approved, proceed
    if state.get("plan_approved", False):
        intermediate_results = state.get("intermediate_results", {})
        if "market_data" not in intermediate_results:
            return "execute_fetch_backtest_data"
        if "backtest_results" not in intermediate_results:
            return "execute_run_backtest"
        return "finalize_backtest" # All steps done
    else:
        # Interrupted state or rejected plan
        return "finalize_backtest"


# --- Workflow Class --- 

class BacktestWorkflow:
    def __init__(self, task_id: UUID, db_session):
        self.task_id = task_id
        self.db_session = db_session
        self.planner = create_planner_agent()
        self.backtester = create_backtest_agent()
        self.coordinator = create_coordinator_agent()
        self.memory = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(WorkflowState)

        # Define async wrappers
        async def _wrapped_generate_plan(state): 
            return await generate_backtest_plan_node(state, self.planner, self.db_session, self.task_id)
        async def _wrapped_fetch_data(state): 
            return await execute_fetch_backtest_data_node(state, self.coordinator, self.db_session, self.task_id)
        async def _wrapped_run_backtest(state): 
            return await execute_run_backtest_node(state, self.coordinator)
        async def _wrapped_finalize(state): 
            return await finalize_backtest_node(state, self.backtester, self.db_session, self.task_id)

        # Add nodes
        workflow.add_node("generate_backtest_plan", _wrapped_generate_plan)
        workflow.add_node("execute_fetch_backtest_data", _wrapped_fetch_data)
        workflow.add_node("execute_run_backtest", _wrapped_run_backtest)
        workflow.add_node("finalize_backtest", _wrapped_finalize)

        # Set entry point
        workflow.set_entry_point("generate_backtest_plan")

        # Conditional edge after planning (will be interrupted)
        workflow.add_conditional_edges(
            "generate_backtest_plan",
            should_continue_backtest_edge, 
            {
                "execute_fetch_backtest_data": "execute_fetch_backtest_data",
                "finalize_backtest": "finalize_backtest"
            }
        )
        
        # Edges for resuming after approval
        workflow.add_conditional_edges(
            "execute_fetch_backtest_data",
            should_continue_backtest_edge, 
            {
                "execute_run_backtest": "execute_run_backtest",
                "finalize_backtest": "finalize_backtest"
            }
        )
        workflow.add_conditional_edges(
            "execute_run_backtest",
            should_continue_backtest_edge, 
            {
                 "finalize_backtest": "finalize_backtest"
            }
        )

        workflow.add_edge("finalize_backtest", END)

        # Compile with checkpointing and interruption
        return workflow.compile(checkpointer=self.memory, interrupt_after=["generate_backtest_plan"])

    async def execute(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        if "task_status" not in initial_state:
             task = await crud_task.get_task(self.db_session, self.task_id)
             initial_state["task_status"] = task.status if task else TaskStatus.PLANNING
             
        config = {"configurable": {"thread_id": str(self.task_id)}}
        return await self.graph.ainvoke(initial_state, config=config)

    async def resume(self) -> Dict[str, Any]:
        """Resume execution after interruption."""
        config = {"configurable": {"thread_id": str(self.task_id)}}
        await self.graph.update_state(config, {"plan_approved": True, "task_status": TaskStatus.APPROVED})
        return await self.graph.ainvoke(None, config=config)
        
    async def get_state(self) -> Optional[WorkflowState]:
        """Get the current state from the checkpointer."""
        config = {"configurable": {"thread_id": str(self.task_id)}}
        state_info = await self.graph.get_state(config)
        return state_info.values if state_info else None