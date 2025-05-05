from app.agents.planner_agent import create_planner_agent as _create_planner_agent
# from app.agents.research_agent import create_research_agent as _create_research_agent # Removed
# from app.agents.coordinator_agent import create_coordinator_agent as _create_coordinator_agent # Removed
from app.agents.strategy_agent import create_strategy_agent as _create_strategy_agent
from app.agents.backtest_agent import create_backtest_agent as _create_backtest_agent
from app.agents.base_agent import BaseAssistantAgent, BaseUserProxyAgent


def create_planner_agent():
    """Factory function to create a PlannerAgent instance."""
    return _create_planner_agent()

# Removed create_research_agent
# def create_research_agent():
#     """Factory function to create a ResearchAgent instance."""
#     # Assuming ResearchAgent is defined elsewhere or needs specific config
#     return _create_research_agent()

# Removed create_coordinator_agent
# def create_coordinator_agent():
#     """Factory function to create a CoordinatorAgent instance."""
#     # Assuming CoordinatorAgent is defined elsewhere or needs specific config
#     return _create_coordinator_agent()


# Example factory functions for base types if needed directly
def create_assistant_agent(name: str, description: str):
    return BaseAssistantAgent(name=name, description=description)

def create_user_proxy_agent(name: str):
    return BaseUserProxyAgent(name=name)

def create_strategy_agent():
    """Create a strategy agent for developing trading strategies."""
    return _create_strategy_agent()

def create_backtest_agent():
    """Create a backtest agent for testing trading strategies."""
    return _create_backtest_agent() 