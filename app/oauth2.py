from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from . import schemas, database, models
from .config import settings

# Point to your custom login route securely
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='login')

def create_access_token(data: dict):
    to_encode = data.copy()
    # FIXED: Replaced lowercase variables with uppercase configuration attributes
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_access_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        raw_id = payload.get("user_id")
        
        # FIXED: Removed the aggressive str() cast to handle missing payloads correctly
        if raw_id is None:
            raise credentials_exception
            
        token_data = schemas.TokenData(id=str(raw_id))
    except JWTError:
        raise credentials_exception
    return token_data

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}
    )
    token_data = verify_access_token(token, credentials_exception)
    
    # FIXED: Wrapped raw type-casting operations in a try/except block to intercept ValueError exceptions
    try:
        user_id_int = int(token_data.id)
    except ValueError:
        raise credentials_exception
        
    result = await db.execute(select(models.User).where(models.User.id == user_id_int))
    user = result.scalars().first()
    
    if not user:
        raise credentials_exception
    return user

# Govt Officials & Admins have full map access
async def require_official_clearance(current_user: models.User = Depends(get_current_user)):
    # Clean check utilizing string representation mapping comparisons
    if current_user.role not in [models.RoleEnum.admin, models.RoleEnum.official]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Clearance Level Too Low. Official login required."
        )
    return current_user
