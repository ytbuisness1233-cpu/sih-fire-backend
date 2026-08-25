# app/schemas.py
from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str = "user"

class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class FireEventPublicOut(BaseModel):
    id: int
    region: str
    classification: str
    danger_level: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class FireEventSensitiveOut(BaseModel):
    id: int
    latitude: float
    longitude: float
    brightness: float
    frp: float
    satellite_source: str
    confidence: str
    osm_industrial_zone: Optional[str] = None
    classification: Optional[str] = "Thermal Anomaly"
    danger_level: Optional[str] = "MODERATE"
    chemical_released: Optional[str] = "None Detected"
    scientific_impact: Optional[str] = "None Tracked"
    inference_confidence: float = 0.90
    is_persistent_anomaly: bool = False
    region: str = "India"
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        populate_by_name=True
    )

class SpreadPredictionOut(BaseModel):
    fire_id: int
    origin_coordinates: Dict[str, float]
    projected_centroid_24h: Dict[str, float]
    rate_of_spread_kmh: float
    projected_distance_24h_km: float
    toxic_plume_radius_m: float
    live_wind: Dict[str, float]
    threatened_downstream_infrastructure: List[str]
    ai_generated_incident_report: str
