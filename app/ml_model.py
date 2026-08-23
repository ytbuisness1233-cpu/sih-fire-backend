# Heuristic AI Classification Engine for SIH26162
# Evaluates Satellite Telemetry & Geospatial Data without massive RAM overhead

def classify_anomaly(frp: float, brightness: float, osm_zone: str) -> dict:
    """
    Classifies satellite thermal hotspots based on Fire Radiative Power (FRP),
    brightness temperature values, and OpenStreetMap spatial land-use tags.
    """
    # 1. Type defense and data sanitization
    safe_frp = float(frp) if frp is not None else 0.0
    safe_brightness = float(brightness) if brightness is not None else 0.0
    
    # Clean string inputs to prevent falsy/placeholder strings from breaking classification logic
    clean_zone = str(osm_zone).strip() if osm_zone else ""
    is_valid_zone = clean_zone and clean_zone.lower() not in ["none", "null", "false", "undefined"]
    
    is_persistent = False
    
    # 2. Spatial Filtering Engine
    if is_valid_zone:
        is_persistent = True
        classification = f"Industrial Thermal Source ({clean_zone})"
        
    # 3. Telemetry Classification Engine (Utilizing dual-sensor data metrics)
    else:
        # Solar glint / reflection filter: high brightness but near-zero radiant power
        if safe_brightness > 320.0 and safe_frp < 0.5:
            classification = "Solar Glint / Surface Reflection Noise"
            
        elif safe_frp > 80.0:
            classification = "High-Intensity Wildfire"
            
        elif 20.0 < safe_frp <= 80.0:
            # High brightness temperature helps confirm active burning signatures
            if safe_brightness >= 315.0:
                classification = "Agricultural / Stubble Burning"
            else:
                classification = "Moderate / Controlled Thermal Source"
                
        else:
            classification = "Minor Thermal Anomaly"

    return {
        "classification": classification,
        "is_persistent_anomaly": is_persistent
    }
