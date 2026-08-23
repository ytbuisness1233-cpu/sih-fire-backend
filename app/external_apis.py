import httpx
import csv
import asyncio
from io import StringIO
from .config import settings
from . import models
from .ml_model import classify_anomaly

async def check_osm_industrial(lat: float, lon: float) -> str:
    overpass_url = "http://overpass-api.de/api/interpreter"
    # Radius of 500 meters to check for industrial polygons or nodes
    query = f"""
    [out:json][timeout:10];
    (
      way["landuse"="industrial"](around:500,{lat},{lon});
      node["man_made"="works"](around:500,{lat},{lon});
    );
    out tags;
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(overpass_url, data={'data': query})
            if response.status_code == 200:
                data = response.json()
                elements = data.get('elements', [])
                # FIXED: Check list bounds before reading indices to prevent IndexError crashes
                if elements and len(elements) > 0:
                    tags = elements[0].get('tags', {})
                    return tags.get('name', 'Industrial Zone')
    except Exception as e:
        print(f"OSM Error: {e}")
    return None

async def fetch_and_process_firms(db_session):
    # FIXED: Capitalized attributes to match our updated secure config file layout
    firms_url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{settings.FIRMS_API_KEY}/VIIRS_SNPP_NRT/68,7,97,37/1"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(firms_url)
            
        if response.status_code != 200:
            print(f"Failed to fetch FIRMS data. HTTP Status: {response.status_code}")
            return

        csv_reader = csv.DictReader(StringIO(response.text))
        added_count = 0

        for row in csv_reader:
            if added_count >= 15: # Cap at 15 for safety during demo/dev
                break
                
            # FIXED: Handle possible corrupted or missing numeric string rows safely
            try:
                lat = float(row.get('latitude', 0))
                lon = float(row.get('longitude', 0))
                brightness = float(row.get('bright_ti4', row.get('brightness', 0)))
                frp = float(row.get('frp', 0))
            except ValueError:
                continue # Skip corrupted entries and advance loop safely
                
            confidence = row.get('confidence', 'l')
            
            # Process only high or nominal confidence points
            if confidence in ['h', 'n']: 
                # 1. Fetch OSM Spatial Data
                osm_result = await check_osm_industrial(lat, lon)
                
                # 2. Run Integrated AI Engine
                ai_result = classify_anomaly(frp, brightness, osm_result)
                
                # 3. Save to Database
                new_fire = models.FireEvent(
                    latitude=lat,
                    longitude=lon,
                    brightness=brightness,
                    frp=frp,
                    satellite_source="VIIRS",
                    confidence=confidence,
                    osm_industrial_zone=osm_result,
                    classification=ai_result["classification"],
                    is_persistent_anomaly=ai_result["is_persistent_anomaly"],
                    region="India"
                )
                db_session.add(new_fire)
                added_count += 1
                
                # Prevent OSM IP rate-limits
                await asyncio.sleep(0.5) 
                
        # FIXED: Await the database session commit to prevent async thread deadlocks
        await db_session.commit()
        print(f"Autonomous Pipeline Complete. {added_count} fires analyzed & classified.")
        
    except Exception as e:
        print(f"Pipeline Error: {e}")
