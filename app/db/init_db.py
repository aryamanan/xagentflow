import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
from app.core.config import settings
from app.db.base import Base
from app.models.task import Task  # Import the Task model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_db():
    logger.info("Creating database engine...")
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=True
    )
    
    logger.info("Creating all database tables...")
    async with engine.begin() as conn:
        # Don't drop tables in production
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # Verify tables were created
    async with AsyncSession(engine) as session:
        result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
        tables = result.scalars().all()
        logger.info(f"Created tables: {tables}")
        await session.commit()

    await engine.dispose()
    logger.info("Database initialization completed.")

if __name__ == "__main__":
    asyncio.run(init_db())