# app/models.py
import enum
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import Column, Integer, String, Boolean, Float, TIMESTAMP, text, Enum, Index
from database import Base

class RoleEnum(str, enum.Enum):
    user = "user"
    admin = "admin"
    official = "official"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    password = Column(String, nullable=False)
    role = Column(Enum(RoleEnum, create_type=False), default=RoleEnum.user, server_default=RoleEnum.user.value, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('now()'))

class FireEvent(Base):
    __tablename__ = "fire_events"
    
    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    brightness = Column(Float, nullable=False)
    frp = Column(Float, nullable=False)
    satellite_source = Column(String, default="VIIRS_SNPP", nullable=False)
    confidence = Column(String, default="n", nullable=False)
    
    osm_industrial_zone = Column(String, nullable=True)
    classification = Column(String, nullable=False)
    danger_level = Column(String, default="MODERATE", nullable=False)
    chemical_released = Column(String, nullable=True)
    scientific_impact = Column(String, nullable=True)
    inference_confidence = Column(Float, default=0.90, nullable=False)
    
    is_persistent_anomaly = Column(Boolean, server_default=text('FALSE'), default=False, nullable=False)
    region = Column(String, default="India", nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('now()'))

    __table_args__ = (
        Index('idx_fire_coords', 'latitude', 'longitude'),
    )
