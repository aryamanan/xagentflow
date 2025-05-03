import os
from dotenv import load_dotenv

# Load the environment variables from .env file
load_dotenv()

class Settings:
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "XAgentFlow"
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    EXTERNAL_MARKET_DATA_API_URL: str = os.getenv("EXTERNAL_MARKET_DATA_API_URL")
    EXTERNAL_MARKET_DATA_API_KEY: str = os.getenv("EXTERNAL_MARKET_DATA_API_KEY")
    
    # Local Knowledge Base
    LOCAL_KB_PATH: str = os.getenv("LOCAL_KB_PATH", "./local_kb")

# FinancialModelingPrep settings
FMP_API_KEY: str = os.getenv("FMP_API_KEY")

# OpenBB settings
# OPENBB_HUB_USERNAME: Optional[str] = os.getenv("OPENBB_HUB_USERNAME", None)

settings = Settings()
