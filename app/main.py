from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.api.test_routes import router as test_router

app = FastAPI(title=settings.PROJECT_NAME)

# Set up logging
setup_logging()

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router)
app.include_router(test_router)

@app.get("/")
async def root():
    return {"message": "XAgentFlow API"}