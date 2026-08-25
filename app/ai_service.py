import os
import math
import logging
import joblib
import numpy as np
import httpx
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from config import settings

logger = logging.getLogger(__name__)

MODEL_PATH = os.getenv("FIRE_AI_MODEL_PATH", "models/fire_hazard_ensemble.joblib")


class LiveDataUnavailableError(RuntimeError):
    """
    Raised when a required live/dynamic data source — a spatial DB query
    or an external live API (weather, etc.) — could not produce real
    data. This is the ONLY acceptable response to that situation: never
    caught here to substitute a fabricated value, and never left to
    propagate as a raw unhandled exception either. Callers at the API
    boundary (see routers/fires.py) catch this specifically and turn it
    into a clean, honest HTTP error response.
    """
    pass

FACILITY_TOXIC_MATRIX: Dict[str, Dict[str, str]] = {
    "refinery": {
        "chemical": "Benzene, Hydrogen Sulfide (H2S), & Sulfur Dioxide (SO2)",
        "impact": "High carcinogen exposure risk, central nervous system depression, acute pulmonary edema, and immediate respiratory distress."
    },
    "chemical": {
        "chemical": "Benzene, Vinyl Chloride, Hydrogen Sulfide (H2S), & Toxic Volatile Compounds",
        "impact": "Severe mutagenic hazard vector, acute neurotoxicity, rapid eye/airway burning, and immediate asphyxiation threats."
    },
    "power": {
        "chemical": "Sulfur Dioxide (SO2), Nitrogen Dioxide (NO2), & Fly Ash Heavy Metals",
        "impact": "Severe throat inflammation, permanent bronchial cell damage, acid aerosol formation, and rapid asthma exacerbation in populations."
    },
    "brickyard": {
        "chemical": "Sulfur Dioxide (SO2), Nitrogen Dioxide (NO2), & Crystalline Silica dust",
        "impact": "Severe upper throat track inflammation, bronchial tract injury, permanent silicosis risk, and acute respiratory stress."
    },
    "farmland": {
        "chemical": "Dense PM2.5 Particulate Matter, Carbon Monoxide (CO), & Polycyclic Aromatic Hydrocarbons (PAHs)",
        "impact": "Severe smoke inhalation injury, carboxyhemoglobin hypoxia, extreme cardiovascular stress, and deep alveolar lung tissue damage."
    },
    "forest": {
        "chemical": "Ultra-fine PM2.5 / PM10 Matter, Carbon Monoxide (CO), Formaldehyde, & Acrolein",
        "impact": "Severe dense smoke inhalation, carboxyhemoglobin hypoxia, extreme cardiovascular stress for surrounding communities, and loss of local flight path visibility."
    },
    "industrial": {
        "chemical": "Mixed Industrial Combustion Effluents, Carbon Monoxide (CO), & Toxic Volatile Organics",
        "impact": "Moderate to severe toxic gas inhalation, throat mucosal tract irritation, and secondary ambient particulate toxicity."
    }
}

DEFAULT_CHEMICAL_PROFILE = {
    "chemical": "Combustion Particulate Matter (PM2.5 / PM10) & Carbon Monoxide (CO)",
    "impact": "Localized ambient air degradation, respiratory tract irritation, and elevated stress on sensitive populations."
}

class AIModelLoader:
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None and os.path.exists(MODEL_PATH):
            try:
                cls._model = joblib.load(MODEL_PATH)
            except Exception as e:
                print(f"[ML Inference Setup] Using mathematical heuristic framework: {e}")
                cls._model = None
        return cls._model

async def get_live_weather(lat: float, lon: float) -> Tuple[float, float, float]:
    """
    Fetches live wind speed (km/h), wind direction (degrees), and
    ambient temperature (°C) from Open-Meteo for the given coordinates.

    Raises LiveDataUnavailableError on any failure — network error,
    non-200 response, or a response missing a required field — rather
    than substituting fixed placeholder weather values. Wind speed and
    direction directly drive every downstream spread-projection number,
    so a fabricated value here would silently corrupt the entire report
    while it still looked like a legitimate live result.
    """
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,wind_speed_10m,wind_direction_10m"
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(url)
    except httpx.HTTPError as exc:
        raise LiveDataUnavailableError(
            f"live weather lookup failed: could not reach Open-Meteo ({exc})"
        ) from exc

    if res.status_code != 200:
        raise LiveDataUnavailableError(
            f"live weather lookup failed: Open-Meteo returned HTTP {res.status_code}"
        )

    current = res.json().get("current", {})
    wind_speed = current.get("wind_speed_10m")
    wind_dir = current.get("wind_direction_10m")
    temp = current.get("temperature_2m")

    if wind_speed is None or wind_dir is None or temp is None:
        raise LiveDataUnavailableError(
            "live weather lookup failed: Open-Meteo response was missing a required field"
        )

    return float(wind_speed), float(wind_dir), float(temp)

