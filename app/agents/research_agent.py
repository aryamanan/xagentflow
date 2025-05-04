from typing import Dict, Any, List
from .base_agent import BaseAssistantAgent
from app.tools.knowledge_tools import query_local_kb
from app.tools.financial_tools import fetch_historical_data, calculate_technical_indicators
import asyncio
import json
import logging
from datetime import datetime
import re

logger = logging.getLogger(__name__)

RESEARCH_PROMPT = """You are a financial research analyst with access to the following tools:

1. Financial Data Tools:
   - fetch_historical_data(symbol: str, period: str = "1y", interval: str = "1d")
     Description: Fetches real market data from yfapi.net
     Returns: OHLCV data for the specified symbol and timeframe
   
   - calculate_technical_indicators(data: Dict, indicators: List[str])
     Description: Calculates technical indicators using real market data
     Supported Indicators: RSI, MACD, Bollinger Bands, SMA, EMA
     Returns: Dictionary of calculated indicator values

2. Knowledge Base Tools:
   - query_local_kb(query: str)
     Description: Queries the knowledge base for financial concepts and strategies
     Returns: Relevant information and explanations

Tool Usage Guidelines:
1. Always use fetch_historical_data for market data - no mock data allowed
2. Calculate indicators using real data from fetch_historical_data
3. Validate data quality before analysis
4. Use knowledge base for interpretation guidelines
5. Document all tool calls and results

Research Process:
1. Fetch required market data
2. Calculate relevant technical indicators
3. Query knowledge base for interpretation context
4. Analyze findings using real data
5. Provide actionable insights with supporting evidence"""

