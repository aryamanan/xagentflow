# app/tools/registry.py
import logging
from langchain.tools import StructuredTool
from langchain_core.pydantic_v1 import BaseModel, Field
from typing import List, Dict, Any

from .financial_tools import fetch_historical_data, calculate_technical_indicators
from .knowledge_tools import query_local_kb

logger = logging.getLogger(__name__)

# Define Input Schemas for Tools using Pydantic V1 from langchain_core
class FetchDataInput(BaseModel):
    symbol: str = Field(description="The stock symbol to fetch data for.")
    period: str = Field(default="2y", description="The time period (e.g., '1y', '2y', 'max').")
    interval: str = Field(default="1d", description="The data interval (e.g., '1d', '1wk').")

class CalculateIndicatorsInput(BaseModel):
    data: List[Dict[str, Any]] = Field(description="The historical data (list of dicts) to process.")
    indicators: List[str] = Field(description="List of indicators to calculate (e.g., ['rsi', 'macd']).")

class QueryKBInput(BaseModel):
    query: str = Field(description="The query string for the knowledge base.")

# Create LangChain Tools from functions
def create_tools() -> Dict[str, StructuredTool]:
    """Creates a dictionary of LangChain StructuredTools from our functions."""
    tools = {
        "fetch_historical_data": StructuredTool.from_function(
            func=fetch_historical_data,
            name="fetch_historical_data",
            description="Fetches historical market data (OHLCV) for a stock symbol.",
            args_schema=FetchDataInput,
            # Coroutines are generally preferred for IO-bound tasks
            coroutine=fetch_historical_data, 
            handle_tool_error=True # Langchain handles exceptions
        ),
        "calculate_technical_indicators": StructuredTool.from_function(
            func=calculate_technical_indicators,
            name="calculate_technical_indicators",
            description="Calculates technical indicators (e.g., RSI, MACD, SMA) from historical data.",
            args_schema=CalculateIndicatorsInput,
            coroutine=calculate_technical_indicators,
            handle_tool_error=True
        ),
        "query_local_kb": StructuredTool.from_function(
            func=query_local_kb,
            name="query_local_kb",
            description="Queries the local knowledge base for information.",
            args_schema=QueryKBInput,
            coroutine=query_local_kb,
            handle_tool_error=True
        ),
    }
    logger.info(f"Created LangChain tools: {list(tools.keys())}")
    return tools

# Instantiate the tools registry
workflow_tools = create_tools() 