from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sih_fires")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

connect_args = {}
if "railway.internal" in DATABASE_URL or "proxy.rlwy.net" in DATABASE_URL:
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