class ResearchAgent(BaseAssistantAgent):
    def __init__(self):
        super().__init__(
            name="ResearchAgent",
            description=RESEARCH_PROMPT
        )
        self.system_prompt = RESEARCH_PROMPT
        self._initialize_tools()
    
    def _initialize_tools(self):
        """Initialize and validate tool availability."""
        self.tools = {
            "fetch_historical_data": fetch_historical_data,
            "calculate_technical_indicators": calculate_technical_indicators,
            "query_local_kb": query_local_kb
        }
        
        # Validate tool availability
        for tool_name, tool_func in self.tools.items():
            if not callable(tool_func):
                logger.error(f"Tool {tool_name} is not callable")
                raise ValueError(f"Invalid tool: {tool_name}")
    
    async def analyze_stock(self, symbol: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
        """Analyze a stock using technical indicators with real data."""
        try:
            logger.info(f"[ResearchAgent] Starting analyze_stock for {symbol}")
            
            # Fetch historical data
            logger.info(f"[ResearchAgent] Attempting to call fetch_historical_data for {symbol}")
            historical_data = await self.tools["fetch_historical_data"](symbol, period, interval)
            logger.info(f"[ResearchAgent] fetch_historical_data call completed for {symbol}. Status: {historical_data.get('status')}")
            if historical_data["status"] != "success":
                logger.error(f"[ResearchAgent] Failed to fetch data: {historical_data.get('error')}")
                return {"error": f"Failed to fetch data: {historical_data.get('error', 'Unknown error')}"}
            
            # Validate data quality
            if not historical_data.get("data") or len(historical_data["data"]) < 2:
                logger.error("[ResearchAgent] Insufficient historical data")
                return {"error": "Insufficient historical data for analysis"}
            
            # Calculate technical indicators
            logger.info(f"[ResearchAgent] Attempting to call calculate_technical_indicators for {symbol}")
            indicators = await self.tools["calculate_technical_indicators"](
                historical_data["data"],
                ["rsi", "macd", "bollinger"]
            )
            logger.info(f"[ResearchAgent] calculate_technical_indicators call completed for {symbol}. Status: {indicators.get('status')}")
            if indicators["status"] != "success":
                logger.error(f"[ResearchAgent] Failed to calculate indicators: {indicators.get('error')}")
                return {"error": f"Failed to calculate indicators: {indicators.get('error', 'Unknown error')}"}
            
            # Query knowledge base for interpretation guidelines
            logger.info(f"[ResearchAgent] Attempting to call query_local_kb for guidelines")
            kb_response = await self.tools["query_local_kb"]("technical analysis interpretation guidelines")
            logger.info(f"[ResearchAgent] query_local_kb call completed.")
            
            # Log successful tool usage
            logger.info(f"[ResearchAgent] Successfully calculated indicators for {symbol}")
            
            # Generate analysis prompt
            analysis_prompt = f"""{self.system_prompt}

Analyze the following technical data for {symbol}:

Historical Data Summary:
- Period: {period}
- Interval: {interval}
- Data Points: {len(historical_data['data'])}
- Latest Close: {historical_data['data'][-1].get('close')}

Technical Indicators:
{json.dumps(indicators['indicators'], indent=2)}

Knowledge Base Guidelines:
{kb_response}

Please provide a comprehensive analysis including:
1. Current market trend with supporting data
2. Technical indicator signals with specific values
3. Support/resistance levels from real price action
4. Trading recommendations based on actual data
5. Risk considerations with specific metrics"""
            
            # Generate analysis
            logger.info(f"[ResearchAgent] Generating final analysis response for {symbol}...")
            analysis = await self.generate_response(analysis_prompt)
            logger.info(f"[ResearchAgent] Final analysis generated for {symbol}")
            
            return {
                "symbol": symbol,
                "period": period,
                "analysis": analysis,
                "data": historical_data,
                "indicators": indicators,
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"[ResearchAgent] Error in analyze_stock: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def execute_step_directly(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a research step, attempting direct tool calls first."""
        step_name = step.get('step_name', 'Unknown Step')
        task_id = state.get("task_id", "unknown")
        logger.info(f"[Task {task_id} / Step {step_name}] ResearchAgent attempting execute_step_directly")

        required_tools = step.get("tools", [])
        description = step.get("description", "")
        input_data = state.get("input_data", {})
        symbol = input_data.get("symbol") # Extract symbol if available

        try:
            # --- Direct Tool Logic --- 
            if "fetch_historical_data" in required_tools and symbol:
                logger.info(f"[Task {task_id} / Step {step_name}] Identified 'fetch_historical_data' tool. Calling analyze_stock for {symbol}...")
                # Use analyze_stock as it bundles fetch, calc, kb query logic
                # Modify period/interval as needed or extract from step description/state
                result = await self.analyze_stock(symbol=symbol, period="1y") 
                return result # analyze_stock already returns a dict with status
            
            elif "calculate_technical_indicators" in required_tools:
                # TODO: Need logic to get data from previous step's output in state['agent_outputs']
                logger.warning(f"[Task {task_id} / Step {step_name}] 'calculate_technical_indicators' requested, but direct execution logic not fully implemented yet.")
                # Fall through to LLM for now
                pass # Fall through to LLM
            
            elif "query_local_kb" in required_tools:
                logger.info(f"[Task {task_id} / Step {step_name}] Identified 'query_local_kb' tool. Calling tool directly...")
                # Extract query from description or a dedicated field if added to state/step
                query_match = re.search(r"Query knowledge base for (.+)", description, re.IGNORECASE)
                kb_query = query_match.group(1).strip() if query_match else description # Fallback to full desc
                result = await self.tools["query_local_kb"](kb_query)
                logger.info(f"[Task {task_id} / Step {step_name}] query_local_kb call completed.")
                return {"status": "success", "result": result}
            
            # --- Fallback to LLM --- 
            logger.info(f"[Task {task_id} / Step {step_name}] No specific tool logic matched or implemented. Falling back to LLM generation.")
            # Reconstruct a suitable prompt for the LLM based on the step
            fallback_prompt = f"""Execute the following research step based on the provided context:

Step Name: {step_name}
Description: {description}
Success Criteria: {step.get('success_criteria', 'No criteria')}

Available Tools (for your reference, but execute the task directly):
- fetch_historical_data(symbol, period, interval)
- calculate_technical_indicators(data, indicators)
- query_local_kb(query)

Current State (JSON):
{json.dumps(state, indent=2, default=str)}

Please provide a detailed report of your findings and actions."""
            llm_result = await self.generate_response(fallback_prompt, expect_json=False)
            return {"status": "completed_by_llm", "content": llm_result}

        except Exception as e:
            logger.error(f"[Task {task_id} / Step {step_name}] Error during execute_step_directly: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def research(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a research task with proper tool usage."""
        try:
            query = request.get('prompt', '')
            logger.info(f"[ResearchAgent] Starting research task: {query}")
            
            # Check if this is a stock analysis request
            is_stock_request = any(keyword in query.lower() for keyword in ['stock', 'ticker', 'symbol', 'aapl'])
            logger.info(f"[ResearchAgent] Is stock request? {is_stock_request}")
            if is_stock_request:
                # Extract symbol from query
                symbols = re.findall(r'[A-Z]{1,5}', query)
                logger.info(f"[ResearchAgent] Found symbols: {symbols}")
                if symbols:
                    symbol = symbols[0]
                    logger.info(f"[ResearchAgent] Detected stock analysis request for {symbol}. Calling analyze_stock...")
                    return await self.analyze_stock(symbol)
                else:
                    logger.warning("[ResearchAgent] Stock request detected but no symbol found in query.")
            
            # For other types of research
            logger.info("[ResearchAgent] Not a stock request or symbol not found. Proceeding with generic research...")
            prompt = f"""{self.system_prompt}

Research Request: {query}

Please analyze this request and provide:
1. Key findings using real data
2. Supporting evidence from tools
3. Comprehensive analysis
4. Actionable recommendations

Use the available tools to gather real data and perform analysis."""

            response = await self.generate_response(prompt)
            logger.info("[ResearchAgent] Generic research task completed successfully")
            return {"content": response}
            
        except Exception as e:
            logger.error(f"[ResearchAgent] Error in research task: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def synthesize_results(self, plan: Dict[str, Any], step_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize research results from multiple steps into a final report.
        
        Args:
            plan: The research plan that was executed
            step_outputs: Dictionary of outputs from each step
            
        Returns:
            Dictionary containing the synthesized results
        """
        try:
            logger.info("Starting result synthesis")
            
            # Create synthesis prompt
            steps = plan.get("plan", {}).get("steps", [])
            if not steps:
                raise ValueError("No steps found in plan")
            
            # Build a summary of each step's results
            step_summaries = []
            for step in steps:
                step_num = step.get("step_number")
                step_output = step_outputs.get(f"step_{step_num-1}", {})  # -1 because index starts at 0
                
                summary = f"""
Step {step_num}: {step.get('step_name', 'Unknown Step')}
Description: {step.get('description', 'No description')}
Results: {step_output.get('research_result', 'No results')}
Validation: {step_output.get('validation', 'No validation')}
"""
                step_summaries.append(summary)
            
            synthesis_prompt = f"""{self.system_prompt}

Please synthesize the results from all research steps into a comprehensive final report.

Research Plan:
{json.dumps(plan, indent=2)}

Step Results:
{''.join(step_summaries)}

Please provide:
1. Executive Summary
2. Key Findings from each step
3. Integrated Analysis
4. Supporting Evidence
5. Actionable Recommendations
6. Risk Considerations

Format the response as a well-structured report suitable for financial professionals."""

            # Generate synthesis
            synthesis = await self.generate_response(synthesis_prompt)
            
            return {
                "synthesis": synthesis,
                "step_summaries": step_summaries,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error synthesizing results: {str(e)}")
            raise ValueError(f"Failed to synthesize results: {str(e)}")

    # Alias for backward compatibility
    asynthesize_results = synthesize_results

def create_research_agent() -> ResearchAgent:
    """Create a research agent instance."""
    return ResearchAgent()