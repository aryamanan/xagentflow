from typing import Dict, Any, List
from .base_agent import BaseAssistantAgent

COORDINATOR_PROMPT = """You are a workflow coordinator responsible for managing the execution of complex tasks.
Your role is to:
1. Understand user requests and delegate to appropriate agents
2. Coordinate between planner and executor agents
3. Monitor progress and handle any issues
4. Ensure tasks are completed successfully
5. Provide clear status updates and results

Always maintain a clear overview of the workflow and ensure proper communication between agents."""

class CoordinatorAgent(BaseAssistantAgent):
    def __init__(self):
        super().__init__(
            name="coordinator",
            description="Workflow coordination and task management specialist"
        )
        self.system_prompt = COORDINATOR_PROMPT

    async def initiate_conversation(self, recipient: BaseAssistantAgent, message: str) -> Dict[str, Any]:
        """Initiate a conversation with another agent."""
        prompt = f"""{self.system_prompt}

Recipient: {recipient.name} ({recipient.description})
Message: {message}

Please coordinate this task by:
1. Understanding the request
2. Delegating appropriately
3. Monitoring execution
4. Ensuring completion
5. Providing clear results"""

        response = await self.generate_response(prompt)
        return {"content": response}

def create_coordinator_agent() -> CoordinatorAgent:
    return CoordinatorAgent()