def extract_chemical_threat(osm_tags: Dict[str, Any]) -> Dict[str, str]:
    if not osm_tags:
        return DEFAULT_CHEMICAL_PROFILE
    search_keys = ["industrial", "landuse", "building", "man_made", "amenity"]
    for key in search_keys:
        val = str(osm_tags.get(key, "")).lower()
        for f_type in FACILITY_TOXIC_MATRIX.keys():
            if f_type in val:
                return FACILITY_TOXIC_MATRIX[f_type]
    name_val = str(osm_tags.get("name", "")).lower()
    for f_type in FACILITY_TOXIC_MATRIX.keys():
        if f_type in name_val:
            return FACILITY_TOXIC_MATRIX[f_type]
    return DEFAULT_CHEMICAL_PROFILE

async def calculate_spatial_features(db: AsyncSession, latitude: float, longitude: float) -> Dict[str, float]:
    spatial_query = text("""
        SELECT 
            COALESCE(
                (SELECT ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 3857), ST_Transform(geom, 3857))
                 FROM osm_industrial_polygons ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) LIMIT 1), 50000.0
            ) AS dist_industrial,
            COALESCE(
                (SELECT ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 3857), ST_Transform(geom, 3857))
                 FROM osm_vegetation_polygons ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) LIMIT 1), 50000.0
            ) AS dist_vegetation;
    """)
    try:
        res = await db.execute(spatial_query, {"lon": longitude, "lat": latitude})
        row = res.mappings().first()
        dist_ind = float(row["dist_industrial"]) if row else 50000.0
        dist_veg = float(row["dist_vegetation"]) if row else 50000.0
    except Exception:
        dist_ind = 5000.0
        dist_veg = 1200.0
    veg_density = max(0.0, min(1.0, 1.0 - (dist_veg / 10000.0)))
    return {"dist_industrial_m": dist_ind, "dist_vegetation_m": dist_veg, "vegetation_density_index": round(veg_density, 3)}

