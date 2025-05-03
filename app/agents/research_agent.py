from typing import Dict, Any
from .base_agent import BaseAssistantAgent
from app.tools.knowledge_tools import query_local_kb
import asyncio
from app.tools.financial_tools import fetch_historical_data

RESEARCH_PROMPT = """You are a financial research analyst. Execute specific research tasks using available tools:
1. Query knowledge base for relevant information
2. Synthesize findings into clear, actionable insights
Always provide structured, concise results."""

class ResearchAgent(BaseAssistantAgent):
    def __init__(self):
        super().__init__(
            name="ResearchAgent",
            description=RESEARCH_PROMPT
        )
        self.system_prompt = RESEARCH_PROMPT
    
    async def synthesize_findings(self, intermediate_results: Dict[str, Any]) -> Dict[str, Any]:
        """Synthesize research findings into a coherent summary."""
        prompt = f"""{self.system_prompt}

Given the following intermediate research results:
{intermediate_results}

Synthesize these findings into a clear, actionable summary. Include:
1. Key insights
2. Supporting evidence
3. Potential implications
4. Recommended actions"""
        
        response = await self.generate_response(prompt)
        return {"summary": response}

    async def research(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a research task."""
        prompt = f"""{self.system_prompt}

Research Request: {request.get('prompt', '')}

Please analyze this request and provide:
1. Key findings
2. Supporting data
3. Analysis
4. Recommendations"""

        response = await self.generate_response(prompt)
        return {"content": response}

def create_research_agent() -> ResearchAgent:
    return ResearchAgent()