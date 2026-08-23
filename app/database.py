from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from .config import settings

DATABASE_URL = settings.DATABASE_URL

# Fix dialect string formatting to guarantee compatibility with asyncpg
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Dynamically enforce secure SSL handshakes over cloud proxy endpoints
connect_args = {}
if "proxy.rlwy.net" in DATABASE_URL or "railway" in DATABASE_URL:
    connect_args = {"ssl": "require"}

engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    pool_size=20,          
    max_overflow=10,
    connect_args=connect_args
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def run_background_pipeline(target_pipeline_func):
    async with AsyncSessionLocal() as session:
        try:
            await target_pipeline_func(session)
        except Exception as e:
            await session.rollback()
            print(f"Background Pipeline Context Error: {e}")
        finally:
            await session.close()
