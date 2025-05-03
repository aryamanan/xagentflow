import pytest
import logging
from typing import Generator, AsyncGenerator
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.base import Base
from app.main import app
from app.db.session import get_db
from app.models.task import TaskType, TaskStatus
from app.schemas.task import TaskCreate
import asyncio

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Ensure models are imported so Base.metadata knows about them
from app.models import task  # Import task model

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_engine():
    """Create a test database engine."""
    logger.info("Creating test database engine")
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    logger.info("Creating test database session")
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()

@pytest.fixture
async def test_client(db_session: AsyncSession) -> TestClient:
    """Create a test client with database session override."""
    logger.info("Creating test client")
    
    async def override_get_db():
        try:
            yield db_session
        finally:
            await db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

@pytest.fixture
def api_key_headers():
    """Create headers with API key."""
    return {"X-API-Key": settings.API_KEY}

@pytest.fixture
def sample_research_task():
    return TaskCreate(
        task_type=TaskType.RESEARCH,
        title="Test Research Task",
        description="Research task for testing",
        input_data={
            "symbols": ["AAPL", "GOOGL"],
            "timeframe": "1d"
        }
    )

@pytest.fixture
def sample_strategy_task():
    return TaskCreate(
        task_type=TaskType.STRATEGY_DEV,
        title="Test Strategy Task",
        description="Strategy development task for testing",
        input_data={
            "market": "crypto",
            "timeframe": "4h",
            "risk_level": "medium"
        }
    )

@pytest.fixture
def sample_backtest_task():
    return TaskCreate(
        task_type=TaskType.BACKTEST,
        title="Test Backtest Task",
        description="Backtest task for testing",
        input_data={
            "strategy_id": "test_strategy_1",
            "start_date": "2024-01-01",
            "end_date": "2024-03-01"
        }
    )