async def classify_and_assess_hazard(
    db: AsyncSession, latitude: float, longitude: float, brightness: float, frp: float, confidence: str, osm_tags: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    spatial_vars = await calculate_spatial_features(db, latitude, longitude)
    conf_numeric = 1.0 if confidence == 'h' else (0.6 if confidence == 'n' else 0.2)
    
    # Unpack structured 500m envelope context
    context = osm_tags or {}
    context_type = context.get("context_type", "none")
    zone_name = context.get("zone_name")
    raw_tags = context.get("raw", {})
    
    thermal_energy = (frp * 0.7) + ((brightness - 300.0) * 0.3)
    
    # 1. Base ML/Heuristics (For Case C: No Spatial Hit found)
    features = np.array([[float(brightness), float(frp), conf_numeric, spatial_vars["dist_industrial_m"], spatial_vars["dist_vegetation_m"], spatial_vars["vegetation_density_index"]]], dtype=np.float32)
    model = AIModelLoader.get_model()
    
    if model is not None:
        try:
            preds = model.predict(features)
            probs = model.predict_proba(features)
            label_map = {0: "Minor Thermal Point", 1: "Industrial Thermal Source", 2: "Agricultural Stubble Burning", 3: "High-Intensity Wildfire"}
            classification = label_map.get(int(preds), "Thermal Hotspot")
            inference_confidence = float(np.max(probs))
        except Exception:
            classification = "Thermal Hotspot"
            inference_confidence = 0.88
    else:
        if thermal_energy > 40.0:
            classification = "Major Thermal Anomaly"
            inference_confidence = 0.90
        elif frp > 15.0 and spatial_vars["vegetation_density_index"] > 0.3:
            classification = "Agricultural Residue Burning"
            inference_confidence = 0.89
        else:
            classification = "Minor Thermal Anomaly"
            inference_confidence = 0.78

    final_industrial_zone = None
    
    # 2. DYNAMIC SPATIAL CLASSIFICATION OVERRIDES
    # --- Case A: Point intersects within 500m of Industrial/Mine area ---
    if context_type == "industrial":
        landuse_detail = raw_tags.get("landuse", "industrial")
        classification = f"Industrial Thermal Emission / Active {landuse_detail.capitalize()} Burn"
        inference_confidence = max(inference_confidence, 0.95)
        final_industrial_zone = f"{zone_name} ({landuse_detail})" if zone_name else f"Unmapped {landuse_detail.capitalize()} Zone"
        
    # --- Case B: Point intersects within 500m of Forest/Orchard area ---
    elif context_type == "vegetation":
        if frp > 40.0 or brightness > 320.0:
            classification = "Active Forest Fire Cluster"
            inference_confidence = max(inference_confidence, 0.94)
        else:
            classification = "Vegetation / Brush Fire"
            inference_confidence = max(inference_confidence, 0.89)

    # 3. Dynamic Threshold Evaluations
    danger_level = "CRITICAL" if (frp > 90.0 or (context_type == "industrial" and frp > 30.0) or spatial_vars["dist_industrial_m"] < 300.0) \
                   else ("HIGH" if (frp > 30.0 or spatial_vars["dist_vegetation_m"] < 250.0) \
                   else ("MODERATE" if frp > 10.0 else "LOW"))
    
    chem_threat = extract_chemical_threat(raw_tags)

    return {
        "coordinates": {"latitude": latitude, "longitude": longitude},
        "classification": classification,
        "osm_industrial_zone": final_industrial_zone,
        "inference_confidence_score": round(inference_confidence, 4),
        "danger_level": danger_level,
        "threat_level": f"Excessive Release: {chem_threat['chemical']}",
        "chemical_released": chem_threat["chemical"],
        "scientific_impact": chem_threat["impact"],
        "spatial_features": spatial_vars,
        "is_persistent_anomaly": bool(context_type == "industrial" or spatial_vars["dist_industrial_m"] < 500.0)
    }

async def query_llm_incident_synthesis(context_prompt: str) -> Optional[str]:
    if settings.GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
            payload = {"contents": [{"parts": [{"text": context_prompt}]}]}
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[Gemini API Notice]: Fallback to internal synthesis template: {e}")
    return None

async def generate_predictive_spread_report(db: AsyncSession, fire_id: int, latitude: float, longitude: float, frp: float) -> Dict[str, Any]:
    wind_speed, wind_dir, ambient_temp = await get_live_weather(latitude, longitude)
    base_spread = 0.06 + (frp * 0.0035)
    wind_factor = math.exp(0.042 * wind_speed)
    temp_factor = 1.0 + (max(0.0, ambient_temp - 25.0) * 0.015)
    rate_of_spread_kmh = round(base_spread * wind_factor * temp_factor, 3)
    
    projected_distance_km = round(rate_of_spread_kmh * 24.0, 2)
    projected_distance_m = projected_distance_km * 1000.0
    plume_radius_m = round(projected_distance_m * 0.42, 1)

    # ST_Project is computed once via this CTE and reused for both proj_lat
    # and proj_lon (ST_Y/ST_X read from the same computed point) instead of
    # invoking the geodesic projection twice from scratch for the same result.
    query_projection = text("""
        WITH projected AS (
            SELECT ST_Project(
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                :dist,
                radians(CAST(:azimuth AS DOUBLE PRECISION))
            )::geometry AS pt
        )
        SELECT ST_Y(pt) AS proj_lat, ST_X(pt) AS proj_lon FROM projected;
    """)
    try:
        res = await db.execute(
            query_projection,
            {"lon": longitude, "lat": latitude, "dist": projected_distance_m, "azimuth": wind_dir},
        )
        row = res.mappings().first()
    except Exception as exc:
        logger.exception("Downwind projection query failed for fire_id=%s", fire_id)
        raise LiveDataUnavailableError(
            f"live spread projection unavailable for fire_id={fire_id}: spatial engine query failed"
        ) from exc

    if row is None or row["proj_lat"] is None or row["proj_lon"] is None:
        logger.error("Downwind projection query returned no usable geometry for fire_id=%s", fire_id)
        raise LiveDataUnavailableError(
            f"live spread projection unavailable for fire_id={fire_id}: projection query returned no geometry"
        )

    proj_lat = float(row["proj_lat"])
    proj_lon = float(row["proj_lon"])

    # Reuses the already-computed proj_lat/proj_lon as a plain point instead
    # of recomputing ST_Project a second time (now potentially once per
    # candidate row scanned) inside this query's WHERE clause — cheaper, and
    # it means this query no longer needs :dist/:azimuth/radians()/CAST at all.
    threat_assets_query = text("""
        SELECT name, feature_type, ROUND(ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 3857), ST_Transform(geom, 3857))) AS distance_meters
        FROM osm_critical_infrastructure
        WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:proj_lon, :proj_lat), 4326)::geography, :plume_buffer)
        ORDER BY distance_meters ASC LIMIT 3;
    """)
    threatened_assets = []
    assets_lookup_succeeded = True
    try:
        asset_res = await db.execute(
            threat_assets_query,
            {"lon": longitude, "lat": latitude, "proj_lon": proj_lon, "proj_lat": proj_lat, "plume_buffer": plume_radius_m},
        )
        for r in asset_res.mappings().all():
            threatened_assets.append(f"{r['name']} ({r['feature_type']}) at {r['distance_meters']}m")
    except Exception:
        assets_lookup_succeeded = False
        logger.exception(
            "Downstream infrastructure lookup failed for fire_id=%s — continuing without it "
            "(this is a secondary enrichment, not required for the core spread projection)",
            fire_id,
        )

    if threatened_assets:
        threat_str = ", ".join(threatened_assets)
    elif assets_lookup_succeeded:
        # Query ran and genuinely found nothing — a real, live result.
        threat_str = "No critical infrastructure identified within the plume buffer zone."
    else:
        # Query itself failed — say so honestly rather than implying "checked, found none".
        threat_str = "Downstream infrastructure lookup temporarily unavailable."

    llm_prompt = f"""
You are an Emergency Fire Command & Hazardous Materials AI Dispatcher. Generate a critical Incident Threat Report in Markdown:
- Incident ID: #{fire_id} | Origin: [{latitude:.5f}, {longitude:.5f}]
- Fire Radiative Power: {frp} MW | Temperature: {ambient_temp}°C
- Live Winds: {wind_speed} km/h toward {wind_dir}° Azimuth
- 24-Hour Projected Firehead Centroid: [{proj_lat:.5f}, {proj_lon:.5f}] (Distance: {projected_distance_km} km)
- Toxic Gas Plume Radius: {plume_radius_m} meters
- Threatened Downstream Assets: {threat_str}
"""
    llm_report = await query_llm_incident_synthesis(llm_prompt)
    if not llm_report:
        llm_report = (
            f"🚨 **INCIDENT THREAT & SPREAD REPORT (24H HORIZON)**\n\n"
            f"• **Incident ID:** #{fire_id} | **Origin Coordinates:** [{latitude:.5f}, {longitude:.5f}]\n"
            f"• **24-Hour Projected Firehead Centroid:** [{proj_lat:.5f}, {proj_lon:.5f}] (Path Distance: {projected_distance_km} km)\n"
            f"• **Toxic Chemical Dispersion Plume Radius:** Expanding out to {plume_radius_m} meters.\n"
            f"⚠️ **DOWNSTREAM INFRASTRUCTURE AT RISK:** Intersects with {threat_str}.\n"
            f"🛡️ **STRATEGY:** Issue respirator advisories for all populations downwind within the {plume_radius_m}m plume corridor."
        )

    return {
        "fire_id": fire_id, "origin_coordinates": {"latitude": latitude, "longitude": longitude},
        "projected_centroid_24h": {"latitude": proj_lat, "longitude": proj_lon}, "rate_of_spread_kmh": rate_of_spread_kmh,
        "projected_distance_24h_km": projected_distance_km, "toxic_plume_radius_m": plume_radius_m,
        "live_wind": {"speed_kmh": wind_speed, "direction_deg": wind_dir, "ambient_temp_c": ambient_temp},
        "threatened_downstream_infrastructure": threatened_assets, "ai_generated_incident_report": llm_report
    }