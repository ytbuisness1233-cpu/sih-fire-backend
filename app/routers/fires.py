from fastapi import APIRouter, Depends, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from .. import models, schemas, oauth2, database
from ..external_apis import fetch_and_process_firms

router = APIRouter(prefix="/fires", tags=['Core Pipeline (Govt & Global)'])

# 1. TRIGGER THE PIPELINE (Safely managed via independent background contexts)
@router.post("/trigger-fetch", status_code=status.HTTP_202_ACCEPTED)
async def trigger_satellite_fetch(
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(oauth2.require_official_clearance)
):
    # Pass the database session factory method itself into the background worker context.
    # This prevents the application from closing the session prematurely before the HTTP request lifecycle concludes.
    background_tasks.add_task(database.run_background_pipeline, fetch_and_process_firms)
    return {"message": "Autonomous FIRMS->OSM->AI Pipeline started in the background."}

# 2. SENSITIVE MAP DATA (For Logged in Govt Officials ONLY)
@router.get("/sensitive", response_model=List[schemas.FireEventSensitiveOut])
async def get_sensitive_fires(
    db: AsyncSession = Depends(database.get_db), 
    current_user: models.User = Depends(oauth2.require_official_clearance)
):
    # Note for Frontend: This naturally returns India-only data. 
    # If the user pans the map to USA, the map will simply show no pins, fulfilling the requirement!
    result = await db.execute(select(models.FireEvent))
    return result.scalars().all()

# 3. PUBLIC MASKED DATA (No coordinates, just general info)
@router.get("/public", response_model=List[schemas.FireEventPublicOut])
async def get_public_fires(db: AsyncSession = Depends(database.get_db)):
    # Performance Patch: Select only columns that schemas.FireEventPublicOut expects
    query = select(
        models.FireEvent.id,
        models.FireEvent.satellite_source,
        models.FireEvent.classification,
        models.FireEvent.is_persistent_anomaly,
        models.FireEvent.region,
        models.FireEvent.created_at  # FIXED: Added to fulfill the Pydantic schema requirement
    )
    result = await db.execute(query)
    
    # Map the scalar tuples smoothly into dictionaries for reliable Pydantic serialization
    return result.mappings().all()

