import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter, Depends, status, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from typing import List
import models
import schemas
import oauth2
import database
from worker import fetch_and_process_firms
from ai_service import generate_predictive_spread_report, LiveDataUnavailableError

router = APIRouter(prefix="/fires", tags=['Core Pipeline'])

@router.post("/trigger-fetch", status_code=status.HTTP_202_ACCEPTED)
async def trigger_satellite_fetch(
    background_tasks: BackgroundTasks, 
    current_user: models.User = Depends(oauth2.require_official_clearance)
):
    background_tasks.add_task(database.run_background_pipeline, fetch_and_process_firms)
    return {"message": "Autonomous PostGIS geofenced AI engine pipeline triggered for live satellite ingest."}

@router.delete("/purge-emulated", status_code=status.HTTP_200_OK)
async def purge_emulated_fires(
    db: AsyncSession = Depends(database.get_db), 
    current_user: models.User = Depends(oauth2.require_official_clearance)
):
    await db.execute(text("DELETE FROM fire_events WHERE satellite_source LIKE '%EMULATED%';"))
    await db.commit()
    return {"message": "All legacy emulated data purged from database."}

@router.get("/sensitive", response_model=List[schemas.FireEventSensitiveOut])
async def get_sensitive_fires(
    db: AsyncSession = Depends(database.get_db), 
    current_user: models.User = Depends(oauth2.require_official_clearance)
):
    try:
        result = await db.execute(
            select(models.FireEvent).order_by(models.FireEvent.id.desc()).limit(200)
        )
        events = result.scalars().all()
        
        sanitized = []
        for e in events:
            e.classification = str(e.classification) if e.classification else "Thermal Anomaly"
            e.danger_level = str(e.danger_level) if e.danger_level else "MODERATE"
            e.chemical_released = str(e.chemical_released) if e.chemical_released else "None Detected"
            e.scientific_impact = str(e.scientific_impact) if e.scientific_impact else "None Tracked"
            sanitized.append(e)
            
        return sanitized
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Database serialization exception: {str(err)}")

@router.get("/public", response_model=List[schemas.FireEventPublicOut])
async def get_public_fires(db: AsyncSession = Depends(database.get_db)):
    try:
        result = await db.execute(
            select(models.FireEvent).order_by(models.FireEvent.id.desc()).limit(200)
        )
        return result.scalars().all()
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Database public validation exception: {str(err)}")

@router.get("/predict-spread/{fire_id}", response_model=schemas.SpreadPredictionOut)
async def get_spread_prediction_report(fire_id: int, db: AsyncSession = Depends(database.get_db)):
    result = await db.execute(select(models.FireEvent).where(models.FireEvent.id == fire_id))
    fire = result.scalars().first()
    if not fire: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fire event target not logged.")
    try:
        return await generate_predictive_spread_report(
            db=db, fire_id=fire.id, latitude=fire.latitude, longitude=fire.longitude, frp=fire.frp
        )
    except LiveDataUnavailableError as exc:
        # A required live data source (weather API or spatial DB query)
        # genuinely failed. Surfaced as a clean 503 with an honest
        # message — never a raw unhandled 500, and never a response
        # silently built from fabricated substitute data.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc