import logging
from typing import Dict, Any, Optional
import google.generativeai as genai
from app.core.config import settings
import asyncio

logger = logging.getLogger(__name__)

def get_base_llm_config() -> Dict[str, Any]:
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your-gemini-api-key":
        raise ValueError("GEMINI_API_KEY not properly configured")
    return {
        "model": "gemini-1.5-flash",
        "api_key": settings.GEMINI_API_KEY,
        "temperature": 0.7,
        "timeout": 600,
    }

class BaseAgent:
    def __init__(self, name: str, description: str = None):
        logger.debug(f"Initializing BaseAgent {name}")
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your-gemini-api-key":
            raise ValueError("GEMINI_API_KEY not properly configured")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.name = name
        self.description = description
        logger.debug(f"BaseAgent {name} initialized successfully")
    
    async def generate_response(self, prompt: str) -> str:
        """Generate a response using the Gemini LLM."""
        try:
            logger.debug(f"[{self.name}] Generating response with event loop: {id(asyncio.get_event_loop())}")
            current_loop = asyncio.get_event_loop()
            logger.debug(f"[{self.name}] Current loop running: {current_loop.is_running()}, closed: {current_loop.is_closed()}")
            
            # Use synchronous version of generate_content
            response = self.model.generate_content(prompt)
            logger.debug(f"[{self.name}] Response generated successfully")
            return response.text
        except Exception as e:
            error_msg = f"Error generating response: {str(e)}"
            logger.error(f"[{self.name}] {error_msg}")
            raise ValueError(error_msg)

class BaseAssistantAgent(BaseAgent):
    def __init__(self, name: str, description: str):
        logger.debug(f"Initializing BaseAssistantAgent {name}")
        super().__init__(name=name, description=description)
        logger.debug(f"BaseAssistantAgent {name} initialized successfully")

class BaseUserProxyAgent(BaseAgent):
    def __init__(self, name: str):
        logger.debug(f"Initializing BaseUserProxyAgent {name}")
        super().__init__(name=name)
        logger.debug(f"BaseUserProxyAgent {name} initialized successfully")