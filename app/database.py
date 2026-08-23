from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from .config import settings

# 1. FIXED: Updated to uppercase attributes to match our secure config file configuration
SQLALCHEMY_DATABASE_URL = (
    f"postgresql+asyncpg://{settings.DATABASE_USERNAME}:{settings.DATABASE_PASSWORD}"
    f"@{settings.DATABASE_HOSTNAME}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}"
)

# 2. Instantiate high-performance async engine configuration
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, 
    echo=False,
    pool_size=20,          # Keeps an optimal buffer of active database connections
    max_overflow=10        # Accommodates spike traffic gracefully during team presentations
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

# 3. Request-bound database session generator dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            # FIXED: Guarantees connection closure even if endpoints raise an unhandled exception
            await session.close()

# 4. FIXED: Background task context wrapper
async def run_background_pipeline(target_pipeline_func):
    """
    Spins up an isolated, transaction-safe database environment for long-running
    background processing threads outside standard HTTP request lifecycles.
    """
    async with AsyncSessionLocal() as session:
        try:
            await target_pipeline_func(session)
        except Exception as e:
            await session.rollback()
            print(f"Background Pipeline Context Error: {e}")
        finally:
            await session.close()
