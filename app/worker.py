import httpx
import csv
from io import StringIO
from typing import Optional
from sqlalchemy import text
import models
from config import settings
from ai_service import classify_and_assess_hazard

NASA_FIRMS_OPEN_LIVE_FEED = "https://nasa.gov"

async def purge_legacy_emulated_records(db_session):
    try:
        await db_session.execute(
            text("DELETE FROM fire_events WHERE satellite_source LIKE '%EMULATED%';")
        )
        await db_session.commit()
    except Exception as e:
        await db_session.rollback()
        print(f"[Database Cleanup Notice]: {e}")

async def fetch_spatial_context(db_session, lat: float, lon: float) -> dict:
    """
    Evaluates a 500-meter proximity envelope around the coordinate to accurately 
    capture satellite pixels falling slightly outside OSM polygons.
    """
    query_planet = text("""
        SELECT 
            landuse,
            tags->'name' as zone_name,
            tags->'natural' as natural_type,
            tags->'industrial' as industrial_type
        FROM planet_osm_polygon 
        WHERE ST_DWithin(
            way, 
            ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 3857), 
            500
        )
        AND (
            landuse IN ('industrial', 'quarry', 'mine', 'forest', 'orchard') 
            OR tags->'natural' IN ('wood', 'scrub')
            OR tags->'industrial' IS NOT NULL
        )
        ORDER BY ST_Distance(way, ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 3857)) ASC
        LIMIT 1;
    """)
    
    # Robust 0-downtime fallback mapping to native schema created in main.py
    query_fallback = text("""
        SELECT 'industrial' as landuse, name as zone_name, NULL as natural_type, 'yes' as industrial_type,
               ST_Distance(ST_Transform(geom, 3857), ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 3857)) as dist
        FROM osm_industrial_polygons
        WHERE ST_DWithin(ST_Transform(geom, 3857), ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 3857), 500)
        UNION ALL
        SELECT 'forest' as landuse, name as zone_name, 'wood' as natural_type, NULL as industrial_type,
               ST_Distance(ST_Transform(geom, 3857), ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 3857)) as dist
        FROM osm_vegetation_polygons
        WHERE ST_DWithin(ST_Transform(geom, 3857), ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 3857), 500)
        ORDER BY dist ASC LIMIT 1;
    """)

    try:
        res = await db_session.execute(query_planet, {"lon": lon, "lat": lat})
        row = res.mappings().first()
    except Exception:
        await db_session.rollback()
        try:
            res = await db_session.execute(query_fallback, {"lon": lon, "lat": lat})
            row = res.mappings().first()
        except Exception:
            await db_session.rollback()
            row = None

    context = {"context_type": "none", "zone_name": None, "raw": {}}
    if row:
        landuse = (row.get("landuse") or "").lower()
        nat_type = (row.get("natural_type") or "").lower()
        ind_type = (row.get("industrial_type") or "").lower()
        
        context["zone_name"] = row.get("zone_name")
        context["raw"] = dict(row)
        context["raw"]["name"] = row.get("zone_name")  # Map name cleanly for toxic chemical matching
        
        if landuse in ['industrial', 'quarry', 'mine'] or ind_type:
            context["context_type"] = "industrial"
        elif landuse in ['forest', 'orchard'] or nat_type in ['wood', 'scrub']:
            context["context_type"] = "vegetation"

    return context

async def verify_india_geofence(db_session, lat: float, lon: float) -> bool:
    query = text("""
        SELECT EXISTS (
            SELECT 1 FROM india_boundary 
            WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
        ) AS is_inside;
    """)
    try:
        res = await db_session.execute(query, {"lon": lon, "lat": lat})
        row = res.mappings().first()
        if row and row["is_inside"] is not None:
            return bool(row["is_inside"])
    except Exception as e:
        print(f"[Geofence Spatial Error]: {e}")
    return bool(6.7 <= lat <= 37.5 and 68.1 <= lon <= 97.4)

