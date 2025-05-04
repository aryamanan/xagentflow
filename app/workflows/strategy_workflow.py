from typing import Dict, Any, Optional
from uuid import UUID
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.agents import (
    create_planner_agent,
    create_strategy_agent,
    create_coordinator_agent
)
from app.models.task import TaskStatus
from app.crud import task as crud_task
from app.core.logging import TaskLogger
from app.workflows.state import WorkflowState
from datetime import datetime

# --- Node Functions --- 

async def generate_strategy_plan_node(state: WorkflowState, planner, db_session, task_id) -> WorkflowState:
    """Generate a strategy development plan."""
    logger = TaskLogger(str(task_id))
    logger.log_state_change("generate_plan_start", {"state": state})
    
    try:
        # Get task from database
        task = await crud_task.get_task(db_session, task_id)
        if not task:
            logger.log_state_change("generate_plan_failed", {"error": "Task not found"})
            raise ValueError("Task not found")
        
        # Generate plan using planner agent
        logger.log_agent_interaction("planner", "generate_plan", {"prompt": task.input_data.get("prompt")})
        plan_result = await planner.generate_plan(
            task_type="STRATEGY_DEV",
            initial_request=state["initial_request"]
        )
        
        # Update task with plan
        await crud_task.update_task_plan(
            db=db_session,
            task_id=task_id,
            plan=plan_result["plan"]
        )
        await crud_task.update_task_status(db_session, task_id, TaskStatus.PENDING_APPROVAL)
        
        # Update state
        state["current_plan"] = plan_result["plan"]
        logger.log_state_change("generate_plan_complete", {"plan": plan_result["plan"]})
        return state
        
    except Exception as e:
        error_info = {"step": "generate_plan", "error": str(e)}
        state["error_info"] = error_info
        logger.log_state_change("generate_plan_failed", error_info)
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, error_details=str(error_info))
        raise

async def execute_fetch_market_data_node(state: WorkflowState, coordinator, db_session, task_id) -> WorkflowState:
    """Fetch market data for strategy development."""
    logger = TaskLogger(str(task_id))
    logger.log_state_change("fetch_data_start", {"state": state})
    
    try:
        # Ensure intermediate_results exists
        if "intermediate_results" not in state:
            state["intermediate_results"] = {}
            
        # Get market data parameters
        market_data_params = state.get("initial_request", {}).get("market_data_params", {})
        if not market_data_params:
            logger.log_state_change("fetch_data_failed", {"error": "Market data parameters missing"})
            raise ValueError("Market data parameters missing in initial request")
             
        # Execute market data fetch
        logger.log_agent_interaction("coordinator", "fetch_market_data", {"params": market_data_params})
        result = await coordinator.execute_tool(
            "get_market_data",
            market_data_params 
        )
        
        # Store results
        state["intermediate_results"]["market_data"] = result
        logger.log_state_change("fetch_data_complete", {"result": result})
        return state
        
    except Exception as e:
        error_info = {"step": "fetch_market_data", "error": str(e)}
        state["error_info"] = error_info
        logger.log_state_change("fetch_data_failed", error_info)
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, error_details=str(error_info))
        raise

async def execute_strategy_development_node(state: WorkflowState, strategist, coordinator) -> WorkflowState:
    """Develop and backtest the trading strategy."""
    logger = TaskLogger(str(state["task_id"]))
    logger.log_state_change("develop_strategy_start", {"state": state})
    
    try:
        # Ensure intermediate_results exists
        if "intermediate_results" not in state:
            state["intermediate_results"] = {}
            
        # Get market data
        market_data = state["intermediate_results"].get("market_data")
        if not market_data:
            logger.log_state_change("develop_strategy_failed", {"error": "Market data not found"})
            raise ValueError("Market data not found in state")
        
        # Ensure initial_request exists and has needed keys
        initial_request = state.get("initial_request", {})
        indicator_config = initial_request.get("indicators", {})
        strategy_requirements = initial_request.get("strategy_requirements", {})
        optimize_params = initial_request.get("optimize_params", False)

        # Calculate indicators
        logger.log_agent_interaction("coordinator", "calculate_indicators", {"data": market_data, "indicator_config": indicator_config})
        indicators = await coordinator.execute_tool(
            "calculate_indicators",
            {"data": market_data, "indicator_config": indicator_config}
        )
        
        # Generate strategy
        logger.log_agent_interaction("strategist", "generate_strategy", {"market_data": market_data, "indicators": indicators, "requirements": strategy_requirements})
        strategy = await strategist.generate_strategy(
            market_data=market_data,
            indicators=indicators,
            requirements=strategy_requirements
        )
        
        # Optimize if requested
        if optimize_params:
            # Ensure coordinator has optimize_strategy_params tool
            logger.log_agent_interaction("coordinator", "optimize_strategy_params", {"strategy_logic_description": strategy.get("logic", ""), "data_dict": market_data, "param_space": strategy.get("param_space", {})})
            optimization = await coordinator.execute_tool(
                "optimize_strategy_params",
                {
                    "strategy_logic_description": strategy.get("logic", ""),
                    "data_dict": market_data,
                    "param_space": strategy.get("param_space", {})
                }
            )
            strategy["optimized_params"] = optimization.get("best_params", {})
        
        # Store results
        state["intermediate_results"]["strategy"] = strategy
        logger.log_state_change("develop_strategy_complete", {"result": strategy})
        return state
        
    except Exception as e:
        error_info = {"step": "develop_strategy", "error": str(e)}
        state["error_info"] = error_info
        logger.log_state_change("develop_strategy_failed", error_info)
        raise

