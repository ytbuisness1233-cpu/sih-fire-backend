# app/main.py
import sys
import os
import json
from contextlib import asynccontextmanager

# Align python execution boundaries cleanly across container paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

# Import our unified infrastructure objects
from database import engine, Base, AsyncSessionLocal
import models
from routers import users, auth, fires

# app/main.py

async def init_database_tables():
    """
    Executes deep schema generation across the AsyncEngine boundary.
    Guarantees structural mapping persistence on startup by executing
    queries sequentially to prevent asyncpg prepared statement violations.
    """
    async with engine.begin() as conn:
        # Step 1: Enable PostGIS spatial parameters natively
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        
        # Step 2: Compile the metadata models base tables (fire_events, users)
        await conn.run_sync(Base.metadata.create_all)
        
        # Step 3: Execute each geospatial custom table statement individually
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS india_boundary (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) DEFAULT 'India',
                geom GEOMETRY(MultiPolygon, 4326)
            );
        """))
        
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS osm_industrial_polygons (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                geom GEOMETRY(Geometry, 4326)
            );
        """))
        
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS osm_vegetation_polygons (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                geom GEOMETRY(Geometry, 4326)
            );
        """))
        
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS osm_critical_infrastructure (
                id SERIAL PRIMARY KEY,
                name VARCHAR(150),
                feature_type VARCHAR(50),
                geom GEOMETRY(Point, 4326)
            );
        """))
        
        # Step 4: Build fast GiST R-Tree indexes over the committed columns
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_india_boundary_geom ON india_boundary USING gist(geom);
        """))
        
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_fire_events_spatial_geom ON fire_events USING gist(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326));
        """))
        
        # Step 5: Hydrate India geographic spatial coordinates bounds
        check_seed = await conn.execute(text("SELECT COUNT(*) FROM india_boundary;"))
        if check_seed.scalar() == 0:
            await conn.execute(text("""
                INSERT INTO india_boundary (name, geom) VALUES (
                    'India Mainland',
                    ST_Multi(ST_GeomFromText(
                        'POLYGON((68.1 23.5, 68.8 24.6, 70.5 24.0, 71.0 25.5, 70.0 27.0, 71.5 28.0, 73.8 29.8, 74.5 31.5, 74.0 34.0, 76.5 35.5, 78.5 35.0, 79.5 32.0, 80.5 30.5, 82.0 30.0, 88.0 27.5, 89.0 26.5, 92.0 27.8, 95.0 28.5, 97.4 28.0, 96.5 26.0, 94.0 24.0, 92.5 22.0, 89.0 21.5, 87.0 21.5, 85.0 19.5, 80.0 15.8, 80.2 13.0, 79.8 10.0, 77.5 8.1, 76.5 8.5, 75.0 12.0, 73.5 15.5, 72.8 19.0, 70.0 21.0, 68.1 23.5))', 4326
                    ))
                );
            """))
            print("[Lifespan Initialization] Async PostGIS relations fully operational and compiled.")



@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_database_tables()
    except Exception as e:
        print(f"[Lifespan Operational Warning] Table synchronization notice: {e}")
    yield

app = FastAPI(title="SIH26162 - Autonomous AI Map Backend & Telemetry Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Route Integrations
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(fires.router)

@app.websocket("/ws/v1/live-cursor-tracking")
async def websocket_live_cursor_tracking(websocket: WebSocket):
    await websocket.accept()
    knn_query = text("""
        SELECT id, latitude, longitude, classification, danger_level, chemical_released, scientific_impact, frp, brightness,
            ROUND(ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 3857), ST_Transform(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326), 3857))) AS distance_meters
        FROM fire_events
        ORDER BY ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) LIMIT 1;
    """)
    try:
        while True:
            raw_data = await websocket.receive_text()
            if not raw_data: continue
            try:
                coords = json.loads(raw_data)
                cursor_lat, cursor_lon = float(coords.get("latitude")), float(coords.get("longitude"))
            except Exception:
                await websocket.send_json({"error": "Telemetry validation drop."})
                continue

            async with AsyncSessionLocal() as session:
                result = await session.execute(knn_query, {"lat": cursor_lat, "lon": cursor_lon})
                row = result.mappings().first()
                if row:
                    dist = float(row["distance_meters"])
                    if dist <= 85000.0: 
                        payload = {
                            "matched": True, "hazard_id": row["id"], "coordinates": {"latitude": row["latitude"], "longitude": row["longitude"]},
                            "classification": row["classification"], "danger_level": row["danger_level"], "chemical_effluent": row["chemical_released"],
                            "toxicology_impact": row["scientific_impact"], "frp": row["frp"], "brightness": row["brightness"], "distance_meters": dist, "distance_km": round(dist / 1000.0, 2)
                        }
                    else:
                        payload = {"matched": False, "message": "Proximity bounds out of range.", "closest_distance_km": round(dist / 1000.0, 2)}
                else:
                    payload = {"matched": False, "message": "Database registries currently clear."}
                await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WebSocket Loop Dropped]: {e}")

@app.get("/")
async def root():
    return {"status": "Production AI Telemetry Backend Engine Active", "postgis_geofencing": "Enabled & Functional"}

# At the bottom of app/main.py

if __name__ == "__main__":
    import uvicorn
    # Must listen on 0.0.0.0 so Docker can map port 8000 to Windows
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
