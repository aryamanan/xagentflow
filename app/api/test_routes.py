from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from app.tools.financial_tools import fetch_historical_data, calculate_technical_indicators, optimize_strategy_parameters
from app.tools.backtesting_tools import run_vectorbt_backtest
from app.tools.knowledge_tools import query_local_kb
from app.tools.optimization_tools import optimize_strategy_params
from app.tools.indicator_tools import calculate_indicators

router = APIRouter(prefix="/test/tools", tags=["tool-tests"])

@router.post("/fetch_historical_data")
async def test_fetch_historical_data(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test endpoint for fetch_historical_data tool"""
    try:
        result = await fetch_historical_data(
            symbol=params["symbol"],
            period=params.get("period", "1y"),
            interval=params.get("interval", "1d")
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/calculate_indicators")
async def test_calculate_indicators(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test endpoint for calculate_technical_indicators tool"""
    try:
        result = await calculate_technical_indicators(
            data=params["data"],
            indicators=params["indicators"]
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/optimize_strategy")
async def test_optimize_strategy(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test endpoint for optimize_strategy_parameters tool"""
    try:
        result = await optimize_strategy_parameters(
            strategy_type=params["strategy_type"],
            data=params["data"],
            params_space=params["params_space"],
            optimization_target=params.get("optimization_target", "sharpe_ratio")
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/backtest")
async def test_backtest(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test endpoint for backtesting tool"""
    try:
        result = run_vectorbt_backtest(
            data_dict=params["data"],
            strategy_params=params["strategy_params"],
            logic_identifier=params["logic_identifier"]
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query_knowledge")
async def test_query_knowledge(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test endpoint for knowledge base query tool"""
    try:
        result = await query_local_kb(params["query"])
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/optimize_params")
async def test_optimize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test endpoint for strategy parameter optimization tool"""
    try:
        if not isinstance(params, dict):
            raise HTTPException(status_code=400, detail="Invalid parameters format")
            
        required_fields = ["strategy_logic", "data", "param_space"]
        missing_fields = [field for field in required_fields if field not in params]
        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required fields: {', '.join(missing_fields)}"
            )
            
        result = optimize_strategy_params(
            strategy_logic_description=params["strategy_logic"],
            data_dict=params["data"],
            param_space=params["param_space"],
            method=params.get("method", "bayesian")
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result["error"]
            )
            
        return result
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/calculate_custom_indicators")
async def test_calculate_custom_indicators(params: Dict[str, Any]) -> Dict[str, Any]:
    """Test endpoint for custom indicator calculation tool"""
    try:
        import pandas as pd
        df = pd.DataFrame(params["data"])
        result = calculate_indicators(df, params["indicators"])
        return {"status": "success", "indicators": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 