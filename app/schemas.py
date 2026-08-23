from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional
import enum

# FIXED: Redefine the enum locally in schemas to completely kill the circular import bug.
# This keeps models.py and schemas.py perfectly independent so Python never crashes on boot.
class RoleEnum(str, enum.Enum):
    user = "user"
    admin = "admin"
    official = "official"

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    # SAFETY PATCH: Default registration to standard 'user'. 
    # Let your teammate explicitly pass "official" in their frontend JSON payload during testing.
    role: RoleEnum = RoleEnum.user

class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: RoleEnum
    
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    id: Optional[str] = None

class FireEventPublicOut(BaseModel):
    id: int
    region: str
    classification: str
    created_at: datetime
    
    # FIXED: Added support for reading directly from database mapping keys (result.mappings().all())
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class FireEventSensitiveOut(BaseModel):
    id: int
    latitude: float
    longitude: float
    brightness: float
    frp: float
    satellite_source: str
    confidence: str
    osm_industrial_zone: Optional[str] = None
    is_persistent_anomaly: bool
    classification: str
    region: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
