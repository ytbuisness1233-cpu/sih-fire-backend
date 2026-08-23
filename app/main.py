from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .database import engine, Base
# FIXED: Explicitly import models to guarantee they register on Base.metadata 
# before conn.run_sync compile cycles run
from . import models 
from .routers import users, auth, fires

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize core system database schemas atomically inside Docker isolation
    try:
        async with engine.begin() as conn:
            # Compiles all tables (Users, FireEvents) dynamically onto the connected PostgreSQL engine
            await conn.run_sync(Base.metadata.create_all)
        print("Database schema synchronization complete. All core tables compiled successfully.")
    except Exception as e:
        print(f"CRITICAL: Database auto-migration pipeline failed during lifespan startup: {e}")
        # Allow the application to attempt running even if migrations drop, preventing total engine deadlocks
    
    yield
    # Cleanup operations (like closing background engine connection pools) can be safely added here

app = FastAPI(title="SIH26162 - Autonomous AI Map Backend", lifespan=lifespan)

# 2. CORS configuration layout mapping rules
# Suggestion for Team deployment: Replace "*" with your frontend teammate's Vercel/Netlify URL later
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Mount production routers safely
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(fires.router)

@app.get("/")
async def root():
    return {
        "status": "Govt Map Server & AI Engine Active",
        "system_scope": "India Geospatial Telemetry Processing Layer"
    }
