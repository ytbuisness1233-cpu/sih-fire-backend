# database.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from config import settings

DATABASE_URL = str(settings.DATABASE_URL)

# Enforce secure async dialect maps across all configurations
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

connect_args = {}
if "proxy.rlwy.net" in DATABASE_URL or "railway" in DATABASE_URL or "sslmode=require" in DATABASE_URL:
    connect_args = {"ssl": "require"}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=15,
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
            print(f"[Worker Context Error]: {e}")
        finally:
            await session.close()