async def finalize_strategy_node(state: WorkflowState, db_session, task_id) -> WorkflowState:
    """Finalize the strategy development task."""
    logger = TaskLogger(str(task_id))
    logger.log_state_change("finalize_start", {"state": state})
    
    try:
        final_status = TaskStatus.COMPLETED
        final_result = None
        error_info = state.get("error_info")

        if error_info:
            final_status = TaskStatus.FAILED
        else:
            # Ensure intermediate_results and strategy exist before finalizing
            intermediate_results = state.get("intermediate_results", {})
            strategy = intermediate_results.get("strategy")
            market_data_params = state.get("initial_request", {}).get("market_data_params", {})

            if not strategy:
                final_status = TaskStatus.FAILED
                error_info = {"step": "finalize", "error": "Strategy development failed or missing."}
                state["error_info"] = error_info
            else:
                final_result = {
                    "strategy": strategy,
                    "market_data_summary": {
                        "period": market_data_params,
                        "indicators": intermediate_results.get("indicators", {})
                    }
                }
                state["final_result"] = final_result
         
        # Update status and error details first
        await crud_task.update_task_status(
            db=db_session,
            task_id=task_id,
            status=final_status,
            error_details=str(error_info) if error_info else None
        )
        
        # Update result if successful
        if final_status == TaskStatus.COMPLETED and final_result:
            task_update_payload = TaskUpdate(output_data=final_result, completed_at=datetime.utcnow()) 
            await crud_task.update_task(
                db=db_session,
                task_id=task_id,
                task_update=task_update_payload
            )
            
        logger.log_state_change("finalize_complete", {"result": final_result})
        return state
        
    except Exception as e:
        error_info = {"step": "finalize", "error": str(e)}
        state["error_info"] = error_info
        logger.log_state_change("finalize_failed", error_info)
        await crud_task.update_task_status(db_session, task_id, TaskStatus.FAILED, error_details=str(error_info))
        raise

# --- Conditional Edge Logic --- 

def should_continue_strategy_edge(state: WorkflowState) -> str:
    if state.get("error_info"):
        return "finalize_strategy"

    # If plan is approved, proceed
    if state.get("plan_approved", False):
        intermediate_results = state.get("intermediate_results", {})
        if "market_data" not in intermediate_results:
            return "execute_fetch_market_data"
        if "strategy" not in intermediate_results:
            return "execute_strategy_development"
        return "finalize_strategy" # All steps done
    else:
        # Interrupted state or rejected plan
        return "finalize_strategy"


# --- Workflow Class --- 

