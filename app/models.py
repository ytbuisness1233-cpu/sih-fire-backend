from sqlalchemy import Column, Integer, String, Boolean, Float, TIMESTAMP, text, Enum, Index
from .database import Base
import enum

# 1. Standardizing Roles using standard enum classes
class RoleEnum(str, enum.Enum):
    user = "user"
    admin = "admin"
    official = "official"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    password = Column(String, nullable=False)
    
    # FIXED: Set create_type=False and persist as strings in the database to prevent native Enum migration crashes inside Docker
    role = Column(Enum(RoleEnum, create_type=False), default=RoleEnum.user, server_default=RoleEnum.user.value, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('now()'))

class FireEvent(Base):
    __tablename__ = "fire_events"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # FIXED: Added targeted indices on spatial coordinates to accelerate map bounding-box queries
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    
    brightness = Column(Float, nullable=False)
    frp = Column(Float, nullable=False)
    satellite_source = Column(String, nullable=False)
    confidence = Column(String, nullable=False)
    
    osm_industrial_zone = Column(String, nullable=True) 
    
    # FIXED: Replaced loose string defaults with standardized boolean texts to eliminate parsing errors
    is_persistent_anomaly = Column(Boolean, server_default=text('FALSE'), default=False, nullable=False)
    classification = Column(String, nullable=False)
    
    region = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('now()'))

    # Multi-column Indexing to optimize spatial queries bounding boxes (e.g. India regional data sorting)
    __table_args__ = (
        Index('idx_coordinates', 'latitude', 'longitude'),
    )