async def fetch_and_process_firms(db_session):
    print("🚀 [Worker Pipeline] Purging legacy emulated data and initiating live NASA telemetry fetch...")
    await purge_legacy_emulated_records(db_session)

    has_custom_key = bool(
        settings.FIRMS_API_KEY 
        and settings.FIRMS_API_KEY not in ["demo_key", "your_genuine_nasa_earthdata_key_here", ""]
    )
    
    csv_text = None
    satellite_label = "VIIRS_NOAA20_NRT"

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        if has_custom_key:
            # India Coordinate Envelope bounding parameters passed cleanly to NASA area routing algorithms
            firms_area_url = f"https://nasa.gov{settings.FIRMS_API_KEY}/VIIRS_NOAA20_NRT/68,6,98,38/1"
            try:
                print(f"📡 [Worker Pipeline] Requesting optimized NASA FIRMS Area API...")
                resp = await client.get(firms_area_url)
                if resp.status_code == 200 and "latitude" in resp.text.lower():
                    csv_text = resp.text
                    satellite_label = "VIIRS_NOAA20_NRT"
                else:
                    print(f"⚠️ [NASA Area API Notice]: Status {resp.status_code}. Querying NASA open live 24h satellite stream...")
            except Exception as e:
                print(f"⚠️ [NASA Area API Connection]: {e}. Switching to NASA open live feed...")

        if not csv_text:
            try:
                print(f"🌐 [Worker Pipeline] Fetching live satellite feed from NASA EOSDIS: {NASA_FIRMS_OPEN_LIVE_FEED}")
                resp = await client.get(NASA_FIRMS_OPEN_LIVE_FEED)
                if resp.status_code == 200 and "latitude" in resp.text.lower():
                    csv_text = resp.text
                    satellite_label = "VIIRS_NOAA20_LIVE"
                else:
                    print(f"❌ [NASA Live Feed Error]: HTTP {resp.status_code}")
                    return
            except Exception as e:
                print(f"❌ [NASA Live Feed Network Failure]: {e}")
                return

    csv_reader = csv.DictReader(StringIO(csv_text.strip()))
    added_count = 0

    print("⚡ [Worker Pipeline] Streaming global text frame context and matching coordinate envelopes...")

    for row in csv_reader:
        if added_count >= 150:
            break
            
        try:
            lat_raw = row.get('latitude')
            lon_raw = row.get('longitude')
            bright_raw = row.get('bright_ti4') or row.get('brightness') or 0.0
            frp_raw = row.get('frp') or 0.0

            if lat_raw is None or lon_raw is None:
                continue

            lat = float(lat_raw)
            lon = float(lon_raw)
            brightness = float(bright_raw)
            frp = float(frp_raw)
        except (ValueError, TypeError):
            continue

        # PERFORMANCE GAIN FIX: Check basic boundary coordinates BEFORE execution drops into database.
        # This filters out global points (USA, Brazil, Africa) instantly without locking the database connection pool.
        if not (6.7 <= lat <= 37.5 and 68.1 <= lon <= 97.4):
            continue

        confidence = str(row.get('confidence', 'n')).lower()

        # Execute deep verification inside PostGIS boundary tables for points in proximity
        is_inside_india = await verify_india_geofence(db_session, lat, lon)
        if not is_inside_india:
            continue

        # Replace the old `check_osm_industrial_spatial` calls with this:
        spatial_context = await fetch_spatial_context(db_session, lat, lon)

        ai_matrix = await classify_and_assess_hazard(
            db=db_session,
            latitude=lat,
            longitude=lon,
            brightness=brightness,
            frp=frp,
            confidence=confidence,
            osm_tags=spatial_context
        )

        new_fire = models.FireEvent(
            latitude=lat,
            longitude=lon,
            brightness=brightness,
            frp=frp,
            satellite_source=satellite_label,
            confidence=confidence,
            osm_industrial_zone=ai_matrix.get("osm_industrial_zone"), # Pulled cleanly from spatial dynamic overrides
            classification=ai_matrix["classification"],
            danger_level=ai_matrix["danger_level"],
            chemical_released=ai_matrix["chemical_released"],
            scientific_impact=ai_matrix["scientific_impact"],
            inference_confidence=ai_matrix["inference_confidence_score"],
            is_persistent_anomaly=ai_matrix["is_persistent_anomaly"],
            region="India"
        )
        db_session.add(new_fire)
        added_count += 1

    await db_session.commit()
    print(f"✅ [Worker Pipeline Success] Processed and stored {added_count} genuine, live satellite detections from NASA.")