class StrategyWorkflow:
    def __init__(self, task_id: UUID, db_session):
        self.task_id = task_id
        self.db_session = db_session
        self.logger = TaskLogger(str(task_id))
        
        # Initialize agents
        self.planner = create_planner_agent()
        self.strategist = create_strategy_agent()
        self.coordinator = create_coordinator_agent()
        
        # Initialize memory saver
        self.memory_saver = MemorySaver()
        
        # Build workflow graph
        self.graph = self._build_graph()
        
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(WorkflowState)
        self.logger.log_state_change("building_graph")

        # Define async wrappers
        async def _wrapped_generate_plan(state): 
            self.logger.log_state_change("generating_plan", {"state": state})
            try:
                result = await generate_strategy_plan_node(state, self.planner, self.db_session, self.task_id)
                self.logger.log_state_change("plan_generated", {"result": result})
                return result
            except Exception as e:
                self.logger.log_state_change("plan_generation_failed", {"error": str(e)})
                raise

        async def _wrapped_fetch_data(state): 
            self.logger.log_state_change("fetching_data", {"state": state})
            try:
                result = await execute_fetch_market_data_node(state, self.coordinator, self.db_session, self.task_id)
                self.logger.log_state_change("data_fetched", {"result": result})
                return result
            except Exception as e:
                self.logger.log_state_change("data_fetch_failed", {"error": str(e)})
                raise

        async def _wrapped_dev_strategy(state): 
            self.logger.log_state_change("developing_strategy", {"state": state})
            try:
                result = await execute_strategy_development_node(state, self.strategist, self.coordinator)
                self.logger.log_state_change("strategy_developed", {"result": result})
                return result
            except Exception as e:
                self.logger.log_state_change("strategy_development_failed", {"error": str(e)})
                raise

        async def _wrapped_finalize(state): 
            self.logger.log_state_change("finalizing", {"state": state})
            try:
                result = await finalize_strategy_node(state, self.db_session, self.task_id)
                self.logger.log_state_change("finalized", {"result": result})
                return result
            except Exception as e:
                self.logger.log_state_change("finalization_failed", {"error": str(e)})
                raise

        # Add nodes
        workflow.add_node("generate_strategy_plan", _wrapped_generate_plan)
        workflow.add_node("execute_fetch_market_data", _wrapped_fetch_data)
        workflow.add_node("execute_strategy_development", _wrapped_dev_strategy)
        workflow.add_node("finalize_strategy", _wrapped_finalize)

        # Set entry point
        workflow.set_entry_point("generate_strategy_plan")

        # Conditional edge after planning (will be interrupted)
        workflow.add_conditional_edges(
            "generate_strategy_plan",
            should_continue_strategy_edge, 
            {
                 "execute_fetch_market_data": "execute_fetch_market_data",
                 "finalize_strategy": "finalize_strategy" # Route if error/not approved
            }
        )
        
        # Edges for resuming after approval
        workflow.add_conditional_edges(
            "execute_fetch_market_data",
            should_continue_strategy_edge, 
            {
                "execute_strategy_development": "execute_strategy_development",
                "finalize_strategy": "finalize_strategy"
            }
        )
        workflow.add_conditional_edges(
            "execute_strategy_development",
            should_continue_strategy_edge, 
            {
                "finalize_strategy": "finalize_strategy"
            }
        )
        
        workflow.add_edge("finalize_strategy", END)

        # Compile with checkpointing and interruption
        self.logger.log_state_change("graph_built")
        return workflow.compile(checkpointer=self.memory_saver, interrupt_after=["generate_strategy_plan"])

    async def execute(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.log_state_change("executing", {"initial_state": initial_state})
        try:
            if "task_status" not in initial_state:
                task = await crud_task.get_task(self.db_session, self.task_id)
                initial_state["task_status"] = task.status if task else TaskStatus.PLANNING
                
            config = {"configurable": {"thread_id": str(self.task_id)}}
            result = await self.graph.ainvoke(initial_state, config=config)
            self.logger.log_state_change("executed", {"result": result})
            return result
        except Exception as e:
            self.logger.log_state_change("execution_failed", {"error": str(e)})
            raise

    async def resume(self) -> Dict[str, Any]:
        """Resume execution after interruption."""
        self.logger.log_state_change("resuming")
        try:
            config = {"configurable": {"thread_id": str(self.task_id)}}
            
            # Get task from database to ensure we have latest status
            task = await crud_task.get_task(self.db_session, self.task_id)
            if not task:
                self.logger.log_state_change("resume_failed", {"error": "Task not found"})
                raise ValueError("Task not found")
                
            # Initialize state if not present
            current_state = await self.get_state()
            if not current_state:
                self.logger.log_state_change("initializing_state")
                current_state = {
                    "task_id": self.task_id,
                    "task_type": task.task_type,
                    "initial_request": {
                        "task_type": task.task_type,
                        "title": task.title,
                        "input_data": task.input_data,
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
                    "intermediate_results": {},
                    "final_result": None,
                    "error_info": None,
                    "metadata": {}
                }
                
            # Set required state fields
            current_state["plan_approved"] = True
            current_state["task_status"] = TaskStatus.APPROVED
            current_state["initial_request"] = {
                "task_type": task.task_type,
                "title": task.title,
                "input_data": task.input_data,
                "market_data_params": {
                    "symbol": "TSLA",
                    "start_date": "2020-01-01",
                    "end_date": "2025-05-03"
                }
            }
            
            await self.graph.update_state(config, current_state)
            self.logger.log_state_change("state_updated", {"state": current_state})
            
            result = await self.graph.ainvoke(current_state, config=config)
            self.logger.log_state_change("resumed", {"result": result})
            return result
        except Exception as e:
            self.logger.log_state_change("resume_failed", {"error": str(e)})
            raise
            
    async def get_state(self) -> Optional[WorkflowState]:
        """Get the current state from the checkpointer."""
        self.logger.log_state_change("getting_state")
        try:
            config = {"configurable": {"thread_id": str(self.task_id)}}
            state_info = await self.graph.get_state(config)
            if state_info and state_info.values:
                # Convert StateSnapshot to WorkflowState
                state_dict = dict(state_info.values)
                workflow_state: WorkflowState = {
                    "task_id": self.task_id,
                    "initial_request": state_dict.get("initial_request", {}),
                    "task_type": state_dict.get("task_type", ""),
                    "current_plan": state_dict.get("current_plan"),
                    "plan_approved": state_dict.get("plan_approved", False),
                    "agent_inputs": state_dict.get("agent_inputs", {}),
                    "agent_outputs": state_dict.get("agent_outputs", {}),
                    "intermediate_results": state_dict.get("intermediate_results", {}),
                    "final_result": state_dict.get("final_result"),
                    "error_info": state_dict.get("error_info"),
                    "metadata": state_dict.get("metadata", {})
                }
                self.logger.log_state_change("state_retrieved", {"state": workflow_state})
                return workflow_state
            self.logger.log_state_change("no_state_found")
            return None
        except Exception as e:
            self.logger.log_state_change("get_state_failed", {"error": str(e)})
            raise