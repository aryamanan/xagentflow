import logging
from typing import Dict, Any, Optional
import google.generativeai as genai
from app.core.config import settings
import asyncio
import json

logger = logging.getLogger(__name__)

def get_base_llm_config() -> Dict[str, Any]:
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your-gemini-api-key":
        raise ValueError("GEMINI_API_KEY not properly configured")
    return {
        "model": "gemini-1.5-flash",
        "api_key": settings.GEMINI_API_KEY,
        "temperature": 0.1,  # Lower temperature for more deterministic output
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
    
    async def generate_response(self, prompt: str, expect_json: bool = False) -> str:
        """Generate a response using the Gemini LLM.
        
        Args:
            prompt: The prompt to send to the LLM
            expect_json: Whether to expect and validate JSON output
            
        Returns:
            The generated response text
        """
        try:
            logger.debug(f"[{self.name}] Generating response with event loop: {id(asyncio.get_event_loop())}")
            current_loop = asyncio.get_event_loop()
            logger.debug(f"[{self.name}] Current loop running: {current_loop.is_running()}, closed: {current_loop.is_closed()}")
            
            # Add JSON formatting reminder if needed
            if expect_json:
                prompt = f"{prompt}\n\nIMPORTANT: Your response must be a valid JSON object. Do not include any other text."
            
            # Configure generation parameters
            generation_config = genai.types.GenerationConfig(
                temperature=0.1 if expect_json else 0.7,  # Lower temperature for JSON
                candidate_count=1,
                stop_sequences=["\n\n"] if expect_json else None  # Stop at double newline for JSON
            )
            
            # Generate response
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            response_text = response.text.strip()
            logger.debug(f"[{self.name}] Raw response: {response_text}")
            
            # Validate JSON if expected
            if expect_json:
                try:
                    # Find JSON content
                    start = response_text.find('{')
                    end = response_text.rfind('}')
                    if start >= 0 and end > start:
                        json_str = response_text[start:end+1]
                        # Validate by parsing
                        json.loads(json_str)
                        return json_str
                    else:
                        raise ValueError("No JSON object found in response")
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in response: {str(e)}")
            
            return response_text
            
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